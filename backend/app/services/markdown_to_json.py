"""
Schema-aware Markdown -> Canonical Object converter.

This is NOT a regex free-for-all. It walks the Markdown by section header
(matching the template produced by markdown_renderer.render_markdown) and
reconstructs a JobEvaluationSpecification, then runs it through Pydantic
validation. This lets a TA hand-edit the Markdown (e.g. reclassify a
requirement's priority, fix a typo, remove a flagged ambiguity) and have
those edits flow back into the canonical object and, from there, the JSON.

Design notes:
- We split on level-2 (`## `) headers to get section bodies.
- Sub-sections within sections are split on level-3 (`### `) headers.
- Bullet lines are parsed with small per-field grammars.
- Anything we cannot confidently parse is left out rather than guessed.

Section map (new 18-section layout):
  1.  Role Overview
  2.  Experience Requirements
  3.  Must-Have Requirements
  4.  Preferred Requirements
  5.  Responsibilities
  6.  Evidence Expectations
  7.  Evaluation Guidance
  8.  JD-Specific Parameters
  9.  Ambiguities
  10. Missing Information
  11. Compliance Flags
  12. Evaluation Priorities
  13. Conventional Requirements (Detail)
  14. Responsibility → Requirement Mapping
  15. Requirement Interpretations
  16. Prohibited Inferences
  17. TA Confirmation Required
  18. Source & Version Metadata
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.schemas.canonical import (
    Ambiguity,
    ComplianceFlag,
    ConventionalRequirements,
    EducationRequirement,
    CertificationRequirement,
    EvidenceSpec,
    ExperienceRequirement,
    JobContext,
    JobEvaluationSpecification,
    LocationInfo,
    MetadataInfo,
    MissingInfo,
    NonConventionalParameter,
    OtherRequirement,
    Priority,
    RequirementInterpretation,
    Responsibility,
    ResponsibilityRequirementMapping,
    RoleInfo,
    TechnicalSkill,
    TravelInfo,
    WorkMode,
    ConfidenceLevel,
    ExplicitOrDerived,
)


@dataclass
class MarkdownParseResult:
    spec: JobEvaluationSpecification
    warnings: List[str] = field(default_factory=list)


def _split_h2(md: str) -> Dict[str, str]:
    """Split on '## N. Title' headers -> {title_lower: body}."""
    sections: Dict[str, str] = {}
    pattern = re.compile(r"^##\s+\d+\.\s+(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(md))
    for i, m in enumerate(matches):
        title = m.group(1).strip().lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        sections[title] = md[start:end].strip()
    return sections


def _split_h3(body: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    pattern = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(body))
    for i, m in enumerate(matches):
        title = m.group(1).strip().lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[title] = body[start:end].strip()
    return sections


def _bullets(body: str) -> List[str]:
    items = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("- "):
            items.append(line[2:].strip())
    return [i for i in items if i and not i.startswith("_None") and not i.startswith("_No notable")]


def _kv_bullets(body: str) -> Dict[str, str]:
    """Parse '- **Key:** value' style bullets into a dict."""
    out: Dict[str, str] = {}
    for line in body.splitlines():
        m = re.match(r"-\s+\*\*(.+?):\*\*\s*(.*)", line.strip())
        if m:
            out[m.group(1).strip().lower()] = m.group(2).strip()
    return out


def _unspecified(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = v.strip()
    if v.lower() in ("", "_unspecified_", "unspecified", "none", "_none stated_", "_none identified._", "_no notable omissions detected._"):
        return None
    return v


def _parse_priority(text: str) -> Priority:
    m = re.search(r"\[([A-Z_]+)\]", text)
    if m and m.group(1) in Priority.__members__:
        return Priority[m.group(1)]
    return Priority.INFORMATIONAL


def _parse_eod(text: str) -> ExplicitOrDerived:
    """Parse explicit/derived from text containing [EXPLICIT] or [DERIVED]."""
    m = re.search(r"\[(EXPLICIT|DERIVED)\]", text.upper())
    if m:
        return ExplicitOrDerived.DERIVED if m.group(1) == "DERIVED" else ExplicitOrDerived.EXPLICIT
    return ExplicitOrDerived.EXPLICIT


def markdown_to_spec(md: str) -> MarkdownParseResult:
    warnings: List[str] = []
    h2 = _split_h2(md)

    def get(name: str) -> str:
        return h2.get(name, "")

    # ------------------------------------------------------------------ #
    # Section 1: Role Overview
    # ------------------------------------------------------------------ #
    role_kv = _kv_bullets(get("role overview"))
    role = RoleInfo(
        job_title=_unspecified(role_kv.get("job title")),
        role=_unspecified(role_kv.get("role")),
        seniority=_unspecified(role_kv.get("seniority")),
        department=_unspecified(role_kv.get("department")),
        employment_type=_unspecified(role_kv.get("employment type")),
        reporting_structure=_unspecified(role_kv.get("reporting structure")),
        team_context=_unspecified(role_kv.get("team context")),
    )

    # Parse location from role overview
    loc_str = _unspecified(role_kv.get("location / work mode"))
    city, country, work_mode_inline = None, None, "unspecified"
    if loc_str:
        wm_m = re.search(r"\((\w+)\)", loc_str)
        if wm_m:
            work_mode_inline = wm_m.group(1).lower()
        location_part = re.sub(r"\s*\(.*\)", "", loc_str).strip().rstrip(",")
        parts = [p.strip() for p in location_part.split(",")]
        if parts:
            city = _unspecified(parts[0])
        if len(parts) > 1:
            country = _unspecified(parts[1])
    office_attendance = _unspecified(role_kv.get("office attendance"))
    reloc_raw = _unspecified(role_kv.get("relocation required"))
    reloc = None if reloc_raw is None else reloc_raw.lower() == "true"

    location = LocationInfo(
        country=country,
        city=city,
        work_mode=WorkMode(work_mode_inline) if work_mode_inline in WorkMode._value2member_map_ else WorkMode.UNSPECIFIED,
        office_attendance=office_attendance,
        relocation_required=reloc,
    )

    job_context = JobContext(
        environment=_unspecified(role_kv.get("environment")),
        business_context=_unspecified(role_kv.get("business context")),
        team_size=_unspecified(role_kv.get("team size")),
    )

    # ------------------------------------------------------------------ #
    # Section 2: Experience Requirements
    # ------------------------------------------------------------------ #
    experience = []
    for line in get("experience requirements").splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        b = line[2:].strip()
        if b.startswith("_"):
            continue
        # Format: **[PRIORITY]** [EOD] description (min X yrs)
        prio = _parse_priority(b)
        eod = _parse_eod(b)
        # Strip the markup tokens to get description
        desc = re.sub(r"\*\*\[[A-Z_]+\]\*\*", "", b).strip()
        desc = re.sub(r"\[(?:EXPLICIT|DERIVED)\]", "", desc, flags=re.IGNORECASE).strip()
        min_yrs_m = re.search(r"\(min ([\d.]+) yrs?\)", desc)
        min_years = float(min_yrs_m.group(1)) if min_yrs_m else None
        desc = re.sub(r"\s*\(min [\d.]+ yrs?\)", "", desc).strip()
        if desc:
            experience.append(ExperienceRequirement(description=desc, min_years=min_years, priority=prio, explicit_or_derived=eod))

    # ------------------------------------------------------------------ #
    # Section 5: Responsibilities
    # ------------------------------------------------------------------ #
    responsibilities = []
    for b in _bullets(get("responsibilities")):
        m = re.match(r"\*\*\((\w+)\)\*\*\s*(.+)", b)
        if m:
            responsibilities.append(Responsibility(kind=m.group(1), description=m.group(2).strip()))
        else:
            m2 = re.match(r"\((\w+)\)\s*(.+)", b)
            if m2:
                responsibilities.append(Responsibility(kind=m2.group(1), description=m2.group(2).strip()))
            else:
                responsibilities.append(Responsibility(kind="primary", description=b))

    # ------------------------------------------------------------------ #
    # Section 13: Conventional Requirements (Detail) — Technical Skills
    # ------------------------------------------------------------------ #
    conv_body = get("conventional requirements (detail)")
    h3 = _split_h3(conv_body)

    technical_skills = []
    for b in _bullets(h3.get("technical skills", "")):
        m = re.match(r"(.+?)\s*\((.+?)\)\s*\[([A-Z_]+)\]", b)
        if m:
            name, category, prio = m.groups()
            eod = _parse_eod(b)
            technical_skills.append(
                TechnicalSkill(
                    name=name.strip(),
                    category=category.strip(),
                    priority=Priority[prio] if prio in Priority.__members__ else Priority.INFORMATIONAL,
                    explicit_or_derived=eod,
                )
            )
        else:
            warnings.append(f"Could not parse technical skill line: {b!r}")

    education = [
        EducationRequirement(description=re.sub(r"\s*\[.*\]$", "", b), priority=_parse_priority(b))
        for b in _bullets(h3.get("education", ""))
    ]
    certifications = [
        CertificationRequirement(description=re.sub(r"\s*\[.*\]$", "", b), priority=_parse_priority(b))
        for b in _bullets(h3.get("certifications", ""))
    ]
    domain = _bullets(h3.get("domain", ""))

    travel_kv: Dict[str, str] = {}
    for b in _bullets(h3.get("travel", "")):
        if ":" in b:
            k, v = b.split(":", 1)
            travel_kv[k.strip().lower()] = v.strip()
    required_raw = _unspecified(travel_kv.get("required"))
    travel = TravelInfo(
        required=None if required_raw is None else required_raw.lower() == "true",
        description=_unspecified(travel_kv.get("details")),
    )

    languages = _bullets(h3.get("languages", ""))

    other = []
    for b in _bullets(h3.get("other requirements", "")):
        m = re.match(r"\[(.+?)\]\s*(.+?)\s*\[([A-Z_]+)\]", b)
        if m:
            cat, desc, prio = m.groups()
            other.append(
                OtherRequirement(
                    category=cat.strip(),
                    description=desc.strip(),
                    priority=Priority[prio] if prio in Priority.__members__ else Priority.INFORMATIONAL,
                )
            )
        else:
            warnings.append(f"Could not parse 'other requirement' line: {b!r}")

    conventional_requirements = ConventionalRequirements(
        experience=experience,
        technical_skills=technical_skills,
        education=education,
        certifications=certifications,
        domain=domain,
        location=location,
        work_mode=location.work_mode,
        travel=travel,
        languages=languages,
        other=other,
    )

    # ------------------------------------------------------------------ #
    # Sections 3 & 4: Must-Have / Preferred
    # ------------------------------------------------------------------ #
    must_have_requirements = _bullets(get("must-have requirements"))
    preferred_requirements = _bullets(get("preferred requirements"))

    # ------------------------------------------------------------------ #
    # Section 6: Evidence Expectations
    # ------------------------------------------------------------------ #
    evidence_requirements = []
    ev_block = get("evidence expectations")
    ev_h3 = _split_h3(ev_block)
    for name, body in ev_h3.items():
        kv: Dict[str, str] = {}
        for b in _bullets(body):
            if ":" in b:
                k, v = b.split(":", 1)
                kv[k.strip().lower()] = v.strip()
        prio_raw = (kv.get("priority") or "INFORMATIONAL").strip()
        conf_raw = (kv.get("confidence") or "medium").strip().lower()
        eod_raw = (kv.get("explicit/derived") or "explicit").strip().lower()
        evidence_requirements.append(
            EvidenceSpec(
                requirement=name,
                priority=Priority[prio_raw] if prio_raw in Priority.__members__ else Priority.INFORMATIONAL,
                explicit_or_derived=ExplicitOrDerived.DERIVED if "derived" in eod_raw else ExplicitOrDerived.EXPLICIT,
                evidence_to_look_for=[e.strip() for e in (kv.get("evidence to look for") or "").split(",") if e.strip()],
                strong_evidence=_unspecified(kv.get("strong evidence")),
                moderate_evidence=_unspecified(kv.get("moderate evidence")),
                weak_evidence=_unspecified(kv.get("weak evidence")),
                insufficient_evidence=_unspecified(kv.get("insufficient evidence")),
                prohibited_inference=_unspecified(kv.get("prohibited inference")),
                confidence=ConfidenceLevel(conf_raw) if conf_raw in ConfidenceLevel._value2member_map_ else ConfidenceLevel.MEDIUM,
            )
        )

    # ------------------------------------------------------------------ #
    # Section 7: Evaluation Guidance
    # ------------------------------------------------------------------ #
    eval_body = get("evaluation guidance")
    evaluation_rules = _bullets(eval_body)
    # UNCORED rules are in a bold subsection of section 7
    unscored_rules = []
    uncored_m = re.search(r"\*\*UNCORED Rules\*\*.+?\n((?:-[^\n]+\n?)+)", eval_body)
    if uncored_m:
        unscored_rules = [b[2:].strip() for b in uncored_m.group(1).splitlines() if b.strip().startswith("- ")]

    # ------------------------------------------------------------------ #
    # Section 8: JD-Specific Parameters
    # ------------------------------------------------------------------ #
    non_conventional = []
    nc_block = get("jd-specific parameters")
    nc_h3 = _split_h3(nc_block)
    for header, body in nc_h3.items():
        m = re.match(r"(.+)\((.+)\)", header)
        name = m.group(1).strip() if m else header
        category = m.group(2).strip() if m else "uncategorized"
        kv = {}
        for b in _bullets(body):
            if ":" in b:
                k, v = b.split(":", 1)
                kv[k.strip().lower()] = v.strip()
        eod_raw = (kv.get("explicit/derived") or "derived").strip().lower()
        conf_raw = (kv.get("confidence") or "medium").strip().lower()
        non_conventional.append(
            NonConventionalParameter(
                parameter_name=name,
                category=category,
                why_it_is_relevant=kv.get("why it matters for this jd", ""),
                jd_evidence=kv.get("jd evidence", "").strip('"'),
                explicit_or_derived=ExplicitOrDerived.DERIVED if "derived" in eod_raw else ExplicitOrDerived.EXPLICIT,
                evaluation_guidance=kv.get("evaluation guidance", ""),
                evidence_to_look_for=[e.strip() for e in (kv.get("evidence to look for") or "").split(",") if e.strip()],
                strong_evidence=_unspecified(kv.get("strong evidence")),
                moderate_evidence=_unspecified(kv.get("moderate evidence")),
                weak_evidence=_unspecified(kv.get("weak evidence")),
                prohibited_inference=_unspecified(kv.get("prohibited inference")),
                confidence=ConfidenceLevel(conf_raw) if conf_raw in ConfidenceLevel._value2member_map_ else ConfidenceLevel.MEDIUM,
                unscored_if=_unspecified(kv.get("return uncored if")),
            )
        )

    # ------------------------------------------------------------------ #
    # Section 9: Ambiguities
    # ------------------------------------------------------------------ #
    ambiguities = []
    amb_block = get("ambiguities")
    for chunk in amb_block.split("\n- **\""):
        chunk = chunk.strip()
        if not chunk:
            continue
        if not chunk.startswith('"'):
            chunk = '"' + chunk
        m = re.match(r'"(.+?)"\*\*\s*—\s*(.+)', chunk)
        if not m:
            continue
        statement, rest = m.groups()
        suggested_m = re.search(r"Suggested interpretation:\s*(.+)", rest)
        evidence_m = re.search(r"Evidence required:\s*(.+)", rest)
        ta_m = re.search(r"TA confirmation required:\s*(True|False)", rest)
        why_ambiguous = rest.split("\n")[0].strip()
        ambiguities.append(
            Ambiguity(
                statement=statement,
                why_ambiguous=why_ambiguous,
                suggested_interpretation=suggested_m.group(1).strip() if suggested_m else None,
                evidence_required=[e.strip() for e in evidence_m.group(1).split(",")] if evidence_m else [],
                ta_confirmation_required=(ta_m.group(1) == "True") if ta_m else True,
            )
        )

    # ------------------------------------------------------------------ #
    # Section 10: Missing Information
    # ------------------------------------------------------------------ #
    missing_information = []
    mi_block = get("missing information")
    for b in _bullets(mi_block):
        m = re.match(r"\*\*(.+?):\*\*\s*(.*)", b)
        if m:
            field_name, why = m.groups()
            missing_information.append(
                MissingInfo(
                    field=field_name.strip(),
                    why_it_matters=why.strip(),
                )
            )
        else:
            warnings.append(f"Could not parse missing information line: {b!r}")

    # ------------------------------------------------------------------ #
    # Section 11: Compliance Flags
    # ------------------------------------------------------------------ #
    compliance_flags = []
    for b in _bullets(get("compliance flags")):
        m = re.match(r'\*\*Flagged text:\*\*\s*"(.+?)"\s*—\s*(.+?)\s*\(`(.+?)`\)\.\s*(.+)', b)
        if m:
            flagged_text, concern, category, action = m.groups()
            compliance_flags.append(
                ComplianceFlag(flagged_text=flagged_text, concern=concern, category=category, recommended_action=action)
            )
        else:
            warnings.append(f"Could not parse compliance flag line: {b!r}")

    # ------------------------------------------------------------------ #
    # Section 12: Evaluation Priorities -> candidate_analysis_instructions
    # ------------------------------------------------------------------ #
    pri_block = get("evaluation priorities")
    candidate_analysis_instructions = [
        re.sub(r"^\d+\.\s*", "", line.strip())
        for line in pri_block.splitlines()
        if re.match(r"^\d+\.\s*", line.strip())
    ]

    # ------------------------------------------------------------------ #
    # Section 14: Responsibility → Requirement Mapping
    # ------------------------------------------------------------------ #
    mapping = []
    resp_block = (
        get("responsibility → requirement mapping")
        or get("responsibility -> requirement mapping")
    )
    for chunk in re.split(r"\n\s*\n", resp_block):
        m = re.search(r"\*\*Responsibility:\*\*\s*(.+)", chunk)
        if not m:
            continue
        responsibility = m.group(1).strip()
        caps = _bullets(chunk)
        rationale_m = re.search(r"_Rationale:\s*(.+?)_", chunk)
        mapping.append(
            ResponsibilityRequirementMapping(
                responsibility=responsibility,
                required_capabilities=caps,
                rationale=rationale_m.group(1) if rationale_m else None,
            )
        )

    # ------------------------------------------------------------------ #
    # Section 15: Requirement Interpretations
    # ------------------------------------------------------------------ #
    interpretations = []
    interp_block = get("requirement interpretations")
    for chunk in re.split(r"\n\s*\n", interp_block):
        m = re.search(r"\*\*Explicit Requirement:\*\*\s*(.+)", chunk)
        if not m:
            continue
        explicit_requirement = m.group(1).strip()
        derived = _bullets(chunk)
        rationale_m = re.search(r"_Rationale:\s*(.+?)_", chunk)
        interpretations.append(
            RequirementInterpretation(
                explicit_requirement=explicit_requirement,
                derived_interpretation=derived,
                rationale=rationale_m.group(1) if rationale_m else None,
            )
        )

    # ------------------------------------------------------------------ #
    # Section 16: Prohibited Inferences
    # ------------------------------------------------------------------ #
    prohibited_inferences = _bullets(get("prohibited inferences"))

    # ------------------------------------------------------------------ #
    # Section 17: TA Confirmation Required
    # ------------------------------------------------------------------ #
    ta_confirmation_required = _bullets(get("ta confirmation required"))

    # ------------------------------------------------------------------ #
    # Section 18: Metadata
    # ------------------------------------------------------------------ #
    meta_kv: Dict[str, str] = {}
    for b in _bullets(get("source & version metadata")):
        if ":" in b:
            k, v = b.split(":", 1)
            meta_kv[k.strip().lower()] = v.strip()
    metadata = MetadataInfo(
        jd_id=_unspecified(meta_kv.get("jd id")),
        jd_version=int(meta_kv["jd version"]) if _unspecified(meta_kv.get("jd version")) and meta_kv["jd version"].isdigit() else None,
        specification_version=(
            int(meta_kv["specification version"])
            if _unspecified(meta_kv.get("specification version")) and meta_kv["specification version"].isdigit()
            else None
        ),
        prompt_version=_unspecified(meta_kv.get("prompt version")),
        model_version=_unspecified(meta_kv.get("model version")),
    )

    spec = JobEvaluationSpecification(
        metadata=metadata,
        role=role,
        job_context=job_context,
        responsibilities=responsibilities,
        conventional_requirements=conventional_requirements,
        must_have_requirements=must_have_requirements,
        preferred_requirements=preferred_requirements,
        responsibility_requirement_mapping=mapping,
        requirement_interpretations=interpretations,
        evidence_requirements=evidence_requirements,
        non_conventional_parameters=non_conventional,
        evaluation_rules=evaluation_rules,
        unscored_rules=unscored_rules,
        prohibited_inferences=prohibited_inferences,
        compliance_flags=compliance_flags,
        ambiguities=ambiguities,
        missing_information=missing_information,
        ta_confirmation_required=ta_confirmation_required,
        candidate_analysis_instructions=candidate_analysis_instructions,
    )

    return MarkdownParseResult(spec=spec, warnings=warnings)
