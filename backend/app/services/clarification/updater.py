"""
clarification/updater.py — TA Answer Applicator & Finalization Gate.

Applies TA answers to the JDMasterContext atomically:
  1. Validates the answer (question exists, status transition is legal).
  2. Updates the question status and answer_text on the schema object.
  3. Applies the answer to the specific field_target in master context where applicable.
  4. Adds a ProvenanceRecord with origin_type=TA_CONFIRMED.
  5. Recomputes all is_blocking flags via engine.recompute_all_blocking_flags().
  6. Updates lifecycle_status to READY_FOR_REVIEW when no blocking questions remain.

Finalization gate:
  - Rejects finalization if any BLOCKING question is still unresolved and has no override_record.
  - On success: sets lifecycle_status=FINALIZED, finalized_at=utcnow(), seals audit trail entry.

Zero LLM calls. Fully deterministic.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.schemas.master_context import (
    JDLifecycleStatus,
    JDMasterContext,
    OriginType,
    ProvenanceRecord,
    QuestionStatus,
    QuestionPriority,
    RequirementPriority,
    StructuredRequirement,
)
from app.services.clarification.engine import compute_is_blocking, recompute_all_blocking_flags

logger = logging.getLogger("jd_agent.clarification.updater")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class ClarificationUpdateError(Exception):
    """Raised when a TA answer submission is invalid or cannot be applied."""


def submit_answer(
    master: JDMasterContext,
    question_key: str,
    answer_text: str,
    *,
    answered_by: str,
    status: QuestionStatus = QuestionStatus.ANSWERED,
    override_record: Optional[Dict[str, Any]] = None,
) -> JDMasterContext:
    """
    Apply a TA answer to a clarification question and update master context.

    Args:
        master: The authoritative JDMasterContext to mutate.
        question_key: The stable question_key identifying the question.
        answer_text: The TA's answer. Required when status=ANSWERED.
        answered_by: User ID or system identifier of the answerer.
        status: One of ANSWERED, SKIPPED, EXPLICITLY_UNSPECIFIED.
        override_record: Required when submitting a SKIPPED answer for a BLOCKING question.
            Must include: {authorized_by, override_reason, timestamp}.

    Returns:
        The mutated JDMasterContext.

    Raises:
        ClarificationUpdateError: If the question key is not found, or if a BLOCKING
        question is SKIPPED without an authorized override_record.
    """
    _validate_status_arg(status)

    question = next((q for q in master.clarification_history if q.question_key == question_key), None)
    if question is None:
        if question_key.startswith("amb_") or question_key.startswith("jd_ambiguity_"):
            target_id = question_key.replace("jd_ambiguity_", "")
            question = next((
                q for q in master.clarification_history
                if target_id in q.question_key or (q.field_target and target_id in q.field_target)
            ), None)

        if question is None:
            if question_key.startswith("amb_"):
                try:
                    idx = int(question_key.replace("amb_", ""))
                    raw_ambs = getattr(master, "raw_ambiguities", []) or []
                    if idx < len(raw_ambs):
                        target_amb = raw_ambs[idx]
                        target_amb.requires_ta_confirmation = False
                        if not hasattr(target_amb, "suggested_interpretations") or target_amb.suggested_interpretations is None:
                            target_amb.suggested_interpretations = []
                        target_amb.suggested_interpretations.insert(0, f"TA Resolution: {answer_text}")
                        master.add_audit_entry(
                            "clarification_answered",
                            f"Ambiguity '{question_key}' answered directly by TA.",
                            actor=answered_by,
                            question_key=question_key,
                            answer_preview=answer_text[:80] if answer_text else None,
                        )
                        return master
                except Exception:
                    pass
            raise ClarificationUpdateError(
                f"No question with key '{question_key}' found in master context jd_id={master.jd_id}."
            )

    # Guard: BLOCKING + SKIPPED requires an authorized override
    if (
        question.priority == QuestionPriority.BLOCKING
        and status == QuestionStatus.SKIPPED
        and not override_record
    ):
        raise ClarificationUpdateError(
            f"BLOCKING question '{question_key}' cannot be SKIPPED without an authorized override_record. "
            f"Provide override_record={{authorized_by, override_reason, timestamp}}."
        )

    now = datetime.now(timezone.utc)

    # Apply answer to the question object
    question.status = status
    question.answer_text = answer_text
    question.answered_by = answered_by
    question.answered_at = now
    if override_record:
        question.override_record = override_record

    # Recompute is_blocking
    question.is_blocking = compute_is_blocking(question)

    # Apply the answer to the specific field in master context
    _apply_field_patch(master, question.field_target, answer_text, answered_by, question_key, status)

    # Recompute ALL blocking flags after this change
    recompute_all_blocking_flags(master)

    # Update lifecycle based on remaining blocking questions
    _update_lifecycle_status(master)

    master.add_audit_entry(
        "clarification_answered",
        f"Question '{question_key}' answered with status={status.value}.",
        actor=answered_by,
        question_key=question_key,
        status=status.value,
        answer_preview=answer_text[:80] if answer_text else None,
    )

    logger.info(
        "Clarification answered: jd_id=%s question_key=%s status=%s by=%s",
        master.jd_id,
        question_key,
        status.value,
        answered_by,
    )
    return master


def attempt_finalization(
    master: JDMasterContext,
    *,
    actor: Optional[str] = None,
) -> JDMasterContext:
    """
    Attempt to finalize the JD.

    Validation gate: Rejects finalization if any BLOCKING question is still
    unresolved (UNANSWERED or SKIPPED without override_record).

    On success:
      - Sets lifecycle_status = FINALIZED.
      - Sets finalized_at = utcnow().
      - Seals an immutable FINALIZED audit trail entry.

    Raises:
        ClarificationUpdateError: If the finalization gate fails.
    """
    recompute_all_blocking_flags(master)

    unresolved = master.unresolved_blocking_questions
    if unresolved:
        keys = [q.question_key for q in unresolved]
        raise ClarificationUpdateError(
            f"Cannot finalize JD '{master.jd_id}'. "
            f"{len(unresolved)} unresolved BLOCKING question(s) remain: {keys}. "
            f"Answer or provide authorized overrides for all blocking questions before finalizing."
        )

    now = datetime.now(timezone.utc)
    master.lifecycle_status = JDLifecycleStatus.FINALIZED
    master.finalized_at = now

    master.add_audit_entry(
        "finalized",
        f"JD finalized successfully. Version={master.version}. "
        f"Total clarification questions resolved: {len(master.clarification_history)}.",
        actor=actor,
        version=master.version,
        finalized_at=now.isoformat(),
    )

    logger.info(
        "JD finalized: jd_id=%s version=%d finalized_at=%s",
        master.jd_id,
        master.version,
        now.isoformat(),
    )
    return master


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _validate_status_arg(status: QuestionStatus) -> None:
    allowed = {QuestionStatus.ANSWERED, QuestionStatus.SKIPPED, QuestionStatus.EXPLICITLY_UNSPECIFIED}
    if status not in allowed:
        raise ClarificationUpdateError(
            f"Invalid status '{status}'. Must be one of: {[s.value for s in allowed]}. "
            f"UNANSWERED cannot be set manually."
        )


def _apply_field_patch(
    master: JDMasterContext,
    field_target: str,
    answer_text: str,
    answered_by: str,
    question_key: str,
    status: QuestionStatus = QuestionStatus.ANSWERED,
) -> None:
    """
    Apply the answer to a specific field in the master context based on field_target.
    Only well-known field_targets are handled here; unknown targets are logged and skipped.

    The provenance of every applied patch is set to TA_CONFIRMED.
    """
    provenance = ProvenanceRecord(
        origin_type=OriginType.TA_CONFIRMED,
        author=answered_by,
        rule_id=f"clarification:{question_key}",
    )

    # --- job_context fields ---
    if field_target == "job_context.team_size":
        if status == QuestionStatus.EXPLICITLY_UNSPECIFIED or (
            answer_text and answer_text.lower() in ("not specified", "explicitly unspecified")
        ):
            master.job_context.team_size_explicitly_unspecified = True
        elif answer_text:
            master.job_context.team_size = answer_text
        return

    if field_target == "job_context.salary_range":
        if status == QuestionStatus.EXPLICITLY_UNSPECIFIED or (
            answer_text and answer_text.lower() in ("not disclosed", "competitive / market rate", "explicitly unspecified")
        ):
            master.job_context.salary_explicitly_unspecified = True
        elif answer_text:
            master.job_context.salary_range = answer_text
        return

    # --- ambiguities[id=...] or ambiguities[...] fields ---
    if field_target.startswith("ambiguities[") or field_target.startswith("raw_ambiguities["):
        amb_id = _extract_id_from_target(field_target)
        raw_ambs = getattr(master, "raw_ambiguities", []) or []
        for amb in raw_ambs:
            cur_id = getattr(amb, "ambiguity_id", "") or str(getattr(amb, "id", ""))
            if amb_id and (cur_id == amb_id or amb_id in cur_id):
                amb.requires_ta_confirmation = False
                if not hasattr(amb, "suggested_interpretations") or amb.suggested_interpretations is None:
                    amb.suggested_interpretations = []
                resolution_note = f"TA Resolution: {answer_text}"
                if resolution_note not in amb.suggested_interpretations:
                    amb.suggested_interpretations.insert(0, resolution_note)
                break
        return

    # --- requirements[id=...].priority fields ---
    if field_target.startswith("requirements[id=") and ".priority" in field_target:
        req_id = _extract_id_from_target(field_target)
        if req_id:
            ans_clean = (answer_text or "").lower().strip()
            if any(k in ans_clean for k in ("must have", "must_have", "mandatory", "required")):
                new_priority = RequirementPriority.MUST_HAVE
            elif any(k in ans_clean for k in ("preferred", "nice to have", "optional")):
                new_priority = RequirementPriority.PREFERRED
            elif any(k in ans_clean for k in ("informational", "context", "role context")):
                new_priority = RequirementPriority.INFORMATIONAL
            else:
                new_priority = None

            for item in master.requirements:
                if isinstance(item, StructuredRequirement) and item.id == req_id:
                    if new_priority:
                        item.priority = new_priority
                        item.requires_clarification = False
                        if new_priority == RequirementPriority.MUST_HAVE:
                            item.is_mandatory = True
                        else:
                            item.is_mandatory = False
                        item.provenance = ProvenanceRecord(
                            origin_type=OriginType.TA_CONFIRMED,
                            source_span=item.provenance.source_span if item.provenance else None,
                            author=answered_by,
                            rule_id=f"clarification:{question_key}",
                        )
                    return

        return

    # --- responsibilities[id=...].interpretation_status ---
    if field_target.startswith("responsibilities[id=") and ".interpretation_status" in field_target:
        resp_id = _extract_id_from_target(field_target)
        if resp_id:
            for resp in master.responsibilities:
                if resp.id == resp_id:
                    resp.interpretation_status = "TA_CONFIRMED"  # type: ignore[assignment]
                    resp.provenance.append(provenance)
                    return

    # Unknown field target — log and skip (non-fatal; answer is still recorded on the question)
    logger.warning(
        "Unknown field_target '%s' for question '%s' — answer recorded but no field patch applied.",
        field_target,
        question_key,
    )


def _extract_id_from_target(field_target: str) -> Optional[str]:
    """Extract the id value from patterns like 'requirements[id=abc-123].priority' or 'ambiguities[amb_123]'."""
    import re
    match = re.search(r"\[id=([^\]]+)\]", field_target)
    if match:
        return match.group(1)
    match2 = re.search(r"\[([^\]]+)\]", field_target)
    return match2.group(1) if match2 else None


def _update_lifecycle_status(master: JDMasterContext) -> None:
    """
    After every answer submission, recompute lifecycle status:
    - If no unresolved blocking questions remain → READY_FOR_REVIEW
    - If some remain → stay at AWAITING_CLARIFICATION
    - Never revert from FINALIZED.
    """
    if master.lifecycle_status == JDLifecycleStatus.FINALIZED:
        return
    if master.is_ready_to_finalize:
        master.lifecycle_status = JDLifecycleStatus.READY_FOR_REVIEW
    else:
        master.lifecycle_status = JDLifecycleStatus.AWAITING_CLARIFICATION
