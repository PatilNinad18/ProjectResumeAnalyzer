"""
comparison_service.py — Service for comparing Baseline, Enriched, and Ambiguity-Resolved JD contexts.

Enforces:
1. Clear differentiation between Source Evidence (verbatim JD quotes) and TA-Confirmed Facts.
2. Accurate diff classifications: Added, Removed, Modified, and Unchanged requirements.
3. Tracking of Resolved vs Unresolved ambiguities.
4. Robust fallback when historical versions are partially missing.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.models.db_models import (
    JobDescription,
    JobDescriptionVersion,
    JobSpecificationVersion,
)
from app.services.storage import get_storage

logger = logging.getLogger("jd_agent.comparison")
storage = get_storage()


def _normalize_text(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _extract_provenance_info(req: Dict[str, Any]) -> Dict[str, Any]:
    prov = req.get("provenance") or {}
    if not isinstance(prov, dict):
        prov = {}
    origin_type = prov.get("origin_type") or req.get("origin_type") or "EXPLICIT_JD"
    if hasattr(origin_type, "value"):
        origin_type = origin_type.value
    origin_type = str(origin_type).upper()

    source_span = prov.get("source_span") or req.get("source_span") or req.get("source") or {}
    if not isinstance(source_span, dict):
        source_span = {}

    source_text = source_span.get("raw_text") or source_span.get("text") or req.get("text") or ""
    source_section = source_span.get("section") or "Requirements"

    if origin_type in ("TA_CONFIRMED", "TA_MANUAL_EDIT"):
        provenance_type = "ta_confirmed"
        provenance_badge = "TA-Confirmed Fact"
    elif origin_type == "LLM_HYPOTHESIS":
        provenance_type = "llm_hypothesis"
        provenance_badge = "AI Guidance (Hypothesis)"
    elif origin_type == "EKG_DERIVED":
        provenance_type = "ekg_derived"
        provenance_badge = "Domain Graph Derived"
    else:
        provenance_type = "source_evidence"
        provenance_badge = "Source Evidence (Verbatim JD)"

    return {
        "origin_type": origin_type,
        "provenance_type": provenance_type,
        "provenance_badge": provenance_badge,
        "source_text": source_text,
        "source_section": source_section,
        "author": prov.get("author") or req.get("answered_by"),
        "timestamp": prov.get("timestamp"),
    }


def _extract_requirements_from_spec(spec_version: JobSpecificationVersion) -> List[Dict[str, Any]]:
    """Extract flattened requirements with provenance from master_context_json or canonical_json."""
    reqs: List[Dict[str, Any]] = []

    # 1. Prefer master_context_json (authoritative lossless domain model)
    mc = spec_version.master_context_json
    if mc and isinstance(mc, dict) and "requirements" in mc:
        from app.services.projection.canonical_projector import _flatten_requirements
        from app.schemas.master_context import JDMasterContext

        try:
            master = JDMasterContext.model_validate(mc)
            flat = _flatten_requirements(master.requirements)
            for r in flat:
                r_dict = r.model_dump(mode="json") if hasattr(r, "model_dump") else dict(r)
                prov_info = _extract_provenance_info(r_dict)
                priority = r_dict.get("priority")
                if hasattr(priority, "value"):
                    priority = priority.value
                reqs.append({
                    "id": str(r_dict.get("id") or ""),
                    "text": str(r_dict.get("text") or ""),
                    "priority": str(priority or "MUST_HAVE"),
                    "clause_type": str(r_dict.get("clause_type") or "REQUIREMENT"),
                    "is_mandatory": bool(r_dict.get("is_mandatory", False)),
                    **prov_info,
                })
            return reqs
        except Exception as exc:
            logger.warning("Could not parse master_context_json with JDMasterContext: %s; falling back to raw dict", exc)
            for r in mc.get("requirements", []):
                if isinstance(r, dict):
                    # Handle DisjunctionGroup if present
                    if "requirements" in r and isinstance(r["requirements"], list):
                        for sub_r in r["requirements"]:
                            if isinstance(sub_r, dict):
                                prov_info = _extract_provenance_info(sub_r)
                                reqs.append({
                                    "id": str(sub_r.get("id") or ""),
                                    "text": str(sub_r.get("text") or ""),
                                    "priority": str(sub_r.get("priority") or "MUST_HAVE"),
                                    "clause_type": str(sub_r.get("clause_type") or "REQUIREMENT"),
                                    "is_mandatory": bool(sub_r.get("is_mandatory", False)),
                                    **prov_info,
                                })
                    else:
                        prov_info = _extract_provenance_info(r)
                        reqs.append({
                            "id": str(r.get("id") or ""),
                            "text": str(r.get("text") or ""),
                            "priority": str(r.get("priority") or "MUST_HAVE"),
                            "clause_type": str(r.get("clause_type") or "REQUIREMENT"),
                            "is_mandatory": bool(r.get("is_mandatory", False)),
                            **prov_info,
                        })
            if reqs:
                return reqs

    # 2. Fallback to canonical_json
    cj = spec_version.canonical_json
    if cj and isinstance(cj, dict):
        must_haves = cj.get("must_have_requirements") or []
        preferred = cj.get("preferred_requirements") or []
        for idx, text in enumerate(must_haves):
            reqs.append({
                "id": f"must_{idx}",
                "text": str(text),
                "priority": "MUST_HAVE",
                "clause_type": "REQUIREMENT",
                "is_mandatory": True,
                "origin_type": "EXPLICIT_JD",
                "provenance_type": "source_evidence",
                "provenance_badge": "Source Evidence (Verbatim JD)",
                "source_text": str(text),
                "source_section": "Requirements",
                "author": None,
                "timestamp": None,
            })
        for idx, text in enumerate(preferred):
            reqs.append({
                "id": f"pref_{idx}",
                "text": str(text),
                "priority": "PREFERRED",
                "clause_type": "REQUIREMENT",
                "is_mandatory": False,
                "origin_type": "EXPLICIT_JD",
                "provenance_type": "source_evidence",
                "provenance_badge": "Source Evidence (Verbatim JD)",
                "source_text": str(text),
                "source_section": "Preferred Qualifications",
                "author": None,
                "timestamp": None,
            })

    return reqs


def _extract_ambiguities_from_spec(spec_version: JobSpecificationVersion) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Returns (resolved_ambiguities, unresolved_ambiguities)."""
    resolved: List[Dict[str, Any]] = []
    unresolved: List[Dict[str, Any]] = []

    mc = spec_version.master_context_json
    if mc and isinstance(mc, dict):
        # 1. Clarification history
        for q in mc.get("clarification_history", []):
            if not isinstance(q, dict):
                continue
            status = str(q.get("status") or "UNANSWERED").upper()
            q_key = str(q.get("question_key") or "")
            q_text = str(q.get("question_text") or "")
            cat = str(q.get("category") or "GENERAL")
            prio = str(q.get("priority") or "RECOMMENDED")
            is_blocking = bool(q.get("is_blocking", False))
            ans_text = q.get("answer_text") or ""
            answered_by = q.get("answered_by") or "TA"
            answered_at = q.get("answered_at")
            override = q.get("override_record")

            if status in ("ANSWERED", "EXPLICITLY_UNSPECIFIED") or (status == "SKIPPED" and override):
                resolved.append({
                    "question_key": q_key,
                    "question_text": q_text,
                    "category": cat,
                    "priority": prio,
                    "status": status,
                    "answer_text": ans_text or ("Explicitly confirmed unspecified" if status == "EXPLICITLY_UNSPECIFIED" else "Skipped with executive override"),
                    "answered_by": answered_by,
                    "answered_at": answered_at,
                    "is_ta_confirmed": True,
                    "override_record": override,
                })
            else:
                unresolved.append({
                    "question_key": q_key,
                    "question_text": q_text,
                    "category": cat,
                    "priority": prio,
                    "is_blocking": is_blocking,
                    "status": status,
                    "why_ambiguous": q.get("rationale") or "Requires hiring team confirmation",
                    "suggested_options": q.get("suggested_options") or [],
                })

        # 2. Raw ambiguities from deterministic extraction if not in clarification history
        for amb in mc.get("raw_ambiguities", []):
            if not isinstance(amb, dict):
                continue
            text = str(amb.get("text") or "")
            reason = str(amb.get("reason") or "")
            amb_id = str(amb.get("ambiguity_id") or "")
            # Check if this statement was already answered in clarification_history
            already_covered = any(
                _normalize_text(text)[:30] in _normalize_text(r["question_text"])
                for r in resolved
            )
            if not already_covered and not any(u.get("question_key") == amb_id for u in unresolved):
                unresolved.append({
                    "question_key": amb_id or f"raw_amb_{len(unresolved)}",
                    "question_text": f'Ambiguous phrasing: "{text}"',
                    "category": "TECHNICAL_SCOPE",
                    "priority": "RECOMMENDED",
                    "is_blocking": False,
                    "status": "UNANSWERED",
                    "why_ambiguous": reason,
                    "suggested_options": amb.get("suggested_interpretations") or [],
                })

    # If canonical_json has ambiguities and unresolved is empty
    if not resolved and not unresolved and spec_version.canonical_json:
        cj_ambs = spec_version.canonical_json.get("ambiguities") or []
        for idx, a in enumerate(cj_ambs):
            if isinstance(a, dict):
                unresolved.append({
                    "question_key": f"cj_amb_{idx}",
                    "question_text": a.get("statement") or "",
                    "category": "TECHNICAL_SCOPE",
                    "priority": "BLOCKING" if a.get("ta_confirmation_required") else "RECOMMENDED",
                    "is_blocking": bool(a.get("ta_confirmation_required")),
                    "status": "UNANSWERED",
                    "why_ambiguous": a.get("why_ambiguous") or "",
                    "suggested_options": a.get("suggested_clarifications") or [],
                })

    return resolved, unresolved


def get_jd_contexts_and_versions(jd_id: str, db: Session) -> Dict[str, Any]:
    """
    Retrieves and classifies Baseline, Enriched, and Ambiguity-Resolved specifications.
    Guarantees reliable recovery even if some historical records are missing.
    """
    spec_versions = (
        db.query(JobSpecificationVersion)
        .join(JobDescriptionVersion)
        .filter(JobDescriptionVersion.job_description_id == jd_id)
        .order_by(JobSpecificationVersion.specification_version.asc())
        .all()
    )

    if not spec_versions:
        return {
            "has_baseline": False,
            "has_enriched": False,
            "has_resolved": False,
            "versions": [],
            "baseline_spec": None,
            "enriched_spec": None,
            "resolved_spec": None,
        }

    # Baseline is the earliest specification (v1)
    baseline_spec = spec_versions[0]

    # Enriched is the latest specification that contains an enrichment report
    enriched_spec = None
    for sv in reversed(spec_versions):
        if sv.enrichment_report_json or sv.s3_enriched_markdown_key:
            enriched_spec = sv
            break

    # Ambiguity-Resolved is the latest specification where clarifications were resolved
    # (specification_version > 1 or parent_specification_version_id is set or lifecycle_status is FINALIZED
    # or clarification_history has answered questions)
    resolved_spec = None
    for sv in reversed(spec_versions):
        if sv.specification_version > 1 or sv.parent_specification_version_id:
            resolved_spec = sv
            break
        mc = sv.master_context_json or {}
        if any(q.get("status") in ("ANSWERED", "EXPLICITLY_UNSPECIFIED") for q in mc.get("clarification_history", [])):
            resolved_spec = sv
            break

    # If only 1 version exists and it has answered questions, baseline can be extracted as pre-resolution
    has_resolved = resolved_spec is not None and (
        resolved_spec.specification_version > baseline_spec.specification_version
        or any(
            q.get("status") in ("ANSWERED", "EXPLICITLY_UNSPECIFIED")
            for q in (resolved_spec.master_context_json or {}).get("clarification_history", [])
        )
    )

    return {
        "has_baseline": baseline_spec is not None,
        "has_enriched": enriched_spec is not None,
        "has_resolved": has_resolved,
        "versions": [
            {
                "specification_version": sv.specification_version,
                "created_at": sv.created_at.isoformat() if sv.created_at else None,
                "has_enrichment": bool(sv.enrichment_report_json or sv.s3_enriched_markdown_key),
                "lifecycle_status": getattr(sv.lifecycle_status, "value", str(sv.lifecycle_status)),
            }
            for sv in spec_versions
        ],
        "baseline_spec": baseline_spec,
        "enriched_spec": enriched_spec,
        "resolved_spec": resolved_spec if has_resolved else None,
    }


def compute_context_diff(
    base_reqs: List[Dict[str, Any]],
    target_reqs: List[Dict[str, Any]],
    base_type: str,
    target_type: str,
    enrichment_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Computes a clean, semantic diff between base and target requirements:
    Added, Removed, Modified, and Unchanged.
    """
    # Build lookup by id and normalized text
    base_by_id = {r["id"]: r for r in base_reqs if r.get("id")}
    base_by_text = {_normalize_text(r["text"]): r for r in base_reqs if r.get("text")}

    target_by_id = {r["id"]: r for r in target_reqs if r.get("id")}
    target_by_text = {_normalize_text(r["text"]): r for r in target_reqs if r.get("text")}

    enrichment_map = {}
    if enrichment_report and isinstance(enrichment_report, dict):
        for item in enrichment_report.get("items", []):
            req_id = item.get("requirement_id")
            if req_id:
                enrichment_map[req_id] = item

    added: List[Dict[str, Any]] = []
    removed: List[Dict[str, Any]] = []
    modified: List[Dict[str, Any]] = []
    unchanged: List[Dict[str, Any]] = []

    matched_base_ids = set()

    for treq in target_reqs:
        tid = treq.get("id")
        t_norm = _normalize_text(treq.get("text", ""))

        breq = None
        if tid and tid in base_by_id:
            breq = base_by_id[tid]
        elif t_norm and t_norm in base_by_text:
            breq = base_by_text[t_norm]

        # Attach enriched guidance if target_type is enriched or target has it
        enriched_item = enrichment_map.get(tid)
        treq_enriched = dict(treq)
        if enriched_item:
            treq_enriched["enriched_guidance"] = {
                "technical_concept_summary": enriched_item.get("technical_concept_summary"),
                "strong_evidence_signals": enriched_item.get("strong_evidence_signals") or [],
                "weak_or_ambiguous_signals": enriched_item.get("weak_or_ambiguous_signals") or [],
                "screening_question": enriched_item.get("screening_question"),
            }

        if breq is None:
            # Added in target
            added.append({
                **treq_enriched,
                "diff_status": "added",
                "diff_badge": "+ Added",
                "diff_reason": "New requirement confirmed or added in target context",
            })
        else:
            matched_base_ids.add(breq.get("id"))
            changes = []
            if breq.get("priority") != treq.get("priority"):
                changes.append(f"Priority changed: {breq.get('priority')} → {treq.get('priority')}")
            if breq.get("provenance_type") != treq.get("provenance_type"):
                changes.append(f"Status changed: {breq.get('provenance_badge')} → {treq.get('provenance_badge')}")
            if _normalize_text(breq.get("text", "")) != t_norm:
                changes.append("Requirement phrasing refined")
            if target_type == "enriched" and enriched_item:
                changes.append("Enriched with technical explanation, resume signals, and screening question")

            if changes:
                modified.append({
                    **treq_enriched,
                    "diff_status": "modified",
                    "diff_badge": "~ Modified",
                    "base_priority": breq.get("priority"),
                    "target_priority": treq.get("priority"),
                    "base_provenance": breq.get("provenance_badge"),
                    "target_provenance": treq.get("provenance_badge"),
                    "base_text": breq.get("text"),
                    "changes": changes,
                })
            else:
                unchanged.append({
                    **treq_enriched,
                    "diff_status": "unchanged",
                    "diff_badge": "= Unchanged",
                })

    for breq in base_reqs:
        bid = breq.get("id")
        b_norm = _normalize_text(breq.get("text", ""))
        if bid not in matched_base_ids and (not b_norm or b_norm not in target_by_text):
            removed.append({
                **breq,
                "diff_status": "removed",
                "diff_badge": "- Removed",
                "diff_reason": "Omitted or de-prioritized in target context",
            })

    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "unchanged": unchanged,
        "counts": {
            "total_base": len(base_reqs),
            "total_target": len(target_reqs),
            "added": len(added),
            "removed": len(removed),
            "modified": len(modified),
            "unchanged": len(unchanged),
        },
    }


def build_comparison_payload(
    jd_id: str,
    db: Session,
    base_context: str = "baseline",
    target_context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Builds the full comparison payload across Baseline, Enriched, and Ambiguity-Resolved contexts.
    """
    context_data = get_jd_contexts_and_versions(jd_id, db)
    baseline_spec = context_data["baseline_spec"]
    enriched_spec = context_data["enriched_spec"]
    resolved_spec = context_data["resolved_spec"]

    if not baseline_spec:
        return {
            "jd_id": jd_id,
            "has_baseline": False,
            "has_enriched": False,
            "has_resolved": False,
            "message": "No specifications found for this JD",
        }

    # Extract requirements
    baseline_reqs = _extract_requirements_from_spec(baseline_spec) if baseline_spec else []
    resolved_reqs = _extract_requirements_from_spec(resolved_spec) if resolved_spec else baseline_reqs

    # Ambiguities
    base_resolved_ambs, base_unresolved_ambs = _extract_ambiguities_from_spec(baseline_spec) if baseline_spec else ([], [])
    target_resolved_ambs, target_unresolved_ambs = (
        _extract_ambiguities_from_spec(resolved_spec) if resolved_spec else (base_resolved_ambs, base_unresolved_ambs)
    )

    # Markdown
    baseline_md = ""
    if baseline_spec and baseline_spec.s3_markdown_key:
        try:
            baseline_md = storage.get_text(baseline_spec.s3_markdown_key)
        except Exception:
            baseline_md = ""

    enriched_md = ""
    if enriched_spec and enriched_spec.s3_enriched_markdown_key:
        try:
            enriched_md = storage.get_text(enriched_spec.s3_enriched_markdown_key)
        except Exception:
            enriched_md = ""

    resolved_md = ""
    if resolved_spec and resolved_spec.s3_markdown_key:
        try:
            resolved_md = storage.get_text(resolved_spec.s3_markdown_key)
        except Exception:
            resolved_md = ""

    # Auto-select target_context if not specified
    if not target_context:
        if context_data["has_resolved"]:
            target_context = "resolved"
        elif context_data["has_enriched"]:
            target_context = "enriched"
        else:
            target_context = "baseline"

    # Select base and target requirement lists for diff calculation
    req_sets = {
        "baseline": baseline_reqs,
        "enriched": baseline_reqs,  # Enriched starts from baseline requirements + guidance
        "resolved": resolved_reqs,
    }

    base_set = req_sets.get(base_context, baseline_reqs)
    target_set = req_sets.get(target_context, resolved_reqs)

    enrichment_report = enriched_spec.enrichment_report_json if enriched_spec else None

    diff_result = compute_context_diff(
        base_set,
        target_set,
        base_context,
        target_context,
        enrichment_report=enrichment_report if target_context == "enriched" else None,
    )

    return {
        "jd_id": jd_id,
        "has_baseline": context_data["has_baseline"],
        "has_enriched": context_data["has_enriched"],
        "has_resolved": context_data["has_resolved"],
        "selected_base_context": base_context,
        "selected_target_context": target_context,
        "versions": context_data["versions"],
        "contexts": {
            "baseline": {
                "version": baseline_spec.specification_version if baseline_spec else 1,
                "markdown": baseline_md,
                "requirements_count": len(baseline_reqs),
                "created_at": baseline_spec.created_at.isoformat() if baseline_spec and baseline_spec.created_at else None,
            },
            "enriched": {
                "version": enriched_spec.specification_version if enriched_spec else None,
                "markdown": enriched_md,
                "has_guidance": bool(enrichment_report),
                "evaluation_priorities": (enrichment_report or {}).get("evaluation_priorities", []),
                "created_at": enriched_spec.created_at.isoformat() if enriched_spec and enriched_spec.created_at else None,
            },
            "resolved": {
                "version": resolved_spec.specification_version if resolved_spec else None,
                "markdown": resolved_md,
                "requirements_count": len(resolved_reqs),
                "lifecycle_status": getattr(resolved_spec.lifecycle_status, "value", str(resolved_spec.lifecycle_status)) if resolved_spec else None,
                "created_at": resolved_spec.created_at.isoformat() if resolved_spec and resolved_spec.created_at else None,
            },
        },
        "diff": diff_result,
        "ambiguities": {
            "resolved": target_resolved_ambs,
            "unresolved": target_unresolved_ambs,
            "counts": {
                "resolved": len(target_resolved_ambs),
                "unresolved": len(target_unresolved_ambs),
            },
        },
    }
