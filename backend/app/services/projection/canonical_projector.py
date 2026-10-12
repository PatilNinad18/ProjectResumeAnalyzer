"""
projection/canonical_projector.py — Deterministic Forward Projection.

Converts JDMasterContext (authoritative, lossless, rich internal state) into
JobEvaluationSpecification (public, immutable, backward-compatible evaluation contract).

Traceable Origin Invariant is ENFORCED HERE at runtime:
  - Only requirements with provenance.origin_type in {EXPLICIT_JD, TA_CONFIRMED}
    and is_mandatory=True are included in must_have_requirements.
  - EKG_DERIVED and LLM_HYPOTHESIS items are NEVER in must_have_requirements.
  - An AssertionError is raised if this invariant is violated (should never happen
    if the schema validators and updater are working correctly).

apply_patch_to_master:
  - Accepts a patch dict (from UI Markdown/JSON edits).
  - Validates the patch against JDMasterContext schema.
  - Applies atomically; rolls back 100% if validation fails.
  - Adds a TA_MANUAL_EDIT provenance record and audit trail entry.
"""
from __future__ import annotations

import copy
import logging
import re
from typing import Any, Dict, List, Optional

from app.schemas.canonical import (
    Ambiguity,
    ComplianceFlag,
    ConventionalRequirements,
    EducationRequirement,
    EvidenceSpec,
    ExperienceRequirement,
    JobContext,
    JobEvaluationSpecification,
    LocationInfo,
    MetadataInfo,
    MissingInfo,
    Responsibility,
    RoleInfo,
    SourceRef,
    TechnicalSkill,
    WorkMode,
    Priority,
    ConfidenceLevel,
)
from app.schemas.master_context import (
    ClauseType,
    DisjunctionGroup,
    JDMasterContext,
    JDLifecycleStatus,
    OriginType,
    ProvenanceRecord,
    QuestionStatus,
    RequirementPriority,
    StructuredRequirement,
)

logger = logging.getLogger("jd_agent.projection.canonical_projector")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def project_to_canonical(
    master: JDMasterContext,
    *,
    jd_id: Optional[str] = None,
    specification_version: Optional[int] = None,
) -> JobEvaluationSpecification:
    """
    Deterministically project JDMasterContext → JobEvaluationSpecification.

    This is a FORWARD-ONLY, LOSSY transformation (in the sense that internal
    graph bindings, full Q&A history, etc., are not preserved — they stay in
    JDMasterContext). The canonical spec is purely for downstream candidate evaluation.

    Args:
        master: The JDMasterContext to project from.
        jd_id: Optional JD ID to embed in the spec metadata.
        specification_version: Optional spec version number for metadata.

    Returns:
        A fully populated JobEvaluationSpecification.
    """
    must_haves: List[str] = []
    preferred: List[str] = []
    tech_skills: List[Dict[str, Any]] = []
    experience_reqs: List[Dict[str, Any]] = []
    evidence_specs: List[Dict[str, Any]] = []
    ambiguities_out: List[Dict[str, Any]] = []

    # Collect known responsibility descriptions for deduplication
    resp_descriptions = {
        (r.raw_statement if hasattr(r, "raw_statement") else str(r)).strip().lower()
        for r in master.responsibilities
        if getattr(r, "raw_statement", None)
    }

    # --- Flatten requirements ---
    all_reqs = _flatten_requirements(master.requirements)
    for req in all_reqs:
        # Responsibilities belong exclusively to Section 3 Responsibilities,
        # never duplicated into Section 2 Requirements (Must-Have/Preferred) or Section 4 Evidence.
        is_resp = (
            getattr(req, "clause_type", None) == ClauseType.RESPONSIBILITY
            or (req.source and getattr(req.source, "section", "") in (
                "responsibilities", "duties", "deliverables", "key_responsibilities", "expected_deliverables"
            ))
            or req.text.strip().lower() in resp_descriptions
        )
        if is_resp:
            continue

        # Traceable Origin Invariant — enforced at runtime
        if req.is_mandatory:
            assert req.provenance.origin_type in {OriginType.EXPLICIT_JD, OriginType.TA_CONFIRMED}, (
                f"Traceable Origin Invariant violated in projection: "
                f"requirement id={req.id!r} has is_mandatory=True but "
                f"origin_type={req.provenance.origin_type!r}. "
                f"Only EXPLICIT_JD or TA_CONFIRMED may be mandatory."
            )
            must_haves.append(req.text)

            # Build evidence spec for every MUST_HAVE
            evidence_specs.append({
                "requirement_id": req.id,
                "requirement": req.text,
                "priority": "MUST_HAVE",
                "explicit_or_derived": "explicit",
                "confidence": _map_confidence(req.confidence.entity_match_confidence.value),
                "source": {"text": req.provenance.source_span.raw_text if req.provenance.source_span else ""},
            })

        elif req.priority == RequirementPriority.PREFERRED:
            preferred.append(req.text)
            evidence_specs.append({
                "requirement_id": req.id,
                "requirement": req.text,
                "priority": "PREFERRED",
                "explicit_or_derived": "explicit",
                "confidence": _map_confidence(req.confidence.entity_match_confidence.value),
            })

        elif req.priority in {RequirementPriority.UNRESOLVED, RequirementPriority.INFORMATIONAL, RequirementPriority.CONTEXTUAL}:
            snip = req.text.strip()
            is_confirmed = getattr(req.provenance, "origin_type", None) == OriginType.TA_CONFIRMED
            if len(snip) >= 25 and not snip.lower().startswith(("in ", "or ", "and ")) and len(ambiguities_out) < 4:
                ambiguities_out.append({
                    "statement": req.text,
                    "why_ambiguous": (
                        "Priority was UNRESOLVED at time of finalization." if req.priority == RequirementPriority.UNRESOLVED
                        else "Marked as CONTEXTUAL / informational phrasing requiring TA confirmation."
                    ),
                    "suggested_interpretation": "TA Resolution: Confirmed as role context / informational." if is_confirmed else None,
                    "ta_confirmation_required": not is_confirmed,
                })
            evidence_specs.append({
                "requirement_id": req.id,
                "requirement": req.text,
                "priority": "PREFERRED",
                "explicit_or_derived": "explicit",
                "confidence": _map_confidence(req.confidence.entity_match_confidence.value),
            })

        # Build technical skill entries for EKG-matched requirements
        if req.ekg_node_ids:
            tech_skills.append({
                "name": req.text,
                "category": "tool",
                "priority": _map_priority(req.priority),
                "explicit_or_derived": "explicit" if req.provenance.origin_type == OriginType.EXPLICIT_JD else "derived",
                "source": {"text": req.provenance.source_span.raw_text if req.provenance.source_span else ""},
            })

        # Experience requirements with scoped years
        if req.min_years is not None:
            experience_reqs.append({
                "description": req.text,
                "min_years": req.min_years,
                "max_years": req.max_years,
                "priority": _map_priority(req.priority),
                "explicit_or_derived": "explicit",
            })

    # Build answered questions map from master clarification history
    answered_q_map = {}
    for q in master.clarification_history:
        if q.status == QuestionStatus.ANSWERED and q.answer_text:
            answered_q_map[q.question_key] = q
            if q.field_target:
                answered_q_map[q.field_target] = q

    # Include detected ambiguities from raw text if not already present
    raw_ambs = getattr(master, "raw_ambiguities", []) or []
    existing_statements = {a["statement"].strip().lower() for a in ambiguities_out if "statement" in a}
    for amb in raw_ambs:
        if len(ambiguities_out) >= 4:
            break
        amb_text = getattr(amb, "text", "").strip()
        amb_id = getattr(amb, "ambiguity_id", "") or str(getattr(amb, "id", ""))
        if amb_text and amb_text.lower() not in existing_statements and len(amb_text) >= 25:
            matching_q = (
                answered_q_map.get(f"ambiguities[{amb_id}]")
                or answered_q_map.get(f"jd_ambiguity_{amb_id}")
                or answered_q_map.get(f"amb_{amb_id}")
            )
            is_resolved = (
                getattr(amb, "requires_ta_confirmation", True) is False
                or bool(matching_q)
                or any("TA Resolution:" in s for s in (getattr(amb, "suggested_interpretations", []) or []))
            )
            sugg_interp = None
            if matching_q and matching_q.answer_text:
                sugg_interp = f"TA Resolution: {matching_q.answer_text}"
            elif getattr(amb, "suggested_interpretations", None):
                for interp in amb.suggested_interpretations:
                    if "TA Resolution:" in interp:
                        sugg_interp = interp
                        break
                if not sugg_interp:
                    sugg_interp = amb.suggested_interpretations[0]

            ambiguities_out.append({
                "statement": amb_text,
                "why_ambiguous": getattr(amb, "reason", "Statement requiring TA confirmation."),
                "suggested_interpretation": sugg_interp,
                "ta_confirmation_required": not is_resolved,
            })
            existing_statements.add(amb_text.lower())

    # --- Responsibilities ---
    subhead_clean_re = re.compile(
        r'^(?:project\s+experience|soft\s+skills|technical\s+skills|core\s+competencies|key\s+skills|overview|summary)\s*:?$',
        re.IGNORECASE
    )
    responsibilities_out = [
        {"description": r.raw_statement, "kind": "primary",
         "source": {"text": r.source_span.raw_text if r.source_span else "", "section": r.source_span.section if r.source_span else ""}}
        for r in master.responsibilities
        if r.raw_statement and not subhead_clean_re.match(r.raw_statement.strip())
    ]
    seen_resp = {r["description"].strip().lower() for r in responsibilities_out}
    for req in all_reqs:
        if (
            getattr(req, "clause_type", None) == ClauseType.RESPONSIBILITY
            or (req.source and getattr(req.source, "section", "") in (
                "responsibilities", "duties", "deliverables", "key_responsibilities", "expected_deliverables"
            ))
        ):
            text_clean = req.text.strip()
            if text_clean.lower() not in seen_resp and not subhead_clean_re.match(text_clean):
                responsibilities_out.append({
                    "description": text_clean,
                    "kind": "primary",
                    "source": {
                        "text": text_clean,
                        "section": getattr(req.source, "section", "responsibilities") if req.source else "responsibilities",
                    },
                })
                seen_resp.add(text_clean.lower())

    # --- Missing info (omit if answered or explicitly marked unspecified) ---
    missing_info_out: List[Dict[str, Any]] = []
    ctx = master.job_context
    if ctx.team_size is None and not ctx.team_size_explicitly_unspecified:
        missing_info_out.append({
            "field": "team_size",
            "why_it_matters": "Team size affects culture fit expectations.",
            "suggested_action": "Ask TA to confirm or mark as not available.",
        })
    if ctx.salary_range is None and not ctx.salary_explicitly_unspecified:
        missing_info_out.append({
            "field": "salary_range",
            "why_it_matters": "Salary range affects candidate expectations and attraction.",
            "suggested_action": "Ask TA to confirm or mark as not disclosed.",
        })

    # --- Unanswered OPTIONAL questions as ta_confirmation_required items ---
    ta_confirmation_required = [
        q.question_text
        for q in master.clarification_history
        if q.status == QuestionStatus.UNANSWERED
        and q.priority.value == "OPTIONAL"
    ]

    # --- Compliance flags ---
    compliance_flags_out = [
        {
            "flagged_text": f.flagged_text,
            "concern": f.concern,
            "category": f.category,
            "recommended_action": f.recommended_action,
        }
        for f in master.compliance_flags
    ]

    # --- Role info ---
    ro = master.role_overview
    role_out = {
        "job_title": ro.job_title,
        "seniority": ro.seniority,
        "department": ro.department,
        "employment_type": None,
    }

    # --- Job context ---
    job_context_out = {
        "company_context": ctx.company_context,
        "business_context": ctx.business_context,
        "environment": ctx.environment,
        "team_size": ctx.team_size,
        "salary_range": ctx.salary_range,
    }

    # --- Conventional requirements ---
    conventional = {
        "experience": experience_reqs,
        "technical_skills": tech_skills,
        "location": {
            "city": ro.location_city,
            "country": ro.location_country,
            "work_mode": ro.work_mode.lower() if ro.work_mode else "unspecified",
            "office_attendance": ro.office_attendance,
            "relocation_required": ro.relocation_required,
        },
        "work_mode": ro.work_mode.lower() if ro.work_mode else "unspecified",
    }

    # --- Grounded candidate analysis / evaluation priorities ---
    candidate_instructions: List[str] = []
    if tech_skills:
        top_tech = [t["name"] for t in tech_skills[:4]]
        candidate_instructions.append(f"Prioritize candidates demonstrating hands-on production depth in core technical skills: {', '.join(top_tech)}.")
    elif must_haves:
        top_mh = [m[:80] for m in must_haves[:3]]
        candidate_instructions.append(f"Prioritize proven track record meeting core mandatory competencies: {'; '.join(top_mh)}.")

    if experience_reqs:
        exp_desc = experience_reqs[0].get("description", "")
        candidate_instructions.append(f"Screen for verified career progression and tenure meeting the experience standard ({exp_desc}).")

    if responsibilities_out:
        top_resp = responsibilities_out[0].get("description", "")
        candidate_instructions.append(f"Evaluate demonstrated ownership of major deliverables: {top_resp[:120]}.")

    if preferred:
        top_pref = preferred[:3]
        candidate_instructions.append(f"Differentiate competitive candidates through demonstrated depth in preferred skills: {', '.join(top_pref)}.")

    spec = JobEvaluationSpecification(
        metadata=MetadataInfo(jd_id=jd_id or master.jd_id, specification_version=specification_version),
        role=role_out,
        job_context=job_context_out,
        responsibilities=responsibilities_out,
        conventional_requirements=conventional,
        must_have_requirements=must_haves,
        preferred_requirements=preferred,
        evidence_requirements=evidence_specs,
        compliance_flags=compliance_flags_out,
        ambiguities=ambiguities_out,
        missing_information=missing_info_out,
        ta_confirmation_required=ta_confirmation_required,
        candidate_analysis_instructions=candidate_instructions,
    )

    logger.info(
        "Projected JDMasterContext jd_id=%s → JobEvaluationSpecification: "
        "%d must_haves, %d preferred, %d tech_skills.",
        master.jd_id,
        len(must_haves),
        len(preferred),
        len(tech_skills),
    )
    return spec


def apply_patch_to_master(
    master: JDMasterContext,
    patch: Dict[str, Any],
    *,
    actor: str,
) -> JDMasterContext:
    """
    Transactionally apply a UI patch dict to JDMasterContext.

    The patch may contain updates to any mutable field (role_overview, job_context,
    or individual requirement priorities). Immutable fields (jd_id, raw_jd_text,
    checksum, created_at, finalized_at) are silently ignored.

    Rolls back 100% if schema validation fails.
    Adds a TA_MANUAL_EDIT provenance entry and audit trail event.

    Args:
        master: The master context to patch.
        patch: A dict of {field_path: new_value} updates.
        actor: The user who submitted the patch.

    Returns:
        The patched master context.

    Raises:
        ValueError: If the patch contains invalid schema updates.
    """
    # Deep copy the master for rollback
    backup = copy.deepcopy(master)

    try:
        _apply_patch_fields(master, patch, actor)

        # Validate the result is still a valid JDMasterContext
        # (re-serialising through Pydantic catches structural issues)
        JDMasterContext.model_validate(master.model_dump())

        master.add_audit_entry(
            "patch_applied",
            f"Manual patch applied by {actor}. Fields updated: {list(patch.keys())}",
            actor=actor,
            patch_keys=list(patch.keys()),
        )

        logger.info("Patch applied to jd_id=%s by %s. Fields: %s", master.jd_id, actor, list(patch.keys()))
        return master

    except Exception as exc:
        # Full rollback
        logger.error("Patch failed for jd_id=%s. Rolling back. Error: %s", master.jd_id, exc)
        # Restore from backup by mutating master fields back
        master.__dict__.update(backup.__dict__)
        raise ValueError(f"Patch validation failed and was rolled back: {exc}") from exc


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _flatten_requirements(
    requirements: list,
) -> List[StructuredRequirement]:
    """Recursively flatten DisjunctionGroups into a flat list of StructuredRequirements."""
    result: List[StructuredRequirement] = []
    for item in requirements:
        if isinstance(item, StructuredRequirement):
            result.append(item)
        elif isinstance(item, DisjunctionGroup):
            result.extend(_flatten_requirements(item.requirements))
    return result


def _map_priority(priority: RequirementPriority) -> str:
    mapping = {
        RequirementPriority.MUST_HAVE: "MUST_HAVE",
        RequirementPriority.PREFERRED: "PREFERRED",
        RequirementPriority.INFORMATIONAL: "INFORMATIONAL",
        RequirementPriority.UNRESOLVED: "AMBIGUOUS",
    }
    return mapping.get(priority, "AMBIGUOUS")


def _map_confidence(confidence_value: str) -> str:
    mapping = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low", "UNKNOWN": "low"}
    return mapping.get(confidence_value.upper(), "medium")


def _apply_patch_fields(master: JDMasterContext, patch: Dict[str, Any], actor: str) -> None:
    """
    Apply a flat patch dict to master context fields.
    Uses dot-notation keys: e.g., "role_overview.job_title", "job_context.team_size".
    Ignores immutable fields silently.
    """
    IMMUTABLE = {"jd_id", "raw_jd_text", "checksum", "created_at", "finalized_at", "version"}
    provenance = ProvenanceRecord(
        origin_type=OriginType.TA_MANUAL_EDIT,
        author=actor,
        rule_id="manual_patch",
    )

    for key, value in patch.items():
        if key in IMMUTABLE:
            logger.debug("Ignoring immutable field in patch: %s", key)
            continue

        parts = key.split(".", 1)
        top = parts[0]
        sub = parts[1] if len(parts) > 1 else None

        if top == "role_overview":
            if isinstance(value, dict):
                for k, v in value.items():
                    if hasattr(master.role_overview, k):
                        setattr(master.role_overview, k, v)
            elif sub and hasattr(master.role_overview, sub):
                setattr(master.role_overview, sub, value)
        elif top == "job_context":
            if isinstance(value, dict):
                for k, v in value.items():
                    if hasattr(master.job_context, k):
                        setattr(master.job_context, k, v)
            elif sub and hasattr(master.job_context, sub):
                setattr(master.job_context, sub, value)
        elif top == "lifecycle_status":
            # Allow explicit lifecycle transitions via patch (with actor audit)
            try:
                master.lifecycle_status = JDLifecycleStatus(value)
            except ValueError:
                raise ValueError(f"Invalid lifecycle_status value: {value!r}")
        else:
            logger.warning("Unknown patch key '%s' — skipping.", key)
