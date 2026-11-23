"""
Resume Profiler (Phase 2)
=========================
Extracts structured candidate profile information from plain-text resume content.
Works entirely with deterministic regex — no Ollama calls, no external dependencies.

Extracted fields:
  - candidate_name
  - email
  - phone
  - work_history (list of WorkEntry with company, title, start/end dates)
  - total_experience_years (sum of deduped date ranges)
  - skills (flat list of tech keywords)
  - education (list of EducationEntry)
  - current_or_last_title
  - companies (list of company name strings)

Design constraints:
  - Must be deterministic and fast (< 100ms per resume).
  - Must NOT make any network calls.
  - Returns a dict (parsed_profile_json) for storage in DB and a CandidateProfile schema
    for the API response layer.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_EMAIL_RE    = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE    = re.compile(
    r"(?:(?:\+?91[\s\-]?)?(?:\(\d{3,5}\)[\s\-]?|\d{3,5}[\s\-]?)?\d{3,5}[\s\-]?\d{4,5})"
)

# Date patterns: "Jan 2020", "January 2020", "2020", "01/2020", "03-2022"
_MONTH_NAMES = (
    "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|"
    "january|february|march|april|june|july|august|september|october|november|december"
)
_DATE_RE = re.compile(
    rf"(?:(?:{_MONTH_NAMES})\.?\s*\d{{4}}|\d{{1,2}}[/\-]\d{{4}}|\d{{4}})",
    re.IGNORECASE,
)
_DATE_RANGE_RE = re.compile(
    rf"({_DATE_RE.pattern})\s*[-–—to]+\s*({_DATE_RE.pattern}|present|current|now|till date)",
    re.IGNORECASE,
)

# Section headers commonly found in resumes
_SECTION_HEADERS = {
    "experience": re.compile(
        r"^(?:(?:professional|work|industry|relevant|internship)\s+)?(?:experience|employment|work\s+history|career\s+history|positions?\s+held|internships?)\b",
        re.IGNORECASE | re.MULTILINE,
    ),
    "skills": re.compile(
        r"^(?:technical\s+)?(?:skills|skill\s+set|core\s+competencies|technologies|tools|tech\s+stack|proficiencies)\b",
        re.IGNORECASE | re.MULTILINE,
    ),
    "education": re.compile(
        r"^(?:education|academic|qualifications?|degrees?|educational\s+background)\b",
        re.IGNORECASE | re.MULTILINE,
    ),
    "projects": re.compile(
        r"^(?:(?:technical|academic|key|personal|side)\s+)?(?:projects?)\b",
        re.IGNORECASE | re.MULTILINE,
    ),
    "non_work_headers": re.compile(
        r"^(?:education|academic|technical\s+projects|projects|technical\s+skills|skills|publications?|achievements?|certifications?|leadership|activities|extracurricular|about\s+me|summary)\b",
        re.IGNORECASE | re.MULTILINE,
    ),
}

# Common tech skill keywords (expandable list)
_SKILL_KEYWORDS = [
    # Languages
    "python", "java", "javascript", "typescript", "golang", "go", "rust", "c\\+\\+", "c#",
    "ruby", "php", "swift", "kotlin", "scala", "r", "matlab", "bash", "shell", "perl",
    # Frameworks & libraries
    "react", "angular", "vue", "next\\.?js", "node\\.?js", "django", "flask", "fastapi",
    "spring", "spring boot", "express", "rails", "laravel", "tensorflow", "pytorch",
    "keras", "scikit-learn", "pandas", "numpy", "spark", "kafka",
    # Databases
    "postgresql", "postgres", "mysql", "sqlite", "mongodb", "redis", "cassandra",
    "elasticsearch", "dynamodb", "oracle", "sql server", "mariadb", "neo4j",
    # Cloud & DevOps
    "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "k8s", "terraform",
    "ansible", "jenkins", "github actions", "gitlab ci", "circleci", "helm", "istio",
    "prometheus", "grafana", "datadog", "airflow", "celery",
    # Concepts
    "rest", "graphql", "grpc", "microservices", "event-driven", "ci/cd", "devops",
    "agile", "scrum", "tdd", "bdd", "machine learning", "deep learning", "nlp",
    "computer vision", "llm", "rag", "data engineering", "etl",
    # Tools
    "git", "jira", "confluence", "linux", "ubuntu", "nginx", "apache",
]
_SKILL_RE = re.compile(
    r"\b(?:" + "|".join(_SKILL_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_month_year(text: str) -> Optional[date]:
    """Parse a date string like 'Jan 2020' or '2020' into a date object."""
    text = text.strip().lower()
    # Year only
    if re.fullmatch(r"\d{4}", text):
        return date(int(text), 1, 1)
    # MM/YYYY or MM-YYYY
    m = re.fullmatch(r"(\d{1,2})[/\-](\d{4})", text)
    if m:
        return date(int(m.group(2)), int(m.group(1)), 1)
    # Month name + year
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
        "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10,
        "november": 11, "december": 12,
    }
    m2 = re.match(r"([a-z]+)\.?\s*(\d{4})", text)
    if m2:
        month_str = m2.group(1).rstrip(".")
        month_num = months.get(month_str, 1)
        return date(int(m2.group(2)), month_num, 1)
    return None


def _extract_date_ranges(text: str) -> List[Tuple[date, date]]:
    """Extract all (start_date, end_date) pairs found in a text block."""
    today = date.today()
    ranges: List[Tuple[date, date]] = []
    for m in _DATE_RANGE_RE.finditer(text):
        start_raw = m.group(1)
        end_raw   = m.group(2)
        start = _parse_month_year(start_raw)
        if not start:
            continue
        if re.match(r"present|current|now|till date", end_raw.strip(), re.IGNORECASE):
            end = today
        else:
            end = _parse_month_year(end_raw) or today
        if end < start:
            end = today
        ranges.append((start, end))
    return ranges


def _total_years_from_ranges(ranges: List[Tuple[date, date]]) -> float:
    """
    Sum of all date ranges, deduplicated by merging overlapping intervals.
    Returns years as a float rounded to 1 decimal place.
    """
    if not ranges:
        return 0.0
    sorted_ranges = sorted(ranges, key=lambda r: r[0])
    merged: List[Tuple[date, date]] = []
    cur_start, cur_end = sorted_ranges[0]
    for s, e in sorted_ranges[1:]:
        if s <= cur_end:
            cur_end = max(cur_end, e)
        else:
            merged.append((cur_start, cur_end))
            cur_start, cur_end = s, e
    merged.append((cur_start, cur_end))
    total_days = sum((e - s).days for s, e in merged)
    return round(total_days / 365.25, 1)


def _extract_section_text(resume_text: str, section: str) -> str:
    """
    Extract the text under a specific section header until the next section header.
    Returns empty string if section not found.
    """
    header_re = _SECTION_HEADERS.get(section)
    if not header_re:
        return ""
    lines = resume_text.split("\n")
    all_header_positions: List[Tuple[int, str]] = []
    for i, line in enumerate(lines):
        for sec_name, sec_re in _SECTION_HEADERS.items():
            if sec_re.match(line.strip()):
                all_header_positions.append((i, sec_name))

    # Find start of target section
    target_start = None
    for idx, (line_no, sec_name) in enumerate(all_header_positions):
        if sec_name == section:
            target_start = line_no + 1
            # Find end: next different section header
            if idx + 1 < len(all_header_positions):
                target_end = all_header_positions[idx + 1][0]
            else:
                target_end = len(lines)
            return "\n".join(lines[target_start:target_end])
    return ""


def _extract_name(resume_text: str) -> Optional[str]:
    """
    Heuristic: candidate name is often the first non-empty line of the resume.
    Validated: contains only letters, spaces, dots, hyphens; between 2–5 words.
    """
    for line in resume_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # Must look like a name: 2-5 words, mostly alphabetic
        if re.match(r"^[A-Za-z][A-Za-z\s.\-']{3,50}$", line):
            word_count = len(line.split())
            if 2 <= word_count <= 5:
                # Not a section header
                is_header = any(r.match(line) for r in _SECTION_HEADERS.values())
                if not is_header:
                    return line.title()
        break  # Only check first non-empty line
    return None


def _extract_skills(resume_text: str) -> List[str]:
    """Extract technology and skill keywords from the full resume text."""
    found = set()
    for match in _SKILL_RE.finditer(resume_text):
        found.add(match.group(0).lower())
    return sorted(found)


_EDUCATION_TERMS = {
    "school", "college", "university", "institute", "b.tech", "btech", "b.e", "m.tech",
    "bachelor", "master", "phd", "cgpa", "secondary", "hsc", "ssc",
    "class xii", "class x", "class 12", "class 10", "cbse", "icse",
}


def _extract_work_history(resume_text: str) -> List[Dict[str, Any]]:
    """
    Parse work experience and internship section into structured entries.
    Strictly excludes education, academic coursework, and degrees.
    Returns empty list if no job or internship experience is present (fresher).
    """
    exp_text = _extract_section_text(resume_text, "experience")
    if not exp_text:
        # Do NOT fallback to full document — freshers have no work experience section
        return []

    entries = []
    # Split by date ranges as natural separators for job entries
    range_positions = [(m.start(), m.end(), m.group()) for m in _DATE_RANGE_RE.finditer(exp_text)]

    if not range_positions:
        return []

    for i, (rstart, rend, date_str) in enumerate(range_positions):
        # Lines around the date range: title/company are usually 1-3 lines before
        before_text = exp_text[max(0, rstart - 300):rstart].strip()
        lines_before = [l.strip() for l in before_text.split("\n") if l.strip()]
        title   = lines_before[-1] if lines_before else None
        company = lines_before[-2] if len(lines_before) >= 2 else None

        # Filter out accidental education entries inside the section
        check_str = f"{title or ''} {company or ''}".lower()
        if any(term in check_str for term in _EDUCATION_TERMS):
            continue

        # Text after the date range up to the next date range
        if i + 1 < len(range_positions):
            after_end = range_positions[i + 1][0]
        else:
            after_end = len(exp_text)
        description = exp_text[rend:after_end].strip()[:500]

        # Parse dates
        dates = _extract_date_ranges(date_str)
        if dates:
            start_d, end_d = dates[0]
            dur = round((end_d - start_d).days / 365.25, 1)
        else:
            start_d = end_d = None
            dur = 0.0

        entries.append({
            "title":          title,
            "company":        company,
            "start_date":     start_d.isoformat() if start_d else None,
            "end_date":       end_d.isoformat()   if end_d   else None,
            "duration_years": dur,
            "description":    description,
        })

    return entries


def _extract_education(resume_text: str) -> List[Dict[str, str]]:
    """
    Extract education entries: degree, institution, year.
    """
    edu_text = _extract_section_text(resume_text, "education") or resume_text
    degree_re = re.compile(
        r"\b(?:b\.?tech|b\.?e|b\.?sc|b\.?s|m\.?tech|m\.?sc|m\.?s|mba|ph\.?d|bachelor|master|doctorate|"
        r"engineering|computer science|information technology|b\.?c\.?a|m\.?c\.?a)\b",
        re.IGNORECASE,
    )
    year_re = re.compile(r"\b(19|20)\d{2}\b")

    entries = []
    for line in edu_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if degree_re.search(line):
            years = year_re.findall(line)
            entries.append({
                "raw_line": line,
                "year":     years[-1] if years else None,
            })
    return entries[:5]  # reasonable cap


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def profile_resume(parsed_text: str) -> Dict[str, Any]:
    """
    Main profiler function.
    Takes the plain-text output of document_parser.parse_document() and returns
    a structured profile dict suitable for storage in CandidateResume.parsed_profile_json.

    Returns:
        {
          "candidate_name":         str | None,
          "email":                  str | None,
          "phone":                  str | None,
          "total_experience_years": float,
          "work_history":           List[WorkEntry],
          "skills":                 List[str],
          "education":              List[EducationEntry],
          "companies":              List[str],
          "current_or_last_title":  str | None,
        }
    """
    # --- Contact info ---
    email_match = _EMAIL_RE.search(parsed_text)
    email = email_match.group(0).lower() if email_match else None

    phone_match = _PHONE_RE.search(parsed_text)
    phone = phone_match.group(0).strip() if phone_match else None

    # --- Name ---
    candidate_name = _extract_name(parsed_text)

    # --- Work history ---
    work_history = _extract_work_history(parsed_text)

    # --- Total experience: ONLY from validated job & internship entries ---
    total_experience_years = 0.0
    if work_history:
        wh_ranges = []
        for entry in work_history:
            if entry.get("start_date") and entry.get("end_date"):
                try:
                    s = date.fromisoformat(entry["start_date"])
                    e = date.fromisoformat(entry["end_date"])
                    wh_ranges.append((s, e))
                except ValueError:
                    pass
        if wh_ranges:
            total_experience_years = _total_years_from_ranges(wh_ranges)

    # --- Skills ---
    skills = _extract_skills(parsed_text)

    # --- Education ---
    education = _extract_education(parsed_text)

    # --- Companies & Current Title ---
    companies = [e["company"] for e in work_history if e.get("company")]
    # Most recent entry = first entry with a date range
    current_or_last_title = work_history[0]["title"] if work_history else None

    return {
        "candidate_name":         candidate_name,
        "email":                  email,
        "phone":                  phone,
        "total_experience_years": total_experience_years,
        "work_history":           work_history,
        "skills":                 skills,
        "education":              education,
        "companies":              companies,
        "current_or_last_title":  current_or_last_title,
    }
