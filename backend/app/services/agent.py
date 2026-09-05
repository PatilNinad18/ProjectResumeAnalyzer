"""
JD Understanding Agent orchestration.

RAW JD -> LLMService (structured output) -> Pydantic validation ->
JobEvaluationSpecification (canonical object) -> caller renders MD/JSON.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError

from app.schemas.canonical import JobEvaluationSpecification, MetadataInfo
from app.services.llm_service import LLMService, LLMResult
from app.services.prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt


class JDUnderstandingError(Exception):
    """Raised when the agent cannot produce a valid canonical specification."""


class JDUnderstandingAgent:
    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm_service = llm_service or LLMService()

    def understand(
        self,
        jd_text: str,
        jd_id: Optional[str] = None,
        jd_version: Optional[int] = None,
        specification_version: Optional[int] = None,
    ) -> tuple[JobEvaluationSpecification, LLMResult]:
        """
        Runs the JD through the Agent and returns a validated canonical
        JobEvaluationSpecification, plus the raw LLM call metadata (for
        cost/latency/audit tracking).
        """
        if not jd_text or not jd_text.strip():
            raise JDUnderstandingError("JD text is empty.")

        user_prompt = build_user_prompt(jd_text)
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