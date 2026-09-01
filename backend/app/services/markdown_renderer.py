"""
Deterministic Canonical Object -> Markdown renderer.

Markdown is a VIEW of the canonical JobEvaluationSpecification, never a
separate source of truth. Given the same object, this renderer always
produces the same Markdown (no LLM calls here).

Section layout (matches the 12-section target structure):
  1. Role Overview
  2. Experience Requirements
  3. Must-Have Requirements
  4. Preferred Requirements
  5. Responsibilities
  6. Evidence Expectations
  7. Evaluation Guidance
  8. JD-Specific Parameters
  9. Ambiguities
  10. Missing Information
  11. Compliance Flags
  12. Evaluation Priorities
  --- (supplementary sections follow) ---
  13. Requirement Interpretations
  14. Prohibited Inferences
  15. TA Confirmation Required
  16. Candidate Analysis Instructions
  17. Source & Version Metadata
"""
from __future__ import annotations

from app.schemas.canonical import JobEvaluationSpecification


def _bullet_list(items: list[str], empty: str = "_None identified._") -> str:
    if not items:
        return empty
    return "\n".join(f"- {i}" for i in items)


def _source_ref(source) -> str:
    """Render a SourceRef as a compact inline citation."""
    if source is None:
        return ""
    parts = []
    if source.text:
        parts.append(f'> "{source.text}"')
    if source.section:
        parts.append(f"_(section: {source.section})_")
    return "  " + " ".join(parts) if parts else ""


def render_markdown(spec: JobEvaluationSpecification) -> str:
    md: list[str] = []
    md.append("# Job Evaluation Specification\n")

    # ------------------------------------------------------------------ #
    # Section 1: Role Overview
    # ------------------------------------------------------------------ #
    md.append("## 1. Role Overview\n")
    r = spec.role
    md.append(f"- **Job Title:** {r.job_title or '_unspecified_'}")
    md.append(f"- **Role:** {r.role or '_unspecified_'}")
    md.append(f"- **Seniority:** {r.seniority or '_unspecified_'}")
    md.append(f"- **Department:** {r.department or '_unspecified_'}")
    md.append(f"- **Employment Type:** {r.employment_type or '_unspecified_'}")
    md.append(f"- **Reporting Structure:** {r.reporting_structure or '_unspecified_'}")
    md.append(f"- **Team Context:** {r.team_context or '_unspecified_'}")
    # Location / Work Mode inline summary
    loc = spec.conventional_requirements.location
    wm = loc.work_mode.value if hasattr(loc.work_mode, "value") else loc.work_mode
    city = loc.city or "_unspecified_"
    country = loc.country or ""
    location_str = f"{city}{', ' + country if country else ''} ({wm})"
    md.append(f"- **Location / Work Mode:** {location_str}")
    if loc.office_attendance:
        md.append(f"- **Office Attendance:** {loc.office_attendance}")
    reloc = loc.relocation_required
    md.append(f"- **Relocation Required:** {reloc if reloc is not None else '_unspecified_'}")
    # Job context inline
    jc = spec.job_context
    if jc.environment:
        md.append(f"- **Environment:** {jc.environment}")
    if jc.business_context:
        md.append(f"- **Business Context:** {jc.business_context}")
    if jc.team_size:
        md.append(f"- **Team Size:** {jc.team_size}")
    md.append("")

    # ------------------------------------------------------------------ #
    # Section 2: Experience Requirements
    # ------------------------------------------------------------------ #
    md.append("## 2. Experience Requirements\n")
    cr = spec.conventional_requirements
    if cr.experience:
        for e in cr.experience:
            eod = e.explicit_or_derived.value if hasattr(e.explicit_or_derived, "value") else e.explicit_or_derived
            yrs = f" (min {e.min_years} yrs)" if e.min_years is not None else ""
            md.append(f"- **[{e.priority.value}]** [{eod.upper()}] {e.description}{yrs}")
            if e.source:
                md.append(f"  - _JD text:_ \"{e.source.text}\"")
    else:
        md.append("_No explicit experience requirements stated._")
    md.append("")

    # ------------------------------------------------------------------ #
    # Section 3: Must-Have Requirements
    # ------------------------------------------------------------------ #
    md.append("## 3. Must-Have Requirements\n")
    md.append(_bullet_list(spec.must_have_requirements))
    md.append("")

    # ------------------------------------------------------------------ #
    # Section 4: Preferred Requirements
    # ------------------------------------------------------------------ #
    md.append("## 4. Preferred Requirements\n")
    md.append(_bullet_list(spec.preferred_requirements))
    md.append("")

    # ------------------------------------------------------------------ #
    # Section 5: Responsibilities
    # ------------------------------------------------------------------ #
    md.append("## 5. Responsibilities\n")
    if spec.responsibilities:
        for res in spec.responsibilities:
            md.append(f"- **({res.kind})** {res.description}")
    else:
        md.append("_None identified._")
    md.append("")

    # ------------------------------------------------------------------ #
    # Section 6: Evidence Expectations
    # ------------------------------------------------------------------ #
    md.append("## 6. Evidence Expectations\n")
    md.append(
        "_How the downstream Candidate Analysis LLM should judge evidence "
        "for each requirement. Evidence strength must always be based on "
        "the candidate's own materials — never assumed or inferred from "
        "adjacent technologies or job titles._\n"
    )
    if not spec.evidence_requirements:
        md.append("_None specified._\n")
    for ev in spec.evidence_requirements:
        eod = ev.explicit_or_derived.value if hasattr(ev.explicit_or_derived, "value") else ev.explicit_or_derived
        md.append(f"### {ev.requirement}")
        md.append(f"- **Priority:** {ev.priority.value}")
        md.append(f"- **Explicit/Derived:** {eod}")
        md.append(f"- **Confidence:** {ev.confidence.value if hasattr(ev.confidence, 'value') else ev.confidence}")
        if ev.evidence_to_look_for:
            md.append(f"- **Evidence to look for:** {', '.join(ev.evidence_to_look_for)}")
        md.append(f"- **Strong evidence:** {ev.strong_evidence or '_unspecified_'}")
        md.append(f"- **Moderate evidence:** {ev.moderate_evidence or '_unspecified_'}")
        md.append(f"- **Weak evidence:** {ev.weak_evidence or '_unspecified_'}")
        md.append(f"- **Insufficient evidence:** {ev.insufficient_evidence or '_unspecified_'}")
        md.append(f"- **Prohibited inference:** {ev.prohibited_inference or '_none stated_'}")
        md.append("")

    # ------------------------------------------------------------------ #
    # Section 7: Evaluation Guidance
    # ------------------------------------------------------------------ #
    md.append("## 7. Evaluation Guidance\n")
    md.append(
        "_Rules governing how the Candidate Analysis LLM must reason about "
        "evidence. These are process rules, not scoring weights._\n"
    )
    md.append(_bullet_list(spec.evaluation_rules))
    md.append("")
    if spec.unscored_rules:
        md.append("**UNCORED Rules** (return UNCORED when these apply):\n")
        md.append(_bullet_list(spec.unscored_rules))
        md.append("")

    # ------------------------------------------------------------------ #
    # Section 8: JD-Specific Parameters
    # ------------------------------------------------------------------ #
    md.append("## 8. JD-Specific Parameters\n")
    md.append(
        "_Non-conventional evaluation parameters derived from THIS specific JD. "
        "Each parameter includes verbatim JD evidence and a WHY explanation. "
        "Parameters not supported by JD evidence are excluded._\n"
    )
    if not spec.non_conventional_parameters:
        md.append("_None identified — no JD evidence supported additional parameters._\n")
    for p in spec.non_conventional_parameters:
        eod = p.explicit_or_derived.value if hasattr(p.explicit_or_derived, "value") else p.explicit_or_derived
        conf = p.confidence.value if hasattr(p.confidence, "value") else p.confidence
        md.append(f"### {p.parameter_name} ({p.category})")
        md.append(f"- **Explicit/Derived:** {eod}")
        md.append(f"- **Why it matters for this JD:** {p.why_it_is_relevant}")
        md.append(f"- **JD evidence:** \"{p.jd_evidence}\"")
        md.append(f"- **Evaluation guidance:** {p.evaluation_guidance}")
        if p.evidence_to_look_for:
            md.append(f"- **Evidence to look for:** {', '.join(p.evidence_to_look_for)}")
        md.append(f"- **Strong evidence:** {p.strong_evidence or '_unspecified_'}")
        md.append(f"- **Moderate evidence:** {p.moderate_evidence or '_unspecified_'}")
        md.append(f"- **Weak evidence:** {p.weak_evidence or '_unspecified_'}")
        md.append(f"- **Confidence:** {conf}")
        md.append(f"- **Prohibited inference:** {p.prohibited_inference or '_none stated_'}")
        if p.unscored_if:
            md.append(f"- **Return UNCORED if:** {p.unscored_if}")
        md.append("")

    # ------------------------------------------------------------------ #
    # Section 9: Ambiguities
    # ------------------------------------------------------------------ #
    md.append("## 9. Ambiguities\n")
    if not spec.ambiguities:
        md.append("_None detected._\n")
    for a in spec.ambiguities:
        md.append(f"- **\"{a.statement}\"** — {a.why_ambiguous}")
        if a.suggested_interpretation:
            md.append(f"  - Suggested interpretation: {a.suggested_interpretation}")
        if a.evidence_required:
            md.append(f"  - Evidence required: {', '.join(a.evidence_required)}")
        md.append(f"  - TA confirmation required: {a.ta_confirmation_required}")
    md.append("")

    # ------------------------------------------------------------------ #
    # Section 10: Missing Information
    # ------------------------------------------------------------------ #
    md.append("## 10. Missing Information\n")
    md.append(
        "_These fields are absent from the JD. Missing ≠ not required — "
        "the downstream LLM must not fabricate values or assume defaults._\n"
    )
    if not spec.missing_information:
        md.append("_No notable omissions detected._\n")
    for mi in spec.missing_information:
        md.append(f"- **{mi.field}:** {mi.why_it_matters}")
        if mi.suggested_action:
            md.append(f"  - Suggested action: {mi.suggested_action}")
    md.append("")

    # ------------------------------------------------------------------ #
    # Section 11: Compliance Flags
    # ------------------------------------------------------------------ #
    md.append("## 11. Compliance Flags\n")
    if not spec.compliance_flags:
        md.append("_None detected._\n")
    for cf in spec.compliance_flags:
        md.append(
            f"- **Flagged text:** \"{cf.flagged_text}\" — {cf.concern} "
            f"(`{cf.category}`). {cf.recommended_action}"
        )
    md.append("")

    # ------------------------------------------------------------------ #
    # Section 12: Evaluation Priorities
    # ------------------------------------------------------------------ #
    md.append("## 12. Evaluation Priorities\n")
    md.append(
        "_Summary of what a downstream candidate evaluation must prioritise, "
        "in order of importance derived from the JD._\n"
    )
    if spec.candidate_analysis_instructions:
        for i, instr in enumerate(spec.candidate_analysis_instructions, start=1):
            md.append(f"{i}. {instr}")
    else:
        md.append("_No explicit evaluation priorities extracted._")
    md.append("")

    # ------------------------------------------------------------------ #
    # Supplementary sections (for completeness / TA review)
    # ------------------------------------------------------------------ #

    # 13. Conventional Requirements (detail view)
    md.append("## 13. Conventional Requirements (Detail)\n")

    md.append("### Technical Skills")
    if cr.technical_skills:
        for t in cr.technical_skills:
            eod = t.explicit_or_derived.value if hasattr(t.explicit_or_derived, "value") else t.explicit_or_derived
            md.append(f"- {t.name} ({t.category}) [{t.priority.value}] [{eod.upper()}]")
    else:
        md.append("_None identified._")
    md.append("")

    md.append("### Education")
    md.append(_bullet_list([f"{e.description} [{e.priority.value}]" for e in cr.education]))
    md.append("")

    md.append("### Certifications")
    md.append(_bullet_list([f"{c.description} [{c.priority.value}]" for c in cr.certifications]))
    md.append("")

    md.append("### Domain")
    md.append(_bullet_list(cr.domain))
    md.append("")

    md.append("### Travel")
    md.append(f"- Required: {cr.travel.required if cr.travel.required is not None else '_unspecified_'}")
    md.append(f"- Details: {cr.travel.description or '_none stated_'}\n")

    md.append("### Languages")
    md.append(_bullet_list(cr.languages))
    md.append("")

    md.append("### Other Requirements")
    md.append(_bullet_list([f"[{o.category}] {o.description} [{o.priority.value}]" for o in cr.other]))
    md.append("")

    # 14. Responsibility → Requirement Mapping
    md.append("## 14. Responsibility → Requirement Mapping\n")
    if not spec.responsibility_requirement_mapping:
        md.append("_None identified._\n")
    for m in spec.responsibility_requirement_mapping:
        md.append(f"**Responsibility:** {m.responsibility}")
        md.append(_bullet_list(m.required_capabilities))
        if m.rationale:
            md.append(f"_Rationale: {m.rationale}_")
        md.append("")

    # 15. Requirement Interpretations
    md.append("## 15. Requirement Interpretations\n")
    if not spec.requirement_interpretations:
        md.append("_None identified._\n")
    for ri in spec.requirement_interpretations:
        md.append(f"**Explicit Requirement:** {ri.explicit_requirement}")
        md.append("Derived Evaluation Interpretation:")
        md.append(_bullet_list(ri.derived_interpretation))
        if ri.rationale:
            md.append(f"_Rationale: {ri.rationale}_")
        md.append("")

    # 16. Prohibited Inferences
    md.append("## 16. Prohibited Inferences\n")
    md.append(_bullet_list(spec.prohibited_inferences))
    md.append("")

    # 17. TA Confirmation Required
    md.append("## 17. TA Confirmation Required\n")
    md.append(_bullet_list(spec.ta_confirmation_required))
    md.append("")

    # 18. Source & Version Metadata
    md.append("## 18. Source & Version Metadata\n")
    meta = spec.metadata
    md.append(_bullet_list([
        f"JD ID: {meta.jd_id or '_unspecified_'}",
        f"JD Version: {meta.jd_version if meta.jd_version is not None else '_unspecified_'}",
        f"Specification Version: {meta.specification_version if meta.specification_version is not None else '_unspecified_'}",
        f"Prompt Version: {meta.prompt_version or '_unspecified_'}",
        f"Model Version: {meta.model_version or '_unspecified_'}",
        f"Generated At: {meta.generated_at.isoformat() if meta.generated_at else '_unspecified_'}",
    ]))
    md.append("")

    return "\n".join(md)
