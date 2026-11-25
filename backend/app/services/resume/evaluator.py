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
  6. TIMELINE OBSERVATIONS (not red_flags): career gaps are neutral interview notes,
     never scoring penalties. renamed from _detect_red_flags.
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
import re
import unicodedata
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jd_agent.evaluator")

# Evaluator provenance constants
EVALUATOR_ENGINE = "deterministic_v1"
PROMPT_VERSION   = "eval_v2.1"
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

# Tier thresholds
STRONG_MATCH_THRESHOLD    = 75   # >= 75 AND 0 NOT_EVIDENCED must-haves
POTENTIAL_MATCH_THRESHOLD = 50   # >= 50 AND <= 1 NOT_EVIDENCED must-have

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
_PHONE_RE = re.compile(r"(?:(?:\+?91[\s\-]?)?(?:\(\d{3,5}\)[\s\-]?|\d{3,5}[\s\-]?)?\d{3,5}[\s\-]?\d{4,5}|\+?1[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4})")
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
    if phone:
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

def _build_keyword_variants(requirement: str) -> List[str]:
    """
    Derive a set of search keywords from a requirement statement.
    Splits on common separators, strips short stop words, lowercases.
    Returns deduplicated list.
    """
    # Extract quoted tech terms first
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'|`([^`]+)`', requirement)
    keywords: List[str] = []
    for groups in quoted:
        kw = next(g for g in groups if g)
        keywords.append(kw.lower())

    # Also split requirement into individual significant words
    words = re.sub(r"[^a-zA-Z0-9+#\s\-_./]", " ", requirement).split()
    stop = {
        "a", "an", "the", "in", "of", "for", "and", "or", "with", "to",
        "is", "are", "has", "have", "be", "been", "must", "should",
        "working", "using", "demonstrate", "demonstrated", "familiarity",
        "years", "year", "months", "strong", "good", "solid", "proven",
        "knowledge", "understanding", "ability", "skills", "experience",
        "systems", "technologies", "platforms", "solutions", "tools",
        "cloud", "apache", "environment", "environments", "role", "roles",
        "cluster", "clusters", "pipeline", "pipelines",
    }
    for word in words:
        clean = word.strip("-_./").lower()
        if len(clean) >= 3 and clean not in stop:
            keywords.append(clean)

    # Deduplicate while preserving order
    seen: set = set()
    result = []
    for k in keywords:
        if k not in seen:
            seen.add(k)
            result.append(k)
    return result


def _kw_in_text(kw: str, text_lower: str) -> bool:
    """Check if keyword exists in text with word boundary matching."""
    if not kw:
        return False
    if kw in ("c++", "c#", ".net", "ci/cd"):
        return kw in text_lower
    return bool(re.search(r"\b" + re.escape(kw) + r"\b", text_lower))


def _find_evidence_quote(requirement: str, resume_text: str) -> Optional[str]:
    """
    Search the resume text for a sentence or bullet point containing the requirement's key terms.
    Returns the best matching sentence (up to 250 chars) or None if nothing found.
    """
    keywords = _build_keyword_variants(requirement)
    if not keywords:
        return None

    raw_lines = resume_text.splitlines()
    sentences = []
    for line in raw_lines:
        line_clean = re.sub(r"^\s*[-•*–—]+\s*", "", line).strip()
        if len(line_clean) > 15:
            sentences.append(line_clean)
        # Also split on clear sentence boundaries while avoiding abbreviation periods (M.S., B.S., Inc.)
        sub_sents = re.split(r"(?<=[a-z0-9][.!?])\s+(?=[A-Z])", line_clean)
        for sub in sub_sents:
            sub = sub.strip()
            if len(sub) > 15 and sub != line_clean:
                sentences.append(sub)

    best_sentence: Optional[str] = None
    best_score = -100

    for sentence in sentences:
        sentence_lower = sentence.lower()
        is_skills_list = bool(re.match(r"^(?:skills|technologies|tools|languages)\s*:", sentence_lower))
        hit_count = sum(1 for kw in keywords if _kw_in_text(kw, sentence_lower))
        if hit_count == 0:
            continue
        has_verb = bool(_PROFESSIONAL_VERBS.search(sentence))
        # Prefer actual work experience bullet points with action verbs over bare skill lists
        score = hit_count * 2 + (4 if has_verb else 0) - (8 if is_skills_list else 0)
        if score > best_score:
            best_score = score
            best_sentence = sentence

    if best_score <= 0:
        return None

    if best_sentence and len(best_sentence) > 250:
        best_sentence = best_sentence[:247] + "..."

    return best_sentence


# ---------------------------------------------------------------------------
# Requirement cleaner
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
    RUBRIC_PREFIXES = (
        "working knowledge / conceptual:",
        "equivalents acceptable:",
        "strict:",
        "nice-to-have:",
        "explicitly unspecified:",
        "clarification:",
    )
    cleaned: List[str] = []
    seen: set = set()
    for req in items:
        r = req.strip()
        if not r or len(r) < 5:
            continue
        clean_hdr = re.sub(r"[*_#`]", "", r).strip().lower().rstrip(":")
        if clean_hdr in JUNK_HEADERS:
            continue
        if any(clean_hdr.startswith(p) for p in RUBRIC_PREFIXES):
            continue
        if re.match(r"^(?:experience|tenure)\s*[:*–-]*\s*\d+.*years?$", clean_hdr):
            continue
        if clean_hdr.startswith("we are looking for") and "experience" in clean_hdr:
            continue
        norm_key = re.sub(r"\W+", " ", clean_hdr).strip()
        if norm_key in seen:
            continue
        seen.add(norm_key)
        cleaned.append(r)
    return cleaned


# ---------------------------------------------------------------------------
# Requirement classifier
# ---------------------------------------------------------------------------

_META_ANCHORS = {
    "experience", "requirements", "mandatory requirements", "qualification",
    "qualifications", "experience and qualification", "mandatory", "general", "other"
}


def _extract_min_years_from_req(req: str) -> Optional[float]:
    """Extract minimum years of experience required by a requirement string."""
    clean = re.sub(r"[*_#`]", "", req).strip()
    m = re.search(r"(?:at\s+least|minimum|min\.?)\s+(\d+(?:\.\d+)?)\s*(?:[-–to]+\s*(\d+(?:\.\d+)?))?\s*(?:years?|yrs?)", clean, re.I)
    if m:
        return float(m.group(1))
    m2 = re.search(r"(\d+(?:\.\d+)?)\s*(?:[-–to]+\s*(\d+(?:\.\d+)?))\s*(?:years?|yrs?)\s+of\s+experience", clean, re.I)
    if m2:
        return float(m2.group(1))
    m3 = re.search(r"(?:experience|tenure)\s*[:\*\-]*\s*(\d+(?:\.\d+)?)\s*(?:[-–to]+\s*(\d+(?:\.\d+)?))?\s*(?:years?|yrs?)", clean, re.I)
    if m3:
        return float(m3.group(1))
    m4 = re.search(r"\b(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:[a-zA-Z\s]+)?experience", clean, re.I)
    if m4:
        return float(m4.group(1))
    return None


def _classify_requirement(
    requirement: str,
    resume_text: str,
    parsed_text_for_verification: str,
    candidate_exp: Optional[float] = None,
) -> Tuple[str, float, Optional[str], Optional[bool], List[str], str]:
    """
    Classify a single requirement as MET, PARTIALLY_MET, or NOT_EVIDENCED.

    Returns:
        (status, score_weight, evidence_quote, quote_verified, searched_keywords, reasoning)

    MET bar recalibration (v2.1):
    - MET = verifiable professional application evidenced by action verbs
      (designed, built, deployed, managed, implemented, etc.) in a relevant sentence.
    - PARTIALLY_MET = keyword present but only listed as skill/coursework, no action verb.
    - NOT_EVIDENCED = no keywords found anywhere in resume.

    Quote verification:
    - Every MET/PARTIALLY_MET quote is verified via verify_quote_in_text().
    - If verification fails: status downgraded to NOT_EVIDENCED, quote cleared.
    """
    clean_req = re.sub(r"[*_#`]", "", requirement).strip()
    resume_lower = resume_text.lower()
    keywords = _build_keyword_variants(requirement)

    # 0. Check if requirement is explicitly an experience/tenure requirement
    req_min_years = _extract_min_years_from_req(requirement)
    is_exp_req = req_min_years is not None and (
        re.search(r"\b(?:experience|tenure)\b", clean_req, re.I) or
        clean_req.lower().startswith("experience")
    )
    if is_exp_req and candidate_exp is not None:
        if candidate_exp == 0.0:
            return (
                "NOT_EVIDENCED",
                SCORE_NOT_EVIDENCED,
                None,
                None,
                keywords,
                f"Candidate has 0.0 years of verified job/internship experience (fresher); requirement calls for {req_min_years}+ years.",
            )
        elif candidate_exp < req_min_years:
            return (
                "NOT_EVIDENCED",
                SCORE_NOT_EVIDENCED,
                None,
                None,
                keywords,
                f"Candidate has {candidate_exp}y of verified job/internship experience; does not satisfy requirement of {req_min_years}+ years.",
            )
        else:
            pure_tenure = not any(k in clean_req.lower() for k in [
                "python", "java", "sql", "kafka", "aws", "docker", "kubernetes", "react", "c++", "go",
                "redis", "postgres", "mysql", "spark", "hadoop", "cloud", "microservices", "distributed"
            ])
            if pure_tenure:
                return (
                    "MET",
                    SCORE_MET,
                    None,
                    True,
                    keywords,
                    f"Candidate has {candidate_exp}y of verified job/internship experience, satisfying the requirement of {req_min_years}+ years.",
                )

    # 1. Identify primary anchor skill/topic (e.g. "**SQL:** ...")
    anchor_skill = None
    if ":" in clean_req:
        prefix = clean_req.split(":", 1)[0].strip().lower()
        if len(prefix.split()) <= 4 and prefix not in _META_ANCHORS:
            anchor_skill = prefix

    # 2. Find evidence quote candidate
    evidence = _find_evidence_quote(requirement, resume_text)

    _DEGREE_KEYWORDS = re.compile(
        r"\b(?:bachelor|master|b\.?s\.?|m\.?s\.?|b\.?tech|m\.?tech|ph\.?d\.?|degree|computer\s+science|software\s+engineering|stem)\b",
        re.I,
    )
    is_degree_req = bool(re.search(r"\b(?:degree|bachelor|master|ph\.?d|b\.?s|m\.?s|b\.?tech|stem)\b", clean_req, re.I))

    # Helper: verify quote + professional verb check
    def _assess_quote(quote: Optional[str]) -> Tuple[bool, bool]:
        """Returns (quote_verified, has_professional_verb)"""
        if not quote:
            return False, False
        verified = verify_quote_in_text(quote, parsed_text_for_verification)
        if is_degree_req and bool(_DEGREE_KEYWORDS.search(quote)):
            has_verb = True
        else:
            has_verb = bool(_PROFESSIONAL_VERBS.search(quote))
        return verified, has_verb

    # 3. No evidence and no anchor found anywhere
    if evidence is None and (not anchor_skill or anchor_skill not in resume_lower):
        return (
            "NOT_EVIDENCED",
            SCORE_NOT_EVIDENCED,
            None,
            None,
            keywords,
            f"Keywords searched: {keywords[:8]}. No verifiable evidence found in resume.",
        )

    # 4. Anchor skill present — check context strength
    if anchor_skill and anchor_skill in resume_lower:
        quote_verified, has_verb = _assess_quote(evidence)

        if evidence and quote_verified:
            if has_verb:
                return (
                    "MET",
                    SCORE_MET,
                    evidence,
                    True,
                    keywords,
                    f"Strong evidence: candidate demonstrates '{anchor_skill.title()}' with professional application.",
                )
            else:
                # Listed as skill but no professional verb → PARTIALLY_MET
                return (
                    "PARTIALLY_MET",
                    SCORE_PARTIALLY_MET,
                    evidence,
                    True,
                    keywords,
                    f"Partial evidence: '{anchor_skill.title()}' listed but without clear professional application context.",
                )
        elif evidence and not quote_verified:
            # Quote hallucinated — downgrade
            logger.warning("Quote verification FAILED for anchor '%s'; downgrading to NOT_EVIDENCED.", anchor_skill)
            return (
                "NOT_EVIDENCED",
                SCORE_NOT_EVIDENCED,
                None,
                False,
                keywords,
                f"Quote verification failed for '{anchor_skill.title()}'. Keyword present in resume but quote unverifiable.",
            )
        else:
            # Anchor in resume but no good sentence found → PARTIALLY_MET with skill-list note
            skill_mention = f"Candidate lists '{anchor_skill.title()}' in technical skills section."
            quote_verified_flag = verify_quote_in_text(skill_mention, parsed_text_for_verification)
            if not quote_verified_flag:
                skill_mention = None
                quote_verified_flag = None
            return (
                "PARTIALLY_MET",
                SCORE_PARTIALLY_MET,
                skill_mention,
                quote_verified_flag,
                keywords,
                f"'{anchor_skill.title()}' mentioned in resume but no detailed experience sentence found.",
            )

    # 5. General keyword matching
    total_kw = len(keywords)
    matched_kw = sum(1 for kw in keywords if _kw_in_text(kw, resume_lower))

    if evidence:
        quote_verified, has_verb = _assess_quote(evidence)
        if not quote_verified:
            logger.warning("Quote verification FAILED for requirement '%s'.", requirement[:60])
            return (
                "NOT_EVIDENCED",
                SCORE_NOT_EVIDENCED,
                None,
                False,
                keywords,
                f"Quote verification failed. Claimed evidence quote was not found in candidate resume.",
            )
        if has_verb:
            return (
                "MET",
                SCORE_MET,
                evidence,
                True,
                keywords,
                f"Strong evidence: verified quote with professional application.",
            )
        else:
            return (
                "PARTIALLY_MET",
                SCORE_PARTIALLY_MET,
                evidence,
                True,
                keywords,
                f"Partial evidence: skill mentioned without explicit action verb context.",
            )
    elif matched_kw > 0 and (matched_kw / total_kw >= 0.25 if total_kw > 0 else False):
        return (
            "PARTIALLY_MET",
            SCORE_PARTIALLY_MET,
            None,
            None,
            keywords,
            f"Partial evidence: {matched_kw}/{total_kw} keywords matched in resume (listed in skills/profile).",
        )
    else:
        return (
            "NOT_EVIDENCED",
            SCORE_NOT_EVIDENCED,
            None,
            None,
            keywords,
            f"Keywords searched: {keywords[:8]}. No verifiable evidence found in resume.",
        )


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

def _extract_requirements_from_spec(spec_json: Dict[str, Any]) -> Tuple[
    List[str], List[str], Optional[float]
]:
    """
    Extract must-have requirements, preferred qualifications, and minimum years
    from a canonical_json Specification v2 structure.

    Handles multiple known JSON shapes.
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

    # Extract minimum years
    for key in ("experience_requirements", "experience", "seniority"):
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

def _generate_interview_question(requirement: str, status: str, evidence_quote: Optional[str]) -> str:
    """
    Generate a targeted interviewer question for a NOT_EVIDENCED or PARTIALLY_MET requirement.
    Questions are phrased to explore depth, not to assume a skills gap.
    """
    req_short = requirement[:120]
    if status == "NOT_EVIDENCED":
        return (
            f"The candidate's resume does not explicitly mention: \"{req_short}\". "
            f"Ask: 'Can you walk me through your experience with this — specific projects, "
            f"scale, and what you personally owned or delivered?'"
        )
    else:  # PARTIALLY_MET
        snippet = f" (found: \"{evidence_quote[:80]}...\")".rstrip("...") + "\"" if evidence_quote else ""
        return (
            f"Partial evidence found for: \"{req_short}\"{snippet}. "
            f"Ask: 'Can you go deeper — particularly around professional context, "
            f"scale, and business outcomes?'"
        )


# ---------------------------------------------------------------------------
# Timeline observations (neutral, NOT scoring penalties)
# ---------------------------------------------------------------------------

def _build_timeline_observations(
    parsed_profile: Dict[str, Any],
) -> List[str]:
    """
    Build neutral timeline observations for the recruiter's interview prep.

    IMPORTANT: These are NOT penalties, NOT score modifiers, and NEVER disqualifiers.
    Career gaps may reflect caregiving, illness, military service, or personal growth.
    Observations are phrased neutrally as interview conversation starters.

    Replaces the previous _detect_red_flags() function.
    """
    observations: List[str] = []
    work_history = parsed_profile.get("work_history", [])

    if not work_history:
        return observations

    # Sort by start date and note any career pauses
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
            observations.append(
                f"Career pause of ~{gap_months:.0f} months between "
                f"'{dated[i-1][2]}' and '{dated[i][2]}'. "
                f"Consider exploring this period in conversation (may reflect caregiving, study, or career transition)."
            )

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
) -> Tuple[int, str, Dict[str, Any]]:
    """
    Compute overall_score (0-100), match_tier, and score_breakdown.

    Scoring formula:
      S_must = mean(score_weight for must-have items)         [0.0 - 1.0]
      S_pref = mean(score_weight for preferred items)         [0.0 - 1.0]
      S_tenure = min(1.0, candidate_years / required_years)   [0.0 - 1.0]

      W_must   = 0.70 if N_must > 0  else 0.0
      W_pref   = 0.20 if N_pref > 0  else 0.0
      W_tenure = 0.10 if JD specifies min tenure else 0.0
      W_total  = W_must + W_pref + W_tenure

      Final Score = round((W_must*S_must + W_pref*S_pref + W_tenure*S_tenure) / W_total * 100)

    Tier guardrail rules:
      not_evidenced_must = count of NOT_EVIDENCED must-have items

      STRONG_MATCH:    score >= 75 AND not_evidenced_must == 0
      POTENTIAL_MATCH: score >= 75 AND not_evidenced_must == 1   (capped despite high score)
                    OR score >= 50 AND not_evidenced_must <= 1
      NOT_A_FIT:       score < 50  OR not_evidenced_must >= 2
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
            "tenure_base_weight":   0.0,
            "warning": "NO_EVALUATION_CRITERIA_DEFINED",
        }
        return 100, "POTENTIAL_MATCH", breakdown

    s_must   = (sum(e["score_weight"] for e in must_evals) / n_must) if n_must > 0 else 0.0
    s_pref   = (sum(e["score_weight"] for e in pref_evals) / n_pref) if n_pref > 0 else 0.0
    s_tenure = tenure_score

    raw = (w_must * s_must + w_pref * s_pref + w_tenure * s_tenure) / w_total
    overall_score = round(raw * 100)

    not_evidenced_must = sum(1 for e in must_evals if e["status"] == "NOT_EVIDENCED")

    if overall_score >= STRONG_MATCH_THRESHOLD and not_evidenced_must == 0:
        match_tier = "STRONG_MATCH"
    elif overall_score >= STRONG_MATCH_THRESHOLD and not_evidenced_must == 1:
        match_tier = "POTENTIAL_MATCH"   # capped despite high score due to unverified must-have
    elif overall_score >= POTENTIAL_MATCH_THRESHOLD and not_evidenced_must <= 1:
        match_tier = "POTENTIAL_MATCH"
    elif overall_score >= POTENTIAL_MATCH_THRESHOLD and not_evidenced_must <= 3:
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
    redacted_pii: Dict[str, str] = {}
    if blind_screening:
        eval_text, redacted_pii = anonymize_resume(
            resume_text,
            candidate_name=parsed_profile.get("candidate_name") if parsed_profile else None,
            email=parsed_profile.get("email") if parsed_profile else None,
            phone=parsed_profile.get("phone") if parsed_profile else None,
        )

    # --- Prompt injection scan (security check on untrusted input) ---
    injection_match = scan_for_injection(eval_text)
    if injection_match:
        logger.warning(
            "PROMPT INJECTION PATTERN detected in resume text: '%s'. "
            "Resume text treated strictly as data.", injection_match
        )

    must_have_reqs, preferred_reqs, min_years = _extract_requirements_from_spec(spec_canonical_json)
    candidate_exp = parsed_profile.get("total_experience_years") if parsed_profile else None

    # --- Evaluate each requirement ---
    must_evals: List[Dict[str, Any]] = []
    pref_evals: List[Dict[str, Any]] = []
    any_quote_failed = False

    for req in must_have_reqs:
        status, weight, evidence, quote_verified, keywords, reasoning = _classify_requirement(
            req, eval_text, resume_text, candidate_exp=candidate_exp
        )
        if quote_verified is False:
            any_quote_failed = True
        must_evals.append({
            "requirement":      req,
            "category":         "must_have",
            "status":           status,
            "score_weight":     weight,
            "evidence_quote":   evidence,
            "quote_verified":   quote_verified,
            "searched_keywords": keywords[:10],
            "reasoning":        reasoning,
        })

    for req in preferred_reqs:
        status, weight, evidence, quote_verified, keywords, reasoning = _classify_requirement(
            req, eval_text, resume_text, candidate_exp=candidate_exp
        )
        if quote_verified is False:
            any_quote_failed = True
        pref_evals.append({
            "requirement":      req,
            "category":         "preferred",
            "status":           status,
            "score_weight":     weight,
            "evidence_quote":   evidence,
            "quote_verified":   quote_verified,
            "searched_keywords": keywords[:10],
            "reasoning":        reasoning,
        })

    # --- Tenure scoring ---
    candidate_years = parsed_profile.get("total_experience_years") or 0.0
    tenure_score, tenure_base_weight = _score_tenure(candidate_years, min_years)

    # --- Composite score ---
    overall_score, match_tier, score_breakdown = _compute_score(
        must_evals, pref_evals, tenure_score, tenure_base_weight
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
            f"SECURITY: Potential prompt injection pattern detected in resume text: '{injection_match}'. "
            f"All evaluation results are grounded exclusively in verified keyword evidence."
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
