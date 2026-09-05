"""
Deterministic Canonical Object -> Markdown renderer.

Markdown is a VIEW of the canonical JobEvaluationSpecification, never a
separate source of truth.  Given the same object, this renderer always
produces the same Markdown (no LLM calls here).

Section layout (8-section target structure):
  1. Role Overview
  2. Requirements (### Must-Have / ### Preferred)
  3. Responsibilities
  4. Evidence & Evaluation Rules
  5. JD-Specific Evaluation Parameters
  6. Ambiguities & Missing Information
  7. Evaluation Priorities
  8. Compliance

Internal metadata (JD ID, prompt/model version, timestamps) and
detailed canonical fields (explicit/derived, rationale, confidence,
source text, TA confirmation lists, responsibility mapping, requirement
interpretations, conventional-requirements breakdown) are intentionally
omitted from Markdown. They remain fully available in the canonical
JSON / Pydantic object.
"""
from __future__ import annotations

from app.schemas.canonical import JobEvaluationSpecification


def _bullet_list(items: list[str], empty: str = "_None identified._") -> str:
    if not items:
        return empty
    return "\n".join(f"- {i}" for i in items)


def render_markdown(spec: JobEvaluationSpecification) -> str:
    md: list[str] = []
    md.append("# Job Evaluation Specification\n")

    # ------------------------------------------------------------------ #
    # Section 1: Role Overview
    # ------------------------------------------------------------------ #
    md.append("## 1. Role Overview\n")
    r = spec.role
    md.append(f"- **Job Title:** {r.job_title or '_unspecified_'}")
    md.append(f"- **Seniority:** {r.seniority or '_unspecified_'}")
    if r.department:
        md.append(f"- **Department:** {r.department}")
    if r.employment_type:
        md.append(f"- **Employment Type:** {r.employment_type}")
    if r.reporting_structure:
        md.append(f"- **Reporting To:** {r.reporting_structure}")
    if r.team_context:
        md.append(f"- **Team Context:** {r.team_context}")

    # Location / Work Mode
    loc = spec.conventional_requirements.location
    wm = loc.work_mode.value if hasattr(loc.work_mode, "value") else loc.work_mode
    city = loc.city or "_unspecified_"
    country = loc.country or ""
    location_str = f"{city}{', ' + country if country else ''} ({wm})"
    md.append(f"- **Location / Work Mode:** {location_str}")
    if loc.office_attendance:
        md.append(f"- **Office Attendance:** {loc.office_attendance}")
    if loc.relocation_required is not None:
        md.append(f"- **Relocation Required:** {loc.relocation_required}")

    # Job context
    jc = spec.job_context
    if jc.environment:
        md.append(f"- **Environment:** {jc.environment}")
    if jc.business_context:
        md.append(f"- **Business Context:** {jc.business_context}")
    if jc.team_size:
        md.append(f"- **Team Size:** {jc.team_size}")
    md.append("")

    # ------------------------------------------------------------------ #
    # Section 2: Requirements
    # ------------------------------------------------------------------ #
    md.append("## 2. Requirements\n")

    # --- Must-Have ---
    md.append("### Must-Have\n")
    must_have_lines: list[str] = []

    # Include experience requirements that are MUST_HAVE
    cr = spec.conventional_requirements
    for e in cr.experience:
        if e.priority.value in ("MUST_HAVE", "MUST_HAVE"):  # always include experience here
            yrs = f" ({e.min_years}+ yrs)" if e.min_years is not None else ""
            must_have_lines.append(f"{e.description}{yrs}")

    # Append the flat must_have_requirements list (deduplicate against experience lines)
    exp_descs = {line.split(" (")[0].strip().lower() for line in must_have_lines}
    for req in spec.must_have_requirements:
        if req.strip().lower() not in exp_descs:
            must_have_lines.append(req)

    md.append(_bullet_list(must_have_lines))
    md.append("")

    # --- Preferred ---
    md.append("### Preferred\n")
    md.append(_bullet_list(spec.preferred_requirements))
    md.append("")

    # ------------------------------------------------------------------ #
    # Section 3: Responsibilities
    # ------------------------------------------------------------------ #
    md.append("## 3. Responsibilities\n")
    if spec.responsibilities:
        for res in spec.responsibilities:
            md.append(f"- {res.description}")
    else:
        md.append("_None identified._")
    md.append("")

    # ------------------------------------------------------------------ #
    # Section 4: Evidence & Evaluation Rules
    # ------------------------------------------------------------------ #
    md.append("## 4. Evidence & Evaluation Rules\n")

    # Per-requirement evidence specs
    if spec.evidence_requirements:
        for ev in spec.evidence_requirements:
            md.append(f"### {ev.requirement}")
            if ev.evidence_to_look_for:
                md.append(f"**Evidence:** {', '.join(ev.evidence_to_look_for)}")
            if ev.strong_evidence:
                md.append(f"- **Strong:** {ev.strong_evidence}")
            if ev.moderate_evidence:
                md.append(f"- **Moderate:** {ev.moderate_evidence}")
            if ev.weak_evidence:
                md.append(f"- **Weak:** {ev.weak_evidence}")
            if ev.insufficient_evidence:
                md.append(f"- **Insufficient (→ UNCORED):** {ev.insufficient_evidence}")
            if ev.prohibited_inference:
                md.append(f"- **Do not infer:** {ev.prohibited_inference}")
            md.append("")

    # General evaluation process rules
    if spec.evaluation_rules:
        md.append("**Evaluation Process Rules**\n")
        md.append(_bullet_list(spec.evaluation_rules))
        md.append("")

    # UNCORED conditions
    if spec.unscored_rules:
        md.append("**Return UNCORED when:**\n")
        md.append(_bullet_list(spec.unscored_rules))
        md.append("")

    # Prohibited inferences (global)
    if spec.prohibited_inferences:
        md.append("**Prohibited Inferences**\n")
        md.append(_bullet_list(spec.prohibited_inferences))
        md.append("")

    if not spec.evidence_requirements and not spec.evaluation_rules and not spec.unscored_rules and not spec.prohibited_inferences:
        md.append("_None specified._\n")

    # ------------------------------------------------------------------ #
    # Section 5: JD-Specific Evaluation Parameters
    # ------------------------------------------------------------------ #
    md.append("## 5. JD-Specific Evaluation Parameters\n")
    if not spec.non_conventional_parameters:
        md.append("_None identified — no JD evidence supported additional parameters._\n")
    for p in spec.non_conventional_parameters:
        md.append(f"### {p.parameter_name}")
        md.append(f"{p.why_it_is_relevant}\n")
        if p.evidence_to_look_for:
            md.append(f"**Evidence:** {', '.join(p.evidence_to_look_for)}")
        else:
            md.append(f"**Evidence:** {p.evaluation_guidance}")
        if p.unscored_if:
            md.append(f"- **Return UNCORED if:** {p.unscored_if}")
        md.append("")

    # ------------------------------------------------------------------ #
    # Section 6: Ambiguities & Missing Information
    # ------------------------------------------------------------------ #
    md.append("## 6. Ambiguities & Missing Information\n")

    has_ambiguities = bool(spec.ambiguities)
    has_missing = bool(spec.missing_information)

    if has_ambiguities:
        md.append("**Ambiguities**\n")
        for a in spec.ambiguities:
            ta_flag = " _(TA confirmation required)_" if a.ta_confirmation_required else ""
            md.append(f"- **\"{a.statement}\"** — {a.why_ambiguous}{ta_flag}")
            if a.suggested_interpretation:
                md.append(f"  - Interpretation: {a.suggested_interpretation}")
            if a.evidence_required:
                md.append(f"  - Evidence needed: {', '.join(a.evidence_required)}")
        md.append("")

    if has_missing:
        md.append("**Missing Information**\n")
        md.append("_Absent from JD. Do not fabricate or assume defaults._\n")
        for mi in spec.missing_information:
            md.append(f"- **{mi.field}:** {mi.why_it_matters}")
            if mi.suggested_action:
                md.append(f"  - Action: {mi.suggested_action}")
        md.append("")

    if not has_ambiguities and not has_missing:
        md.append("_None detected._\n")

    # ------------------------------------------------------------------ #
    # Section 7: Evaluation Priorities
    # ------------------------------------------------------------------ #
    md.append("## 7. Evaluation Priorities\n")
    if spec.candidate_analysis_instructions:
        for i, instr in enumerate(spec.candidate_analysis_instructions, start=1):
            md.append(f"{i}. {instr}")
    else:
        md.append("_No explicit evaluation priorities extracted._")
    md.append("")

    # ------------------------------------------------------------------ #
    # Section 8: Compliance
    # ------------------------------------------------------------------ #
    md.append("## 8. Compliance\n")
    if not spec.compliance_flags:
        md.append("_None detected._\n")
    for cf in spec.compliance_flags:
        md.append(
            f"- **\"{cf.flagged_text}\"** — {cf.concern} "
            f"(`{cf.category}`). _{cf.recommended_action}_"
        )
    md.append("")

    return "\n".join(md)
