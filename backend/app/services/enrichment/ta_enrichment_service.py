"""
ta_enrichment_service.py — Grounded TA Evidence Enrichment Service.

Produces recruiter-friendly technical explanations, candidate resume evidence signals,
and screening questions strictly anchored to deterministic baseline requirement IDs.
All generated guidance is flagged as OriginType.LLM_HYPOTHESIS.

Fixes in this version:
  * think=False is sent to Ollama. Thinking models (qwen3) otherwise spend the whole
    output budget on hidden thinking and return EMPTY content ("Expecting value: line 1
    column 1 (char 0)").
  * Larger output budget (ENRICH_NUM_PREDICT, default 2048) so a batch of 5 items is not truncated.
  * Logs under the "jd_agent" logger so INFO lines (batch progress, empty responses) are visible.
  * If every batch returns nothing, an error is raised instead of silently saving an empty report,
    so callers fall back to the deterministic baseline honestly.
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from app.config import get_settings
from app.schemas.enrichment import RequirementEnrichmentItem, TAEnrichmentReport
from app.schemas.master_context import OriginType

logger = logging.getLogger("jd_agent.enrichment")

# Thread-safe in-memory cache for Ollama service availability
# Key: f"{base_url}|{model}" -> (is_available: bool, checked_at: float)
_AVAILABILITY_CACHE: Dict[str, Tuple[bool, float]] = {}
_AVAILABILITY_LOCK = threading.Lock()
_OFFLINE_CACHE_TTL = 5.0   # Fast 5-second recovery window when Ollama is launched
_ONLINE_CACHE_TTL = 30.0   # 30-second TTL when confirmed online


def invalidate_availability_cache(base_url: Optional[str] = None) -> None:
    """Clear cached Ollama availability state so subsequent checks re-probe immediately."""
    with _AVAILABILITY_LOCK:
        if base_url:
            keys_to_del = [k for k in _AVAILABILITY_CACHE if k.startswith(f"{base_url}|")]
            for k in keys_to_del:
                _AVAILABILITY_CACHE.pop(k, None)
        else:
            _AVAILABILITY_CACHE.clear()

SYSTEM_PROMPT = """You are a Technical Talent Acquisition (TA) Specialist and Engineering Hiring Evaluator.
Your role is to enrich verified job requirements with recruiter-friendly technical explanations,
concrete resume evidence signals, targeted screening questions, and top candidate evaluation priorities.

CRITICAL RULES:
1. STRICT GROUNDING: You will be given a list of verified requirement IDs and texts.
   You must ONLY produce enrichment for the provided requirement IDs.
   DO NOT create new requirement IDs or alter existing requirement IDs.
2. DO NOT change requirement priority or whether a requirement is mandatory vs preferred.
3. NATURAL & NON-REPETITIVE GUIDANCE: Produce distinct, requirement-specific technical interpretations.
   Avoid generic boilerplate or repeating identical sentences across different requirements.
4. TECHNICAL CONCEPT SUMMARY: Explain the core technology or concept in clear, recruiter-friendly language
   so a non-engineer understands what it is, why production systems use it, and its technical significance.
5. STRONG EVIDENCE SIGNALS: Describe concrete evidence that should appear on a candidate's resume
   (e.g. specific frameworks, architectural patterns, throughput metrics, hardware targets, production deliverables).
6. WEAK OR AMBIGUOUS SIGNALS: Describe signals that indicate superficial exposure or buzzword padding
   (e.g. passive mentions, simple tutorial projects, lack of ownership or metrics).
7. SCREENING QUESTION: Provide 1-2 focused, conversational technical screening questions a recruiter
   or hiring manager can ask during an initial phone screen to test real depth.
8. EVALUATION PRIORITIES: Provide 3-5 concise, grounded priority instructions for how evaluators should rank candidates based strictly on the verified requirements and resolved clarifications.
9. Output MUST be a single valid JSON object strictly matching this schema:
{
  "items": [
    {
      "requirement_id": "req_...",
      "technical_concept_summary": "...",
      "strong_evidence_signals": ["...", "..."],
      "weak_or_ambiguous_signals": ["...", "..."],
      "screening_question": "..."
    }
  ],
  "evaluation_priorities": [
    "Prioritize deep hands-on expertise in...",
    "Verify architectural ownership in...",
    "Screen for..."
  ]
}
"""

_THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)


class OllamaUnavailableError(RuntimeError):
    """Raised when Ollama is unreachable or the requested model is not installed."""
    pass


def _extract_json_text(raw_text: str) -> str:
    """Strip <think> blocks and markdown fences, then cut out the outermost JSON object."""
    text = _THINK_RE.sub("", raw_text or "")
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start:end + 1]
    return text


class GroundedEnrichmentService:
    """Service that enriches deterministic JD requirements using Ollama (qwen3:4b)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        llm_caller: Optional[Callable[[str, str], str]] = None,
    ):
        settings = get_settings()
        self._explicit_base_url = bool(base_url)
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or getattr(settings, "llm_model", None) or os.getenv("LLM_MODEL", "qwen2.5:1.5b")
        self.llm_caller = llm_caller

    def check_ollama_available(self, timeout: float = 3.0, force_refresh: bool = False) -> bool:
        """Check if local Ollama daemon is reachable and the required model is loaded."""
        if self.llm_caller is not None:
            return True

        cache_key = f"{self.base_url}|{self.model}"
        now = time.time()

        if not force_refresh:
            with _AVAILABILITY_LOCK:
                cached = _AVAILABILITY_CACHE.get(cache_key)
                if cached is not None:
                    is_avail, checked_at = cached
                    ttl = _ONLINE_CACHE_TTL if is_avail else _OFFLINE_CACHE_TTL
                    if (now - checked_at) < ttl:
                        return is_avail

        # Candidates to probe. When default localhost is used, probe 127.0.0.1 directly to
        # avoid redundant duplicate probes and Windows IPv6 [::1] connection timeout delays.
        if not self._explicit_base_url and "localhost:11434" in self.base_url:
            candidates = ["http://127.0.0.1:11434"]
        else:
            candidates = [self.base_url]

        connect_timeout = min(0.35, timeout)
        probe_timeout = httpx.Timeout(connect=connect_timeout, read=timeout, write=0.5, pool=0.5)

        is_available = False
        for candidate_url in candidates:
            try:
                with httpx.Client(timeout=probe_timeout, trust_env=False) as client:
                    r = client.get(f"{candidate_url}/api/tags")
                    if r.status_code != 200:
                        continue
                    data = r.json()
                    models = [m.get("name", "").split(":")[0] for m in data.get("models", [])] + [
                        m.get("name", "") for m in data.get("models", [])
                    ]
                    target_base = self.model.split(":")[0]
                    if (
                        self.model in models
                        or target_base in models
                        or any(m.startswith("qwen") for m in models)
                    ):
                        self.base_url = candidate_url
                        is_available = True
                        break
            except Exception as exc:
                logger.debug("Ollama availability check failed for %s: %s", candidate_url, exc)

        with _AVAILABILITY_LOCK:
            _AVAILABILITY_CACHE[cache_key] = (is_available, now)

        if not is_available:
            logger.warning(
                "Ollama not available at %s (or model '%s' missing): enrichment will be skipped.",
                self.base_url, self.model,
            )
        return is_available

    def build_user_prompt(
        self,
        requirements: List[Dict[str, Any]],
        clarification_context: Optional[List[Dict[str, Any]]] = None,
        role_context: Optional[Dict[str, Any]] = None,
        is_final_refinement: bool = False,
    ) -> str:
        """Format the requirements into a structured grounded prompt."""
        sections: List[str] = []
        if role_context:
            role_lines: List[str] = []
            if role_context.get("role_title"):
                role_lines.append(f"- Target Role: {role_context['role_title']}")
            if role_context.get("team_size"):
                role_lines.append(f"- Team Size: {role_context['team_size']}")
            if role_context.get("salary_range"):
                role_lines.append(f"- Salary Range: {role_context['salary_range']}")
            if role_context.get("work_mode"):
                role_lines.append(f"- Work Mode / Location: {role_context['work_mode']}")
            if role_lines:
                sections.append("### Structured Role Context:\n" + "\n".join(role_lines))

        if clarification_context:
            clarif_lines: List[str] = []
            for c in clarification_context:
                q_text = c.get("question_text") or c.get("question_key") or ""
                a_text = c.get("answer_text") or ""
                by = c.get("answered_by") or "TA"
                if a_text:
                    clarif_lines.append(f"- Q: {q_text}\n  A ({by}): {a_text}")
            if clarif_lines:
                sections.append("### Resolved Clarifications & Confirmed Scope:\n" + "\n".join(clarif_lines))

        req_lines: List[str] = []
        for r in requirements:
            r_id = r.get("id") or r.get("requirement_id")
            r_text = r.get("text") or r.get("requirement", "")
            r_prio = r.get("priority", "MUST_HAVE")
            req_lines.append(f"- ID: {r_id}\n  Priority: {r_prio}\n  Requirement: {r_text}")

        header = (
            "Please provide FINAL REFINED TA technical enrichment and candidate evaluation priorities incorporating the resolved clarifications above:\n\n"
            if is_final_refinement and clarification_context
            else "Please provide TA technical enrichment and candidate screening guidance for the following verified requirements:\n\n"
        )

        sections.append(header + "\n".join(req_lines))
        sections.append("Respond with JSON matching the required schema. Ensure every requirement ID gets natural, specific, non-repetitive guidance.")
        return "\n\n".join(sections)

    def _stream_once(self, payload: Dict[str, Any], read_timeout: float) -> str:
        """One streamed /api/chat call. Returns the visible content (may be empty)."""
        timeout = httpx.Timeout(connect=15.0, read=read_timeout, write=30.0, pool=15.0)
        collected: List[str] = []
        thinking_chars = 0
        done_reason = ""
        out_tokens = 0
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                response.raise_for_status()
                for raw_line in response.iter_lines():
                    if not raw_line:
                        continue
                    try:
                        chunk = json.loads(raw_line)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if chunk.get("error"):
                        raise RuntimeError(f"Ollama error: {chunk['error']}")
                    msg = chunk.get("message") or {}
                    content = msg.get("content") or ""
                    if content:
                        collected.append(content)
                    thinking_chars += len(msg.get("thinking") or "")
                    if chunk.get("done"):
                        done_reason = chunk.get("done_reason") or ""
                        out_tokens = int(chunk.get("eval_count") or 0)
                        break
        text = "".join(collected)
        logger.info(
            "Ollama enrichment call: out_tokens=%d content_chars=%d thinking_chars=%d done_reason=%s",
            out_tokens, len(text), thinking_chars, done_reason or "n/a",
        )
        if not text.strip():
            logger.warning(
                "Ollama returned EMPTY content (done_reason=%s, thinking_chars=%d). "
                "If thinking_chars is large the model spent its budget thinking; "
                "think=False should prevent that.",
                done_reason or "n/a", thinking_chars,
            )
        return text

    def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        """Execute chat completion against local Ollama instance."""
        if self.llm_caller is not None:
            return self.llm_caller(system_prompt, user_prompt)

        if not self.check_ollama_available():
            raise OllamaUnavailableError(
                f"Local Ollama service at {self.base_url} is unreachable or model '{self.model}' is not present."
            )

        user_prompt_final = user_prompt
        lowered = self.model.lower()
        if "qwen3" in lowered and "instruct" not in lowered:
            user_prompt_final += "\n\n/no_think"  # soft switch honoured by hybrid Qwen3 builds

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt_final},
            ],
            "stream": True,
            "think": False,
            "format": "json",
            "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
            "options": {
                "num_ctx": int(os.getenv("ENRICH_NUM_CTX", "4096")),
                "num_predict": int(os.getenv("ENRICH_NUM_PREDICT", "1024")),
                "temperature": 0.1,
            },
        }

        read_timeout = float(os.getenv("OLLAMA_READ_TIMEOUT", "300"))
        try:
            for _ in range(2):
                try:
                    return self._stream_once(payload, read_timeout)
                except httpx.HTTPStatusError as exc:
                    # Older Ollama builds reject the `think` field: retry once without it.
                    if exc.response.status_code == 400 and "think" in payload:
                        logger.warning("Ollama rejected think=False (HTTP 400); retrying without it")
                        payload.pop("think")
                        continue
                    raise
            raise RuntimeError("Ollama request failed after fallbacks.")
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            with _AVAILABILITY_LOCK:
                _AVAILABILITY_CACHE[f"{self.base_url}|{self.model}"] = (False, time.time())
            raise OllamaUnavailableError(f"Could not connect to Ollama at {self.base_url}") from exc
        except httpx.ReadTimeout as exc:
            raise RuntimeError(f"Ollama inference timed out after {read_timeout}s") from exc
        except OllamaUnavailableError:
            raise
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Ollama chat error: {exc}") from exc

    def _parse_and_validate_response(
        self,
        raw_text: str,
        known_reqs: Dict[str, str],
    ) -> tuple[List[RequirementEnrichmentItem], List[str]]:
        """
        Parse LLM response and strictly filter against known requirement IDs.
        Silently discards any hallucinated or fabricated requirement IDs.
        """
        cleaned = _extract_json_text(raw_text)

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning(
                "Failed to decode JSON from enrichment response: %s (response chars=%d, preview=%r)",
                exc, len(raw_text or ""), (raw_text or "")[:120],
            )
            return [], []

        raw_items = parsed.get("items", []) if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
        eval_priorities = [
            str(p).strip() for p in (parsed.get("evaluation_priorities", []) if isinstance(parsed, dict) else [])
            if str(p).strip()
        ]
        validated_items: List[RequirementEnrichmentItem] = []

        for item in raw_items:
            if not isinstance(item, dict):
                continue
            r_id = item.get("requirement_id")
            if not r_id or r_id not in known_reqs:
                logger.warning("Dropping enrichment item with unknown or missing requirement_id: %r", r_id)
                continue

            tech_summary = item.get("technical_concept_summary") or ""
            strong_signals = item.get("strong_evidence_signals") or []
            if isinstance(strong_signals, str):
                strong_signals = [strong_signals]
            weak_signals = item.get("weak_or_ambiguous_signals") or []
            if isinstance(weak_signals, str):
                weak_signals = [weak_signals]
            screening_q = item.get("screening_question") or ""

            validated_items.append(
                RequirementEnrichmentItem(
                    requirement_id=r_id,
                    requirement_text=known_reqs[r_id],
                    technical_concept_summary=str(tech_summary).strip(),
                    strong_evidence_signals=[str(s).strip() for s in strong_signals if str(s).strip()],
                    weak_or_ambiguous_signals=[str(s).strip() for s in weak_signals if str(s).strip()],
                    screening_question=str(screening_q).strip(),
                    origin_type=OriginType.LLM_HYPOTHESIS,
                )
            )

        return validated_items, eval_priorities

    def generate_enrichment_report(
        self,
        spec_version_id: str,
        specification_version: int,
        source_checksum: str,
        requirements: List[Dict[str, Any]],
        clarification_context: Optional[List[Dict[str, Any]]] = None,
        role_context: Optional[Dict[str, Any]] = None,
        raw_jd_text: Optional[str] = None,
    ) -> TAEnrichmentReport:
        """
        Generate a TAEnrichmentReport anchored to the provided baseline version and requirements.
        Optionally incorporates resolved clarifications and role context for final refinement.

        Raises RuntimeError if Ollama produced no usable enrichment at all, so that callers fall
        back to the deterministic baseline instead of saving an empty "enriched" report.
        """
        if not requirements:
            return TAEnrichmentReport(
                source_specification_version_id=spec_version_id,
                source_specification_version=specification_version,
                source_checksum=source_checksum,
                items=[],
                evaluation_priorities=[],
                status="completed",
                model_version=self.model,
            )

        known_reqs = {}
        for r in requirements:
            r_id = r.get("id") or r.get("requirement_id")
            r_text = r.get("text") or r.get("requirement", "")
            if r_id:
                known_reqs[r_id] = r_text

        # Deduplicate and prioritize substantive requirements across the entire JD (up to 35 requirements)
        meaningful_reqs = []
        seen_texts = set()
        for r in requirements:
            r_id = r.get("id") or r.get("requirement_id")
            r_text = (r.get("text") or r.get("requirement") or "").strip()
            if not r_id or len(r_text) < 4:
                continue
            norm_key = r_text.lower()
            if norm_key in seen_texts:
                continue
            seen_texts.add(norm_key)
            prio = str(r.get("priority", "")).upper()
            rank = 0 if ("MUST" in prio or "MAND" in prio) else (1 if "PREF" in prio else 2)
            meaningful_reqs.append((rank, r))

        meaningful_reqs.sort(key=lambda x: x[0])
        selected_reqs = [x[1] for x in meaningful_reqs[:35]]
        if not selected_reqs:
            selected_reqs = requirements[:35]

        batch_size = int(os.getenv("ENRICHMENT_BATCH_SIZE", "6"))
        # If requirements are 8 or fewer, process in a single batch to eliminate redundant round-trips
        if len(selected_reqs) <= 8:
            batches = [selected_reqs]
        else:
            batches = [selected_reqs[i : i + batch_size] for i in range(0, len(selected_reqs), batch_size)]

        total_batches = len(batches)
        is_final = bool(clarification_context)
        max_workers = min(int(os.getenv("ENRICHMENT_MAX_WORKERS", "2")), total_batches)

        def _process_chunk(b_idx: int, chunk: List[Dict[str, Any]]) -> tuple[int, List[RequirementEnrichmentItem], List[str], Optional[Exception]]:
            prompt = self.build_user_prompt(
                chunk,
                clarification_context=clarification_context if b_idx == 1 else None,
                role_context=role_context if b_idx == 1 else None,
                is_final_refinement=is_final,
            )
            logger.info("Enriching batch %d/%d (%d requirements) via Ollama...", b_idx, total_batches, len(chunk))
            try:
                raw_output = self._call_ollama(SYSTEM_PROMPT, prompt)
                batch_items, batch_priorities = self._parse_and_validate_response(raw_output, known_reqs)
                logger.info("Batch %d/%d completed: %d items validated", b_idx, total_batches, len(batch_items))
                return b_idx, batch_items, batch_priorities, None
            except OllamaUnavailableError as exc:
                return b_idx, [], [], exc
            except Exception as exc:
                logger.warning("Enrichment batch %d/%d failed: %s", b_idx, total_batches, exc)
                return b_idx, [], [], exc

        batch_results: List[tuple[int, List[RequirementEnrichmentItem], List[str], Optional[Exception]]] = []

        from app.core.concurrency import acquire_ollama_slot
        try:
            with acquire_ollama_slot(f"enrich_spec_{spec_version_id}"):
                if total_batches <= 1:
                    res = _process_chunk(1, batches[0])
                    if isinstance(res[3], OllamaUnavailableError):
                        raise res[3]
                    batch_results.append(res)
                else:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                        futures = [
                            executor.submit(_process_chunk, b_idx, chunk)
                            for b_idx, chunk in enumerate(batches, start=1)
                        ]
                        for fut in concurrent.futures.as_completed(futures):
                            res = fut.result()
                            if isinstance(res[3], OllamaUnavailableError):
                                # Ollama is unreachable: fail fast and abort
                                raise res[3]
                            batch_results.append(res)
        except TimeoutError as exc:
            logger.warning("Timed out waiting for Ollama concurrency slot: %s", exc)
            raise OllamaUnavailableError(str(exc))

        # Sort by batch index to preserve natural requirement priority ordering
        batch_results.sort(key=lambda x: x[0])

        all_validated_items: List[RequirementEnrichmentItem] = []
        all_evaluation_priorities: List[str] = []
        last_error: Optional[Exception] = None

        for b_idx, batch_items, batch_priorities, err in batch_results:
            if err:
                last_error = err
            all_validated_items.extend(batch_items)
            for prio in batch_priorities:
                if prio not in all_evaluation_priorities:
                    all_evaluation_priorities.append(prio)

        if selected_reqs and not all_validated_items:
            raise RuntimeError(
                "Ollama returned no usable enrichment items for any batch"
                + (f" (last error: {last_error})" if last_error else "")
                + ". Check the 'Ollama enrichment call' log lines above."
            )

        if not all_evaluation_priorities and selected_reqs:
            top_skills = [
                (r.get("text") or r.get("requirement", "")).strip()
                for r in selected_reqs
                if len((r.get("text") or r.get("requirement", "")).strip()) < 80
            ][:3]
            if top_skills:
                all_evaluation_priorities.append(f"Prioritize candidate depth in core competencies: {'; '.join(top_skills)}.")
            all_evaluation_priorities.append("Verify proven hands-on deliverables and production track record over keyword stuffing.")
            all_evaluation_priorities.append("Evaluate cross-functional communication and architectural decision-making.")

        return TAEnrichmentReport(
            source_specification_version_id=spec_version_id,
            source_specification_version=specification_version,
            source_checksum=source_checksum,
            items=all_validated_items,
            evaluation_priorities=all_evaluation_priorities,
            status="completed",
            model_version=self.model,
        )