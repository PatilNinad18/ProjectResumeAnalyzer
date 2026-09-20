"""
JD Understanding Agent orchestration with RAG grounding.

Pipeline:
  RAW JD
    → RAG pre-processing (atomic extraction → classification → hybrid retrieval → RRF)
    → build_user_prompt (raw JD + domain knowledge context)
    → LLMService (structured output)
    → Pydantic validation
    → JobEvaluationSpecification (canonical object)
    → caller renders MD/JSON

The raw JD remains the immutable source of truth throughout. RAG provides
supporting interpretation guidance only and must never override JD facts.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError

from app.schemas.canonical import JobEvaluationSpecification
from app.services.llm_service import LLMService, LLMResult
from app.services.prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from app.services.rag import (
    extract_and_classify,
    format_snippets_for_prompt,
    generate_queries,
    run_rag_pipeline,
    select_context,
)
from app.services.rag.retrieval import HybridRetriever

logger = logging.getLogger("jd_agent.agent")


class JDUnderstandingError(Exception):
    """Raised when the agent cannot produce a valid canonical specification."""


class JDUnderstandingAgent:
    def __init__(self, llm_service: Optional[LLMService] = None, enable_rag: bool = True):
        self.llm_service = llm_service or LLMService()
        self.enable_rag = enable_rag

    def _run_rag(self, jd_text: str) -> str:
        """
        Run the full RAG pipeline for the given JD text.

        Returns a formatted domain knowledge context string ready for prompt
        injection, or an empty string if RAG produced no useful snippets.
        """
        try:
            rag_context = run_rag_pipeline(jd_text, max_snippets=8)
            if not rag_context.selected_snippets:
                logger.debug("[RAG] No snippets selected for prompt injection.")
                return ""
            formatted = format_snippets_for_prompt(rag_context.selected_snippets)
            logger.info(
                "[RAG] Grounding complete: %d classified requirements, "
                "%d snippets injected (budget_used=%d, total_retrieved=%d).",
                len(rag_context.classified_requirements),
                rag_context.budget_used,
                rag_context.budget_used,
                rag_context.total_retrieved,
            )
            return formatted
        except Exception as exc:  # noqa: BLE001
            # RAG failure must never block the core JD analysis pipeline.
            logger.warning("[RAG] Pipeline failed — proceeding without RAG context: %s", exc)
            return ""

    def understand(
        self,
        jd_text: str,
        jd_id: Optional[str] = None,
        jd_version: Optional[int] = None,
        specification_version: Optional[int] = None,
    ) -> tuple[JobEvaluationSpecification, LLMResult]:
        """
        Runs the JD through the RAG-grounded Agent and returns a validated canonical
        JobEvaluationSpecification, plus the raw LLM call metadata (for
        cost/latency/audit tracking).

        Stage 1-6: RAG pre-processing (extraction, classification, retrieval, RRF, selection).
        Stage 7:   Context Creator (build_user_prompt with RAG snippets).
        Stage 8:   LLM structured generation.
        Stage 9:   Pydantic validation → JobEvaluationSpecification.
        """
        if not jd_text or not jd_text.strip():
            raise JDUnderstandingError("JD text is empty.")

        # ── Stage 1–6: RAG grounding ─────────────────────────────────────────
        rag_context_str: str = ""
        if self.enable_rag:
            rag_context_str = self._run_rag(jd_text)

        # ── Stage 7: Context Creator ──────────────────────────────────────────
        user_prompt = build_user_prompt(jd_text, rag_context=rag_context_str or None)

        # ── Stage 8: LLM structured generation ───────────────────────────────
        result = self.llm_service.complete_structured(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=16384,
        )

        if result.parsed_json is None:
            reason_hint = ""
            if result.finish_reason in ("MAX_TOKENS", "max_tokens"):
                reason_hint = (
                    " The response was truncated (finish_reason="
                    f"{result.finish_reason}) before the JSON object closed -- "
                    "increase max_tokens."
                )
            raise JDUnderstandingError(
                "LLM did not return parseable JSON."
                f"{reason_hint} Full raw output has been written to "
                "storage_data/debug_llm_failures/ for review."
            )

        # ── Stage 9: Pydantic validation ──────────────────────────────────────
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

        return spec, result