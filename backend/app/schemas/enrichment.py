"""
enrichment.py — Data contracts for Grounded TA Evidence Enrichment.

These schemas define the structured output of the enrichment service.
Enrichment is strictly advisory evaluator aid (LLM_HYPOTHESIS) pinned to
a specific baseline JobSpecificationVersion.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.master_context import OriginType


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RequirementEnrichmentItem(BaseModel):
    """Enrichment details for a single requirement, anchored to requirement_id."""

    requirement_id: str = Field(
        ...,
        description="ID matching JDMasterContext.requirements or canonical evidence_requirements",
    )
    requirement_text: str = Field(
        ...,
        description="Verbatim requirement text from JD",
    )
    technical_concept_summary: str = Field(
        ...,
        description="Recruiter-friendly summary of what this technology is, why it is used, and industry context",
    )
    strong_evidence_signals: List[str] = Field(
        default_factory=list,
        description="Concrete candidate resume evidence signals (projects, tools, metrics, deliverables)",
    )
    weak_or_ambiguous_signals: List[str] = Field(
        default_factory=list,
        description="Vague or weak signals (e.g. passive mentions, keyword stuffing, tutorial projects)",
    )
    screening_question: str = Field(
        ...,
        description="Suggested screening question for recruiter or technical interviewer",
    )
    origin_type: OriginType = Field(
        default=OriginType.LLM_HYPOTHESIS,
        description="Origin marker indicating this is advisory AI guidance",
    )


class TAEnrichmentReport(BaseModel):
    """Immutable enrichment report linked to a specific JobSpecificationVersion."""

    enrichment_id: str = Field(default_factory=lambda: str(uuid4()))
    source_specification_version_id: str = Field(
        ...,
        description="ID of the baseline JobSpecificationVersion",
    )
    source_specification_version: int = Field(
        ...,
        description="Specification version number of the baseline",
    )
    source_checksum: str = Field(
        ...,
        description="SHA256 checksum of the baseline raw JD text",
    )
    items: List[RequirementEnrichmentItem] = Field(
        default_factory=list,
        description="Enriched requirement items validated against deterministic IDs",
    )
    evaluation_priorities: List[str] = Field(
        default_factory=list,
        description="Top grounded candidate evaluation priorities",
    )
    status: str = Field(
        default="completed",
        description="Status of enrichment generation",
    )
    model_version: str = Field(
        default="qwen2.5:1.5b",
        description="Model identifier used for enrichment",
    )
    created_at: str = Field(
        default_factory=_utcnow_iso,
        description="ISO 8601 UTC timestamp of creation",
    )
