"""
A tiny, transparent, rule-based JD extractor.

This exists ONLY to let the pipeline run end-to-end offline (dev/CI)
without a real LLM. It is intentionally simple and conservative: it never
invents values that aren't supported by the JD text, in keeping with the
same non-fabrication principle the real Agent must follow.

In production, `AnthropicAdapter` (or another real ProviderAdapter) is
used instead, driven by the prompt in `app/services/prompt.py`.

Mock extractor improvements (v2):
- Hardware keyword support (PCB, FPGA, oscilloscope, firmware, C/C++, etc.)
- Evidence requirements reflect DEMONSTRATED HANDS-ON experience, not keywords.
- missing_information populated for commonly absent JD fields.
- Non-conventional parameters are JD-specific, not generic.
- Experience requirements correctly capture relevant-skill experience.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

TECH_KEYWORDS: Dict[str, str] = {
    # Software & Cloud

    "python": "language",
    "fastapi": "framework",
    "django": "framework",
    "flask": "framework",
    "react": "framework",
    "next.js": "framework",
    "typescript": "language",
    "javascript": "language",
    "java": "language",
    "go": "language",
    "grpc": "framework",
    "aws": "cloud",
    "gcp": "cloud",
    "azure": "cloud",
    "postgresql": "database",
    "postgres": "database",
    "mysql": "database",
    "mongodb": "database",
    "redis": "database",
    "kubernetes": "infra",
    "k8s": "infra",
    "docker": "infra",
    "sql": "language",
    # AI / ML / Data Science
    "machine learning": "methodology",
    "ml": "methodology",
    "ai": "methodology",
    "deep learning": "methodology",
    "scikit-learn": "framework",
    "tensorflow": "framework",
    "pytorch": "framework",
    "numpy": "library",
    "pandas": "library",
    "mlflow": "tool",
    "sagemaker": "cloud",
    "amazon sagemaker": "cloud",
    "kubeflow": "tool",
    "airflow": "tool",
    "arize": "tool",
    "evidently": "tool",
    "llm": "domain",
    "rag": "domain",
    "nlp": "domain",
    "computer vision": "domain",
    # Hardware / Embedded
    "fpga": "platform",
    "vhdl": "language",
    "verilog": "language",
    "pcb": "tool",
    "altium": "tool",
    "eagle": "tool",
    "kicad": "tool",
    "oscilloscope": "tool",
    "multimeter": "tool",
    "jtag": "tool",
    "firmware": "methodology",
    "embedded": "methodology",
    "rtos": "platform",
    "freertos": "platform",
    "arm": "platform",
    "cortex": "platform",
    "microcontroller": "platform",
    "microcontrollers": "platform",
    "arduino": "platform",
    "stm32": "platform",
    "c++": "language",
    "rust": "language",
    "labview": "tool",
    "matlab": "tool",
    "simulink": "tool",
}


PREFERRED_MARKERS = ["preferred", "nice to have", "a plus", "bonus", "advantage"]
REQUIRED_MARKERS = ["required", "must", "mandatory", "strong"]

BIAS_PATTERNS = [
    (r"\bage\b\s*(\d{2})", "age"),
    (r"\byoung\b|\benergetic\b", "age"),
    (r"\bmale\b|\bfemale\b", "gender"),
    (r"\bmarried\b|\bsingle\b|\bmarital status\b", "marital_status"),
    (r"\bno family obligations\b|\bno obligations\b", "marital_status"),
    (r"\bgraduation year\b", "age_proxy_graduation_year"),
    (r"\brecently graduated\b", "age_proxy_recent_graduation"),
]

# Common JD fields that are frequently absent
_COMMONLY_MISSING = [
    ("Compensation / Salary Range", "Candidates typically want to know compensation before applying; absence may reduce applicant quality.", "Ask TA to confirm if compensation details exist internally."),
    ("Work Authorization / Visa Sponsorship", "Unknown sponsorship policy prevents candidates from self-selecting appropriately.", "Ask TA to confirm work authorization requirements and sponsorship policy."),
]


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def mock_extract_canonical(jd_text: str) -> Dict[str, Any]:  # noqa: C901 (complexity accepted for mock)
    jd_text = re.sub(r"\s+", " ", jd_text).strip()
    text_lower = jd_text.lower()
    sentences = _sentences(jd_text)

    # ------------------------------------------------------------------ #
    # Experience extraction
    # ------------------------------------------------------------------ #
    experience = []
    # Try to find "<N>+ years of <technology/domain>" patterns
    exp_pattern = re.compile(
        r"(\d+)\s*\+?\s*(?:to\s*(\d+))?\s*years?(?:\s+of(?:\s+relevant)?\s+([\w\s/,+-]+?))?",
        re.IGNORECASE,
    )
    for exp_m in exp_pattern.finditer(jd_text):
        min_years = float(exp_m.group(1))
        max_years = float(exp_m.group(2)) if exp_m.group(2) else None
        domain_hint = exp_m.group(3).strip().rstrip(".,;") if exp_m.group(3) else None
        if domain_hint:
            domain_hint = re.sub(r"^(?:experience\s+in|experience\s+with|experience\s+of|e\s+experience\s+in)\s*", "", domain_hint, flags=re.IGNORECASE).strip()
        sentence = next((s for s in sentences if exp_m.group(0) in s), exp_m.group(0))
        is_preferred = any(p in sentence.lower() for p in PREFERRED_MARKERS)
        prio = "PREFERRED" if is_preferred else "MUST_HAVE"
        desc = (
            f"{int(min_years)}+ years of relevant {domain_hint} experience"
            if domain_hint
            else f"{int(min_years)}+ years of relevant experience"
        )
        experience.append(
            {
                "description": desc,
                "min_years": min_years,
                "max_years": max_years,
                "priority": prio,
                "explicit_or_derived": "explicit",
                "source": {"text": sentence, "section": "experience"},
            }
        )

    # ------------------------------------------------------------------ #
    # Technical skills — must-have vs preferred
    # ------------------------------------------------------------------ #
    technical_skills = []
    must_have_skills, preferred_skills = [], []
    for kw, category in TECH_KEYWORDS.items():
        if kw in text_lower:
            sentence = next((s for s in sentences if kw in s.lower()), kw)
            is_preferred = any(p in sentence.lower() for p in PREFERRED_MARKERS)
            priority = "PREFERRED" if is_preferred else "MUST_HAVE"
            display_name = kw if kw != "next.js" else "Next.js"
            technical_skills.append(
                {
                    "name": display_name,
                    "category": category,
                    "priority": priority,
                    "explicit_or_derived": "explicit",
                    "source": {"text": sentence, "section": "requirements"},
                }
            )
            (preferred_skills if is_preferred else must_have_skills).append(display_name)

    # ------------------------------------------------------------------ #
    # Location / Work Mode
    # ------------------------------------------------------------------ #
    location: Dict[str, Any] = {"work_mode": "unspecified"}
    city_match = re.search(r"(?:location|based in)\s*[-:]?\s*([A-Z][a-zA-Z\s]+?)(?:\.|,|\n|\r|$)", jd_text, re.IGNORECASE)
    if city_match:
        location["city"] = city_match.group(1).strip()
    if "office" in text_lower and ("day" in text_lower or "onsite" in text_lower or "on-site" in text_lower):
        location["work_mode"] = "onsite" if "remote" not in text_lower else "hybrid"
        attendance_match = re.search(r"(\w+)\s+days?\s+(?:per week\s+)?(?:in|at|from)?\s*(?:the\s+)?office", text_lower)
        if attendance_match:
            location["office_attendance"] = f"{attendance_match.group(1)} days/week onsite"
        elif re.search(r"(\d+)\s+day", text_lower):
            days_m = re.search(r"(\d+)\s+day", text_lower)
            location["office_attendance"] = f"{days_m.group(1)} days/week onsite"
    elif "remote" in text_lower or "pan india" in text_lower or "work from home" in text_lower:
        location["work_mode"] = "remote"
    elif "hybrid" in text_lower:
        location["work_mode"] = "hybrid"

    # ------------------------------------------------------------------ #
    # Lab / Hardware Environment (hardware-specific)
    # ------------------------------------------------------------------ #
    lab_required = bool(re.search(r"\b(hardware lab|oscilloscope|soldering|bench work|jtag|vhdl|verilog|pcb layout)\b", text_lower))
    if lab_required:
        location["work_mode"] = "onsite"  # lab work requires physical presence

    # ------------------------------------------------------------------ #
    # Salary / Compensation
    # ------------------------------------------------------------------ #
    salary_match = re.search(
        r"(\d+\s*K?\s*(?:INR|USD|EUR|GBP|₹|\$)\s*/\s*(?:month|year|annum)|\d+\s*-\s*\d+\s*K?\s*(?:INR|USD|₹|\$)|(?:₹|\$)?\s*\d+\s*K?\s*(?:INR|USD)?\s*/\s*month\s*-\s*\d+\s*K?\s*(?:INR|USD)?\s*/\s*month|\d+\s*-\s*\d+\s*(?:LPA|CTC|lpa|ctc))",
        jd_text,
        re.IGNORECASE,
    )
    salary_text = salary_match.group(0).strip() if salary_match else None
    if not salary_text:
        sal_line_m = re.search(r"(\d+K?\s*(?:INR|USD|\$|₹)?\s*[/|-]\s*\d*K?\s*(?:INR|USD|\$|₹)?\s*(?:/month|/year|month|lpa)?)", jd_text, re.IGNORECASE)
        if sal_line_m and any(k in sal_line_m.group(0).lower() for k in ["inr", "usd", "$", "₹", "month", "lpa"]):
            salary_text = sal_line_m.group(0).strip()

    # ------------------------------------------------------------------ #
    # Travel
    # ------------------------------------------------------------------ #
    travel: Dict[str, Any] = {}
    if "travel" in text_lower:
        travel["required"] = True
        travel["description"] = next((s for s in sentences if "travel" in s.lower()), None)

    # ------------------------------------------------------------------ #
    # Responsibilities
    # ------------------------------------------------------------------ #
    responsibilities = []
    resp_block_match = re.search(
        r"(?:Role\s*&\s*Responsibilities|Responsibilities|Key\s+Responsibilities)[:\n\r]+(.*?)(?=\n\s*\n[A-Z]|\n[A-Z][a-z]+\s*&?\s*[A-Z]|\Z)",
        jd_text, re.IGNORECASE | re.DOTALL
    )
    if resp_block_match:
        resp_lines = [line.strip("-*• ") for line in resp_block_match.group(1).splitlines() if line.strip("-*• ")]
        for line in resp_lines[:8]:
            if len(line) > 10:
                responsibilities.append({"description": line, "kind": "primary"})

    if not responsibilities:
        resp_match = re.search(
            r"(?:responsible for|will include|responsibilities include|will be expected to)\s+(.+)",
            jd_text, re.IGNORECASE | re.DOTALL
        )
        if resp_match:
            resp_section = resp_match.group(1)
            for chunk in re.split(r",| and |\n", resp_section):
                chunk = chunk.strip(" .-*\n")
                if len(chunk.split()) >= 2 and len(chunk) < 150:
                    responsibilities.append({"description": chunk, "kind": "primary"})
        responsibilities = responsibilities[:8]

    # ------------------------------------------------------------------ #
    # Seniority & Role Title
    # ------------------------------------------------------------------ #
    seniority = None
    for level in ["principal", "staff", "senior", "lead", "junior", "mid-level"]:
        if level in text_lower:
            seniority = level.capitalize()
            break

    if not seniority:
        yrs_m = re.search(r"(\d+)\s*\+?\s*yrs?", text_lower)
        if yrs_m:
            yrs_val = int(yrs_m.group(1))
            if yrs_val >= 8:
                seniority = "Lead"
            elif yrs_val >= 5:
                seniority = "Senior"
            elif yrs_val >= 2:
                seniority = "Mid-level"
            else:
                seniority = "Junior"

    job_title = None
    role_header_match = re.search(r"(?:Role|Title|Job Title|Position)\s*[-:]\s*([^\n\r,]+)", jd_text, re.IGNORECASE)
    if role_header_match:
        job_title = role_header_match.group(1).strip()

    if not job_title:
        first_line = jd_text.splitlines()[0].strip() if jd_text.splitlines() else ""
        first_line_clean = re.sub(r"_\d+\+?\s*yrs?.*$", "", first_line, flags=re.IGNORECASE).strip()
        if len(first_line_clean) < 60 and any(k in first_line_clean.lower() for k in ["engineer", "developer", "architect", "lead", "manager", "analyst", "scientist", "specialist"]):
            job_title = first_line_clean

    if not job_title:
        role_title_match = re.search(r"(?:looking for|hiring|seeking)\s+an?\s+([A-Za-z\s]+?)(?:\.|,|\swith\b)", jd_text, re.IGNORECASE)
        if role_title_match:
            job_title = role_title_match.group(1).strip()


    # ------------------------------------------------------------------ #
    # Non-conventional parameters — JD-specific only
    # ------------------------------------------------------------------ #
    non_conventional = []

    if location.get("work_mode") == "onsite" and not lab_required:
        nc_sentence = next((s for s in sentences if "office" in s.lower()), "")
        non_conventional.append(
            {
                "parameter_name": "On-site Compatibility",
                "category": "Work Arrangement",
                "why_it_is_relevant": (
                    "The JD specifies regular in-office attendance. "
                    "This is relevant because a candidate who cannot or will not work onsite "
                    "cannot fulfill the role as described."
                ),
                "jd_evidence": nc_sentence,
                "explicit_or_derived": "explicit",
                "evaluation_guidance": (
                    "Check candidate's stated location and work-mode preference against the required "
                    "attendance pattern. Do not infer willingness from proximity alone. "
                    "Only flag as evidence if the candidate explicitly states it."
                ),
                "evidence_to_look_for": [
                    "candidate explicitly states current or preferred onsite work",
                    "candidate states they are located in the required city",
                    "candidate explicitly states willingness to relocate",
                ],
                "strong_evidence": "Candidate explicitly states willingness and ability to work onsite at this location on the required schedule.",
                "moderate_evidence": "Candidate is currently located in the required city and does not state a preference for remote.",
                "weak_evidence": "No location information stated in resume.",
                "prohibited_inference": (
                    "Do not assume willingness to work onsite from job title, gender, family status, or commuting distance. "
                    "Do not assume unwillingness from remote work history alone."
                ),
                "confidence": "medium",
                "unscored_if": "Candidate location and work-mode preference are not stated in candidate materials.",
            }
        )

    if lab_required:
        lab_sentence = next((s for s in sentences if any(kw in s.lower() for kw in ["lab", "oscilloscope", "bench", "soldering"])), "")
        non_conventional.append(
            {
                "parameter_name": "Laboratory / Bench Work Requirement",
                "category": "Work Arrangement",
                "why_it_is_relevant": (
                    "The JD references lab, bench, or physical hardware testing activities "
                    "that cannot be performed remotely. Physical presence is implied by the nature of the work."
                ),
                "jd_evidence": lab_sentence,
                "explicit_or_derived": "derived",
                "evaluation_guidance": (
                    "Look for evidence that the candidate has worked in a hardware lab or bench environment. "
                    "Lab experience is qualitatively different from simulation-only work — evaluate accordingly."
                ),
                "evidence_to_look_for": [
                    "explicit mention of hands-on lab or bench work",
                    "oscilloscope / logic analyzer / multimeter usage in described roles",
                    "hardware debugging described in a physical lab context",
                ],
                "strong_evidence": "Candidate describes hands-on debugging, prototyping, or testing with physical hardware instruments.",
                "moderate_evidence": "Candidate's prior roles were in hardware or EE departments with implied lab access.",
                "weak_evidence": "Candidate lists hardware tools in a skills section with no context.",
                "prohibited_inference": "Do not assume lab experience from software/simulation skills alone.",
                "confidence": "medium",
                "unscored_if": "No hardware lab or bench work mentioned in candidate materials.",
            }
        )

    if travel.get("required"):
        non_conventional.append(
            {
                "parameter_name": "Travel Readiness",
                "category": "Work Arrangement",
                "why_it_is_relevant": "The JD explicitly states travel is required for this role.",
                "jd_evidence": travel.get("description") or "",
                "explicit_or_derived": "explicit",
                "evaluation_guidance": (
                    "Look for explicit statements of travel willingness or history of travel-intensive roles. "
                    "Do not infer willingness or unwillingness from gender, family status, or caregiving responsibilities."
                ),
                "evidence_to_look_for": [
                    "candidate explicitly states willingness to travel",
                    "candidate held prior roles with described travel requirements",
                ],
                "strong_evidence": "Candidate explicitly states willingness to travel or describes frequent travel in prior roles.",
                "moderate_evidence": "Candidate held a prior role that plausibly required travel (e.g., field engineer, sales).",
                "weak_evidence": "No mention of travel in candidate materials.",
                "prohibited_inference": "Do not assume unwillingness to travel due to caregiving, gender, age, or family status.",
                "confidence": "medium",
                "unscored_if": "No candidate evidence about travel willingness or history exists.",
            }
        )

    if "startup" in text_lower or "fast-paced" in text_lower:
        env_sentence = next((s for s in sentences if "startup" in s.lower() or "fast-paced" in s.lower()), "")
        non_conventional.append(
            {
                "parameter_name": "Fast-Paced / Startup Environment Fit",
                "category": "Work Environment",
                "why_it_is_relevant": (
                    "The JD explicitly describes a fast-paced or startup environment. "
                    "This may imply expectations of ambiguity tolerance, broad ownership, and rapid iteration "
                    "that differ from structured enterprise roles."
                ),
                "jd_evidence": env_sentence,
                "explicit_or_derived": "derived",
                "evaluation_guidance": (
                    "Look for evidence of ambiguity tolerance, ownership of loosely-defined problems, "
                    "or prior experience at small/early-stage companies. "
                    "Do NOT infer personality traits (e.g., 'energetic', 'driven') — "
                    "only evaluate based on concrete described work context."
                ),
                "evidence_to_look_for": [
                    "described experience at early-stage companies",
                    "described ownership of ambiguous or undefined projects",
                    "described rapid iteration or product pivots",
                ],
                "strong_evidence": "Candidate describes taking ownership of undefined projects with limited resources at a small company.",
                "moderate_evidence": "Candidate has prior experience at a startup or small team context.",
                "weak_evidence": "No relevant environment context described.",
                "prohibited_inference": "Do not infer personality or 'culture fit' beyond stated, evidence-backed work context.",
                "confidence": "low",
                "unscored_if": "No relevant environment evidence available in candidate materials.",
            }
        )

    # ------------------------------------------------------------------ #
    # Ambiguities
    # ------------------------------------------------------------------ #
    ambiguities = []
    AMBIGUOUS_PHRASES = {
        "strong communication": "Undefined and subjective — 'strong communication' could mean written, verbal, cross-functional, or client-facing communication.",
        "fast-paced": "Subjective term with no defined metric. May imply startup environment, rapid deadlines, or both.",
        "comfortable working": "Undefined preference statement with no measurable criteria.",
        "fast learner": "Personality trait claim with no defined evaluation criteria.",
        "team player": "Undefined personality trait — not evaluable without behavioral evidence.",
        "comfortable wearing many hats": "Vague scope statement; specific responsibilities are not enumerated.",
        "modern technologies": "Unspecified — any technology could qualify; makes evaluation impossible.",
    }
    for phrase, why in AMBIGUOUS_PHRASES.items():
        if phrase in text_lower:
            sentence = next((s for s in sentences if phrase in s.lower()), phrase)
            ambiguities.append(
                {
                    "statement": sentence,
                    "why_ambiguous": why,
                    "suggested_interpretation": (
                        "Look for concrete, job-relevant evidence (specific tools, projects, or described outcomes) "
                        "rather than self-reported personality traits."
                    ),
                    "evidence_required": ["concrete examples tied to job-relevant tasks"],
                    "ta_confirmation_required": True,
                }
            )

    # ------------------------------------------------------------------ #
    # Compliance flags
    # ------------------------------------------------------------------ #
    compliance_flags = []
    for pattern, category in BIAS_PATTERNS:
        m2 = re.search(pattern, text_lower)
        if m2:
            compliance_flags.append(
                {
                    "flagged_text": m2.group(0),
                    "concern": f"Possible protected-characteristic-related language: {category}.",
                    "category": category,
                    "recommended_action": "Flag for TA review. Do not use in automated scoring.",
                }
            )

    # ------------------------------------------------------------------ #
    # Missing information
    # ------------------------------------------------------------------ #
    missing_information = []
    for field_name, why, suggested in _COMMONLY_MISSING:
        if field_name.startswith("Compensation") and salary_text:
            continue
        missing_information.append({"field": field_name, "why_it_matters": why, "suggested_action": suggested})

    # If work authorization is not mentioned explicitly, flag it
    if "visa" not in text_lower and "work authorization" not in text_lower and "sponsorship" not in text_lower:
        # Already covered by _COMMONLY_MISSING above; avoid duplicate
        pass

    # If team size is not mentioned
    if not re.search(r"\bteam of \d+\b|\b\d+ engineer|\bsmall team\b", text_lower):
        missing_information.append({
            "field": "Team Size",
            "why_it_matters": "Team size affects candidate expectations regarding collaboration intensity and breadth of ownership.",
            "suggested_action": "Ask TA to provide team size context for candidate briefing.",
        })

    # If education requirements are absent
    if not re.search(r"\bdegree\b|\bbachelor\b|\bmaster\b|\bphd\b|\bbs\b|\bms\b|\be\.e\.\b", text_lower):
        missing_information.append({
            "field": "Education Requirements",
            "why_it_matters": "No education requirement is stated. Unclear whether a degree is required, preferred, or not evaluated.",
            "suggested_action": "Default to 'not required unless stated'. Ask TA if education should be a filter.",
        })

    # ------------------------------------------------------------------ #
    # Must-have / preferred requirements (summary list)
    # ------------------------------------------------------------------ #
    must_have_requirements = []
    if seniority:
        must_have_requirements.append(f"{seniority}-level experience")
    if experience:
        must_have_requirements.append(experience[0]["description"])
    must_have_requirements += [s for s in must_have_skills if s not in must_have_requirements]
    if location.get("work_mode") == "onsite" and location.get("city"):
        must_have_requirements.append(
            f"Ability to work onsite in {location['city']} "
            f"({location.get('office_attendance', 'office attendance required')})"
        )

    preferred_requirements = list(preferred_skills)

    # ------------------------------------------------------------------ #
    # Evidence requirements — hands-on proof emphasis
    # ------------------------------------------------------------------ #
    evidence_requirements = []
    for skill in technical_skills:
        sn = skill["name"]
        is_hardware = any(
            kw in sn.lower() for kw in ["fpga", "pcb", "oscilloscope", "firmware", "embedded", "rtos", "vhdl", "verilog", "jtag", "altium", "eagle", "kicad", "multimeter", "arduino", "stm32", "arm", "cortex", "labview"]
        )

        if is_hardware:
            evidence_requirements.append(
                {
                    "requirement": sn,
                    "priority": skill["priority"],
                    "explicit_or_derived": "explicit",
                    "evidence_to_look_for": [
                        f"described {sn} usage in a hardware development, prototyping, or testing role",
                        f"specific project outcomes involving {sn}",
                    ],
                    "strong_evidence": (
                        f"Candidate describes professional use of {sn} in a hardware engineering context "
                        f"with specific outcomes (e.g., boards designed, firmware deployed, systems validated)."
                    ),
                    "moderate_evidence": (
                        f"Candidate describes project-level use of {sn} with described outcomes, "
                        f"even if not in a professional setting."
                    ),
                    "weak_evidence": f"{sn} appears only in a skills list with no accompanying project or role description.",
                    "insufficient_evidence": f"No mention of {sn} or closely related technology anywhere in candidate materials.",
                    "prohibited_inference": (
                        f"Do not assume {sn} experience from adjacent software or simulation skills. "
                        f"Hands-on lab usage is qualitatively different from theoretical knowledge."
                    ),
                    "confidence": "medium",
                }
            )
        else:
            evidence_requirements.append(
                {
                    "requirement": sn,
                    "priority": skill["priority"],
                    "explicit_or_derived": "explicit",
                    "evidence_to_look_for": [
                        f"professional or production-level {sn} usage described in job history",
                        f"project-level {sn} usage with described outcomes",
                    ],
                    "strong_evidence": (
                        f"Candidate explicitly describes sustained professional/production usage of {sn} "
                        f"in job descriptions, including scope (team size, scale, or business impact)."
                    ),
                    "moderate_evidence": (
                        f"Candidate describes substantial project experience with {sn} and includes outcomes, "
                        f"even if not strictly a professional production environment."
                    ),
                    "weak_evidence": (
                        f"{sn} appears only in a technology/skills list or is mentioned once without "
                        f"any accompanying project, role, or outcome context."
                    ),
                    "insufficient_evidence": f"No mention of {sn} anywhere in candidate materials.",
                    "prohibited_inference": (
                        f"Do not assume {sn} expertise from related technologies "
                        f"(e.g., do not assume FastAPI knowledge from Flask, or AWS from GCP). "
                        f"Do not treat a skills-list mention as demonstrated hands-on experience."
                    ),
                    "confidence": "medium",
                }
            )

    # ------------------------------------------------------------------ #
    # Responsibility → requirement mapping
    # ------------------------------------------------------------------ #
    responsibility_mapping = []
    for r in responsibilities:
        caps = []
        rl = r["description"].lower()
        if "api" in rl:
            caps += ["API design and development", "Backend engineering", "System scalability awareness"]
        if "database" in rl or "optim" in rl:
            caps += ["Database performance optimization", "Query analysis"]
        if "collaborat" in rl or "cross-functional" in rl:
            caps += ["Cross-functional collaboration", "Stakeholder communication"]
        if "pcb" in rl or "layout" in rl:
            caps += ["PCB layout design", "Signal integrity awareness"]
        if "firmware" in rl or "embedded" in rl:
            caps += ["Embedded software development", "Hardware-software integration"]
        if "architect" in rl or "design" in rl:
            caps += ["System architecture", "Technical decision making"]
        if "mentor" in rl or "lead" in rl:
            caps += ["Technical leadership", "Mentoring"]
        if caps:
            responsibility_mapping.append(
                {"responsibility": r["description"], "required_capabilities": caps}
            )

    # ------------------------------------------------------------------ #
    # Requirement interpretations
    # ------------------------------------------------------------------ #
    requirement_interpretations = []
    for exp in experience:
        if "+" in exp["description"] and exp["min_years"] is not None:
            skill_hint = exp["description"].replace(f"{int(exp['min_years'])}+ years of relevant ", "").replace(" experience", "")
            requirement_interpretations.append(
                {
                    "explicit_requirement": exp["description"],
                    "derived_interpretation": [
                        f"Candidate must demonstrate {int(exp['min_years'])}+ years of hands-on, relevant {skill_hint} experience — "
                        f"not merely {int(exp['min_years'])} years of total employment.",
                        "Evidence must come from described roles, projects, or verifiable contributions, "
                        "not from a skills-list mention alone.",
                        "Adjacent or related technology experience is NOT a substitute without explicit transferability evidence.",
                    ],
                    "rationale": (
                        f"JD states: \"{exp['source']['text']}\". "
                        f"This specifies relevant {skill_hint} experience; "
                        f"a candidate with {int(exp['min_years'])} years total employment but less {skill_hint} usage "
                        f"does not satisfy this requirement."
                    ),
                }
            )

    return {
        "role": {
            "job_title": job_title,
            "seniority": seniority,
        },
        "job_context": {
            "business_context": f"Salary / Compensation: {salary_text}" if salary_text else None,
            "environment": (
                "fast-paced startup" if "startup" in text_lower
                else "hardware/lab environment" if lab_required
                else None
            ),
        },

        "responsibilities": responsibilities,
        "conventional_requirements": {
            "experience": experience,
            "technical_skills": technical_skills,
            "education": [],
            "certifications": [],
            "domain": [],
            "location": location,
            "work_mode": location.get("work_mode", "unspecified"),
            "travel": travel,
            "languages": [],
            "other": [],
        },
        "must_have_requirements": must_have_requirements,
        "preferred_requirements": preferred_requirements,
        "responsibility_requirement_mapping": responsibility_mapping,
        "requirement_interpretations": requirement_interpretations,
        "evidence_requirements": evidence_requirements,
        "non_conventional_parameters": non_conventional,
        "evaluation_rules": [
            "Classify every requirement as MUST_HAVE, PREFERRED, CONTEXTUAL, INFORMATIONAL, or AMBIGUOUS.",
            "Never fabricate candidate evidence.",
            "Never invent numeric weights; the backend scoring engine assigns weights deterministically.",
            (
                "Experience requirements (e.g. '5+ years Python') mean RELEVANT experience in that "
                "technology/domain, not total years of employment."
            ),
            (
                "Prioritize demonstrated, hands-on/professional/project evidence over isolated keyword "
                "mentions in skills lists."
            ),
            "Every DERIVED interpretation must cite verbatim JD text and explain why the derivation follows.",
        ],
        "unscored_rules": [
            "If a requirement cannot be evaluated from available candidate data, return UNCORED.",
            "Absence of evidence is not negative evidence unless the JD explicitly requires demonstrated proof.",
            "Contradictory evidence must resolve to UNCORED with an explanation, not a guess.",
        ],
        "prohibited_inferences": [
            "Do not infer protected characteristics (age, gender, race, religion, disability, marital status).",
            "Do not infer why a candidate left a previous role.",
            "Do not treat short tenure as automatically negative.",
            "Do not assume technology expertise from adjacent/related technologies without explicit evidence.",
            "Do not treat a skills-list keyword as equivalent to demonstrated hands-on experience.",
        ],
        "compliance_flags": compliance_flags,
        "ambiguities": ambiguities,
        "missing_information": missing_information,
        "ta_confirmation_required": [a["statement"] for a in ambiguities] + [f["flagged_text"] for f in compliance_flags],
        "candidate_analysis_instructions": [
            "Use this specification as the authoritative interpretation of the JD.",
            (
                "For every requirement: identify candidate evidence, determine evidence strength "
                "(strong/moderate/weak/insufficient), compare against the requirement, provide provenance, "
                "assign confidence, and mark UNCORED when evidence is insufficient."
            ),
            (
                "Evaluate experience requirements (e.g. '5+ years Python') as relevant experience "
                "in that specific technology, not total years of employment."
            ),
            (
                "Prioritize demonstrated hands-on professional or project experience over keyword-only "
                "mentions in skills sections."
            ),
            "Never fabricate candidate information or infer protected characteristics.",
            "Separate explicit candidate evidence from your own interpretation.",
        ],
    }
