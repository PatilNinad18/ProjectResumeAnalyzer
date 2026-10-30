"""
clarification/engine.py — Evidence-grounded clarification question generator.

A question is generated only after the existing LLM service verifies that a
specific JD statement has materially different, unresolved interpretations
that affect candidate screening.

Never questioned: company/culture text, career-profile / recruiting
instructions, legal disclaimers, scam notices, generic team descriptions,
responsibilities, optional metadata (team size, salary, hybrid cadence), or
low EKG confidence on its own.

Every question uses one standard layout:
    short_topic    -> Topic
    rationale      -> "Topic / Original JD Statement / Issue Identified /
                       Reason for Clarification"
    question_text  -> one concise professional question (no intro)
    options        -> only options that fit the actual ambiguity

Lifecycle: zero open questions -> READY_FOR_REVIEW ("Analysis completed —
no clarification required."); the caller should then run spec generation.

Regeneration reconciles persisted history: obsolete / invalid generated
questions are removed (audit entry written), legitimate TA answers kept.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional, Sequence, Tuple

from app.schemas.master_context import (
    ClarificationOptionSchema,
    ClarificationQuestionSchema,
    ConfidenceBand,
    JDMasterContext,
    JDLifecycleStatus,
    QuestionCategory,
    QuestionPriority,
    QuestionStatus,
    RequirementPriority,
    StructuredRequirement,
)

logger = logging.getLogger("jd_agent.clarification.engine")

MAX_QUESTIONS = 5
Option = Tuple[str, str]  # (label, description)


@dataclass(frozen=True)
class AmbiguityCandidate:
    key: str
    category: QuestionCategory
    kind: str
    source_statements: Tuple[str, ...]
    requirement_id: Optional[str]
    field_target: str
    reason: str
    blocking: bool = False
    related_requirement_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceContext:
    statements: Tuple[str, ...]
    paragraph: str
    heading: str

# ---------------------------------------------------------------------------
# Boilerplate / non-screening text filter
# ---------------------------------------------------------------------------

_BOILERPLATE_PATTERNS = re.compile(
    r"""
    equal\s+opportunit | affirmative\s+action | background\s+check |
    reasonable\s+accommodation | \bdiversity\b | \binclusi(ve|on)\b |
    our\s+(culture|mission|values|vision|people|purpose) |
    about\s+(us|the\s+company|the\s+team) |
    how\s+we\s+work | when\s+you\s+join | you\s+become\s+one |
    global\s+team | team\s+of\s+(scientists|clinicians|professionals) |
    diverse\s+(ideas|perspectives|backgrounds|team) |
    each\s+individual | believe\s+in |
    we\s+(are|offer|value|believe|strive|provide|celebrate) |
    career\s+(growth|site|page|profile) | careers\s+(site|page) |
    \bscam\b | \bfraud(ulent)?\b | legitimate | recruiter |
    verify\s+(by|the|that) | employment\s+offer | offer\s+of\s+employment |
    disclaimer | privacy\s+policy | data\s+protection | terms\s+(of|and) |
    by\s+(applying|submitting) | talent\s+(community|network) |
    apply\s+(now|online|here) | send\s+(your\s+)?(resume|cv) |
    click\s+(to|here) | learn\s+more | \bjoin\s+(us|our\s+team)\b |
    \bbenefits?\s+(include|package|offered)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_VAGUE_SCOPE = re.compile(
    r"\b(strong|deep|extensive|proficient|expert(?:ise)?|familiarity|relevant|"
    r"related|appropriate|industry[- ]standard|etc\.?|and/or)\b",
    re.IGNORECASE,
)
_TECHNICAL_SCOPE = re.compile(
    r"\b(technical|technology|technologies|tool(?:s|chain)?|frameworks?|platforms?|"
    r"protocols?|simulators?|languages?|systems?|architecture|development|"
    r"experience|knowledge|skill(?:s)?)\b",
    re.IGNORECASE,
)
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "have",
    "in", "is", "it", "of", "on", "or", "that", "the", "their", "this", "to",
    "with", "work", "years", "year", "experience", "knowledge", "required",
    "preferred", "mandatory", "must", "should", "candidate", "candidates",
}

_SEGMENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _is_boilerplate(text: str) -> bool:
    """True if the statement is company / legal / recruiting boilerplate."""
    return bool(text) and bool(_BOILERPLATE_PATTERNS.search(text))


def _segments(text: str) -> List[str]:
    return [s.strip() for s in _SEGMENT_SPLIT.split(text or "") if s and s.strip()]


def _strip_boilerplate(text: str) -> str:
    return "\n".join(s for s in _segments(text) if not _is_boilerplate(s))


def _find_statement(text: str, phrase: str) -> str:
    low = phrase.lower()
    for seg in _segments(text):
        if low in seg.lower():
            return seg
    return phrase


def _clip(text: str, n: int = 240) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _is_screening_requirement(req: StructuredRequirement) -> bool:
    text = (getattr(req, "text", "") or "").strip()
    return bool(text) and not _is_boilerplate(text) and len(text.split()) <= 60


def _req_priority_is_explicit(req: "StructuredRequirement") -> bool:
    return req.priority in {
        RequirementPriority.MUST_HAVE,
        RequirementPriority.MANDATORY,
        RequirementPriority.PREFERRED,
    }


# ---------------------------------------------------------------------------
# Standard question builder
# ---------------------------------------------------------------------------

def _build_question(
    *,
    key: str,
    category: QuestionCategory,
    topic: str,
    jd_statement: str,
    issue: str,
    reason: str,
    question: str,
    options: Sequence[Option],
    field_target: str,
    priority: QuestionPriority = QuestionPriority.RECOMMENDED,
    is_blocking: bool = False,
) -> ClarificationQuestionSchema:
    rationale = (
        f"Topic: {topic}\n"
        f"Original JD Statement: \"{_clip(jd_statement)}\"\n"
        f"Issue Identified: {issue}\n"
        f"Reason for Clarification: {reason}"
    )
    return ClarificationQuestionSchema(
        question_key=key,
        category=category,
        priority=priority,
        is_blocking=is_blocking,
        field_target=field_target,
        short_topic=topic,
        question_text=question,
        rationale=rationale,
        structured_options=[
            ClarificationOptionSchema(label=l, description=d) for l, d in options
        ],
        suggested_options=[f"{l} — {d}" for l, d in options],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _is_open(q: ClarificationQuestionSchema) -> bool:
    if q.status in {QuestionStatus.ANSWERED, QuestionStatus.EXPLICITLY_UNSPECIFIED}:
        return False
    return getattr(q, "override_record", None) is None


def _is_resolved(q: ClarificationQuestionSchema) -> bool:
    return not _is_open(q)


def _looks_legacy_or_invalid(q: ClarificationQuestionSchema) -> bool:
    """Persisted questions generated by the old contextual/raw-ambiguity paths."""
    blob = f"{q.question_text or ''}\n{q.rationale or ''}"
    low = blob.lower()
    if "contextual / informational" in low or "informational phrasing" in low:
        return True
    key = (q.question_key or "").lower()
    if key.startswith(("contextual", "raw_ambig", "raw_")):
        return True
    return _is_boilerplate(q.question_text or "")


def _prune_obsolete_questions(
    master: JDMasterContext,
    valid_keys: set,
    actor: Optional[str],
) -> int:
    """
    Remove obsolete / invalid generated questions from active history.
      - Unanswered question no longer produced by the engine  -> removed.
      - Answered question that is legacy/boilerplate          -> removed from
        active history, but its key/status/answer go to the audit log.
      - Any other answered/overridden question                -> preserved.
    """
    kept: List[ClarificationQuestionSchema] = []
    removed_keys: List[str] = []
    archived_answers: List[dict] = []

    for q in master.clarification_history:
        if q.question_key in valid_keys:
            kept.append(q)
        elif _is_resolved(q) and not _looks_legacy_or_invalid(q):
            kept.append(q)  # legitimate TA answer, keep
        else:
            removed_keys.append(q.question_key)
            if _is_resolved(q):
                archived_answers.append({
                    "question_key": q.question_key,
                    "status": str(q.status),
                    "answer": getattr(q, "answer", None) or getattr(q, "answer_text", None),
                })

    if removed_keys:
        master.clarification_history = kept
        master.add_audit_entry(
            "clarification_obsolete_removed",
            f"Removed {len(removed_keys)} obsolete/invalid clarification question(s) on regeneration.",
            actor=actor,
            removed_keys=removed_keys,
            archived_answers=archived_answers,
        )
        logger.info("Pruned obsolete clarification questions: %s", removed_keys)
    return len(removed_keys)


def generate_clarification_questions(
    master: JDMasterContext,
    *,
    actor: Optional[str] = None,
) -> JDMasterContext:
    """
    Propose source-grounded candidates, semantically verify each using the
    configured LLM service, reconcile persisted questions, then set lifecycle.
    """
    proposals: List[AmbiguityCandidate] = []
    for detector in (
        _detect_contradictions,
        _detect_unresolved_mandatory,
        _detect_conversational_ambiguities,
        _detect_low_confidence_requirements,
        _detect_uninterpreted_responsibilities,
        _detect_contextual_ambiguities,
        _detect_raw_ambiguities,
        _detect_missing_metadata,
    ):
        proposals.extend(detector(master, set()))

    seen: set = set()
    unique: List[AmbiguityCandidate] = []
    for candidate in proposals:
        if candidate.key not in seen:
            seen.add(candidate.key)
            unique.append(candidate)

    raw_jd = _original_jd_text(master)
    persisted_by_key = {
        question.question_key: question
        for question in master.clarification_history
    }
    verified_questions: List[ClarificationQuestionSchema] = []
    for candidate in unique[:MAX_QUESTIONS]:
        persisted = persisted_by_key.get(candidate.key)
        if persisted is not None:
            verified_questions.append(persisted)
            continue
        context = _source_context(raw_jd, candidate.source_statements)
        if context is None:
            logger.warning(
                "Skipping clarification candidate without verifiable original-JD evidence: %s",
                candidate.key,
            )
            continue
        verification = _verify_ambiguity_candidate(master, candidate, context)
        if verification is None:
            continue
        question = _question_from_verification(candidate, context, verification)
        if question is not None:
            verified_questions.append(question)

    valid_keys = {q.question_key for q in verified_questions}
    valid_keys.update(
        q.question_key for q in master.clarification_history if _is_resolved(q)
    )
    _prune_obsolete_questions(master, valid_keys, actor)

    existing_keys = {q.question_key for q in master.clarification_history}
    new_questions = [
        q for q in verified_questions if q.question_key not in existing_keys
    ]
    master.clarification_history.extend(new_questions)
    recompute_all_blocking_flags(master)

    if new_questions:
        master.add_audit_entry(
            "clarification_generated",
            f"Generated {len(new_questions)} new clarification question(s).",
            actor=actor,
            question_count=len(new_questions),
            blocking_count=sum(1 for q in new_questions if q.is_blocking),
        )

    if any(_is_open(q) for q in master.clarification_history):
        master.lifecycle_status = JDLifecycleStatus.AWAITING_CLARIFICATION
    else:
        master.lifecycle_status = JDLifecycleStatus.READY_FOR_REVIEW
        master.add_audit_entry(
            "clarification_none_needed",
            "Analysis completed — no clarification required.",
            actor=actor,
        )
    return master


def compute_is_blocking(question: ClarificationQuestionSchema) -> bool:
    if question.priority != QuestionPriority.BLOCKING:
        return False
    if question.status in {QuestionStatus.ANSWERED, QuestionStatus.EXPLICITLY_UNSPECIFIED}:
        return False
    if question.override_record is not None:
        return False
    return True


def recompute_all_blocking_flags(master: JDMasterContext) -> JDMasterContext:
    for question in master.clarification_history:
        question.is_blocking = compute_is_blocking(question)
    return master


# ---------------------------------------------------------------------------
# Source-grounded semantic verification
# ---------------------------------------------------------------------------

def _original_jd_text(master: JDMasterContext) -> str:
    return (
        getattr(master, "raw_jd_text", "")
        or getattr(getattr(master, "extraction_metadata", None), "source_text", "")
        or ""
    )


def _normalize_evidence(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _source_value(source: object) -> str:
    return (
        getattr(source, "raw_text", "")
        or getattr(source, "text", "")
        or ""
    ).strip()


def _resolve_source_statement(master: JDMasterContext, requirement: StructuredRequirement) -> Optional[str]:
    raw_jd = _original_jd_text(master)
    if not raw_jd:
        return None
    sources = (
        getattr(requirement, "source", None),
        getattr(getattr(requirement, "provenance", None), "source_span", None),
    )
    for source in sources:
        candidate = _source_value(source)
        if candidate and _normalize_evidence(candidate) in _normalize_evidence(raw_jd):
            return candidate

    requirement_text = (requirement.text or "").strip()
    normalized_requirement = _normalize_evidence(requirement_text)
    if normalized_requirement and normalized_requirement in _normalize_evidence(raw_jd):
        return requirement_text
    for line in raw_jd.splitlines():
        normalized_line = _normalize_evidence(line)
        if normalized_line and normalized_line in normalized_requirement:
            return line.strip()
    return None


def _source_context(raw_jd: str, statements: Tuple[str, ...]) -> Optional[SourceContext]:
    if not raw_jd or not statements:
        return None
    normalized_jd = _normalize_evidence(raw_jd)
    if any(not statement or _normalize_evidence(statement) not in normalized_jd for statement in statements):
        return None

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", raw_jd) if part.strip()]
    matching = [
        paragraph for paragraph in paragraphs
        if all(_normalize_evidence(statement) in _normalize_evidence(paragraph) for statement in statements)
    ]
    paragraph = matching[0] if matching else "\n".join(statements)
    heading = ""
    first_line = paragraph.splitlines()[0].strip()
    if first_line.startswith("#") or first_line.endswith(":"):
        heading = first_line.lstrip("# ").rstrip(":").strip()
    else:
        before = raw_jd[:raw_jd.find(paragraph)] if paragraph in raw_jd else ""
        prior_lines = [line.strip() for line in before.splitlines() if line.strip()]
        for line in reversed(prior_lines[-8:]):
            if line.startswith("#") or line.endswith(":"):
                heading = line.lstrip("# ").rstrip(":").strip()
                break
    return SourceContext(statements=statements, paragraph=paragraph, heading=heading)


def _requirement_priority(requirement: StructuredRequirement) -> str:
    return str(getattr(requirement.priority, "value", requirement.priority))


def _priority_is_mandatory(requirement: StructuredRequirement) -> bool:
    return requirement.priority in {
        RequirementPriority.MUST_HAVE,
        RequirementPriority.MANDATORY,
    }


@lru_cache(maxsize=1)
def _get_clarification_llm_service():
    from app.services.llm_service import LLMService

    return LLMService()


def _verification_prompt(
    master: JDMasterContext,
    candidate: AmbiguityCandidate,
    context: SourceContext,
) -> Tuple[str, str]:
    requirements = [
        item for item in getattr(master, "requirements", [])
        if isinstance(item, StructuredRequirement)
        and (
            candidate.requirement_id is None
            or item.id in (candidate.requirement_id, *candidate.related_requirement_ids)
        )
    ]
    extracted = [
        {
            "text": item.text,
            "priority": _requirement_priority(item),
            "is_mandatory": item.is_mandatory,
            "confidence": item.confidence.model_dump(mode="json"),
        }
        for item in requirements
    ]
    system_prompt = (
        "You verify proposed job-description ambiguities for recruiter screening. "
        "Use only the original JD. Do not invent requirements or treat absent "
        "information as mandatory. Return one JSON object with exactly these "
        "fields: is_genuine_ambiguity (boolean), ambiguity_type (string), "
        "interpretation_a (string), interpretation_b (string), material_impact "
        "(string), source_evidence (string), clarification_question (string), "
        "answer_options (array of objects with label and description), and "
        "reasoning (string). Approve only when two plausible interpretations "
        "are both supported by the JD, materially different for candidate "
        "eligibility/screening/evaluation, and cannot be resolved from the full "
        "JD context. Otherwise set is_genuine_ambiguity=false. Quote exact JD "
        "evidence. Ask exactly one precise question that refers to that evidence. "
        "Answer options, when appropriate, must be relevant and mutually exclusive."
    )
    user_prompt = json.dumps(
        {
            "complete_original_jd": _original_jd_text(master),
            "exact_source_statements": list(context.statements),
            "surrounding_paragraph": context.paragraph,
            "section_heading": context.heading,
            "extracted_requirement_and_priority": extracted,
            "candidate_ambiguity": {
                "type": candidate.kind,
                "reason": candidate.reason,
            },
        },
        ensure_ascii=False,
    )
    return system_prompt, user_prompt


def _verification_payload(result: object) -> Optional[dict]:
    payload = getattr(result, "parsed_json", None)
    if isinstance(payload, dict):
        return payload
    raw_text = getattr(result, "raw_text", "")
    try:
        parsed = json.loads(raw_text)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _validate_verification(
    payload: Optional[dict],
    raw_jd: str,
    candidate: AmbiguityCandidate,
) -> Optional[dict]:
    if not isinstance(payload, dict) or payload.get("is_genuine_ambiguity") is not True:
        return None
    required_strings = (
        "ambiguity_type", "interpretation_a", "interpretation_b",
        "material_impact", "source_evidence", "clarification_question", "reasoning",
    )
    if any(not isinstance(payload.get(key), str) or not payload[key].strip() for key in required_strings):
        return None

    evidence = payload["source_evidence"].strip()
    normalized_evidence = _normalize_evidence(evidence)
    if normalized_evidence not in _normalize_evidence(raw_jd):
        logger.warning("Rejecting clarification verification with non-source evidence: %s", candidate.key)
        return None
    if any(_normalize_evidence(statement) not in normalized_evidence for statement in candidate.source_statements):
        logger.warning("Rejecting clarification verification that omits candidate evidence: %s", candidate.key)
        return None
    if _normalize_evidence(payload["interpretation_a"]) == _normalize_evidence(payload["interpretation_b"]):
        return None

    question = payload["clarification_question"].strip()
    if question.count("?") != 1:
        return None
    terms = {
        word for word in re.findall(r"[a-z0-9]+", normalized_evidence)
        if len(word) > 3 and word not in _STOP_WORDS
    }
    question_terms = set(re.findall(r"[a-z0-9]+", _normalize_evidence(question)))
    if terms and not terms.intersection(question_terms):
        return None

    options = payload.get("answer_options")
    if not isinstance(options, list) or len(options) < 2:
        return None
    normalized_labels: set = set()
    for option in options:
        if not isinstance(option, dict):
            return None
        label = option.get("label")
        description = option.get("description")
        if not isinstance(label, str) or not label.strip():
            return None
        if not isinstance(description, str) or not description.strip():
            return None
        normalized_label = _normalize_evidence(label)
        if normalized_label in normalized_labels:
            return None
        normalized_labels.add(normalized_label)
    return payload


def _verify_ambiguity_candidate(
    master: JDMasterContext,
    candidate: AmbiguityCandidate,
    context: SourceContext,
) -> Optional[dict]:
    system_prompt, user_prompt = _verification_prompt(master, candidate, context)
    try:
        service = _get_clarification_llm_service()
        if getattr(service, "provider", "ollama").lower() != "ollama":
            logger.error(
                "Clarification verification requires the configured Ollama provider; got %s",
                getattr(service, "provider", "unknown"),
            )
            return None
        response = service.complete_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=1200,
        )
    except Exception:
        logger.exception("Clarification semantic verification failed for %s", candidate.key)
        return None
    payload = _validate_verification(
        _verification_payload(response),
        _original_jd_text(master),
        candidate,
    )
    if payload is None:
        logger.info("Semantic verification rejected candidate %s", candidate.key)
    return payload


def _question_from_verification(
    candidate: AmbiguityCandidate,
    context: SourceContext,
    payload: dict,
) -> Optional[ClarificationQuestionSchema]:
    options = payload.get("answer_options", [])
    topic_by_kind = {
        "requirement_priority": "Requirement priority",
        "priority_conflict": "Conflicting requirement priority",
        "boolean_logic": "Requirement logic",
        "vague_technical_criterion": "Technical requirement scope",
        "mandatory_negated": "Contradictory requirement",
    }
    topic = topic_by_kind.get(candidate.kind, "Requirement clarification")
    issue = (
        f"{payload['ambiguity_type']}: {payload['interpretation_a']} versus "
        f"{payload['interpretation_b']}."
    )
    rationale = (
        f"Topic: {topic}\n"
        f"Original JD Statement: \"{_clip(' / '.join(context.statements))}\"\n"
        f"Issue Identified: {issue}\n"
        f"Reason for Clarification: {payload['material_impact'].strip()}"
    )
    return ClarificationQuestionSchema(
        question_key=candidate.key,
        category=candidate.category,
        priority=QuestionPriority.BLOCKING if candidate.blocking else QuestionPriority.RECOMMENDED,
        is_blocking=candidate.blocking,
        field_target=candidate.field_target,
        short_topic=topic,
        question_text=payload["clarification_question"].strip(),
        rationale=rationale,
        structured_options=[
            ClarificationOptionSchema(
                label=option["label"].strip(),
                description=option["description"].strip(),
            )
            for option in options
        ],
        suggested_options=[
            f"{option['label'].strip()} — {option['description'].strip()}"
            for option in options
        ],
    )


# ---------------------------------------------------------------------------
# Candidate detectors (propose only; semantic verification decides)
# ---------------------------------------------------------------------------

def _detect_contradictions(master, existing_keys: set) -> List[AmbiguityCandidate]:
    """Propose source-backed mandatory/negated or mandatory/preferred conflicts."""
    requirements = [
        item for item in getattr(master, "requirements", [])
        if isinstance(item, StructuredRequirement) and _is_screening_requirement(item)
    ]
    candidates: List[AmbiguityCandidate] = []
    for item in requirements:
        if not (item.is_mandatory and item.negated):
            continue
        statement = _resolve_source_statement(master, item)
        if statement:
            candidates.append(AmbiguityCandidate(
                key=f"contradiction_mandatory_negated_{item.id[:8]}",
                category=QuestionCategory.CONTRADICTION,
                kind="mandatory_negated",
                source_statements=(statement,),
                requirement_id=item.id,
                field_target=f"requirements[id={item.id}].priority",
                reason="The extracted requirement is simultaneously mandatory and negated.",
                blocking=True,
            ))

    for index, first in enumerate(requirements):
        if first.priority not in {RequirementPriority.MUST_HAVE, RequirementPriority.MANDATORY, RequirementPriority.PREFERRED}:
            continue
        for second in requirements[index + 1:]:
            if second.priority not in {RequirementPriority.MUST_HAVE, RequirementPriority.MANDATORY, RequirementPriority.PREFERRED}:
                continue
            if _priority_is_mandatory(first) == _priority_is_mandatory(second):
                continue
            first_terms = {
                term for term in re.findall(r"[a-z0-9]+", first.text.lower())
                if len(term) > 2 and term not in _STOP_WORDS
            }
            second_terms = {
                term for term in re.findall(r"[a-z0-9]+", second.text.lower())
                if len(term) > 2 and term not in _STOP_WORDS
            }
            shared = first_terms & second_terms
            if not shared or len(shared) / max(1, min(len(first_terms), len(second_terms))) < 0.4:
                continue
            first_statement = _resolve_source_statement(master, first)
            second_statement = _resolve_source_statement(master, second)
            if not first_statement or not second_statement:
                continue
            pair = "|".join(sorted((first.id, second.id)))
            digest = hashlib.sha1(pair.encode()).hexdigest()[:8]
            candidates.append(AmbiguityCandidate(
                key=f"conflicting_priority_{digest}",
                category=QuestionCategory.CONTRADICTION,
                kind="priority_conflict",
                source_statements=(first_statement, second_statement),
                requirement_id=first.id,
                field_target=f"requirements[id={first.id}].priority",
                reason=(
                    f"Overlapping requirements classify the same criterion as "
                    f"{_requirement_priority(first)} and {_requirement_priority(second)}."
                ),
                blocking=True,
                related_requirement_ids=(second.id,),
            ))
    return candidates


def _detect_unresolved_mandatory(master, existing_keys: set) -> List[AmbiguityCandidate]:
    """Propose unresolved extracted priorities only when original text is citable."""
    candidates: List[AmbiguityCandidate] = []
    for item in getattr(master, "requirements", []):
        if (
            not isinstance(item, StructuredRequirement)
            or item.priority != RequirementPriority.UNRESOLVED
            or not _is_screening_requirement(item)
        ):
            continue
        statement = _resolve_source_statement(master, item)
        if not statement:
            continue
        candidates.append(AmbiguityCandidate(
            key=f"unresolved_priority_{item.id[:8]}",
            category=QuestionCategory.TECHNICAL_SCOPE,
            kind="requirement_priority",
            source_statements=(statement,),
            requirement_id=item.id,
            field_target=f"requirements[id={item.id}].priority",
            reason="Extraction did not determine the screening priority of this source-backed requirement.",
            blocking=True,
        ))
    return candidates


def _legacy_detect_conversational_ambiguities(master, existing_keys: set) -> List[ClarificationQuestionSchema]:
    """
    Genuine scope ambiguities only (niche tooling, wide experience band,
    lead-role scope, protocol breadth, chiplet title vs preferred-only).
    Boilerplate is stripped before analysis. Hybrid cadence was removed:
    it does not affect resume-vs-JD scoring.
    """
    questions: List[ClarificationQuestionSchema] = []

    ro = getattr(master, "role_overview", None)
    job_title = (
        getattr(ro, "job_title", None) or getattr(ro, "title", None)
        or getattr(ro, "role_title", None) or ""
    )
    raw_jd = _strip_boilerplate(
        getattr(master, "raw_jd_text", None)
        or getattr(getattr(master, "extraction_metadata", None), "source_text", None)
        or ""
    )
    reqs = [
        r for r in getattr(master, "requirements", [])
        if isinstance(r, StructuredRequirement) and getattr(r, "text", None)
        and not _is_boilerplate(r.text)
    ]
    all_text = f"{job_title}\n{raw_jd}\n" + "\n".join(r.text for r in reqs)
    text_lower = all_text.lower()
    title_lower = job_title.lower()

    # 1. Niche tooling with no priority label --------------------------------
    niche_tools = [
        ("synopsys virtualizer", "Synopsys Virtualizer / VDK",
         "Cadence Helium, Arm Fast Models/FVP, Siemens Vista, or QEMU+SystemC co-sim"),
        ("virtualizer development kit", "Synopsys VDK", "equivalent virtual prototyping toolchains"),
        ("vdk", "Synopsys VDK", "equivalent virtual prototyping toolchains"),
        ("systemc/tlm", "SystemC/TLM", "equivalent transaction-level modelling frameworks"),
        ("questasim", "Questasim", "VCS, Xcelium, or other industry-standard simulators"),
        ("cadence helium", "Cadence Helium", "Synopsys VDK, Arm Fast Models, or similar tools"),
    ]
    if "vdk_tooling_strictness" not in existing_keys and "tooling_strictness" not in existing_keys:
        for phrase, tool, equiv in niche_tools:
            if not re.search(rf"\b{re.escape(phrase)}\b", text_lower):
                continue
            if any(phrase in r.text.lower() and _req_priority_is_explicit(r) for r in reqs):
                break
            snippet = " ".join(
                m.group() for m in re.finditer(
                    rf".{{0,80}}{re.escape(phrase)}.{{0,80}}", text_lower, re.DOTALL)
            )
            if re.search(r"\b(preferred|nice.to.have|required|mandatory|must.have)\b", snippet):
                break
            questions.append(_build_question(
                key="vdk_tooling_strictness",
                category=QuestionCategory.TECHNICAL_SCOPE,
                topic=f"{tool} tooling",
                jd_statement=_find_statement(all_text, phrase),
                issue=f"{tool} is named without stating whether it is mandatory or whether equivalents qualify.",
                reason="A strict tool match and an equivalent-tool match select very different resumes.",
                question=f"Is hands-on {tool} experience mandatory, or are equivalent tools acceptable?",
                options=[
                    ("Strict must-have", f"Only candidates with hands-on {tool} experience qualify."),
                    ("Equivalents acceptable", f"{equiv} count as equivalent."),
                    ("Strong preference", f"{tool} preferred; adjacent tools still considered."),
                ],
                field_target="requirements.tooling.specialised",
            ))
            break

    # 2. Wide experience band in a deep-specialisation domain ----------------
    if "experience_specialization_split" not in existing_keys:
        domains = ("semiconductor", "virtual platform", "systemc", "chiplet",
                   "soc design", "vlsi", "rtl design", "virtual prototyping")
        m = re.search(r"(\d+)\s*[–\-]\s*(\d+)\+?\s*(?:years?|yrs)", text_lower)
        domain_years_stated = re.search(
            r"\d+\+?\s*(?:years?|yrs)[^.\n]{0,40}\b(?:in|with|of)\b[^.\n]{0,40}"
            r"(?:systemc|virtual|chiplet|soc|vlsi|rtl|semiconductor)", text_lower)
        if m and any(d in text_lower for d in domains) and not domain_years_stated:
            lo, hi = int(m.group(1)), int(m.group(2))
            if hi - lo >= 5:
                fm = re.search(r"(\d+\s*[–\-]\s*\d+\+?\s*(?:years?|yrs))", all_text, re.IGNORECASE)
                exp_str = fm.group(1).strip() if fm else f"{lo}–{hi}+ years"
                questions.append(_build_question(
                    key="experience_specialization_split",
                    category=QuestionCategory.TECHNICAL_SCOPE,
                    topic="Experience",
                    jd_statement=_find_statement(all_text, exp_str),
                    issue="A wide experience band is given without saying how much must be in the core domain.",
                    reason="Resume scoring needs to know whether to weight total years or domain-specific years.",
                    question="How many of these years must be in the core specialisation?",
                    options=[
                        (f"{lo}+ total, deep domain", f"At least {lo} years, majority in the core specialisation."),
                        (f"{lo}+ total, general", f"{lo}+ years of engineering; domain depth judged from skills."),
                        (f"{hi}+ preferred", f"Target {hi}+ years; {lo} is the floor for outstanding profiles."),
                    ],
                    field_target="requirements.experience.domain_split",
                ))

    # 3. Lead/Architect title, people management unstated --------------------
    if "leadership_people_management" not in existing_keys:
        lead_terms = ("technical lead", "tech lead", "architect", "principal engineer",
                      "staff engineer", "engineering manager", "director of engineering")
        if any(t in title_lower for t in lead_terms) and not re.search(
            r"\b(direct\s+report|manage\s+(a\s+team|engineer|developer)|people\s+management"
            r"|no\s+(direct\s+)?report|individual\s+contributor|ic\s+role|report\s+to"
            r"|team\s+of\s+\d|will\s+manage)\b", text_lower):
            questions.append(_build_question(
                key="leadership_people_management",
                category=QuestionCategory.ROLE_ALIGNMENT,
                topic="Leadership scope",
                jd_statement=job_title,
                issue="The title implies leadership but the JD does not say whether people management is involved.",
                reason="Management experience is either a screening criterion or irrelevant, depending on the answer.",
                question="Does this role include direct people management?",
                options=[
                    ("Technical lead, no reports", "Sets technical direction; no formal management."),
                    ("Lead with direct reports", "Manages engineers directly."),
                    ("Lead now, manager later", "Starts as IC lead; management added as team scales."),
                ],
                field_target="role_overview.people_management",
            ))

    # 4. Protocol breadth (word-boundary match; 'chi' != 'chiplet') ----------
    if "protocol_coverage_depth" not in existing_keys:
        hs = ["pcie", "cxl", "ucie", "amba", "axi", "chi", "nvlink", "ccix"]
        matched = [p for p in hs if re.search(rf"\b{p}\b", text_lower)]
        if len(matched) >= 4 and not re.search(
            r"\b(any\s+one|at\s+least\s+one|one\s+or\s+more|either)\b", text_lower
        ):
            pstr = " / ".join(p.upper() for p in matched[:4])
            questions.append(_build_question(
                key="protocol_coverage_depth",
                category=QuestionCategory.TECHNICAL_SCOPE,
                topic="Protocol coverage",
                jd_statement=_find_statement(all_text, matched[0]),
                issue=f"Four or more protocols ({pstr}) are listed without saying how many are needed.",
                reason="Requiring all of them narrows the pool far more than requiring any one.",
                question="Must candidates have hands-on experience with all listed protocols?",
                options=[
                    ("All required", f"Hands-on experience with each of {pstr}."),
                    ("At least two", "Depth in at least two; others are a plus."),
                    ("Any one", "Experience with any single protocol qualifies."),
                ],
                field_target="requirements.protocols.coverage",
            ))

    # 5. Chiplet in title but only preferred in requirements -----------------
    if "chiplet_experience_must_have" not in existing_keys and "chiplet" in title_lower:
        chiplet_reqs = [r for r in reqs if "chiplet" in r.text.lower()]
        if chiplet_reqs:
            only_preferred = all(r.priority == RequirementPriority.PREFERRED for r in chiplet_reqs)
            stmt = chiplet_reqs[0].text
        else:
            only_preferred = bool(re.search(
                r"(preferred|nice.to.have).{0,120}chiplet|chiplet.{0,120}(preferred|nice.to.have)", text_lower
            )) and not re.search(
                r"(required|mandatory|must.have).{0,120}chiplet|chiplet.{0,120}(required|mandatory|must.have)",
                text_lower)
            stmt = _find_statement(all_text, "chiplet")
        if only_preferred:
            questions.append(_build_question(
                key="chiplet_experience_must_have",
                category=QuestionCategory.TECHNICAL_SCOPE,
                topic="Chiplet experience",
                jd_statement=stmt,
                issue=f"The title '{job_title}' centres on chiplets, but chiplet experience is listed only as preferred.",
                reason="The title and requirement priority disagree, which changes who passes screening.",
                question="Is chiplet experience mandatory for this role?",
                options=[
                    ("Must-have", "Candidate must have worked on multi-die/chiplet systems."),
                    ("Preferred only", "A strong SoC architect without chiplet exposure qualifies."),
                ],
                field_target="requirements.chiplet.priority",
            ))

    return questions


def _detect_conversational_ambiguities(master, existing_keys: set) -> List[AmbiguityCandidate]:
    """Propose mixed boolean logic and explicitly vague technical criteria only."""
    candidates: List[AmbiguityCandidate] = []
    for item in getattr(master, "requirements", []):
        if not isinstance(item, StructuredRequirement) or not _is_screening_requirement(item):
            continue
        statement = _resolve_source_statement(master, item)
        if not statement:
            continue
        text = item.text
        mixed_logic = bool(
            re.search(r"\band\s*/\s*or\b", text, re.IGNORECASE)
            or (
                re.search(r"\band\b", text, re.IGNORECASE)
                and re.search(r"\bor\b", text, re.IGNORECASE)
            )
        )
        if mixed_logic:
            candidates.append(AmbiguityCandidate(
                key=f"mixed_logic_{item.id[:8]}",
                category=QuestionCategory.TECHNICAL_SCOPE,
                kind="boolean_logic",
                source_statements=(statement,),
                requirement_id=item.id,
                field_target=f"requirements[id={item.id}].text",
                reason="The source requirement combines AND and OR relationships without clear grouping.",
                blocking=True,
            ))
            continue
        if _TECHNICAL_SCOPE.search(text) and _VAGUE_SCOPE.search(text):
            candidates.append(AmbiguityCandidate(
                key=f"vague_technical_scope_{item.id[:8]}",
                category=QuestionCategory.TECHNICAL_SCOPE,
                kind="vague_technical_criterion",
                source_statements=(statement,),
                requirement_id=item.id,
                field_target=f"requirements[id={item.id}].text",
                reason="The screening requirement uses a subjective or open-ended technical criterion.",
            ))
    return candidates


def _detect_low_confidence_requirements(master, existing_keys: set) -> List[AmbiguityCandidate]:
    """
    EKG matching confidence alone is never evidence of a clarification need.
    Wording-based candidates are handled by _detect_conversational_ambiguities.
    """
    return []


def _detect_uninterpreted_responsibilities(master, existing_keys: set) -> List[ClarificationQuestionSchema]:
    """Responsibilities are activities, not screening criteria: never questioned."""
    return []


def _detect_contextual_ambiguities(master, existing_keys: set) -> List[ClarificationQuestionSchema]:
    """Contextual/informational statements are preserved as context, never questioned."""
    return []


def _detect_raw_ambiguities(master, existing_keys: set) -> List[ClarificationQuestionSchema]:
    """Text-heuristic ambiguities are not questioned; see _detect_conversational_ambiguities."""
    return []


def _legacy_detect_missing_metadata(master, existing_keys: set) -> List[ClarificationQuestionSchema]:
    """
    Missing team size or salary range creates Tier 3 OPTIONAL, non-blocking questions
    for metadata intake as expected by lifecycle tests.
    """
    questions: List[ClarificationQuestionSchema] = []
    ctx = master.job_context

    if ctx.team_size is None and not ctx.team_size_explicitly_unspecified:
        key = "org_metadata_team_size"
        if key not in existing_keys:
            questions.append(_build_question(
                key=key,
                category=QuestionCategory.ORG_METADATA,
                topic="Team Size",
                jd_statement="Team size not mentioned",
                issue="Team size was not specified in the JD.",
                reason="Candidates may prefer specific team environments (small startup vs large org).",
                question="What is the approximate team size for this role?",
                options=[
                    ("1-5 people", "Small, tight-knit founding engineering team or squad."),
                    ("6-15 people", "Mid-sized dedicated product engineering pod."),
                    ("16-50 people", "Broad engineering organization."),
                    ("50+ people", "Large enterprise engineering division."),
                    ("Not specified", "Keep unspecified for candidate screening."),
                ],
                field_target="job_context.team_size",
                priority=QuestionPriority.OPTIONAL,
                is_blocking=False,
            ))

    if ctx.salary_range is None and not ctx.salary_explicitly_unspecified:
        key = "compensation_salary_range"
        if key not in existing_keys:
            questions.append(_build_question(
                key=key,
                category=QuestionCategory.COMPENSATION_LOGISTICS,
                topic="Compensation",
                jd_statement="Salary range not mentioned",
                issue="Salary range was not mentioned in the JD.",
                reason="Optional context that helps attract candidates and set expectations.",
                question="Is a salary range or compensation band available for this role?",
                options=[
                    ("Competitive / Market Rate", "Calibrated to prevailing competitive market compensation benchmarks."),
                    ("Yes, I can provide it", "Provide a specific compensation band or hourly rate."),
                    ("Not disclosed", "Confidential or discussed during interview rounds."),
                ],
                field_target="job_context.salary_range",
                priority=QuestionPriority.OPTIONAL,
                is_blocking=False,
            ))

    return questions


def _detect_missing_metadata(master, existing_keys: set) -> List[AmbiguityCandidate]:
    """Optional metadata absence is not ambiguity evidence and never prompts."""
    return []


def enrich_questions_conversational(master, questions: list) -> list:
    """
    Deprecated no-op (kept for import compatibility). The standard question
    format forbids conversational rewriting; questions pass through unchanged.
    """
    return questions