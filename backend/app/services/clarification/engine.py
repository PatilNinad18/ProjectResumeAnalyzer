"""
clarification/engine.py — Deterministic Clarification Question Generator.

Implements the 3-Tier Question Classification Policy from Problem 2 (B):
  - Tier 1 (BLOCKING):     Contradictions, unresolvable core scope conflicts.
  - Tier 2 (RECOMMENDED):  Technical scope gaps (non-blocking; has fallback).
  - Tier 3 (OPTIONAL):     Metadata (team size, salary) — quick intake chips.

Design Invariants:
  1. Zero LLM calls. All question generation is purely deterministic rule-based.
  2. Idempotent: questions are keyed by question_key. Calling generate() twice
     on the same master context produces the same set of question_keys (no duplicates).
  3. Questions are merged into master.clarification_history (existing answers preserved).
  4. OPTIONAL questions (team_size, salary) are NEVER is_blocking=True.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from app.schemas.master_context import (
    ClarificationQuestionSchema,
    ConfidenceBand,
    InterpretationStatus,
    JDMasterContext,
    JDLifecycleStatus,
    LogicOperator,
    OriginType,
    QuestionCategory,
    QuestionPriority,
    QuestionStatus,
    RequirementPriority,
    StructuredRequirement,
    DisjunctionGroup,
)

logger = logging.getLogger("jd_agent.clarification.engine")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_clarification_questions(
    master: JDMasterContext,
    *,
    actor: Optional[str] = None,
) -> JDMasterContext:
    """
    Evaluate the master context and generate clarification questions.
    Merges new questions into master.clarification_history (idempotent by question_key).
    Updates lifecycle_status to AWAITING_CLARIFICATION if any questions were generated,
    or READY_FOR_REVIEW if none.

    Returns the mutated master context.
    """
    existing_keys = {q.question_key for q in master.clarification_history}
    new_questions: List[ClarificationQuestionSchema] = []

    # --- Tier 1: BLOCKING — Contradictions ---
    new_questions.extend(_detect_contradictions(master, existing_keys))

    # --- Tier 1: BLOCKING — UNRESOLVED mandatory requirements ---
    new_questions.extend(_detect_unresolved_mandatory(master, existing_keys))

    # --- Tier 2: RECOMMENDED — Technical scope disambiguation ---
    new_questions.extend(_detect_low_confidence_requirements(master, existing_keys))

    # --- Tier 2: RECOMMENDED — Uninterpreted responsibilities with EKG matches ---
    new_questions.extend(_detect_uninterpreted_responsibilities(master, existing_keys))

    # --- Tier 3: OPTIONAL — Missing metadata (team size, salary) ---
    new_questions.extend(_detect_missing_metadata(master, existing_keys))

    if new_questions:
        master.clarification_history.extend(new_questions)
        master.lifecycle_status = JDLifecycleStatus.AWAITING_CLARIFICATION
        master.add_audit_entry(
            "clarification_generated",
            f"Generated {len(new_questions)} new clarification question(s).",
            actor=actor,
            question_count=len(new_questions),
            blocking_count=sum(1 for q in new_questions if q.is_blocking),
        )
        logger.info(
            "Generated %d clarification questions for jd_id=%s (%d blocking).",
            len(new_questions),
            master.jd_id,
            sum(1 for q in new_questions if q.is_blocking),
        )
    else:
        master.lifecycle_status = JDLifecycleStatus.READY_FOR_REVIEW
        master.add_audit_entry(
            "clarification_none_needed",
            "No clarification questions required. JD is ready for review.",
            actor=actor,
        )

    return master


def compute_is_blocking(question: ClarificationQuestionSchema) -> bool:
    """
    Dynamically recompute whether a question is still blocking.
    A BLOCKING-priority question is no longer blocking if it has been
    ANSWERED, EXPLICITLY_UNSPECIFIED, or has an authorized override_record.
    """
    if question.priority != QuestionPriority.BLOCKING:
        return False
    if question.status in {QuestionStatus.ANSWERED, QuestionStatus.EXPLICITLY_UNSPECIFIED}:
        return False
    if question.override_record is not None:
        return False
    return True


def recompute_all_blocking_flags(master: JDMasterContext) -> JDMasterContext:
    """
    Recompute is_blocking on every question in the master's clarification history.
    Call this after any answer is submitted.
    """
    for question in master.clarification_history:
        question.is_blocking = compute_is_blocking(question)
    return master


# ---------------------------------------------------------------------------
# Tier 1: BLOCKING Question Generators
# ---------------------------------------------------------------------------

def _detect_contradictions(
    master: JDMasterContext,
    existing_keys: set,
) -> List[ClarificationQuestionSchema]:
    """
    Detects logical contradictions:
    - A requirement marked MUST_HAVE but also negated=True.
    - Two requirements with conflicting priority signals for the same ekg_node_ids.
    """
    questions: List[ClarificationQuestionSchema] = []

    for item in master.requirements:
        if not isinstance(item, StructuredRequirement):
            continue

        # Contradiction: is_mandatory=True but negated=True
        if item.is_mandatory and item.negated:
            key = f"contradiction_mandatory_negated_{item.id[:8]}"
            if key not in existing_keys:
                questions.append(ClarificationQuestionSchema(
                    question_key=key,
                    category=QuestionCategory.CONTRADICTION,
                    priority=QuestionPriority.BLOCKING,
                    is_blocking=True,
                    field_target=f"requirements[id={item.id}].priority",
                    question_text=(
                        f"The requirement '{item.text[:120]}' appears both as mandatory "
                        f"and negated in the JD. Is this requirement actually required or explicitly excluded?"
                    ),
                    rationale=(
                        "The clause is marked is_mandatory=True but has negated=True. "
                        "This is a logical contradiction that must be resolved before candidate screening."
                    ),
                    suggested_options=["It IS required (remove negation)", "It is NOT required (exclude from must-haves)"],
                ))

    return questions


def _detect_unresolved_mandatory(
    master: JDMasterContext,
    existing_keys: set,
) -> List[ClarificationQuestionSchema]:
    """
    Flags StructuredRequirements with priority=UNRESOLVED that appear in
    critical requirement positions (they cannot be left ambiguous for screening).
    """
    questions: List[ClarificationQuestionSchema] = []
    unresolved = [
        item for item in master.requirements
        if isinstance(item, StructuredRequirement)
        and item.priority == RequirementPriority.UNRESOLVED
        and item.confidence.entity_match_confidence in {ConfidenceBand.HIGH, ConfidenceBand.MEDIUM}
    ]

    for i, item in enumerate(unresolved):
        key = f"unresolved_priority_{item.id[:8]}_{i}"
        if key not in existing_keys:
            questions.append(ClarificationQuestionSchema(
                question_key=key,
                category=QuestionCategory.TECHNICAL_SCOPE,
                priority=QuestionPriority.BLOCKING,
                is_blocking=True,
                field_target=f"requirements[id={item.id}].priority",
                question_text=(
                    f"The phrasing '{item.text[:120]}' was ambiguous — we could not determine "
                    f"if this is a MUST HAVE or a PREFERRED requirement. "
                    f"Is this requirement mandatory for all candidates?"
                ),
                rationale=(
                    "The clause uses ambiguous modal phrasing (e.g. 'ideally', 'experience with', "
                    "'knowledge of') that does not clearly indicate mandatory vs preferred status."
                ),
                suggested_options=["MUST HAVE — mandatory for all candidates", "PREFERRED — nice to have but not disqualifying"],
            ))

    return questions


# ---------------------------------------------------------------------------
# Tier 2: RECOMMENDED Question Generators
# ---------------------------------------------------------------------------

def _detect_low_confidence_requirements(
    master: JDMasterContext,
    existing_keys: set,
) -> List[ClarificationQuestionSchema]:
    """
    Flags requirements where entity_match_confidence=LOW, meaning the EKG
    could not confidently identify what technology/domain was being referenced.
    Non-blocking: has a fallback (use raw text for screening if unanswered).
    """
    questions: List[ClarificationQuestionSchema] = []
    low_conf = [
        item for item in master.requirements
        if isinstance(item, StructuredRequirement)
        and item.confidence.entity_match_confidence == ConfidenceBand.LOW
        and item.priority in {RequirementPriority.MUST_HAVE, RequirementPriority.PREFERRED}
    ]

    for i, item in enumerate(low_conf):
        key = f"low_confidence_entity_{item.id[:8]}_{i}"
        if key not in existing_keys:
            questions.append(ClarificationQuestionSchema(
                question_key=key,
                category=QuestionCategory.TECHNICAL_SCOPE,
                priority=QuestionPriority.RECOMMENDED,
                is_blocking=False,
                field_target=f"requirements[id={item.id}].ekg_node_ids",
                question_text=(
                    f"We could not precisely identify the technology or tool referenced in: "
                    f"'{item.text[:120]}'. "
                    f"Could you clarify what specific technology, framework, or domain is meant?"
                ),
                rationale=(
                    "Low entity match confidence means the EKG cannot confidently link this "
                    "requirement to a known technology. Clarification improves candidate scoring accuracy."
                ),
                suggested_options=[],
            ))

    return questions


def _detect_uninterpreted_responsibilities(
    master: JDMasterContext,
    existing_keys: set,
) -> List[ClarificationQuestionSchema]:
    """
    Flags responsibilities where the EKG matched entities but interpretation
    confidence is LOW — meaning the downstream activities are uncertain.
    Non-blocking: the raw responsibility text is still usable for screening.
    """
    questions: List[ClarificationQuestionSchema] = []
    for resp in master.responsibilities:
        if (
            resp.matched_entities
            and resp.interpretation_status == InterpretationStatus.NOT_INTERPRETED
            and resp.confidence.interpretation_confidence in {ConfidenceBand.LOW, ConfidenceBand.UNKNOWN}
        ):
            key = f"uninterpreted_responsibility_{resp.id[:8]}"
            if key not in existing_keys:
                entity_names = ", ".join(e.canonical_name for e in resp.matched_entities[:3])
                questions.append(ClarificationQuestionSchema(
                    question_key=key,
                    category=QuestionCategory.ROLE_ALIGNMENT,
                    priority=QuestionPriority.RECOMMENDED,
                    is_blocking=False,
                    field_target=f"responsibilities[id={resp.id}].interpretation_status",
                    question_text=(
                        f"The responsibility '{resp.raw_statement[:120]}' involves {entity_names}. "
                        f"What specific activities or depth of expertise should candidates demonstrate for this responsibility?"
                    ),
                    rationale=(
                        "The EKG matched known entities but could not derive specific activity requirements "
                        "at sufficient confidence. TA input will improve screening specificity."
                    ),
                    suggested_options=[],
                ))

    return questions


# ---------------------------------------------------------------------------
# Tier 3: OPTIONAL Question Generators
# ---------------------------------------------------------------------------

def _detect_missing_metadata(
    master: JDMasterContext,
    existing_keys: set,
) -> List[ClarificationQuestionSchema]:
    """
    Generates OPTIONAL questions for missing Tier 3 metadata (team size, salary).
    These NEVER block finalization and are presented as quick intake chips in the UI.
    """
    questions: List[ClarificationQuestionSchema] = []
    ctx = master.job_context

    # Team size
    if ctx.team_size is None and not ctx.team_size_explicitly_unspecified:
        key = "org_metadata_team_size"
        if key not in existing_keys:
            questions.append(ClarificationQuestionSchema(
                question_key=key,
                category=QuestionCategory.ORG_METADATA,
                priority=QuestionPriority.OPTIONAL,
                is_blocking=False,
                field_target="job_context.team_size",
                question_text="What is the approximate team size for this role?",
                rationale=(
                    "Team size was not mentioned in the JD. Some candidates may prefer "
                    "specific team environments (small startup vs large engineering org)."
                ),
                suggested_options=["1-5 people", "6-15 people", "16-50 people", "50+ people", "Not specified"],
            ))

    # Salary range
    if ctx.salary_range is None and not ctx.salary_explicitly_unspecified:
        key = "compensation_salary_range"
        if key not in existing_keys:
            questions.append(ClarificationQuestionSchema(
                question_key=key,
                category=QuestionCategory.COMPENSATION_LOGISTICS,
                priority=QuestionPriority.OPTIONAL,
                is_blocking=False,
                field_target="job_context.salary_range",
                question_text="Is a salary range or compensation band available for this role?",
                rationale=(
                    "Salary range was not mentioned in the JD. This is optional context "
                    "that helps attract candidates and set screening expectations."
                ),
                suggested_options=["Yes, I can provide it", "Not disclosed", "Competitive / Market Rate"],
            ))

    return questions
