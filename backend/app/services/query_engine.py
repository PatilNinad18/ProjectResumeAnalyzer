"""
services/query_engine.py — Deterministic Grounded Query Engine.

Answers natural language questions about a JD by routing them to direct reads
against JDMasterContext. Zero LLM calls. Zero fabrication.

Supported query types (matched via keyword routing):
  - "mandatory requirements" / "must have"     → must_have_requirements list
  - "preferred requirements" / "nice to have"  → PREFERRED requirements
  - "clarification" / "ta clarif" / "answered" → answered clarification Q&A
  - "not specified" / "missing" / "unspecified" → explicitly unspecified fields
  - "responsibilities" / "responsibility"       → responsibility statements + EKG activities
  - "compliance" / "flag"                       → compliance flags
  - "status" / "lifecycle" / "finalized"        → current lifecycle status
  - "audit" / "history"                         → audit trail
  - anything else                               → guided unknown-query response

All answers include provenance labels so the TA knows the source of each datum.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from app.schemas.master_context import (
    JDMasterContext,
    OriginType,
    QuestionStatus,
    RequirementPriority,
    StructuredRequirement,
    DisjunctionGroup,
)

logger = logging.getLogger("jd_agent.query_engine")


# ---------------------------------------------------------------------------
# Query result types
# ---------------------------------------------------------------------------

@dataclass
class QueryAnswer:
    """A single structured answer item with provenance label."""
    text: str
    provenance_label: str  # e.g. "Explicit JD text", "TA Confirmed", "EKG Derived"
    section: Optional[str] = None
    source_quote: Optional[str] = None


@dataclass
class QueryResult:
    """The full result of a grounded query."""
    query: str
    query_type: str
    answers: List[QueryAnswer] = field(default_factory=list)
    summary: str = ""
    fabricated: bool = False  # Always False — this engine never fabricates


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def answer_query(
    master: JDMasterContext,
    query: str,
) -> QueryResult:
    """
    Route a natural language question to the appropriate deterministic handler.

    Returns a QueryResult with provenance-labeled answers.
    Never fabricates; never calls an LLM.

    Args:
        master: The JDMasterContext to query against.
        query: A natural language question from the TA or UI.

    Returns:
        QueryResult with answers, summary, and query_type.
    """
    q = query.lower().strip()

    if any(kw in q for kw in ("must have", "mandatory", "must-have", "required requirement")):
        return _query_mandatory_requirements(master, query)

    if any(kw in q for kw in ("preferred", "nice to have", "optional requirement", "good to have")):
        return _query_preferred_requirements(master, query)

    if any(kw in q for kw in ("clarif", "ta answer", "ta clarif", "answered question", "what did the ta")):
        return _query_clarification_answers(master, query)

    if any(kw in q for kw in ("not specified", "missing", "unspecified", "absent", "not mentioned")):
        return _query_unspecified_fields(master, query)

    if any(kw in q for kw in ("responsibil", "duty", "duties", "what does the role", "what will")):
        return _query_responsibilities(master, query)

    if any(kw in q for kw in ("compliance", "flag", "legal", "discriminat", "red flag")):
        return _query_compliance_flags(master, query)

    if any(kw in q for kw in ("status", "lifecycle", "finalized", "stage", "current state")):
        return _query_lifecycle_status(master, query)

    if any(kw in q for kw in ("audit", "history", "what happened", "timeline", "events")):
        return _query_audit_trail(master, query)

    if any(kw in q for kw in ("unanswered", "pending", "open question", "blocking")):
        return _query_pending_questions(master, query)

    return _query_unknown(master, query)


# ---------------------------------------------------------------------------
# Query Handlers
# ---------------------------------------------------------------------------

def _query_mandatory_requirements(master: JDMasterContext, query: str) -> QueryResult:
    """Returns all MUST_HAVE requirements with provenance labels."""
    must_haves = master.must_have_requirements
    answers: List[QueryAnswer] = []
    for req in must_haves:
        provenance_label = _provenance_label(req.provenance.origin_type)
        answers.append(QueryAnswer(
            text=req.text,
            provenance_label=provenance_label,
            section=req.provenance.source_span.section if req.provenance.source_span else None,
            source_quote=req.provenance.source_span.raw_text if req.provenance.source_span else None,
        ))

    if not answers:
        return QueryResult(
            query=query,
            query_type="mandatory_requirements",
            answers=[],
            summary=(
                "No mandatory requirements have been confirmed yet. "
                "The JD may still be in the ANALYZED or AWAITING_CLARIFICATION stage. "
                "Complete the clarification process and finalize to see confirmed MUST HAVE requirements."
            ),
        )

    return QueryResult(
        query=query,
        query_type="mandatory_requirements",
        answers=answers,
        summary=(
            f"Found {len(answers)} mandatory requirement(s). "
            f"All are sourced from explicit JD text or TA confirmations — never from EKG inference."
        ),
    )


def _query_preferred_requirements(master: JDMasterContext, query: str) -> QueryResult:
    """Returns all PREFERRED requirements."""
    preferred = [
        item for item in master.requirements
        if isinstance(item, StructuredRequirement) and item.priority == RequirementPriority.PREFERRED
    ]
    answers = [
        QueryAnswer(
            text=req.text,
            provenance_label=_provenance_label(req.provenance.origin_type),
            section=req.provenance.source_span.section if req.provenance.source_span else None,
            source_quote=req.provenance.source_span.raw_text if req.provenance.source_span else None,
        )
        for req in preferred
    ]
    return QueryResult(
        query=query,
        query_type="preferred_requirements",
        answers=answers,
        summary=f"Found {len(answers)} preferred (nice-to-have) requirement(s).",
    )


def _query_clarification_answers(master: JDMasterContext, query: str) -> QueryResult:
    """Returns all answered clarification questions with their TA answers."""
    answered = [q for q in master.clarification_history if q.status == QuestionStatus.ANSWERED]
    answers: List[QueryAnswer] = []
    for q in answered:
        answers.append(QueryAnswer(
            text=f"Q: {q.question_text}\nA: {q.answer_text or '(no text)'}",
            provenance_label="TA Confirmed",
            section=f"Category: {q.category.value}, Priority: {q.priority.value}",
            source_quote=f"Answered by {q.answered_by} at {q.answered_at.isoformat() if q.answered_at else 'unknown time'}",
        ))

    explicitly_unspecified = [q for q in master.clarification_history if q.status == QuestionStatus.EXPLICITLY_UNSPECIFIED]
    for q in explicitly_unspecified:
        answers.append(QueryAnswer(
            text=f"Q: {q.question_text}\nA: (Explicitly unspecified — TA confirmed this information is not available)",
            provenance_label="TA Explicitly Unspecified",
            section=f"Category: {q.category.value}",
        ))

    return QueryResult(
        query=query,
        query_type="clarification_answers",
        answers=answers,
        summary=(
            f"{len(answered)} question(s) answered by TA. "
            f"{len(explicitly_unspecified)} field(s) explicitly unspecified. "
            f"{len([q for q in master.clarification_history if q.status == QuestionStatus.UNANSWERED])} still unanswered."
        ),
    )


def _query_unspecified_fields(master: JDMasterContext, query: str) -> QueryResult:
    """Returns fields that are absent from the JD and not fabricated."""
    answers: List[QueryAnswer] = []
    ctx = master.job_context

    if ctx.team_size is None:
        label = "Explicitly unspecified (TA confirmed)" if ctx.team_size_explicitly_unspecified else "Not mentioned in JD"
        answers.append(QueryAnswer(text="Team size: not specified.", provenance_label=label))

    if ctx.salary_range is None:
        label = "Explicitly unspecified (TA confirmed)" if ctx.salary_explicitly_unspecified else "Not mentioned in JD"
        answers.append(QueryAnswer(text="Salary range / compensation: not specified.", provenance_label=label))

    if master.role_overview.seniority is None:
        answers.append(QueryAnswer(text="Seniority level: not explicitly stated.", provenance_label="Not mentioned in JD"))

    # UNRESOLVED requirements count as ambiguous/not fully specified
    unresolved = [
        item for item in master.requirements
        if isinstance(item, StructuredRequirement) and item.priority == RequirementPriority.UNRESOLVED
    ]
    if unresolved:
        answers.append(QueryAnswer(
            text=f"{len(unresolved)} requirement(s) have UNRESOLVED priority — mandatory vs preferred is unclear.",
            provenance_label="Ambiguous in JD",
            section="Requirements",
        ))

    return QueryResult(
        query=query,
        query_type="unspecified_fields",
        answers=answers,
        summary=(
            f"{len(answers)} field(s) are absent or ambiguous in the JD. "
            "None of these are fabricated — they reflect actual gaps in the JD text."
        ),
    )


def _query_responsibilities(master: JDMasterContext, query: str) -> QueryResult:
    """Returns responsibility statements with EKG-derived activity context."""
    answers: List[QueryAnswer] = []
    for resp in master.responsibilities:
        main_text = resp.raw_statement
        # Attach EKG-derived activities as context (clearly labeled as derived, NOT mandatory)
        if resp.graph_derived_activities:
            activity_lines = "\n".join(
                f"  • [{a.relation_type}] {a.activity_description} (EKG derived — context only, not a requirement)"
                for a in resp.graph_derived_activities[:5]
            )
            main_text += f"\n\nImplied technical activities (EKG derived, NOT mandatory requirements):\n{activity_lines}"

        if resp.matched_entities:
            entity_names = ", ".join(e.canonical_name for e in resp.matched_entities[:5])
            main_text += f"\nMatched domain entities: {entity_names}"

        answers.append(QueryAnswer(
            text=main_text,
            provenance_label="Explicit JD text",
            section=resp.source_span.section,
            source_quote=resp.source_span.raw_text,
        ))

    return QueryResult(
        query=query,
        query_type="responsibilities",
        answers=answers,
        summary=(
            f"Found {len(answers)} responsibility statement(s). "
            "EKG-derived activities are shown as context but are NEVER mandatory requirements."
        ),
    )


def _query_compliance_flags(master: JDMasterContext, query: str) -> QueryResult:
    """Returns all compliance flags."""
    answers = [
        QueryAnswer(
            text=f"[{f.category.upper()}] {f.flagged_text}: {f.concern}",
            provenance_label="Compliance Detector",
            section=f.category,
            source_quote=f.recommended_action,
        )
        for f in master.compliance_flags
    ]
    return QueryResult(
        query=query,
        query_type="compliance_flags",
        answers=answers,
        summary=(
            f"Found {len(answers)} compliance flag(s). "
            "These must not be used in automated candidate scoring."
        ) if answers else "No compliance flags detected in this JD.",
    )


def _query_lifecycle_status(master: JDMasterContext, query: str) -> QueryResult:
    """Returns the current lifecycle status and blocking question count."""
    blocking_count = len(master.unresolved_blocking_questions)
    status_text = (
        f"Current lifecycle status: {master.lifecycle_status.value}. "
        f"Version: {master.version}."
    )
    if master.lifecycle_status.value == "FINALIZED":
        status_text += f" Finalized at: {master.finalized_at.isoformat() if master.finalized_at else 'unknown'}."
    elif blocking_count > 0:
        status_text += f" {blocking_count} unresolved BLOCKING question(s) must be answered before finalization."
    elif master.lifecycle_status.value == "READY_FOR_REVIEW":
        status_text += " All blocking questions resolved. Ready to finalize."

    return QueryResult(
        query=query,
        query_type="lifecycle_status",
        answers=[QueryAnswer(text=status_text, provenance_label="System State")],
        summary=status_text,
    )


def _query_audit_trail(master: JDMasterContext, query: str) -> QueryResult:
    """Returns the chronological audit trail."""
    answers = [
        QueryAnswer(
            text=f"[{entry.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}] {entry.event_type}: {entry.description}",
            provenance_label=f"Actor: {entry.actor or 'system'}",
        )
        for entry in master.audit_trail
    ]
    return QueryResult(
        query=query,
        query_type="audit_trail",
        answers=answers,
        summary=f"Audit trail contains {len(answers)} event(s) for JD {master.jd_id}.",
    )


def _query_pending_questions(master: JDMasterContext, query: str) -> QueryResult:
    """Returns all still-unanswered and blocking questions."""
    unanswered = [q for q in master.clarification_history if q.status == QuestionStatus.UNANSWERED]
    answers = [
        QueryAnswer(
            text=f"[{q.priority.value}] {q.question_text}",
            provenance_label=f"Category: {q.category.value}",
            section="Blocking" if q.is_blocking else "Non-blocking",
        )
        for q in unanswered
    ]
    return QueryResult(
        query=query,
        query_type="pending_questions",
        answers=answers,
        summary=(
            f"{len(answers)} question(s) still unanswered. "
            f"{sum(1 for q in unanswered if q.is_blocking)} are BLOCKING (must resolve before finalization)."
        ),
    )


def _query_unknown(master: JDMasterContext, query: str) -> QueryResult:
    """Handles unrecognised queries without fabricating an answer."""
    return QueryResult(
        query=query,
        query_type="unknown",
        answers=[QueryAnswer(
            text=(
                "This query type is not currently handled by the deterministic query engine. "
                "Try asking about: mandatory requirements, preferred requirements, what the TA clarified, "
                "what is not specified, responsibilities, compliance flags, lifecycle status, or audit history."
            ),
            provenance_label="System",
        )],
        summary="Query type not recognised. No data was fabricated.",
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _provenance_label(origin_type: OriginType) -> str:
    mapping = {
        OriginType.EXPLICIT_JD: "Explicit JD text",
        OriginType.EKG_DERIVED: "EKG Derived (context only — not a mandatory requirement)",
        OriginType.LLM_HYPOTHESIS: "LLM Hypothesis (unconfirmed — not a mandatory requirement)",
        OriginType.TA_CONFIRMED: "TA Confirmed",
        OriginType.TA_MANUAL_EDIT: "TA Manual Edit",
    }
    return mapping.get(origin_type, str(origin_type))
