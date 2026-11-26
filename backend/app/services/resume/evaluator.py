"""
Grounded Screening Evaluator (v2.1)
====================================
Evaluates a candidate resume against a Job Evaluation Specification v2.

Changes from v2.0:
  1. QUOTE VERIFICATION: Every MET/PARTIALLY_MET claim is verified to exist
     in parsed_text via verify_quote_in_text(). Hallucinated quotes are cleared
     and status is downgraded to NOT_EVIDENCED.
  2. SEARCHED KEYWORDS in every evaluation result (audit trail for NOT_EVIDENCED).
  3. PARSE QUALITY GATE: check_parse_quality() returns a structured dict; if
     the resume text is too short or garbled the caller sets PARSE_FAILED status.
  4. RECALIBRATED MET BAR: MET requires verifiable professional application
     (action verbs: designed, built, deployed, managed) rather than "production" only.
  5. PROMPT INJECTION SCANNER: scan_for_injection() flags suspicious hidden text.
  6. TIMELINE OBSERVATIONS: Report overlapping roles used for experience scoring.
  7. EVALUATOR PROVENANCE: returns engine/model/prompt/temp/seed in result.
  8. TIER THRESHOLDS updated: STRONG_MATCH >= 75 (was 80), NOT_A_FIT < 50 (was 60).

Design principles:
  1. GROUNDED ONLY: Every MET or PARTIALLY_MET claim MUST have a verbatim
     evidence quote verified present in the resume text.
  2. NOT_EVIDENCED ≠ NOT_MET: Absence of evidence is not proof of absence.
     NOT_EVIDENCED triggers an interview verification checkpoint.
  3. DETERMINISTIC SCORING: Dynamic weight normalization prevents division-by-zero.
  4. MATCH TIER GUARDRAILS: High score can be capped to POTENTIAL_MATCH if any
     must-have is NOT_EVIDENCED.
  5. NO AUTO-REJECTIONS: Tool provides advisory recommendations only.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import hashlib
import logging
import math
import re
import unicodedata
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from app.services.resume.evidence import ResumeEvidence, is_assessable
from app.services.resume.profiler import profile_resume

logger = logging.getLogger("jd_agent.evaluator")

# Evaluator provenance constants
EVALUATOR_ENGINE = "resume-evidence-v3"
PROMPT_VERSION   = "eval_v3"
TEMPERATURE      = 0.0
SEED             = 42

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

# Tier thresholds
STRONG_MATCH_THRESHOLD    = 75
POTENTIAL_MATCH_THRESHOLD = 50

# Action verbs indicating professional application (wider than "production")
_PROFESSIONAL_VERBS = re.compile(
    r"\b(?:designed|built|developed|deployed|implemented|managed|maintained|"
    r"architected|engineered|created|led|integrated|configured|operated|"
    r"optimized|automated|migrated|scaled|monitored|delivered|reduced|"
    r"increased|improved|launched|shipped|owned|drove|established|set up|"
    r"orchestrated|partitioned|indexed|authored|spearheaded|tuned|programmed|"
    r"refactored|containerized|provisioned|administered|streamlined|mentored|"
    r"debugged|tested|modernized|executed|collaborated|resolved|analyzed)\b",
    re.IGNORECASE,
)

# Known prompt injection patterns in resume text
_INJECTION_PATTERNS = [
    r"(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above|other|missing)?\s*(?:instructions?|directives?|rules?|criteria|prompts?|kafka|experience)",
    r"you\s+are\s+now\s+a",
    r"act\s+as\s+(?:a\s+)?(?:different|new|another|grading)",
    r"(?:rate|score|mark|grade|evaluate|award|treat)\s+(?:this\s+candidate|me|them|all\s+requirements)?\s*(?:as|with)?\s*(?:strong|100%|9[0-9]%|points|met)",
    r"output\s+(?:json\s+)?(?:with\s+)?strong_match",
    r"system\s+prompt",
    r"developer\s+message",
    r"<\s*(?:!--\s*)?(?:recruiter|system|assistant|user|directive)",
    r"OVERRIDE_(?:STATUS|SCORE)",
    r"\[(?:CRITICAL\s+)?(?:SYSTEM|EVALUATOR)\s+(?:UPDATE|DIRECTIVE|INSTRUCTION)",
    r"['\"]role['\"]\s*:\s*['\"]system['\"]",
    r"jailbreak",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


# ---------------------------------------------------------------------------
# Parse quality gate
# ---------------------------------------------------------------------------

def check_parse_quality(text: str) -> Dict[str, Any]:
    """
    Run the parse quality gate on extracted resume text.

    Returns a dict:
      { "passed": bool, "text_length": int, "word_count": int,
        "alpha_ratio": float, "failure_reason": str | null }

    Failure conditions (any one triggers PARSE_FAILED):
      - text_length < 150 characters
      - word_count < 30 words
      - alpha_ratio < 0.50 (binary/font noise from corrupted PDFs)
    """
    text_length = len(text)
    words = text.split()
    word_count = len(words)
    alpha_chars = sum(1 for c in text if c.isalpha())
    total_chars = max(len(text.replace(" ", "")), 1)
    alpha_ratio = round(alpha_chars / total_chars, 3)

    failure_reason: Optional[str] = None
    if text_length < 150:
        failure_reason = f"Extracted text too short ({text_length} chars). Likely a scanned image PDF."
    elif word_count < 30:
        failure_reason = f"Too few words extracted ({word_count}). Document may be image-only or corrupted."
    elif alpha_ratio < 0.50:
        failure_reason = f"Alpha character ratio too low ({alpha_ratio:.2f}). Likely binary/font noise."

    return {
        "passed":         failure_reason is None,
        "text_length":    text_length,
        "word_count":     word_count,
        "alpha_ratio":    alpha_ratio,
        "failure_reason": failure_reason,
    }


# ---------------------------------------------------------------------------
# Prompt injection scanner
# ---------------------------------------------------------------------------

def scan_for_injection(text: str) -> Optional[str]:
    """
    Scan resume text for prompt injection patterns.
    Returns the matched pattern string if found, None otherwise.
    """
    m = _INJECTION_RE.search(text)
    if m:
        return m.group(0)[:100]
    return None


# ---------------------------------------------------------------------------
# Blind screening / Anonymization
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?1[ .-]?(?:\(\d{3}\)|\d{3})[ .-]\d{3}[ .-]\d{4}"
    r"|(?:\(\d{3}\)|\d{3})[ .-]\d{3}[ .-]\d{4}|(?:\+91[ -]?)?\d{10})(?!\w)"
)
_LINK_RE  = re.compile(r"(?:https?://)?(?:www\.)?(?:linkedin\.com/(?:in|pub)/[A-Za-z0-9_\-\.]+|github\.com/[A-Za-z0-9_\-\.]+)", re.IGNORECASE)

_TECH_WHITELIST = {
    "python", "java", "c++", "c#", "ruby", "go", "rust", "sql", "html", "css",
    "react", "angular", "vue", "node", "flask", "django", "fastapi", "spring",
    "aws", "azure", "gcp", "docker", "kubernetes", "linux", "git", "github",
    "pandas", "numpy", "power", "bi", "snowflake", "spark", "hadoop", "excel",
    "data", "analyst", "engineer", "developer", "intern", "lead", "manager",
    "senior", "junior", "staff", "architect", "student", "technology", "systems",
}


def anonymize_resume(
    text: str,
    candidate_name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
) -> Tuple[str, Dict[str, str]]:
    """
    Mask personally identifiable information (PII) from resume text for blind screening.
    Preserves all technical evidence, work history dates, roles, and project accomplishments.

    Returns:
        (anonymized_text, redacted_entities_dict)
    """
    if not text:
        return "", {}

    redacted: Dict[str, str] = {}
    anon_text = text

    # 1. Mask Email
    if email:
        redacted["email"] = email
        anon_text = re.sub(re.escape(email), "[CANDIDATE_EMAIL]", anon_text, flags=re.IGNORECASE)
    for m in _EMAIL_RE.finditer(anon_text):
        em = m.group(0)
        redacted.setdefault("email", em)
        anon_text = anon_text.replace(em, "[CANDIDATE_EMAIL]")

    # 2. Mask Phone
    if phone and _PHONE_RE.fullmatch(phone.strip()):
        redacted["phone"] = phone
        anon_text = re.sub(re.escape(phone), "[CANDIDATE_PHONE]", anon_text, flags=re.IGNORECASE)
    for m in _PHONE_RE.finditer(anon_text):
        ph = m.group(0).strip()
        if len(re.sub(r"\D", "", ph)) >= 7:
            redacted.setdefault("phone", ph)
            anon_text = anon_text.replace(ph, "[CANDIDATE_PHONE]")

    # 3. Mask Social Links / Profiles
    for m in _LINK_RE.finditer(anon_text):
        link = m.group(0)
        redacted.setdefault("link", link)
        anon_text = anon_text.replace(link, "[PORTFOLIO_LINK]")

    # 4. Mask Candidate Name
    names_to_mask = []
    if candidate_name:
        names_to_mask.append(candidate_name.strip())
        parts = candidate_name.strip().split()
        if len(parts) >= 2:
            for part in parts:
                p_clean = part.strip(".,()[]'\"").lower()
                if len(p_clean) >= 3 and p_clean not in _TECH_WHITELIST:
                    names_to_mask.append(part.strip(".,()[]'\""))

    if not candidate_name:
        for line in anon_text.split("\n")[:3]:
            line_str = line.strip()
            if 2 <= len(line_str.split()) <= 4 and re.match(r"^[A-Za-z\s.\-']+$", line_str):
                names_to_mask.append(line_str)
                break

    for name in sorted(names_to_mask, key=len, reverse=True):
        if len(name) >= 3 and name.lower() not in _TECH_WHITELIST:
            pattern = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
            anon_text = pattern.sub("[CANDIDATE_NAME]", anon_text)
            redacted.setdefault("name", name)

    return anon_text, redacted


# ---------------------------------------------------------------------------
# Quote verification
# ---------------------------------------------------------------------------

def _normalize_for_comparison(text: str) -> str:
    """Normalize text for fuzzy quote comparison: lowercase, collapse whitespace, strip punctuation."""
    text = unicodedata.normalize("NFKD", text)
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def verify_quote_in_text(quote: str, parsed_text: str) -> bool:
    """
    Verify that a claimed evidence quote actually exists in parsed_text.
    Strict anti-hallucination verification:
      1. Normalizes case, unicode, and punctuation.
      2. Direct substring match (exact verbatim quote).
      3. Handles ellipsis truncation (...).
      4. For short quotes (<= 3 words), requires exact contiguous substring.
      5. For longer quotes, requires ordered sequence similarity >= 0.82 in a local sliding window.
    """
    if not quote or not parsed_text:
        return False

    clean_quote = quote.strip()
    # Strip leading/trailing ellipsis or quotation marks
    clean_quote = re.sub(r"^[\s\"'“”‘’.…]+|[\s\"'“”‘’.…]+$", "", clean_quote)
    if not clean_quote:
        return False

    norm_quote = _normalize_for_comparison(clean_quote)
    norm_text  = _normalize_for_comparison(parsed_text)

    # 1. Exact direct substring match (fastest & strictest)
    if norm_quote in norm_text:
        return True

    quote_tokens = norm_quote.split()
    q_len = len(quote_tokens)
    if q_len == 0:
        return False

    # 2. Short quotes (<= 3 tokens): MUST be a direct contiguous substring
    if q_len <= 3:
        return norm_quote in norm_text

    text_tokens = norm_text.split()
    t_len = len(text_tokens)
    if t_len < q_len:
        # Check if text is a high-ratio match to the quote
        return SequenceMatcher(None, quote_tokens, text_tokens).ratio() >= 0.85

    # 3. Check for substantive key token presence
    stop = {"a", "an", "the", "in", "of", "for", "and", "or", "to", "with", "is", "was", "on", "at", "by"}
    substantive = [t for t in quote_tokens if t not in stop and len(t) > 2]
    if substantive:
        text_tokens_set = set(text_tokens)
        substantive_in_text = sum(1 for t in substantive if t in text_tokens_set)
        if substantive_in_text / len(substantive) < 0.65:
            return False

    # 4. Sliding window with ordered SequenceMatcher
    best_ratio = 0.0
    step = max(1, q_len // 4)

    candidate_starts = []
    first_key = substantive[0] if substantive else quote_tokens[0]
    for idx, tok in enumerate(text_tokens):
        if tok == first_key:
            candidate_starts.append(max(0, idx - 2))

    if not candidate_starts:
        candidate_starts = list(range(0, t_len - q_len + 1, step))

    for start in candidate_starts:
        for w_size in (q_len, q_len + 2, q_len - 2):
            if w_size <= 0:
                continue
            end = min(t_len, start + w_size)
            window = text_tokens[start:end]
            ratio = SequenceMatcher(None, quote_tokens, window).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
            if best_ratio >= 0.82:
                return True

    return False


# ---------------------------------------------------------------------------
# Evidence extraction helpers
# ---------------------------------------------------------------------------

def _clean_requirements(items: List[str]) -> List[str]:
    """
    Filter out non-requirement noise from canonical_json specification:
    section headers, clarification rubric options, pure tenure strings, intro blurbs.
    """
    JUNK_HEADERS = {
        "mandatory requirements", "must have requirements", "must-have requirements",
        "preferred requirements", "key requirements", "qualifications",
        "experience and qualification", "skills required", "job responsibilities",
        "preferred qualifications", "requirements", "overview", "about the role",
        "role overview", "technical requirements", "general requirements",
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
        if re.match(r"^(?:experience|tenure)\s*[:*–-]*\s*\d+.*years?$", clean_hdr):
            continue
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

    Sliding scale: score = min(1.0, candidate_years / required_years)
    If JD specifies no minimum years, weight slot is deactivated (0.0).
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
            preferred = _flatten(req_block.get("preferred") or req_block.get("preferred_qualifications") or [])

    # Shape 3: nested in sections
    if "sections" in spec_json and isinstance(spec_json["sections"], dict):
        sections = spec_json["sections"]
        for sec_key in ("requirements", "must_haves", "qualifications"):
            if sec_key in sections and isinstance(sections[sec_key], dict):
                sec = sections[sec_key]
                if not must_haves:
                    must_haves = _flatten(sec.get("must_have") or sec.get("must_haves") or [])
                if not preferred:
                    preferred = _flatten(sec.get("preferred") or sec.get("preferred_qualifications") or [])

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

def screening_criteria(spec_json: dict[str, Any]) -> list[dict[str, Any]]:
    must_haves, _, _ = _extract_requirements_from_spec(spec_json)
    return [
        {"requirement_id": item["requirement_id"], "text": item["requirement"], "critical": item.get("critical") is True}
        for item in spec_json.get("evidence_requirements") or []
        if isinstance(item, dict) and item.get("requirement_id")
        and item.get("priority") == "MUST_HAVE" and item.get("requirement") in must_haves
    ]


def _generate_interview_question(requirement: str, status: str, evidence_quote: Optional[str]) -> str:
    """
    Generate a targeted interviewer question for a NOT_EVIDENCED or PARTIALLY_MET requirement.
    Questions are phrased to explore depth, not to assume a skills gap.
    """
    req_short = requirement[:120]
    if status == "NOT_EVIDENCED":
        return (
            f"The extracted resume does not substantiate: \"{requirement[:120]}\". "
            "Ask for relevant examples, dates, or credentials."
        )
    else:  # PARTIALLY_MET
        snippet = f" (found: \"{evidence_quote[:80]}...\")".rstrip("...") + "\"" if evidence_quote else ""
        return (
            f"Partial evidence found for: \"{requirement[:120]}\"{snippet}. "
            "Ask which parts they can evidence and what they personally did."
        )


# ---------------------------------------------------------------------------
# Timeline observations (neutral, NOT scoring penalties)
# ---------------------------------------------------------------------------

def _build_timeline_observations(
    parsed_profile: Dict[str, Any],
) -> List[str]:
    """
    Build neutral timeline observations for the recruiter's interview prep.

    Report overlapping dates used to calculate experience.
    """
    observations: List[str] = []
    work_history = parsed_profile.get("work_history", [])

    if not work_history:
        return observations

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

    # Note concurrent roles (overlapping dates) — not suspicious, just informational
    for i in range(len(dated)):
        for j in range(i + 1, len(dated)):
            if dated[j][0] < dated[i][1]:
                observations.append(
                    f"Concurrent roles detected: '{dated[i][2]}' and '{dated[j][2]}' overlap in timeline. "
                    f"May indicate freelance/contract work or multiple part-time positions."
                )
                break  # Only note once per role

    return observations


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

    w_must   = WEIGHT_MUST_HAVE_BASE if n_must > 0 else 0.0
    w_pref   = WEIGHT_PREFERRED_BASE if n_pref > 0 else 0.0
    w_tenure = tenure_base_weight

    w_total = w_must + w_pref + w_tenure

    if w_total == 0.0:
        breakdown = {
            "must_have_subscore":   0.0,
            "preferred_subscore":   0.0,
            "tenure_subscore":      0.0,
            "active_weight_total":  0.0,
            "must_have_base_weight": 0.0,
            "preferred_base_weight": 0.0,
            "tenure_base_weight": 0.0,
            "warning": NO_EVALUATION_CRITERIA,
        }
        return None, None, breakdown

    s_must   = (sum(e["score_weight"] for e in must_evals) / n_must) if n_must > 0 else 0.0
    s_pref   = (sum(e["score_weight"] for e in pref_evals) / n_pref) if n_pref > 0 else 0.0
    s_tenure = tenure_score

    raw = (w_must * s_must + w_pref * s_pref + w_tenure * s_tenure) / w_total
    overall_score = round(raw * 100)

    critical_to_verify = [e["requirement"] for e in must_evals if e.get("critical") and e["status"] != "MET"]
    has_unevidenced_must = any(e["status"] == "NOT_EVIDENCED" for e in must_evals)

    if overall_score >= STRONG_MATCH_THRESHOLD and not has_unevidenced_must and not critical_to_verify:
        match_tier = "STRONG_MATCH"
    elif overall_score >= POTENTIAL_MATCH_THRESHOLD:
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
        "critical_to_verify":   critical_to_verify,
    }
    return overall_score, match_tier, breakdown


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def evaluate_candidate(
    resume_text: str,
    parsed_profile: Dict[str, Any],
    spec_canonical_json: Dict[str, Any],
    blind_screening: bool = False,
) -> Dict[str, Any]:
    """
    Main evaluation function.

    Args:
        resume_text:          Clean plain text from document_parser.parse_document()
        parsed_profile:       Structured dict from profiler.profile_resume()
        spec_canonical_json:  canonical_json from JobSpecificationVersion (the v2 spec)
        blind_screening:      When True, masks candidate names, emails, phones, and social links
                              before running evaluation.

    Returns a dict with keys matching CandidateEvaluation fields plus provenance metadata:
        overall_score, match_tier, must_haves_summary, preferred_summary,
        detailed_evaluations, validation_checkpoints, timeline_observations,
        tailored_interview_questions, score_breakdown,
        quote_verification_pass, injection_warning, provenance
    """
    # --- Blind screening anonymization ---
    eval_text = resume_text
    if blind_screening:
        eval_text, _ = anonymize_resume(
            resume_text,
            candidate_name=parsed_profile.get("candidate_name") if parsed_profile else None,
            email=parsed_profile.get("email") if parsed_profile else None,
            phone=parsed_profile.get("phone") if parsed_profile else None,
        )

    # --- Prompt injection scan (security check on untrusted input) ---
    injection_match = scan_for_injection(eval_text)
    if injection_match:
        logger.warning("The extracted resume text contains a possible instruction directed at a screening system.")

    must_have_reqs, preferred_reqs, min_years = _extract_requirements_from_spec(spec_canonical_json)
    evidence = ResumeEvidence(eval_text, profile_resume(eval_text) if blind_screening else parsed_profile)
    original_text = " ".join(resume_text.split())
    critical_requirements = {item["text"] for item in screening_criteria(spec_canonical_json) if item["critical"]}
    guidance_by_requirement = {
        item["explicit_requirement"]: item["derived_interpretation"]
        for item in spec_canonical_json.get("requirement_interpretations") or []
        if isinstance(item, dict) and item.get("requirement_id") and item.get("explicit_requirement")
        and isinstance(item.get("derived_interpretation"), list)
    }

    any_quote_failed = False

    def assess(requirement: str, category: str) -> dict[str, Any]:
        nonlocal any_quote_failed
        status, quotes, reasoning = evidence.assess(requirement, guidance_by_requirement.get(requirement, []))
        verified = all(" ".join(quote.split()) in original_text for quote in quotes) and bool(quotes)
        quote_verified = verified if status != "NOT_EVIDENCED" else None
        if quote_verified is False:
            any_quote_failed = True
            status, quotes, reasoning = "NOT_EVIDENCED", [], "A supporting excerpt could not be verified in the original resume."
        return {
            "requirement": requirement,
            "category": category,
            "status": status,
            "score_weight": _STATUS_WEIGHTS[status],
            "evidence_quote": quotes[0] if quotes else None,
            "evidence_quotes": quotes,
            "quote_verified": quote_verified,
            "critical": category == "must_have" and requirement in critical_requirements,
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
            "total":         len(evals),
            "met":           sum(1 for e in evals if e["status"] == "MET"),
            "partially_met": sum(1 for e in evals if e["status"] == "PARTIALLY_MET"),
            "not_evidenced": sum(1 for e in evals if e["status"] == "NOT_EVIDENCED"),
        }

    must_haves_summary = _summarize(must_evals)
    preferred_summary  = _summarize(pref_evals)

    # --- Validation checkpoints & interview questions ---
    validation_checkpoints: List[Dict[str, str]] = []
    interview_questions: List[str] = []

    for e in must_evals:
        if e["status"] in ("NOT_EVIDENCED", "PARTIALLY_MET"):
            question = _generate_interview_question(e["requirement"], e["status"], e["evidence_quote"])
            validation_checkpoints.append({
                "requirement":        e["requirement"],
                "status":             e["status"],
                "interview_question": question,
            })
            interview_questions.append(question)

    for e in pref_evals:
        if e["status"] == "NOT_EVIDENCED" and len(interview_questions) < 7:
            question = _generate_interview_question(e["requirement"], e["status"], e["evidence_quote"])
            interview_questions.append(question)

    interview_questions = interview_questions[:5]

    # --- Timeline observations (neutral, not penalties) ---
    timeline_observations = _build_timeline_observations(parsed_profile)

    # Injection warning appended as observation (not a scoring penalty)
    if injection_match:
        timeline_observations.insert(0,
            "The extracted text contains a possible instruction directed at a screening system. Review the source document."
        )

    # --- Evaluator provenance ---
    provenance = {
        "evaluator_engine": EVALUATOR_ENGINE,
        "model_name":       None,
        "model_version":    None,
        "prompt_version":   PROMPT_VERSION,
        "temperature":      TEMPERATURE,
        "seed":             SEED,
    }

    return {
        "overall_score":               overall_score,
        "match_tier":                  match_tier,
        "must_haves_summary":          must_haves_summary,
        "preferred_summary":           preferred_summary,
        "detailed_evaluations":        must_evals + pref_evals,
        "validation_checkpoints":      validation_checkpoints,
        "timeline_observations":       timeline_observations,
        "tailored_interview_questions": interview_questions,
        "score_breakdown":             score_breakdown,
        "quote_verification_pass":     not any_quote_failed,
        "injection_warning":           injection_match,
        "provenance":                  provenance,
    }
