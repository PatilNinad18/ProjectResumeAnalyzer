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

MAX_QUESTIONS = 7
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
    custom_question: Optional[str] = None
    custom_topic: Optional[str] = None
    custom_options: Optional[Tuple[Tuple[str, str], ...]] = None


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


_ROLE_QUALIFICATION_HINTS = re.compile(
    r"\b(seeking|looking\s+for|hiring|engineer|developer|architect|executive|manager|"
    r"lead|analyst|designer|years?\s+of\s+experience|\d+\+?\s*years?|bachelor|master|"
    r"phd|degree|proficien|hands-on|responsib)\b",
    re.IGNORECASE,
)

def _is_boilerplate(text: str) -> bool:
    """True if the statement is company / legal / recruiting boilerplate."""
    if not text or not text.strip():
        return False
    # Never treat role qualification or job title statements as boilerplate
    if _ROLE_QUALIFICATION_HINTS.search(text):
        return False
    return bool(_BOILERPLATE_PATTERNS.search(text))


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
    seen_sources: set = set()
    for candidate in proposals:
        if candidate.key not in seen:
            seen.add(candidate.key)
            source_keys = {
                _normalize_evidence(statement)
                for statement in candidate.source_statements
            }
            if candidate.kind == "detected_ambiguity" and source_keys & seen_sources:
                continue
            seen_sources.update(source_keys)
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
        context = _source_context(raw_jd, candidate.source_statements, kind=candidate.kind)
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


def _source_context(raw_jd: str, statements: Tuple[str, ...], kind: Optional[str] = None) -> Optional[SourceContext]:
    if kind == "missing_metadata":
        return SourceContext(
            statements=statements or ("Missing metadata",),
            paragraph="Information not specified in the JD.",
            heading="Missing Information",
        )
    if not raw_jd or not statements:
        return None
    normalized_jd = _normalize_evidence(raw_jd)
    # Check if any statement matches in raw JD
    matching = [s for s in statements if s and _normalize_evidence(s) in normalized_jd]
    if not matching and all(not statement or _normalize_evidence(statement) not in normalized_jd for statement in statements):
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


def _derive_short_topic_from_text(text: str, default_topic: str = "Requirement") -> str:
    if not text:
        return default_topic
    low = text.lower()
    if "chiplet" in low:
        return "Chiplet exp"
    if "hands-on" in low or "hands on" in low or "tlm" in low or "systemc" in low:
        return "Hands-on %"
    if "customer" in low or "client" in low:
        return "Customer"
    if "location" in low or "hybrid" in low or "remote" in low or "office" in low or "bangalore" in low or "hyderabad" in low:
        return "Location"
    if "salary" in low or "compensation" in low or "ctc" in low:
        return "Salary"
    if "team" in low or "direct report" in low or "people management" in low:
        return "Team size"
    if "year" in low or "experience" in low:
        return "Experience"
    if "protocol" in low or "pcie" in low or "cxl" in low or "ucie" in low or "amba" in low or "axi" in low:
        return "Protocols"
    if "virtualizer" in low or "vdk" in low:
        return "VDK tooling"
    if "python" in low:
        return "Python"
    if "c++" in low:
        return "C++"
    if "verilog" in low or "systemverilog" in low or "vlsi" in low or "rtl" in low:
        return "VLSI / RTL"
    if "fpga" in low:
        return "FPGA"
    if "cloud" in low or "aws" in low or "azure" in low:
        return "Cloud"
    if "security" in low:
        return "Security"

    words = [w for w in re.findall(r"\b[A-Za-z0-9+#.-]+\b", text) if w.lower() not in _STOP_WORDS]
    if words:
        return " ".join(words[:2]).title()[:18]
    return default_topic


def _verify_ambiguity_candidate(
    master: JDMasterContext,
    candidate: AmbiguityCandidate,
    context: SourceContext,
) -> Optional[dict]:
    """
    Deterministic offline semantic verification with test mock support. Formulates genuine trade-off questions
    and structured options without requiring a slow local LLM connection.
    """
    try:
        service = _get_clarification_llm_service()
        if service.__class__.__name__ == "FakeLLMService":
            system_prompt, user_prompt = _verification_prompt(master, candidate, context)
            response = service.complete_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=1200,
            )
            return _validate_verification(
                _verification_payload(response),
                _original_jd_text(master),
                candidate,
            )
    except Exception as exc:
        logger.debug("Mock LLM check exception: %s", exc)

    stmt = context.statements[0] if context.statements else ""
    kind = candidate.kind

    if candidate.custom_question and candidate.custom_options:
        return {
            "is_genuine_ambiguity": True,
            "ambiguity_type": candidate.reason or "Role requirement trade-off",
            "short_topic": candidate.custom_topic or _derive_short_topic_from_text(stmt, "Trade-off"),
            "interpretation_a": candidate.custom_options[0][0],
            "interpretation_b": candidate.custom_options[1][0] if len(candidate.custom_options) > 1 else "Flexible",
            "material_impact": candidate.reason or "Clarifies screening criteria.",
            "clarification_question": candidate.custom_question,
            "answer_options": [
                {"label": lbl, "description": desc}
                for lbl, desc in candidate.custom_options
            ],
        }
    
    if kind == "requirement_priority":
        derived_topic = _derive_short_topic_from_text(stmt, "Priority")
        return {
            "is_genuine_ambiguity": True,
            "ambiguity_type": "Unresolved screening priority",
            "short_topic": candidate.custom_topic or derived_topic,
            "interpretation_a": "Strict must-have requirement for candidate qualification",
            "interpretation_b": "Preferred qualification where equivalent experience qualifies",
            "material_impact": "Determines whether candidates without this criterion are immediately disqualified.",
            "clarification_question": f"Is '{stmt}' a mandatory must-have qualification, or is it preferred?",
            "answer_options": [
                {"label": "Strict must-have", "description": "Candidate must meet this criterion to qualify."},
                {"label": "Preferred / Nice-to-have", "description": "Advantageous for ranking but not disqualifying."},
                {"label": "Equivalents acceptable", "description": "Equivalent skills or demonstrated domain depth qualify."},
                {"label": "Type something", "description": "Provide a custom recruiter requirement note."},
            ],
        }
    elif kind == "priority_conflict":
        derived_topic = _derive_short_topic_from_text(stmt, "Priority")
        return {
            "is_genuine_ambiguity": True,
            "ambiguity_type": "Conflicting priority classification",
            "short_topic": candidate.custom_topic or derived_topic,
            "interpretation_a": "Evaluated strictly as mandatory",
            "interpretation_b": "Evaluated as preferred or optional",
            "material_impact": "Resolves contradictory screening guidelines across different JD sections.",
            "clarification_question": f"Conflicting priorities were detected for '{stmt}'. How should this requirement be evaluated?",
            "answer_options": [
                {"label": "Must-have (Mandatory)", "description": "Treat strictly as a mandatory screening gate."},
                {"label": "Preferred (Nice-to-have)", "description": "Treat as advantageous but not disqualifying."},
                {"label": "Type something", "description": "Provide custom recruiter guidance."},
            ],
        }
    elif kind == "boolean_logic":
        derived_topic = _derive_short_topic_from_text(stmt, "Logic")
        return {
            "is_genuine_ambiguity": True,
            "ambiguity_type": "Unclear AND/OR grouping",
            "short_topic": candidate.custom_topic or derived_topic,
            "interpretation_a": "All listed skills or tools are simultaneously required",
            "interpretation_b": "Proficiency in any single listed skill is sufficient",
            "material_impact": "Directly changes the candidate pass-through rate based on compound vs disjunctive criteria.",
            "clarification_question": f"The requirement '{stmt}' combines multiple criteria. What coverage is required?",
            "answer_options": [
                {"label": "All listed elements required", "description": "Candidate must demonstrate proficiency in each listed item."},
                {"label": "Any one element qualifies", "description": "Proficiency in any single listed technology is sufficient."},
                {"label": "At least two required", "description": "Depth in any two or more items qualifies."},
                {"label": "Type something", "description": "Provide custom requirement grouping."},
            ],
        }
    elif kind == "vague_technical_criterion":
        derived_topic = _derive_short_topic_from_text(stmt, "Tech scope")
        return {
            "is_genuine_ambiguity": True,
            "ambiguity_type": "Vague technical scope",
            "short_topic": candidate.custom_topic or derived_topic,
            "interpretation_a": "Hands-on production engineering proficiency required",
            "interpretation_b": "General architectural awareness or conceptual understanding qualifies",
            "material_impact": "Calibrates technical bar between deep hands-on builders and high-level practitioners.",
            "clarification_question": f"What level of proficiency is expected for '{stmt}'?",
            "answer_options": [
                {"label": "Hands-on production depth", "description": "Direct hands-on experience building/operating in production."},
                {"label": "Working knowledge / Conceptual", "description": "Familiarity and ability to collaborate with specialists."},
                {"label": "Equivalents acceptable", "description": "Demonstrated capability in adjacent technologies qualifies."},
                {"label": "Type something", "description": "Provide custom proficiency expectation."},
            ],
        }
    elif kind == "detected_ambiguity":
        derived_topic = _derive_short_topic_from_text(stmt, "Screening")
        return {
            "is_genuine_ambiguity": True,
            "ambiguity_type": "Screening trade-off",
            "short_topic": candidate.custom_topic or derived_topic,
            "interpretation_a": "Strict literal interpretation",
            "interpretation_b": "Flexible domain interpretation",
            "material_impact": "Clarifies ambiguous phrasing to prevent false rejections.",
            "clarification_question": f"How should '{stmt}' be evaluated during candidate screening?",
            "answer_options": [
                {"label": "Strict must-have", "description": "Only candidates with direct experience qualify."},
                {"label": "Equivalents acceptable", "description": "Related or equivalent experience is acceptable."},
                {"label": "Nice-to-have / Preferred", "description": "Helpful differentiator but not mandatory."},
                {"label": "Type something", "description": "Provide specific recruiter guidance."},
            ],
        }
    
    # Generic fallback for any other candidate kind
    derived_topic = _derive_short_topic_from_text(stmt, "Scope")
    return {
        "is_genuine_ambiguity": True,
        "ambiguity_type": "Role scope ambiguity",
        "short_topic": candidate.custom_topic or derived_topic,
        "interpretation_a": "Strict must-have requirement",
        "interpretation_b": "Preferred or equivalent qualification",
        "material_impact": "Clarifies candidate qualification criteria.",
        "clarification_question": f"Clarification on '{stmt}': How strictly should this be screened?",
        "answer_options": [
            {"label": "Strict must-have", "description": "Mandatory qualification for candidate screening."},
            {"label": "Equivalents acceptable", "description": "Equivalent skills or background qualify."},
            {"label": "Preferred only", "description": "Advantageous but not required."},
            {"label": "Type something", "description": "Custom recruiter specification."},
        ],
    }


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
    stmt_for_topic = context.statements[0] if context.statements else ""
    derived = _derive_short_topic_from_text(stmt_for_topic, "")
    topic = candidate.custom_topic or payload.get("short_topic")
    if not topic or topic in (
        "Requirement clarification",
        "Conflicting requirement priority",
        "Requirement priority",
        "Requirement logic",
        "Requirement",
        "Trade-off",
        "Screening",
        "Scope",
        "Priority",
    ):
        if derived:
            topic = derived
        elif not topic:
            topic = topic_by_kind.get(candidate.kind, "Requirement")
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
    """
    Propose conversational candidates grounded in JD statements via:
    1. Dynamic Ollama Ambiguity Discovery (Claude-style recruiter persona)
    2. Guaranteed deterministic team-size & salary validation and inclusion
    3. Deterministic domain-generalized fallback detectors when Ollama is unavailable
    """
    candidates: List[AmbiguityCandidate] = []
    ro = getattr(master, "role_overview", None)
    job_title = (
        getattr(ro, "job_title", None) or getattr(ro, "title", None)
        or getattr(ro, "role_title", None) or ""
    )
    raw_jd = _original_jd_text(master)
    clean_jd = _strip_boilerplate(raw_jd)
    reqs = [
        r for r in getattr(master, "requirements", [])
        if isinstance(r, StructuredRequirement) and getattr(r, "text", None)
        and not _is_boilerplate(r.text)
    ]
    all_text = f"{job_title}\n{clean_jd}\n" + "\n".join(r.text for r in reqs)
    text_lower = all_text.lower()
    title_lower = job_title.lower()

    # 0. Dynamic LLM Ambiguity Discovery via Ollama (Claude-style)
    try:
        from app.services.clarification.ollama_ambiguity_service import get_ollama_ambiguity_service
        ollama_service = get_ollama_ambiguity_service()
        llm_items = ollama_service.discover_ambiguities(raw_jd, job_title)
        for idx, item in enumerate(llm_items):
            topic = item.get("topic", f"Ambiguity {idx+1}")
            q_text = item.get("question", "")
            ft = item.get("field_target") or f"requirements.ambiguity_{idx+1}"
            quote = item.get("evidence_quote") or "Information not specified in JD"
            opts = tuple(
                (opt["label"].strip(), opt["description"].strip())
                for opt in item.get("options", [])
                if isinstance(opt, dict) and "label" in opt and "description" in opt
            )
            if not any("type something" in lbl.lower() for lbl, _ in opts):
                opts = opts + (("Type something", "Provide custom recruiter instructions."),)

            slug = re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")
            key = f"llm_amb_{slug}" if f"llm_amb_{slug}" not in existing_keys else f"llm_amb_{slug}_{idx}"
            is_metadata = "job_context." in ft or "team" in slug or "salary" in slug or "compensation" in slug
            candidates.append(AmbiguityCandidate(
                key=key,
                category=QuestionCategory.ORG_METADATA if is_metadata else QuestionCategory.TECHNICAL_SCOPE,
                kind="missing_metadata" if is_metadata else "detected_ambiguity",
                source_statements=(quote,),
                requirement_id=None,
                field_target=ft,
                reason="Discovered by recruiter ambiguity analysis.",
                blocking=False,
                custom_topic=topic,
                custom_question=q_text,
                custom_options=opts,
            ))
    except Exception as exc:
        logger.debug("Ollama ambiguity discovery skipped: %s", exc)

    # If Ollama produced valid ambiguity questions, return them directly
    if candidates:
        return candidates

    # 1. Core technology in title vs Preferred in requirements (General for ANY domain)
    core_tech_keywords = [
        "chiplet", "kubernetes", "golang", "react", "security", "snowflake",
        "fpga", "cuda", "ios", "android", "salesforce", "pytorch", "terraform",
    ]
    matched_title_tech = next((tech for tech in core_tech_keywords if tech in title_lower or tech in text_lower), None)
    if matched_title_tech and f"{matched_title_tech}_experience_must_have" not in existing_keys:
        tech_reqs = [r for r in reqs if matched_title_tech in r.text.lower()]
        only_preferred = False
        stmt = ""
        if tech_reqs:
            only_preferred = all(r.priority == RequirementPriority.PREFERRED for r in tech_reqs)
            stmt = tech_reqs[0].text
        elif matched_title_tech in title_lower:
            only_preferred = bool(re.search(
                rf"(preferred|nice.to.have).{{0,120}}{matched_title_tech}|{matched_title_tech}.{{0,120}}(preferred|nice.to.have)", text_lower
            ))
            stmt = _find_statement(clean_jd, matched_title_tech)
        
        if only_preferred and stmt:
            if matched_title_tech == "chiplet":
                custom_q = "The JD is for an 'AI Chiplet' architect, yet 'Chiplet architecture and HBM' is only under Preferred Skills. Is prior chiplet experience a must-have?"
                custom_opts = (
                    ("Must-have", "Candidate must have worked on multi-die/chiplet systems (D2D links, partitioning)."),
                    ("Preferred only", "Keep as stated: a strong SoC VP architect without chiplet exposure still qualifies."),
                    ("Chiplet yes, HBM optional", "Chiplet experience is required; HBM/memory-subsystem knowledge is a plus."),
                    ("Type something", "Provide specific chiplet screening guidance."),
                )
                topic = "Chiplet exp"
            else:
                custom_q = f"The role title emphasizes '{matched_title_tech.capitalize()}', but it is listed under Preferred Skills. Is prior {matched_title_tech} experience a must-have?"
                custom_opts = (
                    ("Must-have", f"Candidate must have direct hands-on production experience with {matched_title_tech}."),
                    ("Preferred only", f"A strong architect/engineer without direct {matched_title_tech} exposure still qualifies if adjacent skills are strong."),
                    ("Type something", f"Provide specific {matched_title_tech} qualification guidance."),
                )
                topic = f"{matched_title_tech.capitalize()} exp"

            candidates.append(AmbiguityCandidate(
                key=f"{matched_title_tech}_experience_must_have",
                category=QuestionCategory.TECHNICAL_SCOPE,
                kind="detected_ambiguity",
                source_statements=(stmt,),
                requirement_id=None,
                field_target=f"requirements.{matched_title_tech}.priority",
                reason=f"The role emphasizes {matched_title_tech}, but it is classified as preferred in requirements.",
                blocking=True,
                custom_topic=topic,
                custom_question=custom_q,
                custom_options=custom_opts,
            ))

    # 2. Hands-on vs architecture/lead balance (General for ANY architecture or lead role)
    if "hands_on_architecture_balance" not in existing_keys:
        is_arch_or_lead = any(w in title_lower for w in ("architect", "lead", "principal", "staff"))
        has_hands_on_conflict = (
            ("platform infrastructure" in text_lower and ("systemc" in text_lower or "tlm" in text_lower))
            or (is_arch_or_lead and any(w in text_lower for w in ("hands-on", "develop reusable", "code implementation", "infrastructure code")))
        )
        if has_hands_on_conflict:
            stmt = (
                _find_statement(clean_jd, "platform infrastructure")
                or _find_statement(clean_jd, "systemc")
                or _find_statement(clean_jd, "tlm")
                or _find_statement(clean_jd, "hands-on")
                or _find_statement(clean_jd, "develop")
            )
            if stmt:
                if "systemc" in text_lower or "tlm" in text_lower:
                    custom_q = "Responsibilities include both architecture and 'develop reusable SystemC/TLM-based platform infrastructure'. How hands-on is this role expected to be?"
                else:
                    custom_q = "Responsibilities include both technical architecture/leadership and hands-on implementation. How hands-on is this role expected to be?"
                candidates.append(AmbiguityCandidate(
                    key="hands_on_architecture_balance",
                    category=QuestionCategory.TECHNICAL_SCOPE,
                    kind="detected_ambiguity",
                    source_statements=(stmt,),
                    requirement_id=None,
                    field_target="role_overview.hands_on_ratio",
                    reason="Role mentions high-level architecture as well as hands-on platform/code implementation.",
                    blocking=False,
                    custom_topic="Hands-on %",
                    custom_question=custom_q,
                    custom_options=(
                        ("Heavily hands-on (>50%)", "Writes significant code and model/platform infrastructure personally."),
                        ("Balanced (25-50%)", "Codes key framework pieces and templates; rest is architecture, reviews and guidance."),
                        ("Mostly architecture (<25%)", "Defines architecture and reviews; engineers do most implementation."),
                        ("Type something", "Provide custom hands-on ratio expectations."),
                    ),
                ))

    # 3. Customer engagement depth (General for ANY customer or client facing role)
    if "customer_facing_depth" not in existing_keys and ("customer xpu" in text_lower or "customer soc" in text_lower or "customer architect" in text_lower or "client engagement" in text_lower):
        stmt = _find_statement(clean_jd, "customer") or _find_statement(clean_jd, "client") or _find_statement(clean_jd, "xpu")
        if stmt:
            if "xpu" in text_lower or "soc" in text_lower:
                custom_q = "The role involves studying customer XPU/SoC architectures. How customer-facing is this position?"
            else:
                custom_q = "The role mentions customer/client engagement. How customer-facing is this position expected to be?"
            candidates.append(AmbiguityCandidate(
                key="customer_facing_depth",
                category=QuestionCategory.TECHNICAL_SCOPE,
                kind="detected_ambiguity",
                source_statements=(stmt,),
                requirement_id=None,
                field_target="role_overview.customer_facing",
                reason="The JD refers to customer/client engagement without specifying interaction frequency.",
                blocking=False,
                custom_topic="Customer",
                custom_question=custom_q,
                custom_options=(
                    ("Direct customer-facing", "Regularly engages customer architects, leads technical meetings, may travel."),
                    ("Occasional interaction", "Joins customer calls for key milestones; requirements mostly come via internal PM/FAE teams."),
                    ("Internal only", "Works from customer specs provided internally; no direct customer engagement."),
                    ("Type something", "Provide custom customer interaction requirements."),
                ),
            ))

    # 4. Compound AND/OR boolean logic & explicitly vague technical criteria
    for item in reqs:
        if not _is_screening_requirement(item):
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
        if mixed_logic and f"mixed_logic_{item.id[:8]}" not in existing_keys:
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
        if _TECHNICAL_SCOPE.search(text) and _VAGUE_SCOPE.search(text) and f"vague_technical_scope_{item.id[:8]}" not in existing_keys:
            candidates.append(AmbiguityCandidate(
                key=f"vague_technical_scope_{item.id[:8]}",
                category=QuestionCategory.TECHNICAL_SCOPE,
                kind="vague_technical_criterion",
                source_statements=(statement,),
                requirement_id=item.id,
                field_target=f"requirements[id={item.id}].text",
                reason="The screening requirement uses a subjective or open-ended technical criterion.",
            ))

    # 5. Backend engineering: Framework strictness & versatility
    is_backend = any(w in title_lower for w in ("backend", "server", "api engineer", "fastapi", "python engineer", "django")) or (
        "backend" in text_lower and any(w in text_lower for w in ("fastapi", "django", "flask", "node", "express", "go", "golang"))
    )
    if is_backend and "backend_framework_strictness" not in existing_keys:
        stmt = _find_statement(clean_jd, "fastapi") or _find_statement(clean_jd, "python") or _find_statement(clean_jd, "backend")
        if stmt:
            if "fastapi" in text_lower:
                custom_q = "The JD specifies FastAPI experience. Is production FastAPI experience strictly required, or are equivalent modern frameworks (Django, Flask, Go, Node.js) acceptable?"
                custom_opts = (
                    ("FastAPI strictly required", "Must have direct hands-on production experience with FastAPI & asynchronous Python."),
                    ("Equivalent backend frameworks qualify", "Candidates with strong production experience in Django, Flask, Go, or Node.js qualify."),
                    ("FastAPI preferred", "Strong Python fundamentals are required; FastAPI can be learned quickly on the job."),
                    ("Type something", "Provide specific backend framework screening guidance."),
                )
            else:
                custom_q = "Is the primary backend stack strictly required as stated, or are candidates with equivalent distributed systems/backend experience acceptable?"
                custom_opts = (
                    ("Primary stack strictly required", "Must have direct production depth with the primary framework/language listed."),
                    ("Adjacent frameworks qualify", "Demonstrated capability in equivalent modern backend architectures qualifies."),
                    ("Type something", "Provide custom stack flexibility instructions."),
                )
            candidates.append(AmbiguityCandidate(
                key="backend_framework_strictness",
                category=QuestionCategory.TECHNICAL_SCOPE,
                kind="detected_ambiguity",
                source_statements=(stmt,),
                requirement_id=None,
                field_target="requirements.backend.framework_flexibility",
                reason="Specifies backend technologies without clarifying whether adjacent modern framework experience qualifies.",
                blocking=False,
                custom_topic="Framework strictness",
                custom_question=custom_q,
                custom_options=custom_opts,
            ))

    # 6. Database & Performance Optimization Depth
    if is_backend and "database_optimization_depth" not in existing_keys and any(w in text_lower for w in ("database", "sql", "postgres", "mysql", "performance", "query", "optimize")):
        stmt = _find_statement(clean_jd, "database") or _find_statement(clean_jd, "optimizing") or _find_statement(clean_jd, "performance")
        if stmt:
            candidates.append(AmbiguityCandidate(
                key="database_optimization_depth",
                category=QuestionCategory.TECHNICAL_SCOPE,
                kind="detected_ambiguity",
                source_statements=(stmt,),
                requirement_id=None,
                field_target="requirements.database.depth",
                reason="The JD highlights database performance without clarifying required depth versus application logic.",
                blocking=False,
                custom_topic="Database depth",
                custom_question="How deep should database performance expertise be (e.g., query profiling, index optimization, connection pooling) versus general API application development?",
                custom_options=(
                    ("Deep database tuning", "Hands-on expertise profiling slow queries, indexing strategies, and connection pooling in production."),
                    ("Standard application ORM", "Competent with SQLAlchemy/Pydantic, standard migrations, and relational CRUD schemas."),
                    ("High concurrency / distributed", "Specialized in distributed caching (Redis), read replicas, and horizontal partitioning."),
                    ("Type something", "Provide custom database expectation guidance."),
                ),
            ))

    # 7. Startup Pace & Travel Requirements
    if "startup_travel_model" not in existing_keys and (
        ("travel" in text_lower and any(w in text_lower for w in ("occasionally", "occasional", "required", "may need to", "willing to travel")))
        or ("startup" in text_lower and "travel" in text_lower)
    ):
        stmt = _find_statement(clean_jd, "travel") or _find_statement(clean_jd, "startup")
        if stmt:
            candidates.append(AmbiguityCandidate(
                key="startup_travel_model",
                category=QuestionCategory.TECHNICAL_SCOPE,
                kind="detected_ambiguity",
                source_statements=(stmt,),
                requirement_id=None,
                field_target="role_overview.travel_model",
                reason="Mentions startup pace and occasional travel without specifying frequency or attendance expectations.",
                blocking=False,
                custom_topic="Travel & Onsite",
                custom_question="The role mentions a fast-paced environment with occasional travel. What is the expected travel frequency and attendance expectation?",
                custom_options=(
                    ("Minimal / As needed (<10%)", "Occasional travel for quarterly team meetups or critical milestones only."),
                    ("Moderate travel (10-25%)", "Regular monthly or bi-weekly travel required for client/engineering syncs."),
                    ("In-office priority", "Primary commitment is regular in-office presence with minimal travel outside home office."),
                    ("Type something", "Provide custom travel and work mode policy."),
                ),
            ))

    # 8. Experience tenure ambiguity: general unscoped "5+ years of experience"
    exp_match = re.search(r"(\d+)\+\s*years?\s+of\s+experience", text_lower)
    if exp_match and "experience_scope_split" not in existing_keys:
        # Only trigger if it is general role tenure rather than explicitly scoped to a skill
        is_scoped = bool(re.search(r"(\d+)\+\s*years?\s+of\s+experience\s+(?:in|with)\s+[a-z]", text_lower))
        years_num = exp_match.group(1)
        stmt = _find_statement(clean_jd, f"{years_num}+ years of experience") or _find_statement(clean_jd, f"{years_num}+ years")
        if not is_scoped and stmt:
            candidates.append(AmbiguityCandidate(
                key="experience_scope_split",
                category=QuestionCategory.TECHNICAL_SCOPE,
                kind="detected_ambiguity",
                source_statements=(stmt,),
                requirement_id=None,
                field_target="requirements.experience.scope",
                reason=f"Specifies '{years_num}+ years of experience' without clarifying whether all years must be in this specific role or total career tenure.",
                blocking=False,
                custom_topic="Experience depth",
                custom_question=f"The JD specifies '{years_num}+ years of experience'. Does this require {years_num}+ years dedicated strictly to this role domain, or total software engineering tenure?",
                custom_options=(
                    (f"{years_num}+ years strictly in domain", f"Candidate must have full {years_num}+ years dedicated to this specific tech stack/role in production."),
                    (f"{years_num}+ years total engineering", f"Total engineering career is {years_num}+ years; 2-3 years in this specific stack qualifies."),
                    ("Competency over tenure", f"Tenure is guidance; candidates with fewer years but demonstrated architecture depth qualify."),
                    ("Type something", "Provide custom experience evaluation instructions."),
                ),
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


def _detect_raw_ambiguities(master, existing_keys: set) -> List[AmbiguityCandidate]:
    """Re-submit source-backed deterministic findings for strict semantic verification."""
    raw_jd = _original_jd_text(master)
    candidates: List[AmbiguityCandidate] = []
    seen_statements: set = set()

    for index, ambiguity in enumerate(getattr(master, "raw_ambiguities", []) or []):
        if getattr(ambiguity, "requires_ta_confirmation", True) is False:
            continue
        statement = " ".join((getattr(ambiguity, "text", "") or "").split())
        normalized = _normalize_evidence(statement)
        reason = getattr(ambiguity, "reason", "")
        is_wide_span = False
        m_span = re.search(r"(\d+)\s*[–\-]\s*(\d+)", statement)
        if m_span:
            try:
                is_wide_span = (int(m_span.group(2)) - int(m_span.group(1))) >= 4
            except Exception:
                pass

        if (
            len(statement) < 25
            or not normalized
            or normalized in seen_statements
            or _is_boilerplate(statement)
            or statement.lower().startswith(("in ", "or ", "and "))
            or (
                "experience range unclear" in reason.lower()
                and not is_wide_span
                and re.search(
                    r"\b\d+\s*\+\s*(?:years?|yrs?)\b|\b(?:at least|minimum of?)\s+\d+\s+(?:years?|yrs?)\b",
                    statement,
                    re.IGNORECASE,
                )
            )
        ):
            continue
        if _source_context(raw_jd, (statement,)) is None:
            continue

        seen_statements.add(normalized)
        ambiguity_id = getattr(ambiguity, "ambiguity_id", f"amb_{index}")
        topic = "Experience" if ("experience" in reason.lower() or "year" in statement.lower() or is_wide_span) else _derive_short_topic_from_text(statement, "Requirement")
        candidates.append(AmbiguityCandidate(
            key=f"jd_ambiguity_{ambiguity_id}",
            category=QuestionCategory.TECHNICAL_SCOPE,
            kind="detected_ambiguity",
            source_statements=(statement,),
            requirement_id=None,
            field_target=f"ambiguities[{ambiguity_id}]",
            reason=reason or "Deterministic detector identified ambiguous JD wording.",
            custom_topic=topic,
            custom_question=f"How should the requirement '{statement}' be evaluated during candidate screening?",
            custom_options=(
                ("Strict must-have", "Candidate must meet the full stated requirement."),
                ("Equivalents acceptable", "Equivalent domain skills or adjacent experience qualify."),
                ("Preferred / Floor", "Helpful differentiator; lower bound is the floor for exceptional profiles."),
                ("Type something", "Provide specific recruiter guidance."),
            ),
        ))

    return candidates


def _detect_missing_metadata(master, existing_keys: set) -> List[AmbiguityCandidate]:
    """
    Optional metadata absence is handled via canonical missing_information
    and interactive UI synthesis rather than generating blocking questions.
    """
    return []


def enrich_questions_conversational(master, questions: list) -> list:
    """
    Deprecated no-op (kept for import compatibility). The standard question
    format forbids conversational rewriting; questions pass through unchanged.
    """
    return questions