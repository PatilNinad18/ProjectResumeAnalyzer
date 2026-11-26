import re
import unicodedata
from typing import Dict, Optional, Tuple

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

import sys
from pathlib import Path
_backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

try:
    from app.services.resume.evaluator import evaluate_candidate  # type: ignore[import-not-found,missing-import] # pyrefly: ignore
    from app.services.resume.profiler import profile_resume       # type: ignore[import-not-found,missing-import] # pyrefly: ignore
except ImportError:
    import importlib
    evaluate_candidate = getattr(importlib.import_module("app.services.resume.evaluator"), "evaluate_candidate")
    profile_resume = getattr(importlib.import_module("app.services.resume.profiler"), "profile_resume")

spec = {
    "role_title": "Data Analyst",
    "must_haves": [
        "Experience: 2-4 years",
        "**SQL:** Practical experience writing queries",
        "**Python:** Hands-on experience with Pandas and NumPy",
        "**Power BI:** Experience creating dashboards",
    ],
    "preferred_qualifications": ["Snowflake cloud data warehouse"],
    "experience_requirements": {"minimum_years": 2},
}

resume_a = """JOHN DOE
Seattle, WA | +1 206-555-0199 | jdoe@gmail.com | linkedin.com/in/johndoe | github.com/johndoe
PROFESSIONAL EXPERIENCE
Data Analyst at Acme Corp June 2022 – Present
• Developed complex SQL queries and ETL pipelines using Python, Pandas, and NumPy.
• Designed interactive Power BI dashboards with DAX measures and KPI reporting.
• Built Snowflake data warehousing models to ingest high-volume telemetry datasets.
EDUCATION
B.S. in Computer Science 2022
"""

resume_b = """PRIYA SHARMA
Bengaluru, India | +91 9845012345 | priya.sharma@yahoo.com | linkedin.com/in/priyasharma | github.com/priyasharma
PROFESSIONAL EXPERIENCE
Data Analyst at Acme Corp June 2022 – Present
• Developed complex SQL queries and ETL pipelines using Python, Pandas, and NumPy.
• Designed interactive Power BI dashboards with DAX measures and KPI reporting.
• Built Snowflake data warehousing models to ingest high-volume telemetry datasets.
EDUCATION
B.S. in Computer Science 2022
"""

prof_a = profile_resume(resume_a)
prof_b = profile_resume(resume_b)

anon_a, red_a = anonymize_resume(resume_a, prof_a.get("candidate_name"), prof_a.get("email"), prof_a.get("phone"))
anon_b, red_b = anonymize_resume(resume_b, prof_b.get("candidate_name"), prof_b.get("email"), prof_b.get("phone"))

print("ANONYMIZED A (top 3 lines):")
print("\n".join(anon_a.split("\n")[:3]))
print()
print("ANONYMIZED B (top 3 lines):")
print("\n".join(anon_b.split("\n")[:3]))
print()

eval_a = evaluate_candidate(anon_a, prof_a, spec)
eval_b = evaluate_candidate(anon_b, prof_b, spec)

print(f"Candidate A Score: {eval_a['overall_score']}, Tier: {eval_a['match_tier']}")
print(f"Candidate B Score: {eval_b['overall_score']}, Tier: {eval_b['match_tier']}")

assert eval_a['overall_score'] == eval_b['overall_score'], "Scores must be identical!"
assert eval_a['match_tier'] == eval_b['match_tier'], "Tiers must be identical!"
assert eval_a['must_haves_summary'] == eval_b['must_haves_summary'], "Summaries must be identical!"
print("\nSUCCESS: 100% IDENTICAL SCORES UNDER BLIND SCREENING!")
