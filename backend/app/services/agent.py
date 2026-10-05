"""
JD Understanding Agent orchestration with RAG grounding.

Pipeline:
  RAW JD
    -> RAG pre-processing (atomic extraction -> classification -> hybrid retrieval -> RRF)
    -> build_user_prompt (raw JD + domain knowledge context)
    -> LLMService (structured output)
    -> Pydantic validation (tolerant: see schemas/canonical.py)
    -> JobEvaluationSpecification (canonical object)
    -> caller renders MD/JSON

The raw JD remains the immutable source of truth throughout. RAG provides
supporting interpretation guidance only and must never override JD facts.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import ValidationError

from app.schemas.canonical import JobEvaluationSpecification, Priority
from app.services.llm_service import LLMResult, LLMService, cfg_int
from app.services.prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from app.services.rag import format_snippets_for_prompt, run_rag_pipeline

logger = logging.getLogger("jd_agent.agent")


# ---------------------------------------------------------------------------
# Deterministic post-processing (a 4B model is not reliable at these)
# ---------------------------------------------------------------------------
_TITLE_RE = re.compile(r"^\s*job title\s*:\s*(.+?)\s*$", re.I)
_STOP = {
    "year", "years", "yr", "yrs", "of", "with", "work", "experience", "in", "and", "the", "a", "an",
    "programming", "language", "relevant", "proficiency", "knowledge", "strong", "hands", "on",
    "using", "development", "skills", "skill", "understanding", "good", "basic", "working", "or",
}


def _sig(text: str) -> frozenset:
    """Significant tokens of a requirement, used to detect duplicates ("React.js" == "react")."""
    toks = set()
    for t in re.findall(r"[a-z][a-z0-9.+#/'-]*", (text or "").lower()):
        t = re.sub(r"\.js$", "", t.strip(".-/"))
        if t and t not in _STOP:
            toks.add(t)
    return frozenset(toks)


def _postprocess(spec: JobEvaluationSpecification, jd_text: str) -> None:
    """
    1. A recruiter-supplied 'Job Title:' header line always wins over the model's guess.
    2. Drop must-haves that merely repeat a structured experience/education entry
       (the renderer already prints those, which caused duplicates).
    3. Make sure every extracted technical skill appears in the requirement lists
       (the renderer does not print technical_skills on its own).
    """
    first_line = next((ln for ln in jd_text.splitlines() if ln.strip()), "")
    m = _TITLE_RE.match(first_line)
    if m:
        spec.role.job_title = m.group(1)

    cr = spec.conventional_requirements
    structured: List[frozenset] = [s for s in (_sig(x.description) for x in [*cr.experience, *cr.education]) if s]

    def covered_by(tokens: frozenset, pool: List[frozenset]) -> bool:
        return bool(tokens) and any(tokens <= p for p in pool)

    spec.must_have_requirements = [r for r in spec.must_have_requirements if not covered_by(_sig(r), structured)]

    pool = structured + [_sig(r) for r in [*spec.must_have_requirements, *spec.preferred_requirements]]
    for skill in cr.technical_skills:
        tokens = _sig(skill.name)
        if not tokens or covered_by(tokens, pool):
            continue
        if skill.priority == Priority.PREFERRED:
            spec.preferred_requirements.append(skill.name)
        elif skill.priority == Priority.MUST_HAVE:
            spec.must_have_requirements.append(skill.name)
        else:
            continue
        pool.append(tokens)

    logger.info(
        "[agent] extracted: title=%r skills=%d experience=%d must_have=%d preferred=%d responsibilities=%d "
        "evidence=%d ambiguities=%d",
        spec.role.job_title, len(cr.technical_skills), len(cr.experience), len(spec.must_have_requirements),
        len(spec.preferred_requirements), len(spec.responsibilities), len(spec.evidence_requirements),
        len(spec.ambiguities),
    )


class JDUnderstandingError(Exception):
    """Raised when the agent cannot produce a valid canonical specification."""


class JDUnderstandingAgent:
    def __init__(self, llm_service: Optional[LLMService] = None, enable_rag: bool = True):
        self.llm_service = llm_service or LLMService()
        self.enable_rag = enable_rag

    def _run_rag(self, jd_text: str) -> str:
        """Return a formatted domain-knowledge string, or "" if RAG is unavailable/empty."""
        try:
            # Fewer snippets = fewer prompt tokens on a local model.
            rag_context = run_rag_pipeline(jd_text, max_snippets=cfg_int("RAG_MAX_SNIPPETS", 5))
            if not rag_context.selected_snippets:
                logger.debug("[RAG] No snippets selected for prompt injection.")
                return ""
            logger.info(
                "[RAG] Grounding complete: %d classified requirements, %d snippets injected "
                "(budget_used=%s, total_retrieved=%s).",
                len(rag_context.classified_requirements),
                len(rag_context.selected_snippets),
                rag_context.budget_used,
                rag_context.total_retrieved,
            )
            return format_snippets_for_prompt(rag_context.selected_snippets)
        except Exception as exc:  # noqa: BLE001
            # RAG failure must never block the core JD analysis pipeline.
            logger.warning("[RAG] Pipeline failed - proceeding without RAG context: %s", exc)
            return ""

    def understand(
        self,
        jd_text: str,
        jd_id: Optional[str] = None,
        jd_version: Optional[int] = None,
        specification_version: Optional[int] = None,
    ) -> tuple[JobEvaluationSpecification, LLMResult]:
        """
        Run the JD through the RAG-grounded agent and return a validated canonical
        JobEvaluationSpecification plus the raw LLM call metadata (cost/latency/audit).
        """
        if not jd_text or not jd_text.strip():
            raise JDUnderstandingError("JD text is empty.")

        rag_context_str = self._run_rag(jd_text) if self.enable_rag else ""
        user_prompt = build_user_prompt(jd_text, rag_context=rag_context_str or None)

        try:
            result = self.llm_service.complete_structured(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=cfg_int("JD_MAX_OUTPUT_TOKENS", 6144),
            )
        except RuntimeError as exc:
            raise JDUnderstandingError(str(exc)) from exc

        if result.parsed_json is None:
            hint = ""
            if (result.finish_reason or "").lower() in ("length", "max_tokens"):
                hint = (f" The response was truncated (finish_reason={result.finish_reason}) "
                        "- increase JD_MAX_OUTPUT_TOKENS.")
            raise JDUnderstandingError(
                f"LLM did not return parseable JSON.{hint} The raw output was saved to "
                "storage_data/debug_llm_failures/ for review."
            )

        payload = dict(result.parsed_json)
        payload["metadata"] = {
            "jd_id": jd_id,
            "jd_version": jd_version,
            "specification_version": specification_version,
            "prompt_version": PROMPT_VERSION,
            "model_version": result.usage.model,
            "generated_at": datetime.now(timezone.utc),
        }

        try:
            spec = JobEvaluationSpecification.model_validate(payload)
        except ValidationError as exc:
            raise JDUnderstandingError(f"Canonical schema validation failed: {exc}") from exc

        _postprocess(spec, jd_text)

        if not spec.role.job_title:
            logger.warning("[agent] Model returned no role.job_title; the renderer will show 'unspecified'.")
        if not spec.job_context.company_context:
            logger.warning("[agent] Model returned no job_context.company_context.")

        return spec, result