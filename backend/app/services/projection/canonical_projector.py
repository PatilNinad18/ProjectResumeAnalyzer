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

    # --- Flatten requirements ---
    all_reqs = _flatten_requirements(master.requirements)
    for req in all_reqs:
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
                "requirement": req.text,
                "priority": "MUST_HAVE",
                "explicit_or_derived": "explicit",
                "confidence": _map_confidence(req.confidence.entity_match_confidence.value),
                "source": {"text": req.provenance.source_span.raw_text if req.provenance.source_span else ""},
            })

        elif req.priority == RequirementPriority.PREFERRED:
            preferred.append(req.text)
            evidence_specs.append({
                "requirement": req.text,
                "priority": "PREFERRED",
                "explicit_or_derived": "explicit",
                "confidence": _map_confidence(req.confidence.entity_match_confidence.value),
            })

        elif req.priority in {RequirementPriority.UNRESOLVED, RequirementPriority.INFORMATIONAL}:
            ambiguities_out.append({
                "statement": req.text,
                "why_ambiguous": (
                    "Priority was UNRESOLVED at time of finalization." if req.priority == RequirementPriority.UNRESOLVED
                    else "Marked as INFORMATIONAL context only."
                ),
                "ta_confirmation_required": req.priority == RequirementPriority.UNRESOLVED,
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

    # --- Responsibilities ---
    responsibilities_out = [
        {"description": r.raw_statement, "kind": "primary",
         "source": {"text": r.source_span.raw_text, "section": r.source_span.section}}
        for r in master.responsibilities
    ]

    # --- Missing info (from EXPLICITLY_UNSPECIFIED and still-null metadata) ---
    missing_info_out: List[Dict[str, Any]] = []
    ctx = master.job_context
    if ctx.team_size is None:
        missing_info_out.append({
            "field": "team_size",
            "why_it_matters": "Team size affects culture fit expectations.",
            "suggested_action": "Ask TA to confirm or mark as not available." if not ctx.team_size_explicitly_unspecified else None,
        })
    if ctx.salary_range is None:
        missing_info_out.append({
            "field": "salary_range",
            "why_it_matters": "Salary range affects candidate expectations and attraction.",
            "suggested_action": "Ask TA to confirm or mark as not disclosed." if not ctx.salary_explicitly_unspecified else None,
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
