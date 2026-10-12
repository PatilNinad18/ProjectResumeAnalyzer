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

from typing import Any, Optional, Union

from app.schemas.canonical import JobEvaluationSpecification
from app.schemas.enrichment import TAEnrichmentReport


def _bullet_list(items: list[str], empty: str = "_None identified._") -> str:
    if not items:
        return empty
    return "\n".join(f"- {i}" for i in items)


def _derive_tailored_evaluation_focus(req_text: str) -> str:
    """
    Generate dynamic, requirement-tailored evaluation guidance derived directly
    from the requirement's specific action, subject, and deliverables.
    Eliminates canned, repetitive template paragraphs.
    """
    cleaned = req_text.strip().rstrip(".").strip()
    lower = cleaned.lower()

    # Degree / Education
    if any(k in lower for k in ("degree", "bachelor", "master", "b.e", "b.tech", "m.tech", "phd", "education")):
        return f"Verify accredited academic credential or equivalent proven engineering foundation in '{cleaned}'."

    # Experience tenure / years
    if any(k in lower for k in ("year", "years", "industry experience", "tenure")):
        return f"Evaluate verified career tenure and sustained hands-on depth ({cleaned}), assessing progressive ownership across complex engineering lifecycles."

    # Cross-functional communication / Leadership / Team
    if any(k in lower for k in ("communication", "lead", "leadership", "collaborat", "team", "teams", "ownership")):
        return f"Assess cross-functional technical communication and stakeholder alignment regarding '{cleaned}', screening for joint debug ownership and interface agreements."

    # Automation / Scripting / CI/CD
    if any(k in lower for k in ("automation", "script", "python", "regression", "ci/cd", "infrastructure", "jenkins")):
        return f"Verify verifiable automation deliverables and scripting depth in '{cleaned}', evaluating execution efficiency, test harness robustness, and pipeline integration."

    # Architecture / Platforms / Systems
    if any(k in lower for k in ("architect", "virtual platform", "vdk", "soc", "system modeling", "chiplet", "xpu")):
        return f"Screen for direct architectural ownership and design trade-offs in '{cleaned}', verifying shipped artifacts and multi-subsystem platform integration."

    # Protocols / Simulation / Emulation / Hardware modeling
    if any(k in lower for k in ("c++", "systemc", "tlm", "pcie", "cxl", "ucie", "amba", "zebu", "palladium", "veloce", "rtl", "emulation")):
        return f"Verify hands-on compliance and practical verification artifacts in '{cleaned}', checking cycle-accurate modeling depth rather than passive keyword familiarity."

    # Default: dynamically incorporate the specific requirement text!
    return f"Screen candidate resume for verifiable hands-on execution and deliverables in '{cleaned}', assessing practical depth and production track record."


def render_markdown(
    spec: JobEvaluationSpecification,
    enrichment_report: Optional[Union[TAEnrichmentReport, dict]] = None,
) -> str:
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
    if getattr(jc, "salary_range", None):
        md.append(f"- **Salary Range:** {jc.salary_range}")
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

    # Collect responsibility descriptions to guarantee zero duplication between Sections 2 and 3
    resp_texts = {
        res.description.strip().lower()
        for res in spec.responsibilities
        if getattr(res, "description", None)
    }

    # Append the flat must_have_requirements list (deduplicate against experience lines and responsibilities)
    exp_descs = {line.split(" (")[0].strip().lower() for line in must_have_lines}
    for req in spec.must_have_requirements:
        req_clean = req.strip().lower()
        if req_clean not in exp_descs and req_clean not in resp_texts:
            must_have_lines.append(req)

    md.append(_bullet_list(must_have_lines))
    md.append("")

    # --- Preferred ---
    md.append("### Preferred\n")
    pref_lines = [
        p for p in spec.preferred_requirements
        if p.strip().lower() not in resp_texts
    ]
    md.append(_bullet_list(pref_lines))
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

    # Build lookup for optional enrichment report
    enrich_by_id: dict[str, Any] = {}
    enrich_by_text: dict[str, Any] = {}
    if enrichment_report is not None:
        items = getattr(enrichment_report, "items", None)
        if items is None and isinstance(enrichment_report, dict):
            items = enrichment_report.get("items", [])
        if items:
            for it in items:
                r_id = getattr(it, "requirement_id", None) or (it.get("requirement_id") if isinstance(it, dict) else None)
                r_text = getattr(it, "requirement_text", None) or (it.get("requirement_text") if isinstance(it, dict) else None)
                if r_id:
                    enrich_by_id[r_id] = it
                if r_text:
                    enrich_by_text[r_text.strip().lower()] = it

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

            # Weave grounded AI guidance if available
            item = enrich_by_id.get(ev.requirement_id) if ev.requirement_id else None
            if not item and ev.requirement:
                item = enrich_by_text.get(ev.requirement.strip().lower())

            if item:
                def _val(attr: str, default: Any = "") -> Any:
                    return getattr(item, attr, None) or (item.get(attr, default) if isinstance(item, dict) else default)

                summary = _val("technical_concept_summary")
                strong_sigs = _val("strong_evidence_signals", [])
                weak_sigs = _val("weak_or_ambiguous_signals", [])
                screen_q = _val("screening_question")

                md.append("> **[AI Guidance — Evaluator Aid]**")
                if summary:
                    md.append(f"> - **Concept Summary:** {summary}")
                if strong_sigs:
                    md.append(f"> - **Strong Candidate Signals:** {'; '.join(strong_sigs)}")
                if weak_sigs:
                    md.append(f"> - **Weak / Ambiguous Signals:** {'; '.join(weak_sigs)}")
                if screen_q:
                    md.append(f"> - **Screening Question:** {screen_q}")
            elif not any([ev.evidence_to_look_for, ev.strong_evidence, ev.weak_evidence, ev.moderate_evidence, ev.insufficient_evidence, ev.prohibited_inference]):
                focus_text = _derive_tailored_evaluation_focus(ev.requirement)
                md.append(f"- **Evaluation Focus:** {focus_text}")

            md.append("")

    elif enrichment_report is not None:
        report_items = getattr(enrichment_report, "items", None) or (enrichment_report.get("items", []) if isinstance(enrichment_report, dict) else [])
        for item in report_items:
            def _val_item(attr: str, default: Any = "") -> Any:
                return getattr(item, attr, None) or (item.get(attr, default) if isinstance(item, dict) else default)

            req_text = _val_item("requirement_text")
            summary = _val_item("technical_concept_summary")
            strong_sigs = _val_item("strong_evidence_signals", [])
            weak_sigs = _val_item("weak_or_ambiguous_signals", [])
            screen_q = _val_item("screening_question")

            if req_text:
                md.append(f"### {req_text}")
                md.append("> **[AI Guidance — Evaluator Aid]**")
                if summary:
                    md.append(f"> - **Concept Summary:** {summary}")
                if strong_sigs:
                    md.append(f"> - **Strong Candidate Signals:** {'; '.join(strong_sigs)}")
                if weak_sigs:
                    md.append(f"> - **Weak / Ambiguous Signals:** {'; '.join(weak_sigs)}")
                if screen_q:
                    md.append(f"> - **Screening Question:** {screen_q}")
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

    has_ev = bool(spec.evidence_requirements or (enrichment_report and getattr(enrichment_report, "items", None)))
    if not has_ev and not spec.evaluation_rules and not spec.unscored_rules and not spec.prohibited_inferences:
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

    resolved_ambs = [
        a for a in spec.ambiguities
        if not a.ta_confirmation_required or (a.suggested_interpretation and "TA Resolution:" in a.suggested_interpretation)
    ]
    unresolved_ambs = [a for a in spec.ambiguities if a not in resolved_ambs]
    has_missing = bool(spec.missing_information)

    if resolved_ambs:
        md.append("**Resolved Clarifications (TA Confirmed)**\n")
        for a in resolved_ambs:
            res_text = a.suggested_interpretation or "Confirmed by TA."
            md.append(f"- **\"{a.statement}\"** — {res_text}")
        md.append("")

    if unresolved_ambs:
        md.append("**Ambiguities Requiring TA Clarification**\n")
        for a in unresolved_ambs:
            md.append(f"- **\"{a.statement}\"** — {a.why_ambiguous} _(TA confirmation required)_")
            if a.suggested_interpretation:
                md.append(f"  - Suggested Interpretation: {a.suggested_interpretation}")
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

    if not resolved_ambs and not unresolved_ambs and not has_missing:
        md.append("_None detected._\n")

    # ------------------------------------------------------------------ #
    # Section 7: Evaluation Priorities
    # ------------------------------------------------------------------ #
    md.append("## 7. Evaluation Priorities\n")
    priorities = spec.candidate_analysis_instructions
    if not priorities and enrichment_report:
        priorities = (
            getattr(enrichment_report, "evaluation_priorities", None)
            or (enrichment_report.get("evaluation_priorities", []) if isinstance(enrichment_report, dict) else [])
        )
    if priorities:
        for i, instr in enumerate(priorities, start=1):
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
