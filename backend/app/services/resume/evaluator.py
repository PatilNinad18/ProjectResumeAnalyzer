"""
Grounded Screening Evaluator (Phase 3)
=======================================
Evaluates a candidate resume against a Job Evaluation Specification v2.

Design principles:
  1. GROUNDED ONLY: Every MET or PARTIALLY_MET claim MUST have a verbatim
     evidence quote extracted directly from the resume text.
  2. NOT_EVIDENCED ≠ NOT_MET: Absence of evidence is not proof of absence.
     NOT_EVIDENCED triggers an interview verification checkpoint.
  3. DETERMINISTIC SCORING: Dynamic weight normalization prevents division-by-zero
     when a JD has zero must-haves, zero preferred qualifications, or no tenure spec.
  4. MATCH TIER GUARDRAILS: A high score can still be capped to POTENTIAL_MATCH
     if any must-have is NOT_EVIDENCED.

Usage:
    from app.services.resume.evaluator import evaluate_candidate
    result = evaluate_candidate(resume_text, spec_v2_canonical_json)
"""
from __future__ import annotations

import logging
import math
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from app.services.resume.evidence import ResumeEvidence, is_assessable

logger = logging.getLogger("jd_agent.evaluator")


# ---------------------------------------------------------------------------
# Score weight constants
# ---------------------------------------------------------------------------
WEIGHT_MUST_HAVE_BASE = 0.70
WEIGHT_PREFERRED_BASE = 0.20
WEIGHT_TENURE_BASE    = 0.10

SCORE_MET           = 1.0
SCORE_PARTIALLY_MET = 0.5
SCORE_NOT_EVIDENCED = 0.0
_STATUS_WEIGHTS = {
    "MET": SCORE_MET,
    "PARTIALLY_MET": SCORE_PARTIALLY_MET,
    "NOT_EVIDENCED": SCORE_NOT_EVIDENCED,
}
NO_EVALUATION_CRITERIA = "NO_EVALUATION_CRITERIA_DEFINED"

# Thresholds
STRONG_MATCH_THRESHOLD    = 80
POTENTIAL_MATCH_THRESHOLD = 60


# ---------------------------------------------------------------------------
# Evidence extraction helpers
# ---------------------------------------------------------------------------

def _clean_requirements(items: List[str]) -> List[str]:
    """
    Filter out non-requirement noise from canonical_json specification:
    - Section headers: 'Mandatory Requirements', 'Experience and Qualification', etc.
    - Clarification rubric options: 'Working knowledge / Conceptual: ...', 'Equivalents acceptable: ...', etc.
    - Pure tenure strings: 'Experience:** 2–4 years' (evaluated separately by tenure scorer)
    - JD intro overview sentences: 'We are looking for a Data Analyst...'
    """
    JUNK_HEADERS = {
        "mandatory requirements", "must have requirements", "must-have requirements",
        "preferred requirements", "key requirements", "qualifications",
        "experience and qualification", "skills required", "job responsibilities",
        "preferred qualifications", "requirements", "overview", "about the role",
        "role overview", "technical requirements", "general requirements"
    }
    RUBRIC_LABELS = {
        "working knowledge / conceptual", "equivalents acceptable", "all listed elements required",
        "any one element qualifies", "at least two required", "strict must-have", "preferred only",
        "hands-on production depth", "strict", "nice-to-have", "explicitly unspecified", "clarification",
    }
    cleaned: List[str] = []
    seen: set = set()
    for req in items:
        r = req.strip()
        if not r:
            continue
        clean_hdr = re.sub(r"^#+\s+|[*_\x60]", "", r).strip().lower().rstrip(":")
        if clean_hdr in JUNK_HEADERS:
            continue
        if clean_hdr.partition(":")[0].strip() in RUBRIC_LABELS:
            continue
        # Pure tenure string e.g. "Experience: 2-4 years"
        if re.match(r"^(?:experience|tenure)\s*[:*–-]*\s*\d+.*years?$", clean_hdr):
            continue
        # Intro blurb
        if clean_hdr.startswith("we are looking for") and "experience" in clean_hdr:
            continue
        if not is_assessable(r):
            continue
        norm_key = " ".join(clean_hdr.split())
        if norm_key in seen:
            continue
        seen.add(norm_key)
        cleaned.append(r)
    return cleaned


# ---------------------------------------------------------------------------
# Tenure scoring
# ---------------------------------------------------------------------------

def _score_tenure(
    candidate_years: Optional[float],
    required_years: Optional[float],
) -> Tuple[float, float]:
    """
    Returns (tenure_score [0.0-1.0], active_tenure_base_weight).
    If no required years specified in JD, returns (0.0, 0.0) so the weight
    slot is deactivated (not counted in denominator).
    """
    if not required_years or required_years <= 0:
        return 0.0, 0.0
    if not candidate_years or candidate_years <= 0:
        return 0.0, WEIGHT_TENURE_BASE
    score = min(1.0, candidate_years / required_years)
    return score, WEIGHT_TENURE_BASE


# ---------------------------------------------------------------------------
# Spec v2 requirement extraction
# ---------------------------------------------------------------------------

_GENERAL_TENURE = re.compile(
    r"(?:experience\s*:\s*)?(?:(?:must have|minimum(?: of)?|at least)\s+)?"
    r"(?:\d+(?:\.\d+)?(?:\+|\s*(?:[-–—]|to)\s*\d+(?:\.\d+)?)?\s*years?"
    r"(?:\s+or more)?(?:\s+of)?\s*)?"
    r"(?:(?:total|overall|professional|work)\s+)?(?:experience)?(?:\s+(?:required|minimum))?",
    re.IGNORECASE,
)


def _extract_requirements_from_spec(spec_json: Dict[str, Any]) -> Tuple[
    List[str], List[str], Optional[float]
]:
    """
    Extract must-have requirements, preferred qualifications, and minimum years
    from a canonical_json Specification v2 structure.

    Handles canonical must_have_requirements, preferred_requirements, and
    conventional_requirements.experience, plus legacy JSON shapes:
      - { must_haves: [...], preferred_qualifications: [...], experience_requirements: {...} }
      - { requirements: { must_have: [...], preferred: [...] } }
      - { sections: { requirements: {...} } }
    """
    must_haves: List[str] = []
    preferred:  List[str] = []
    min_years:  Optional[float] = None

    def _flatten(items) -> List[str]:
        """Flatten list of strings or dicts with 'requirement'/'text'/'description' keys."""
        result = []
        for item in (items or []):
            if isinstance(item, str):
                result.append(item.strip())
            elif isinstance(item, dict):
                for key in ("requirement", "text", "description", "item", "value"):
                    if key in item and isinstance(item[key], str):
                        result.append(item[key].strip())
                        break
        return [r for r in result if r]

    # Shape 1: flat top-level keys
    if "must_haves" in spec_json:
        must_haves = _flatten(spec_json["must_haves"])
    if "must_have_requirements" in spec_json:
        must_haves = _flatten(spec_json["must_have_requirements"])
    if "preferred_qualifications" in spec_json:
        preferred = _flatten(spec_json["preferred_qualifications"])
    if "preferred" in spec_json:
        preferred = _flatten(spec_json["preferred"])
    if "preferred_requirements" in spec_json:
        preferred = _flatten(spec_json["preferred_requirements"])

    # Shape 2: nested requirements dict
    if "requirements" in spec_json and isinstance(spec_json["requirements"], dict):
        req_block = spec_json["requirements"]
        if not must_haves:
            must_haves = _flatten(req_block.get("must_have") or req_block.get("must_haves") or [])
        if not preferred:
            preferred  = _flatten(req_block.get("preferred") or req_block.get("preferred_qualifications") or [])

    # Shape 3: nested in sections
    if "sections" in spec_json and isinstance(spec_json["sections"], dict):
        sections = spec_json["sections"]
        for sec_key in ("requirements", "must_haves", "qualifications"):
            if sec_key in sections and isinstance(sections[sec_key], dict):
                sec = sections[sec_key]
                if not must_haves:
                    must_haves = _flatten(sec.get("must_have") or sec.get("must_haves") or [])
                if not preferred:
                    preferred  = _flatten(sec.get("preferred") or sec.get("preferred_qualifications") or [])

    # Total resume tenure can satisfy only an overall experience minimum.
    conventional = spec_json.get("conventional_requirements") or {}
    experience = conventional.get("experience") if isinstance(conventional, dict) else None
    tenure_descriptions = set()
    for item in experience if isinstance(experience, list) else []:
        if not isinstance(item, dict) or item.get("priority", "MUST_HAVE") not in ("MUST_HAVE", "MANDATORY"):
            continue
        if item.get("explicit_or_derived") == "derived":
            continue
        description = str(item.get("description") or "").strip().rstrip(".")
        if not description or not _GENERAL_TENURE.fullmatch(description):
            continue
        try:
            years = float(item.get("min_years"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(years) and years > 0:
            min_years = max(min_years or 0.0, years)
            tenure_descriptions.add(description.casefold())

    if tenure_descriptions:
        must_haves = [req for req in must_haves if req.strip().rstrip(".").casefold() not in tenure_descriptions]

    # Legacy overall tenure fields.
    for key in ("experience_requirements", "experience", "seniority"):
        if min_years is not None:
            break
        exp_block = spec_json.get(key)
        if isinstance(exp_block, dict):
            for yr_key in ("minimum_years", "min_years", "years_required", "required_years"):
                if yr_key in exp_block:
                    try:
                        min_years = float(exp_block[yr_key])
                    except (TypeError, ValueError):
                        pass
            break
        elif isinstance(exp_block, (int, float)):
            min_years = float(exp_block)

    # Fallback: check top-level for min_years
    if min_years is None:
        for yr_key in ("minimum_years", "min_years", "years_of_experience", "required_years"):
            if yr_key in spec_json:
                try:
                    min_years = float(spec_json[yr_key])
                except (TypeError, ValueError):
                    pass

    return _clean_requirements(must_haves), _clean_requirements(preferred), min_years


# ---------------------------------------------------------------------------
# Interview question synthesis
# ---------------------------------------------------------------------------

def _generate_interview_question(requirement: str, status: str, evidence_quote: Optional[str]) -> str:
    """
    Generate a targeted interviewer question for a NOT_EVIDENCED or PARTIALLY_MET requirement.
    """
    if status == "NOT_EVIDENCED":
        return (
            f"The extracted resume does not substantiate: \"{requirement[:120]}\". "
            "Ask for relevant examples, dates, or credentials."
        )
    else:  # PARTIALLY_MET
        snippet = f" (found: \"{evidence_quote[:80]}...\")" if evidence_quote else ""
        return (
            f"Partial evidence found for: \"{requirement[:120]}\"{snippet}. "
            "Ask which parts they can evidence and what they personally did."
        )


# ---------------------------------------------------------------------------
# Red flag detection
# ---------------------------------------------------------------------------

def _detect_red_flags(
    parsed_profile: Dict[str, Any],
    resume_text: str,
) -> List[str]:
    """
    Detect anomalies in the candidate's resume:
    - Tenure gaps > 6 months between consecutive jobs
    - Very short stints (< 6 months) at multiple companies
    - No work history detected
    - Suspiciously inflated title vs experience
    """
    flags: List[str] = []
    work_history = parsed_profile.get("work_history", [])

    if not work_history:
        flags.append("No verifiable work history sections detected in resume.")
        return flags

    # Sort by start date and check gaps
    dated = []
    for entry in work_history:
        if entry.get("start_date") and entry.get("end_date"):
            try:
                s = date.fromisoformat(entry["start_date"])
                e = date.fromisoformat(entry["end_date"])
                dated.append((s, e, entry.get("title", "Unknown role")))
            except ValueError:
                pass

    dated.sort(key=lambda x: x[0])
    for i in range(1, len(dated)):
        prev_end   = dated[i - 1][1]
        curr_start = dated[i][0]
        gap_months = (curr_start - prev_end).days / 30.44
        if gap_months > 6:
            flags.append(
                f"Employment gap of ~{gap_months:.0f} months detected between "
                f"'{dated[i-1][2]}' and '{dated[i][2]}'."
            )

    # Short stints (< 6 months)
    short_stints = [e for e in work_history if isinstance(e.get("duration_years"), (int, float)) and 0 < e["duration_years"] < 0.5]
    if len(short_stints) >= 2:
        flags.append(
            f"{len(short_stints)} roles with tenure < 6 months detected — may indicate instability or contract work."
        )

    return flags


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------

def _compute_score(
    must_evals: List[Dict[str, Any]],
    pref_evals: List[Dict[str, Any]],
    tenure_score: float,
    tenure_base_weight: float,
) -> Tuple[Optional[int], Optional[str], Dict[str, Any]]:
    """
    Compute overall_score (0-100), match_tier, and score_breakdown.

    Uses dynamic weight normalization to handle edge cases:
    - JD with 0 must-haves: must-have weight slot deactivated
    - JD with 0 preferred: preferred weight slot deactivated
    - JD with no tenure specified: tenure weight slot deactivated
    - All weights zero: leave the evaluation unscored for review
    """
    n_must = len(must_evals)
    n_pref = len(pref_evals)

    # Active base weights
    w_must   = WEIGHT_MUST_HAVE_BASE if n_must > 0 else 0.0
    w_pref   = WEIGHT_PREFERRED_BASE if n_pref > 0 else 0.0
    w_tenure = tenure_base_weight

    w_total = w_must + w_pref + w_tenure

    if w_total == 0.0:
        # No evaluation criteria at all
        breakdown = {
            "must_have_subscore": 0.0,
            "preferred_subscore": 0.0,
            "tenure_subscore": 0.0,
            "active_weight_total": 0.0,
            "must_have_base_weight": 0.0,
            "preferred_base_weight": 0.0,
            "tenure_base_weight": 0.0,
            "warning": NO_EVALUATION_CRITERIA,
        }
        return None, None, breakdown

    # Category subscores (average of item weights)
    s_must   = (sum(e["score_weight"] for e in must_evals) / n_must) if n_must > 0 else 0.0
    s_pref   = (sum(e["score_weight"] for e in pref_evals) / n_pref) if n_pref > 0 else 0.0
    s_tenure = tenure_score

    # Normalized composite score
    raw = (w_must * s_must + w_pref * s_pref + w_tenure * s_tenure) / w_total
    overall_score = round(raw * 100)

    # --- Match tier with guardrail ---
    not_evidenced_must_haves = sum(
        1 for e in must_evals if e["status"] == "NOT_EVIDENCED"
    )

    if overall_score >= STRONG_MATCH_THRESHOLD and not_evidenced_must_haves == 0:
        match_tier = "STRONG_MATCH"
    elif overall_score >= STRONG_MATCH_THRESHOLD and not_evidenced_must_haves == 1:
        # Guardrail: cap at POTENTIAL_MATCH even with high score
        match_tier = "POTENTIAL_MATCH"
    elif overall_score >= POTENTIAL_MATCH_THRESHOLD and not_evidenced_must_haves <= 1:
        match_tier = "POTENTIAL_MATCH"
    elif overall_score >= POTENTIAL_MATCH_THRESHOLD and not_evidenced_must_haves <= 3:
        match_tier = "POTENTIAL_MATCH"
    else:
        match_tier = "NOT_A_FIT"

    breakdown = {
        "must_have_subscore":    round(s_must, 4),
        "preferred_subscore":    round(s_pref, 4),
        "tenure_subscore":       round(s_tenure, 4),
        "active_weight_total":   round(w_total, 4),
        "must_have_base_weight": w_must,
        "preferred_base_weight": w_pref,
        "tenure_base_weight":    w_tenure,
    }
    return overall_score, match_tier, breakdown


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def evaluate_candidate(
    resume_text: str,
    parsed_profile: Dict[str, Any],
    spec_canonical_json: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Main evaluation function.

    Args:
        resume_text:          Clean plain text from document_parser.parse_document()
        parsed_profile:       Structured dict from profiler.profile_resume()
        spec_canonical_json:  canonical_json from JobSpecificationVersion (the v2 spec)

    Returns a dict with keys matching CandidateEvaluation fields:
        overall_score, match_tier, must_haves_summary, preferred_summary,
        detailed_evaluations, validation_checkpoints, red_flags,
        tailored_interview_questions, score_breakdown
    """
    must_have_reqs, preferred_reqs, min_years = _extract_requirements_from_spec(spec_canonical_json)

    evidence = ResumeEvidence(resume_text, parsed_profile)
    guidance_by_requirement = {
        item["explicit_requirement"]: item["derived_interpretation"]
        for item in spec_canonical_json.get("requirement_interpretations") or []
        if isinstance(item, dict) and item.get("requirement_id") and item.get("explicit_requirement")
        and isinstance(item.get("derived_interpretation"), list)
    }

    def assess(requirement: str, category: str) -> dict[str, Any]:
        status, quotes, reasoning = evidence.assess(requirement, guidance_by_requirement.get(requirement, []))
        return {
            "requirement": requirement,
            "category": category,
            "status": status,
            "score_weight": _STATUS_WEIGHTS[status],
            "evidence_quote": quotes[0] if quotes else None,
            "evidence_quotes": quotes,
            "reasoning": reasoning,
        }

    must_evals = [assess(req, "must_have") for req in must_have_reqs]
    pref_evals = [assess(req, "preferred") for req in preferred_reqs]

    # --- Tenure scoring ---
    candidate_years = parsed_profile.get("total_experience_years") or 0.0
    tenure_score, tenure_base_weight = _score_tenure(candidate_years, min_years)

    # --- Composite score ---
    overall_score, match_tier, score_breakdown = _compute_score(
        must_evals, pref_evals, tenure_score, tenure_base_weight
    )
    if tenure_base_weight:
        score_breakdown["tenure_evidence"] = evidence.checked_quotes(
            [entry.get("date_text") for entry in evidence.work_history if entry.get("start_date") and entry.get("end_date")]
        )

    # --- Summaries ---
    def _summarize(evals: List[Dict]) -> Dict[str, int]:
        return {
            "total":          len(evals),
            "met":            sum(1 for e in evals if e["status"] == "MET"),
            "partially_met":  sum(1 for e in evals if e["status"] == "PARTIALLY_MET"),
            "not_evidenced":  sum(1 for e in evals if e["status"] == "NOT_EVIDENCED"),
        }

    must_haves_summary = _summarize(must_evals)
    preferred_summary  = _summarize(pref_evals)

    # --- Validation checkpoints & interview questions ---
    validation_checkpoints: List[Dict[str, str]] = []
    interview_questions: List[str] = []

    # Must-haves first (priority)
    for e in must_evals:
        if e["status"] in ("NOT_EVIDENCED", "PARTIALLY_MET"):
            question = _generate_interview_question(e["requirement"], e["status"], e["evidence_quote"])
            validation_checkpoints.append({
                "requirement":        e["requirement"],
                "status":             e["status"],
                "interview_question": question,
            })
            interview_questions.append(question)

    # Then preferred gaps (secondary)
    for e in pref_evals:
        if e["status"] == "NOT_EVIDENCED" and len(interview_questions) < 7:
            question = _generate_interview_question(e["requirement"], e["status"], e["evidence_quote"])
            interview_questions.append(question)

    # Cap at 5 interview questions
    interview_questions = interview_questions[:5]

    # --- Red flags ---
    red_flags = _detect_red_flags(parsed_profile, resume_text)

    return {
        "overall_score":               overall_score,
        "match_tier":                  match_tier,
        "must_haves_summary":          must_haves_summary,
        "preferred_summary":           preferred_summary,
        "detailed_evaluations":        must_evals + pref_evals,
        "validation_checkpoints":      validation_checkpoints,
        "red_flags":                   red_flags,
        "tailored_interview_questions": interview_questions,
        "score_breakdown":             score_breakdown,
    }
