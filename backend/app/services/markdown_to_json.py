"""
Schema-aware Markdown -> Canonical Object converter.

This walks the Markdown by section header (matching the 8-section target
template produced by markdown_renderer.render_markdown) and reconstructs
a JobEvaluationSpecification, then runs it through Pydantic validation.

Section map (8 target sections):
  1. Role Overview
  2. Requirements (Must-Have & Preferred)
  3. Responsibilities
  4. Evidence & Evaluation Rules
  5. JD-Specific Evaluation Parameters
  6. Ambiguities & Missing Information
  7. Evaluation Priorities
  8. Compliance
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.schemas.canonical import (
    Ambiguity,
    ComplianceFlag,
    ConventionalRequirements,
    EvidenceSpec,
    ExperienceRequirement,
    JobContext,
    JobEvaluationSpecification,
    LocationInfo,
    MetadataInfo,
    MissingInfo,
    NonConventionalParameter,
    Priority,
    Responsibility,
    RoleInfo,
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
    return [i for i in items if i and not i.startswith("_None") and not i.startswith("_No notable") and not i.startswith("_Absent")]


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
    if v.lower() in ("", "_unspecified_", "unspecified", "none", "_none stated_", "_none identified._", "_no notable omissions detected._", "_none detected._"):
        return None
    return v


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
        reporting_structure=_unspecified(role_kv.get("reporting to") or role_kv.get("reporting structure")),
        team_context=_unspecified(role_kv.get("team context")),
    )

    # Location / Work Mode
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
    # Section 2: Requirements (Must-Have & Preferred)
    # ------------------------------------------------------------------ #
    req_body = get("requirements")
    req_h3 = _split_h3(req_body)

    must_have_raw = _bullets(req_h3.get("must-have", ""))
    preferred_requirements = _bullets(req_h3.get("preferred", ""))

    # Separate experience requirement strings from general must_have
    experience = []
    must_have_requirements = []
    for item in must_have_raw:
        m_yrs = re.search(r"\((\d+(?:\.\d+)?)\+\s*yrs?\)", item)
        if m_yrs:
            min_yrs = float(m_yrs.group(1))
            desc = re.sub(r"\s*\(\d+(?:\.\d+)?\+\s*yrs?\)", "", item).strip()
            experience.append(
                ExperienceRequirement(
                    description=desc,
                    min_years=min_yrs,
                    priority=Priority.MUST_HAVE,
                    explicit_or_derived=ExplicitOrDerived.EXPLICIT,
                )
            )
            must_have_requirements.append(item)
        else:
            must_have_requirements.append(item)

    conventional_requirements = ConventionalRequirements(
        experience=experience,
        location=location,
        work_mode=location.work_mode,
    )

    # ------------------------------------------------------------------ #
    # Section 3: Responsibilities
    # ------------------------------------------------------------------ #
    responsibilities = []
    for b in _bullets(get("responsibilities")):
        responsibilities.append(Responsibility(kind="primary", description=b))

    # ------------------------------------------------------------------ #
    # Section 4: Evidence & Evaluation Rules
    # ------------------------------------------------------------------ #
    ev_rules_body = get("evidence & evaluation rules")
    ev_h3 = _split_h3(ev_rules_body)

    evidence_requirements = []
    for name, body in ev_h3.items():
        # Handle evidence spec block
        kv: Dict[str, str] = {}
        evidence_list = []
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("**Evidence:**"):
                ev_str = line.replace("**Evidence:**", "").strip()
                evidence_list = [e.strip() for e in ev_str.split(",") if e.strip()]
            elif line.startswith("- **"):
                m = re.match(r"-\s+\*\*(.+?):\*\*\s*(.*)", line)
                if m:
                    kv[m.group(1).strip().lower()] = m.group(2).strip()

        strong = _unspecified(kv.get("strong"))
        moderate = _unspecified(kv.get("moderate"))
        weak = _unspecified(kv.get("weak"))
        insufficient = _unspecified(kv.get("insufficient (→ uncored)") or kv.get("insufficient"))
        prohibited = _unspecified(kv.get("do not infer"))

        evidence_requirements.append(
            EvidenceSpec(
                requirement=name,
                priority=Priority.MUST_HAVE,
                explicit_or_derived=ExplicitOrDerived.EXPLICIT,
                evidence_to_look_for=evidence_list,
                strong_evidence=strong,
                moderate_evidence=moderate,
                weak_evidence=weak,
                insufficient_evidence=insufficient,
                prohibited_inference=prohibited,
                confidence=ConfidenceLevel.HIGH,
            )
        )

    # Extract process rules, uncored rules, prohibited inferences
    evaluation_rules = []
    unscored_rules = []
    prohibited_inferences = []

    proc_m = re.search(r"\*\*Evaluation Process Rules\*\*\s*\n((?:-[^\n]+\n?)+)", ev_rules_body)
    if proc_m:
        evaluation_rules = [b[2:].strip() for b in proc_m.group(1).splitlines() if b.strip().startswith("- ")]

    unc_m = re.search(r"\*\*Return UNCORED when:\*\*\s*\n((?:-[^\n]+\n?)+)", ev_rules_body)
    if unc_m:
        unscored_rules = [b[2:].strip() for b in unc_m.group(1).splitlines() if b.strip().startswith("- ")]

    prohib_m = re.search(r"\*\*Prohibited Inferences\*\*\s*\n((?:-[^\n]+\n?)+)", ev_rules_body)
    if prohib_m:
        prohibited_inferences = [b[2:].strip() for b in prohib_m.group(1).splitlines() if b.strip().startswith("- ")]

    # ------------------------------------------------------------------ #
    # Section 5: JD-Specific Evaluation Parameters
    # ------------------------------------------------------------------ #
    non_conventional = []
    nc_block = get("jd-specific evaluation parameters")
    nc_h3 = _split_h3(nc_block)
    for name, body in nc_h3.items():
        lines = [l.strip() for l in body.splitlines() if l.strip()]
        why = ""
        evidence_list = []
        unscored_if = None
        for l in lines:
            if l.startswith("**Evidence:**"):
                ev_str = l.replace("**Evidence:**", "").strip()
                evidence_list = [e.strip() for e in ev_str.split(",") if e.strip()]
            elif l.startswith("- **Return UNCORED if:**"):
                unscored_if = _unspecified(l.replace("- **Return UNCORED if:**", "").strip())
            elif not l.startswith("-"):
                if not why:
                    why = l

        non_conventional.append(
            NonConventionalParameter(
                parameter_name=name,
                category="jd_specific",
                why_it_is_relevant=why or name,
                jd_evidence=why,
                explicit_or_derived=ExplicitOrDerived.DERIVED,
                evaluation_guidance=why,
                evidence_to_look_for=evidence_list,
                unscored_if=unscored_if,
            )
        )

    # ------------------------------------------------------------------ #
    # Section 6: Ambiguities & Missing Information
    # ------------------------------------------------------------------ #
    ambiguities = []
    missing_information = []
    amb_missing_block = get("ambiguities & missing information")

    # Ambiguities sub-block
    if "**Ambiguities**" in amb_missing_block:
        amb_chunk = amb_missing_block.split("**Ambiguities**")[1]
        if "**Missing Information**" in amb_chunk:
            amb_chunk = amb_chunk.split("**Missing Information**")[0]
        for line in amb_chunk.splitlines():
            line = line.strip()
            if line.startswith("- **\""):
                m = re.match(r"-\s+\*\*\"(.+?)\"\*\*\s*—\s*(.+)", line)
                if m:
                    stmt, why = m.groups()
                    ta_req = "ta confirmation required" in why.lower()
                    why_clean = re.sub(r"\s*_\(TA confirmation required\)_", "", why, flags=re.IGNORECASE).strip()
                    ambiguities.append(
                        Ambiguity(
                            statement=stmt,
                            why_ambiguous=why_clean,
                            ta_confirmation_required=ta_req,
                        )
                    )

    # Missing Information sub-block
    if "**Missing Information**" in amb_missing_block:
        mi_chunk = amb_missing_block.split("**Missing Information**")[1]
        for line in mi_chunk.splitlines():
            line = line.strip()
            if line.startswith("- **"):
                m = re.match(r"-\s+\*\*(.+?):\*\*\s*(.*)", line)
                if m:
                    f_name, why_val = m.groups()
                    missing_information.append(
                        MissingInfo(
                            field=f_name.strip(),
                            why_it_matters=why_val.strip(),
                        )
                    )

    # ------------------------------------------------------------------ #
    # Section 7: Evaluation Priorities
    # ------------------------------------------------------------------ #
    pri_block = get("evaluation priorities")
    candidate_instructions = [
        re.sub(r"^\d+\.\s*", "", line.strip())
        for line in pri_block.splitlines()
        if re.match(r"^\d+\.\s*", line.strip())
    ]

    # ------------------------------------------------------------------ #
    # Section 8: Compliance
    # ------------------------------------------------------------------ #
    compliance_flags = []
    for b in _bullets(get("compliance")):
        m = re.match(r'\*\*\"(.+?)\"\*\*\s*—\s*(.+?)\s*\(`(.+?)`\)\.\s*_(.+)_\s*', b)
        if m:
            flagged_text, concern, category, action = m.groups()
            compliance_flags.append(
                ComplianceFlag(flagged_text=flagged_text, concern=concern, category=category, recommended_action=action)
            )

    spec = JobEvaluationSpecification(
        metadata=MetadataInfo(),
        role=role,
        job_context=job_context,
        responsibilities=responsibilities,
        conventional_requirements=conventional_requirements,
        must_have_requirements=must_have_requirements,
        preferred_requirements=preferred_requirements,
        evidence_requirements=evidence_requirements,
        non_conventional_parameters=non_conventional,
        evaluation_rules=evaluation_rules,
        unscored_rules=unscored_rules,
        prohibited_inferences=prohibited_inferences,
        compliance_flags=compliance_flags,
        ambiguities=ambiguities,
        missing_information=missing_information,
        candidate_analysis_instructions=candidate_instructions,
    )

    return MarkdownParseResult(spec=spec, warnings=warnings)
