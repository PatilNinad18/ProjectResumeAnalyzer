"""
ta_enrichment_service.py — Grounded TA Evidence Enrichment Service.

Produces recruiter-friendly technical explanations, candidate resume evidence signals,
and screening questions strictly anchored to deterministic baseline requirement IDs.
All generated guidance is flagged as OriginType.LLM_HYPOTHESIS.

Fixes in this version (tuned for qwen3:4b):
  * ROOT CAUSE of "Expecting ',' delimiter": num_predict was 1024 and a 6-item batch needs
    ~1300+ tokens, so every response was cut off (done_reason=length) right before the closing
    brackets. Default is now 3072, batches are 3 items, and string lengths are capped.
  * Structured output: a per-batch JSON schema is sent to Ollama as `format`. It forces valid
    JSON, restricts requirement_id to the IDs of the batch (no hallucinated IDs), and caps the
    length of every string so generation always terminates cleanly.
  * Truncation salvage: if output is still cut off, complete items are recovered from the
    partial JSON instead of discarding the whole batch.
  * Automatic retry: items that are still missing are retried in smaller batches (split in half,
    down to single requirements, with a temperature bump for repetition loops).
  * Qwen3-friendly sampling (no greedy decoding): temperature 0.4, top_p 0.8, top_k 20,
    repeat_penalty 1.05. Greedy/near-greedy decoding causes "token repeat limit reached".
  * Evaluation priorities are requested only once (first batch) instead of in every batch.
  * Resolved clarifications and role context are sent with every batch.
  * Model availability check now requires the configured model (not "any qwen*").
  * Settings are read from app.config first, then OS environment variables.
  * think=False is sent to Ollama so the thinking model does not burn its budget on hidden thinking.
  * If every batch returns nothing, an error is raised so callers fall back to the deterministic
    baseline honestly.

Optional configuration (all have defaults):
    ENRICH_NUM_CTX=8192        (falls back to OLLAMA_NUM_CTX; keep it equal to llm_service's value
                                or Ollama reloads the model every time the two services alternate)
    ENRICH_NUM_PREDICT=3072
    ENRICH_TEMPERATURE=0.4
    ENRICH_REPEAT_PENALTY=1.05
    ENRICHMENT_BATCH_SIZE=3
    ENRICHMENT_MAX_WORKERS=1   (a single local model serves one request at a time anyway)
    ENRICH_MAX_SPLIT_DEPTH=3
    OLLAMA_READ_TIMEOUT=300
    OLLAMA_KEEP_ALIVE=30m
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import httpx

from app.config import get_settings
from app.schemas.enrichment import RequirementEnrichmentItem, TAEnrichmentReport
from app.schemas.master_context import OriginType

logger = logging.getLogger("jd_agent.enrichment")

DEFAULT_MODEL = "qwen3:4b"

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


# --------------------------------------------------------------------------
# Config helpers: app settings first, then real OS environment variables
# --------------------------------------------------------------------------
def _cfg(name: str, default: Any = None) -> Any:
    try:
        value = getattr(get_settings(), name.lower(), None)
    except Exception:  # noqa: BLE001
        value = None
    if value in (None, ""):
        value = os.environ.get(name)
    return default if value in (None, "") else value


def _cfg_int(name: str, default: int) -> int:
    try:
        return int(_cfg(name, default))
    except (TypeError, ValueError):
        return default


def _cfg_float(name: str, default: float) -> float:
    try:
        return float(_cfg(name, default))
    except (TypeError, ValueError):
        return default


def _rid(r: Dict[str, Any]) -> Optional[str]:
    return r.get("id") or r.get("requirement_id")


def _rtext(r: Dict[str, Any]) -> str:
    return (r.get("text") or r.get("requirement") or "").strip()


# --------------------------------------------------------------------------
# Prompt + schema
# --------------------------------------------------------------------------
_SYSTEM_BASE = """You are a Technical Talent Acquisition (TA) Specialist and Engineering Hiring Evaluator.
Your role is to enrich verified job requirements with recruiter-friendly technical explanations,
concrete resume evidence signals and targeted screening questions.

CRITICAL RULES:
1. STRICT GROUNDING: You will be given a list of verified requirement IDs and texts.
   Produce exactly one item for EVERY provided requirement ID, in the same order.
   Copy each requirement_id character-for-character. DO NOT create new IDs or alter existing ones.
2. DO NOT change requirement priority or whether a requirement is mandatory vs preferred.
3. NATURAL & NON-REPETITIVE GUIDANCE: Produce distinct, requirement-specific technical interpretations.
   Avoid generic boilerplate or repeating identical sentences across different requirements.
4. technical_concept_summary: explain the core technology or concept in plain, recruiter-friendly
   language: what it is and why production systems use it.
5. strong_evidence_signals: concrete evidence that should appear on a resume
   (specific frameworks, architectural patterns, metrics, hardware targets, production deliverables).
6. weak_or_ambiguous_signals: signals of superficial exposure or buzzword padding
   (passive mentions, tutorial-level projects, no ownership or metrics).
7. screening_question: one focused, conversational question for an initial phone screen that tests real depth.

LENGTH LIMITS (mandatory; the output is size-capped and MUST be completed):
- technical_concept_summary: ONE sentence, max 30 words.
- strong_evidence_signals: 2-3 items, each max 15 words.
- weak_or_ambiguous_signals: 1-2 items, each max 15 words.
- screening_question: ONE sentence, max 25 words.
"""

_PRIORITIES_RULE = """- evaluation_priorities: 3-5 concise, grounded instructions on how evaluators should rank candidates,
  based strictly on the verified requirements and resolved clarifications. Each max 25 words.
"""

_FORMAT_ITEMS_ONLY = """
Output MUST be a single valid JSON object:
{"items": [{"requirement_id": "req_...", "technical_concept_summary": "...",
  "strong_evidence_signals": ["..."], "weak_or_ambiguous_signals": ["..."], "screening_question": "..."}]}
"""

_FORMAT_WITH_PRIORITIES = """
Output MUST be a single valid JSON object:
{"items": [{"requirement_id": "req_...", "technical_concept_summary": "...",
  "strong_evidence_signals": ["..."], "weak_or_ambiguous_signals": ["..."], "screening_question": "..."}],
 "evaluation_priorities": ["...", "..."]}
"""

# Kept for backwards compatibility with any code that imports SYSTEM_PROMPT.
SYSTEM_PROMPT = _SYSTEM_BASE + _PRIORITIES_RULE + _FORMAT_WITH_PRIORITIES


def _build_system_prompt(include_priorities: bool) -> str:
    if include_priorities:
        return _SYSTEM_BASE + _PRIORITIES_RULE + _FORMAT_WITH_PRIORITIES
    return _SYSTEM_BASE + _FORMAT_ITEMS_ONLY


def _build_schema(req_ids: List[str], include_priorities: bool) -> Dict[str, Any]:
    """JSON schema for one batch. Constrains IDs to the batch and bounds every string length."""
    item_schema = {
        "type": "object",
        "properties": {
            "requirement_id": {"type": "string", "enum": list(req_ids)},
            "technical_concept_summary": {"type": "string", "maxLength": 300},
            "strong_evidence_signals": {
                "type": "array", "items": {"type": "string", "maxLength": 140},
                "minItems": 1, "maxItems": 3,
            },
            "weak_or_ambiguous_signals": {
                "type": "array", "items": {"type": "string", "maxLength": 140},
                "minItems": 1, "maxItems": 2,
            },
            "screening_question": {"type": "string", "maxLength": 220},
        },
        "required": [
            "requirement_id", "technical_concept_summary", "strong_evidence_signals",
            "weak_or_ambiguous_signals", "screening_question",
        ],
    }
    properties: Dict[str, Any] = {
        "items": {"type": "array", "items": item_schema, "minItems": 1, "maxItems": max(1, len(req_ids))}
    }
    required = ["items"]
    if include_priorities:
        properties["evaluation_priorities"] = {
            "type": "array", "items": {"type": "string", "maxLength": 200},
            "minItems": 3, "maxItems": 5,
        }
        required.append("evaluation_priorities")
    return {"type": "object", "properties": properties, "required": required}


# --------------------------------------------------------------------------
# JSON extraction / salvage
# --------------------------------------------------------------------------
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


def _salvage_partial_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Recover every COMPLETE item object from JSON that was cut off mid-way
    (output hit num_predict). Returns {"items": [...], "evaluation_priorities": [...]} or None.
    """
    cleaned = _extract_json_text(text)
    m = re.search(r'"items"\s*:\s*\[', cleaned)
    if not m:
        return None
    decoder = json.JSONDecoder()
    pos, n = m.end(), len(cleaned)
    items: List[Any] = []
    while pos < n:
        while pos < n and cleaned[pos] in " \t\r\n,":
            pos += 1
        if pos >= n or cleaned[pos] != "{":
            break
        try:
            obj, end = decoder.raw_decode(cleaned, pos)
        except json.JSONDecodeError:
            break  # the last, half-written object
        items.append(obj)
        pos = end

    result: Dict[str, Any] = {"items": items}
    pm = re.search(r'"evaluation_priorities"\s*:\s*\[', cleaned)
    if pm:
        try:
            prios, _ = decoder.raw_decode(cleaned, pm.end() - 1)
            if isinstance(prios, list):
                result["evaluation_priorities"] = prios
        except json.JSONDecodeError:
            pass
    return result if items else None


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
        self.model = model or getattr(settings, "llm_model", None) or os.getenv("LLM_MODEL", DEFAULT_MODEL)
        self.llm_caller = llm_caller

    # ----------------------------------------------------------------------
    # Availability
    # ----------------------------------------------------------------------
    def _model_matches(self, installed_name: str) -> bool:
        wanted = self.model
        if installed_name == wanted or installed_name == f"{wanted}:latest":
            return True
        return ":" not in wanted and installed_name.split(":")[0] == wanted

    def check_ollama_available(self, timeout: float = 3.0, force_refresh: bool = False) -> bool:
        """Check if local Ollama daemon is reachable and the configured model is installed."""
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

        # When default localhost is used, probe 127.0.0.1 directly to avoid redundant probes
        # and Windows IPv6 [::1] connection timeout delays.
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
                    installed = [m.get("name", "") for m in r.json().get("models", [])]
                    if any(self._model_matches(n) for n in installed):
                        self.base_url = candidate_url
                        is_available = True
                        break
                    logger.warning(
                        "Ollama is running at %s but model '%s' is not installed. Installed: %s. "
                        "Run: ollama pull %s",
                        candidate_url, self.model, installed or "none", self.model,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("Ollama availability check failed for %s: %s", candidate_url, exc)

        with _AVAILABILITY_LOCK:
            _AVAILABILITY_CACHE[cache_key] = (is_available, now)

        if not is_available:
            logger.warning(
                "Ollama not available at %s (or model '%s' missing): enrichment will be skipped.",
                self.base_url, self.model,
            )
        return is_available

    # ----------------------------------------------------------------------
    # Prompt
    # ----------------------------------------------------------------------
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
            for c in clarification_context[:12]:
                q_text = str(c.get("question_text") or c.get("question_key") or "")[:200]
                a_text = str(c.get("answer_text") or "")[:300]
                by = c.get("answered_by") or "TA"
                if a_text:
                    clarif_lines.append(f"- Q: {q_text}\n  A ({by}): {a_text}")
            if clarif_lines:
                sections.append("### Resolved Clarifications & Confirmed Scope:\n" + "\n".join(clarif_lines))

        req_lines: List[str] = []
        for r in requirements:
            r_prio = r.get("priority", "MUST_HAVE")
            req_lines.append(f"- ID: {_rid(r)}\n  Priority: {r_prio}\n  Requirement: {_rtext(r)}")

        header = (
            "Please provide FINAL REFINED TA technical enrichment incorporating the resolved clarifications above:\n\n"
            if is_final_refinement and clarification_context
            else "Please provide TA technical enrichment and candidate screening guidance for the following verified requirements:\n\n"
        )

        sections.append(header + "\n".join(req_lines))
        sections.append(
            "Respond with JSON matching the required schema. Produce one item per requirement ID above, "
            "copying each ID exactly, and obey the length limits."
        )
        return "\n\n".join(sections)

    # ----------------------------------------------------------------------
    # Ollama transport
    # ----------------------------------------------------------------------
    def _stream_once(self, payload: Dict[str, Any], read_timeout: float) -> Tuple[str, str]:
        """One streamed /api/chat call. Returns (visible_content, done_reason)."""
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
        if done_reason == "length":
            logger.warning(
                "Ollama output was truncated at num_predict=%s; will salvage complete items and retry the rest.",
                (payload.get("options") or {}).get("num_predict"),
            )
        if not text.strip():
            logger.warning(
                "Ollama returned EMPTY content (done_reason=%s, thinking_chars=%d). "
                "If thinking_chars is large the model spent its budget thinking; "
                "think=False should prevent that.",
                done_reason or "n/a", thinking_chars,
            )
        return text, done_reason

    def _call_ollama_ex(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
    ) -> Tuple[str, str]:
        """Chat completion against local Ollama. Returns (text, done_reason)."""
        if self.llm_caller is not None:
            return self.llm_caller(system_prompt, user_prompt), "stop"

        if not self.check_ollama_available():
            raise OllamaUnavailableError(
                f"Local Ollama service at {self.base_url} is unreachable or model '{self.model}' is not present."
            )

        user_prompt_final = user_prompt
        lowered = self.model.lower()
        if "qwen3" in lowered and "instruct" not in lowered:
            user_prompt_final += "\n\n/no_think"  # soft switch honoured by hybrid Qwen3 builds

        num_ctx = _cfg_int("ENRICH_NUM_CTX", _cfg_int("OLLAMA_NUM_CTX", 8192))
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt_final},
            ],
            "stream": True,
            "think": False,
            "format": schema if schema is not None else "json",
            "keep_alive": str(_cfg("OLLAMA_KEEP_ALIVE", "30m")),
            "options": {
                "num_ctx": num_ctx,
                "num_predict": _cfg_int("ENRICH_NUM_PREDICT", 3072),
                # Qwen3 must NOT run greedy; it falls into repetition loops.
                "temperature": temperature if temperature is not None else _cfg_float("ENRICH_TEMPERATURE", 0.4),
                "top_p": 0.8,
                "top_k": 20,
                "repeat_penalty": _cfg_float("ENRICH_REPEAT_PENALTY", 1.05),
            },
        }

        read_timeout = float(_cfg_int("OLLAMA_READ_TIMEOUT", 300))
        try:
            for _ in range(4):
                try:
                    return self._stream_once(payload, read_timeout)
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    if status in (400, 500):
                        # Degrade gracefully: older builds reject `think`; some reject schema grammars.
                        if "think" in payload:
                            logger.warning("Ollama HTTP %s; retrying without think=False", status)
                            payload.pop("think")
                            continue
                        if isinstance(payload.get("format"), dict):
                            logger.warning("Ollama HTTP %s with JSON schema; retrying with format=json", status)
                            payload["format"] = "json"
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
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Ollama chat error: {exc}") from exc

    def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        """Backwards-compatible wrapper: returns only the text."""
        return self._call_ollama_ex(system_prompt, user_prompt)[0]

    # ----------------------------------------------------------------------
    # Parsing
    # ----------------------------------------------------------------------
    def _parse_and_validate_response(
        self,
        raw_text: str,
        known_reqs: Dict[str, str],
        allowed_ids: Optional[Set[str]] = None,
    ) -> tuple[List[RequirementEnrichmentItem], List[str]]:
        """
        Parse LLM response and strictly filter against known requirement IDs.
        Silently discards hallucinated IDs and incomplete (truncated) items.
        Truncated JSON is salvaged: every complete item is kept.
        """
        cleaned = _extract_json_text(raw_text)

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            parsed = _salvage_partial_json(raw_text)
            if parsed is None:
                logger.warning(
                    "Failed to decode JSON from enrichment response: %s (response chars=%d, preview=%r)",
                    exc, len(raw_text or ""), (raw_text or "")[:120],
                )
                return [], []
            logger.warning(
                "Enrichment JSON was truncated; salvaged %d complete item(s) (%s)",
                len(parsed.get("items", [])), exc,
            )

        raw_items = parsed.get("items", []) if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
        eval_priorities = [
            str(p).strip() for p in (parsed.get("evaluation_priorities", []) if isinstance(parsed, dict) else [])
            if str(p).strip()
        ]
        validated_items: List[RequirementEnrichmentItem] = []
        seen: Set[str] = set()

        for item in raw_items:
            if not isinstance(item, dict):
                continue
            r_id = item.get("requirement_id")
            if not r_id or r_id not in known_reqs or (allowed_ids is not None and r_id not in allowed_ids):
                logger.warning("Dropping enrichment item with unknown or missing requirement_id: %r", r_id)
                continue
            if r_id in seen:
                continue

            tech_summary = str(item.get("technical_concept_summary") or "").strip()
            strong_signals = item.get("strong_evidence_signals") or []
            if isinstance(strong_signals, str):
                strong_signals = [strong_signals]
            weak_signals = item.get("weak_or_ambiguous_signals") or []
            if isinstance(weak_signals, str):
                weak_signals = [weak_signals]
            screening_q = str(item.get("screening_question") or "").strip()

            # An item without a summary or question is a half-written (truncated) one: let it be retried.
            if not tech_summary or not screening_q:
                logger.info("Dropping incomplete enrichment item for %s (will be retried)", r_id)
                continue

            seen.add(r_id)
            validated_items.append(
                RequirementEnrichmentItem(
                    requirement_id=r_id,
                    requirement_text=known_reqs[r_id],
                    technical_concept_summary=tech_summary,
                    strong_evidence_signals=[str(s).strip() for s in strong_signals if str(s).strip()],
                    weak_or_ambiguous_signals=[str(s).strip() for s in weak_signals if str(s).strip()],
                    screening_question=screening_q,
                    origin_type=OriginType.LLM_HYPOTHESIS,
                )
            )

        return validated_items, eval_priorities

    # ----------------------------------------------------------------------
    # One batch, with salvage + split-and-retry
    # ----------------------------------------------------------------------
    def _enrich_chunk(
        self,
        chunk: List[Dict[str, Any]],
        *,
        label: str,
        known_reqs: Dict[str, str],
        clarification_context: Optional[List[Dict[str, Any]]],
        role_context: Optional[Dict[str, Any]],
        is_final: bool,
        include_priorities: bool,
        depth: int = 0,
        attempt: int = 0,
    ) -> Tuple[List[RequirementEnrichmentItem], List[str], Optional[Exception]]:
        """
        Enrich one chunk. Anything that comes back missing (truncation, repetition abort, bad JSON)
        is retried in smaller chunks. Raises OllamaUnavailableError if Ollama is unreachable.
        """
        ids = [str(_rid(r)) for r in chunk]
        base_temp = _cfg_float("ENRICH_TEMPERATURE", 0.4)
        max_depth = _cfg_int("ENRICH_MAX_SPLIT_DEPTH", 3)

        prompt = self.build_user_prompt(
            chunk,
            clarification_context=clarification_context,
            role_context=role_context,
            is_final_refinement=is_final,
        )
        logger.info("Enriching batch %s (%d requirements) via Ollama...", label, len(chunk))

        err: Optional[Exception] = None
        items: List[RequirementEnrichmentItem] = []
        prios: List[str] = []
        done_reason = ""
        try:
            raw, done_reason = self._call_ollama_ex(
                _build_system_prompt(include_priorities),
                prompt,
                schema=_build_schema(ids, include_priorities),
                temperature=min(base_temp + 0.2 * attempt, 1.0),
            )
            items, prios = self._parse_and_validate_response(raw, known_reqs, allowed_ids=set(ids))
        except OllamaUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001
            err = exc
            logger.warning("Enrichment batch %s failed: %s", label, exc)

        got = {i.requirement_id for i in items}
        missing = [r for r in chunk if str(_rid(r)) not in got]
        logger.info(
            "Batch %s completed: %d/%d items validated (done_reason=%s)",
            label, len(items), len(chunk), done_reason or ("error" if err else "n/a"),
        )

        if missing and depth < max_depth:
            if len(chunk) > 1:
                mid = (len(missing) + 1) // 2
                parts = [p for p in (missing[:mid], missing[mid:]) if p]
                need_prios = include_priorities and not prios
                logger.info("Batch %s: retrying %d missing requirement(s) in smaller batches", label, len(missing))
                for k, part in enumerate(parts):
                    sub_items, sub_prios, sub_err = self._enrich_chunk(
                        part,
                        label=f"{label}.{k + 1}",
                        known_reqs=known_reqs,
                        clarification_context=clarification_context,
                        role_context=role_context,
                        is_final=is_final,
                        include_priorities=need_prios and k == 0,
                        depth=depth + 1,
                    )
                    items.extend(sub_items)
                    prios.extend(sub_prios)
                    err = sub_err or err
            elif attempt < 1:
                # Single requirement failed: one more try with a higher temperature
                # (breaks "token repeat limit reached" loops).
                logger.info("Batch %s: retrying single requirement with higher temperature", label)
                sub_items, sub_prios, sub_err = self._enrich_chunk(
                    chunk,
                    label=f"{label}.retry",
                    known_reqs=known_reqs,
                    clarification_context=clarification_context,
                    role_context=role_context,
                    is_final=is_final,
                    include_priorities=include_priorities and not prios,
                    depth=depth,
                    attempt=attempt + 1,
                )
                items.extend(sub_items)
                prios.extend(sub_prios)
                err = sub_err or err

        return items, prios, err

    # ----------------------------------------------------------------------
    # Public entry point
    # ----------------------------------------------------------------------
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

        known_reqs: Dict[str, str] = {}
        for r in requirements:
            r_id = _rid(r)
            if r_id:
                known_reqs[r_id] = _rtext(r)

        # Deduplicate and prioritize substantive requirements across the entire JD (up to 35).
        meaningful_reqs: List[Tuple[int, Dict[str, Any]]] = []
        seen_texts: Set[str] = set()
        for r in requirements:
            r_id = _rid(r)
            r_text = _rtext(r)
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
        order = {str(_rid(r)): idx for idx, r in enumerate(selected_reqs)}

        # Small batches finish well inside the output budget and a failure costs little.
        batch_size = max(1, _cfg_int("ENRICHMENT_BATCH_SIZE", 3))
        batches = [selected_reqs[i: i + batch_size] for i in range(0, len(selected_reqs), batch_size)]

        total_batches = len(batches)
        is_final = bool(clarification_context)
        max_workers = max(1, min(_cfg_int("ENRICHMENT_MAX_WORKERS", 1), total_batches))

        def _run(b_idx: int, chunk: List[Dict[str, Any]]):
            items, prios, err = self._enrich_chunk(
                chunk,
                label=f"{b_idx}/{total_batches}",
                known_reqs=known_reqs,
                clarification_context=clarification_context,
                role_context=role_context,
                is_final=is_final,
                include_priorities=(b_idx == 1),  # evaluation priorities are requested once
            )
            return b_idx, items, prios, err

        batch_results: List[Tuple[int, List[RequirementEnrichmentItem], List[str], Optional[Exception]]] = []

        from app.core.concurrency import acquire_ollama_slot
        try:
            with acquire_ollama_slot(f"enrich_spec_{spec_version_id}"):
                if max_workers == 1:
                    for b_idx, chunk in enumerate(batches, start=1):
                        batch_results.append(_run(b_idx, chunk))
                else:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                        futures = [
                            executor.submit(_run, b_idx, chunk)
                            for b_idx, chunk in enumerate(batches, start=1)
                        ]
                        for fut in concurrent.futures.as_completed(futures):
                            batch_results.append(fut.result())  # OllamaUnavailableError propagates
        except TimeoutError as exc:
            logger.warning("Timed out waiting for Ollama concurrency slot: %s", exc)
            raise OllamaUnavailableError(str(exc))

        batch_results.sort(key=lambda x: x[0])

        all_validated_items: List[RequirementEnrichmentItem] = []
        all_evaluation_priorities: List[str] = []
        last_error: Optional[Exception] = None

        for _b_idx, batch_items, batch_priorities, err in batch_results:
            if err:
                last_error = err
            all_validated_items.extend(batch_items)
            for prio in batch_priorities:
                if prio not in all_evaluation_priorities:
                    all_evaluation_priorities.append(prio)

        # Keep the natural requirement priority ordering.
        all_validated_items.sort(key=lambda i: order.get(i.requirement_id, 10 ** 6))

        if selected_reqs and not all_validated_items:
            raise RuntimeError(
                "Ollama returned no usable enrichment items for any batch"
                + (f" (last error: {last_error})" if last_error else "")
                + ". Check the 'Ollama enrichment call' log lines above."
            )

        covered = len(all_validated_items)
        if covered < len(selected_reqs):
            logger.warning(
                "Enrichment covered %d/%d requirements; the rest keep the deterministic baseline.",
                covered, len(selected_reqs),
            )

        if not all_evaluation_priorities and selected_reqs:
            top_skills = [
                _rtext(r) for r in selected_reqs if len(_rtext(r)) < 80
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