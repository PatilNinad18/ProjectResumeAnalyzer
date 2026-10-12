"""
ta_enrichment_service.py — Grounded TA Evidence Enrichment Service.

Produces recruiter-friendly technical explanations, candidate resume evidence signals,
and screening questions strictly anchored to deterministic baseline requirement IDs.
All generated guidance is flagged as OriginType.LLM_HYPOTHESIS.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional

import httpx

from app.config import get_settings
from app.schemas.enrichment import RequirementEnrichmentItem, TAEnrichmentReport
from app.schemas.master_context import OriginType

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Technical Talent Acquisition (TA) Specialist and Engineering Hiring Evaluator.
Your role is to enrich verified job requirements with recruiter-friendly technical explanations,
concrete resume evidence signals, targeted screening questions, and top candidate evaluation priorities.

CRITICAL RULES:
1. STRICT GROUNDING: You will be given a list of verified requirement IDs and texts.
   You must ONLY produce enrichment for the provided requirement IDs.
   DO NOT create new requirement IDs or alter existing requirement IDs.
2. DO NOT change requirement priority or whether a requirement is mandatory vs preferred.
3. TECHNICAL CONCEPT SUMMARY: Explain the core technology or concept in clear, recruiter-friendly language
   so a non-engineer understands what it is, why production systems use it, and its technical significance.
4. STRONG EVIDENCE SIGNALS: Describe concrete evidence that should appear on a candidate's resume
   (e.g. specific frameworks, architectural patterns, throughput metrics, hardware targets, production deliverables).
5. WEAK OR AMBIGUOUS SIGNALS: Describe signals that indicate superficial exposure or buzzword padding
   (e.g. passive mentions, simple tutorial projects, lack of ownership or metrics).
6. SCREENING QUESTION: Provide 1-2 focused, conversational technical screening questions a recruiter
   or hiring manager can ask during an initial phone screen to test real depth.
7. EVALUATION PRIORITIES: Provide 3-5 concise, grounded priority instructions for how evaluators should rank candidates based strictly on the verified requirements.
8. Output MUST be a single valid JSON object strictly matching this schema:
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


class OllamaUnavailableError(RuntimeError):
    """Raised when Ollama is unreachable or the requested model is not installed."""
    pass


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

    def check_ollama_available(self, timeout: float = 3.0) -> bool:
        """Check if local Ollama daemon is reachable and the required model is loaded."""
        if self.llm_caller is not None:
            return True
        candidates = [self.base_url]
        if not self._explicit_base_url:
            for alt in ["http://127.0.0.1:11434", "http://localhost:11434"]:
                if alt not in candidates:
                    candidates.append(alt)

        for candidate_url in candidates:
            try:
                with httpx.Client(timeout=timeout, trust_env=False) as client:
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
                        return True
            except Exception as exc:
                logger.debug("Ollama availability check failed for %s: %s", candidate_url, exc)
        return False

    def build_user_prompt(self, requirements: List[Dict[str, Any]]) -> str:
        """Format the requirements into a structured grounded prompt."""
        req_lines = []
        for r in requirements:
            r_id = r.get("id") or r.get("requirement_id")
            r_text = r.get("text") or r.get("requirement", "")
            r_prio = r.get("priority", "MUST_HAVE")
            req_lines.append(f"- ID: {r_id}\n  Priority: {r_prio}\n  Requirement: {r_text}")

        return (
            "Please provide TA technical enrichment for the following verified requirements:\n\n"
            + "\n".join(req_lines)
            + "\n\nRespond with JSON matching the required schema."
        )

    def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        """Execute chat completion against local Ollama instance."""
        if self.llm_caller is not None:
            return self.llm_caller(system_prompt, user_prompt)

        if not self.check_ollama_available():
            raise OllamaUnavailableError(
                f"Local Ollama service at {self.base_url} is unreachable or model '{self.model}' is not present."
            )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": True,
            "format": "json",
            "options": {
                "num_ctx": 4096,
                "num_predict": 1024,
                "temperature": 0.1,
            },
        }

        read_timeout = float(os.getenv("OLLAMA_READ_TIMEOUT", "300"))
        try:
            timeout = httpx.Timeout(connect=15.0, read=read_timeout, write=30.0, pool=15.0)
            with httpx.Client(timeout=timeout, trust_env=False) as client:
                with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                    response.raise_for_status()
                    collected: List[str] = []
                    for raw_line in response.iter_lines():
                        if not raw_line:
                            continue
                        try:
                            chunk = json.loads(raw_line)
                        except (json.JSONDecodeError, TypeError):
                            continue
                        if chunk.get("error"):
                            raise RuntimeError(f"Ollama error: {chunk['error']}")
                        content = (chunk.get("message") or {}).get("content") or ""
                        if content:
                            collected.append(content)
                        if chunk.get("done"):
                            break
                    return "".join(collected)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise OllamaUnavailableError(f"Could not connect to Ollama at {self.base_url}") from exc
        except httpx.ReadTimeout as exc:
            raise RuntimeError(f"Ollama inference timed out after {read_timeout}s") from exc
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
        # Clean potential markdown fences
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to decode JSON from enrichment response: %s", exc)
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
    ) -> TAEnrichmentReport:
        """
        Generate a TAEnrichmentReport anchored to the provided baseline version and requirements.
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

        # Prioritize substantive technical requirements (filter out short noise fragments, cap at 8)
        meaningful_reqs = []
        for r in requirements:
            r_id = r.get("id") or r.get("requirement_id")
            r_text = (r.get("text") or r.get("requirement") or "").strip()
            if not r_id or len(r_text) < 10:
                continue
            prio = str(r.get("priority", "")).upper()
            rank = 0 if ("MUST" in prio or "MAND" in prio) else (1 if "PREF" in prio else 2)
            meaningful_reqs.append((rank, r))

        meaningful_reqs.sort(key=lambda x: x[0])
        selected_reqs = [x[1] for x in meaningful_reqs[:8]]
        if not selected_reqs:
            selected_reqs = requirements[:8]

        batch_size = 4
        all_validated_items: List[RequirementEnrichmentItem] = []
        all_evaluation_priorities: List[str] = []
        total_batches = (len(selected_reqs) + batch_size - 1) // batch_size
        for batch_idx, i in enumerate(range(0, len(selected_reqs), batch_size), start=1):
            chunk = selected_reqs[i : i + batch_size]
            prompt = self.build_user_prompt(chunk)
            logger.info("Enriching batch %d/%d (%d requirements) via Ollama...", batch_idx, total_batches, len(chunk))
            try:
                raw_output = self._call_ollama(SYSTEM_PROMPT, prompt)
                batch_items, batch_priorities = self._parse_and_validate_response(raw_output, known_reqs)
                all_validated_items.extend(batch_items)
                for prio in batch_priorities:
                    if prio not in all_evaluation_priorities:
                        all_evaluation_priorities.append(prio)
                logger.info("Batch %d/%d completed: %d items validated", batch_idx, total_batches, len(batch_items))
            except Exception as exc:
                logger.warning("Enrichment batch %d/%d failed: %s", batch_idx, total_batches, exc)
                if not all_validated_items and i == 0:
                    raise

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
