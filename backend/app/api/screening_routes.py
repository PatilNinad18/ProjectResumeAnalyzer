"""
Resume Screening REST API (v2.1)
=================================
Endpoints for uploading candidate resumes, triggering evaluation, and
fetching ranked results for a Job Description.

Changes from v2.0:
  - Upload: computes SHA-256 file_hash for deduplication, runs parse quality gate
    at upload time for immediate feedback.
  - Response building: uses timeline_observations (not red_flags), includes
    evaluator provenance, quote_verification_pass, spec_outdated, effective_tier.
  - Leaderboard: excludes PARSE_FAILED from ranked scoring; shows them at bottom.
  - New endpoint: POST /{resume_id}/override — recruiter override with audit trail.
  - New endpoint: GET /status — lightweight polling endpoint (scores + statuses only).

All endpoints are nested under /api/jds/{jd_id}/resumes.
"""
from __future__ import annotations

import copy
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models.db_models import AuditEvent, JDLifecycleStatusEnum, JobDescription, JobSpecificationVersion, gen_uuid
from app.models.screening_models import (
    CandidateEvaluation,
    CandidateResume,
    MatchTierEnum,
    ScreeningStatusEnum,
)
from app.schemas.screening import (
    BatchResumeUploadResponse,
    CandidateEvaluationResponse,
    CandidateProfile,
    EvaluatorProvenance,
    ParseQualityCheck,
    RecruiterOverrideRequest,
    RecruiterOverrideResponse,
    RequirementEvaluation,
    RequirementSummary,
    ResumeUploadResponse,
    ScoreBreakdown,
    ScreeningLeaderboardItem,
    ScreeningLeaderboardResponse,
    ScreeningOverrideEvent,
    ScreeningPolicyUpdate,
    ScreeningRun,
    ScreeningStatus,
    ScreeningTriggerRequest,
    ScreeningTriggerResponse,
    ValidationCheckpoint,
)
from app.schemas.canonical import JobEvaluationSpecification
from app.schemas.enrichment import TAEnrichmentReport
from app.schemas.master_context import JDMasterContext
from app.services.document_parser import DocumentParseError, SUPPORTED_EXTENSIONS, parse_document
from app.services.markdown_renderer import render_markdown
from app.services.projection.canonical_projector import _flatten_requirements
from app.services.resume.evaluator import NO_EVALUATION_CRITERIA, check_parse_quality, screening_criteria
from app.services.resume.ollama_screening import EVALUATOR_ENGINE, PROMPT_VERSION, SEED, configured_model
from app.services.resume.profiler import compute_file_hash, resume_parse_issue
from app.services.resume.storage import RESUME_STORAGE_DIR, ResumeInUseError, remove_candidate_data
from app.services.specification_versions import lock_specification_revision, specification_checksum, specifications_for_jd
from app.services.storage import build_key, checksum, get_storage
from app.workers.screening_worker import NO_CRITERIA_REVIEW, screening_queue

logger = logging.getLogger("jd_agent.screening_routes")

router = APIRouter(prefix="/api/jds/{jd_id}/resumes", tags=["screening"])

# --- Local resume storage directory ---
RESUME_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

# File magic bytes for supported formats
_PDF_MAGIC  = b"%PDF"
_DOCX_MAGIC = b"PK\x03\x04"   # ZIP container (OOXML)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_jd_or_404(jd_id: str, db: Session) -> JobDescription:
    jd = db.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail=f"JobDescription '{jd_id}' not found.")
    return jd


def _get_resume_or_404(jd_id: str, resume_id: str, db: Session) -> CandidateResume:
    resume = (
        db.query(CandidateResume)
        .filter(CandidateResume.id == resume_id, CandidateResume.job_description_id == jd_id)
        .first()
    )
    if not resume:
        raise HTTPException(status_code=404, detail=f"Resume '{resume_id}' not found for JD '{jd_id}'.")
    return resume


def _verify_file_magic(filename: str, content: bytes) -> Optional[str]:
    """
    Check file magic bytes to verify the file is actually the format claimed by extension.
    Returns an error string if mismatch, None if OK.
    """
    ext = Path(filename).suffix.lower()
    if ext == ".pdf" and not content.startswith(_PDF_MAGIC):
        return "File does not appear to be a valid PDF (wrong magic bytes)."
    if ext == ".docx" and not content.startswith(_DOCX_MAGIC):
        return "File does not appear to be a valid DOCX (wrong magic bytes)."
    return None


def _tier_sort_key(tier: Optional[str]) -> int:
    order = {"STRONG_MATCH": 0, "POTENTIAL_MATCH": 1, "NOT_A_FIT": 2}
    return order.get(tier or "", 3)


def _get_latest_eval(resume: CandidateResume) -> Optional[CandidateEvaluation]:
    return max(resume.evaluations, key=lambda e: e.created_at or datetime.min, default=None)


def _is_outdated(evaluation: CandidateEvaluation, spec: Optional[JobSpecificationVersion], digest: Optional[str]) -> bool:
    return (
        spec is None or evaluation.spec_version_id != spec.id or evaluation.spec_checksum != digest
        or evaluation.evaluator_engine != EVALUATOR_ENGINE or evaluation.prompt_version != PROMPT_VERSION
        or evaluation.model_name != configured_model()
    )


def _status_and_review_reason(evaluation: Optional[CandidateEvaluation], resume: CandidateResume) -> tuple[ScreeningStatus, Optional[str]]:
    if evaluation is None:
        quality = resume.parse_quality_check or {}
        if quality.get("passed") is False:
            status = ScreeningStatus(quality.get("status") or "PARSE_FAILED")
            return status, quality.get("failure_reason")
        return ScreeningStatus.QUEUED, None
    if evaluation.status == ScreeningStatusEnum.COMPLETED and (
        (evaluation.score_breakdown or {}).get("warning") == NO_EVALUATION_CRITERIA
        or evaluation.overall_score is None
    ):
        return ScreeningStatus.NEEDS_REVIEW, NO_CRITERIA_REVIEW
    status = ScreeningStatus(evaluation.status.value)
    reason = evaluation.error_message if status in (ScreeningStatus.PARSE_FAILED, ScreeningStatus.NEEDS_REVIEW) else None
    return status, reason


def _build_leaderboard_item(
    resume: CandidateResume, spec: Optional[JobSpecificationVersion], digest: Optional[str],
) -> ScreeningLeaderboardItem:
    latest_eval = _get_latest_eval(resume)
    status, reason = _status_and_review_reason(latest_eval, resume)
    outdated = bool(latest_eval and _is_outdated(latest_eval, spec, digest))
    scored = latest_eval if status == ScreeningStatus.COMPLETED and not outdated else None
    mh_summary = (scored.must_haves_summary or {}) if scored else {}
    return ScreeningLeaderboardItem(
        rank=None,
        candidate_resume_id=resume.id,
        evaluation_id=latest_eval.id if latest_eval else None,
        has_override=bool(scored and scored.recruiter_override_tier),
        filename=resume.filename,
        candidate_name=resume.candidate_name,
        email=resume.email,
        total_experience_years=resume.total_experience_years,
        overall_score=(scored.recruiter_override_score if scored.recruiter_override_score is not None else scored.overall_score) if scored else None,
        match_tier=scored.match_tier if scored else None,
        effective_tier=(scored.recruiter_override_tier or scored.match_tier) if scored else None,
        must_haves_met=mh_summary.get("met", 0),
        must_haves_partially_met=mh_summary.get("partially_met", 0),
        must_haves_total=mh_summary.get("total", 0),
        not_evidenced_count=mh_summary.get("not_evidenced", 0),
        validation_checkpoints_count=len(scored.validation_checkpoints or []) if scored else 0,
        status=status,
        review_reason=reason,
        spec_outdated=outdated,
        parse_failed=status == ScreeningStatus.PARSE_FAILED,
        created_at=resume.created_at,
    )


def _build_evaluation_response(
    db: Session, resume: CandidateResume, evaluation: Optional[CandidateEvaluation], spec: Optional[JobSpecificationVersion],
) -> CandidateEvaluationResponse:
    latest_eval = evaluation
    status, reason = _status_and_review_reason(latest_eval, resume)
    digest = specification_checksum(spec) if spec else None
    outdated = bool(latest_eval and _is_outdated(latest_eval, spec, digest))
    events = []
    if latest_eval:
        events = db.query(AuditEvent).filter_by(
            entity_type="candidate_evaluation", entity_id=latest_eval.id, action="recruiter_override",
        ).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).all()
    history = [
        ScreeningOverrideEvent(**event.details, created_at=event.created_at)
        for event in events
    ]
    runs = [
        ScreeningRun(
            evaluation_id=run.id, specification_version=run.specification_version,
            status=_status_and_review_reason(run, resume)[0],
            overall_score=run.overall_score if _status_and_review_reason(run, resume)[0] == ScreeningStatus.COMPLETED else None,
            match_tier=run.match_tier if _status_and_review_reason(run, resume)[0] == ScreeningStatus.COMPLETED else None,
            evaluator_version=run.evaluator_engine if run.spec_checksum else None,
            spec_outdated=_is_outdated(run, spec, digest), created_at=run.created_at,
        )
        for run in sorted(resume.evaluations, key=lambda item: item.created_at or datetime.min, reverse=True)
    ]
    profile = resume.parsed_profile_json or {}
    candidate_profile = CandidateProfile(
        candidate_name=resume.candidate_name or profile.get("candidate_name"),
        email=resume.email or profile.get("email"),
        phone=resume.phone or profile.get("phone"),
        total_experience_years=resume.total_experience_years,
        skills=profile.get("skills", []),
        companies=profile.get("companies", []),
        current_or_last_title=profile.get("current_or_last_title"),
    )

    provenance = EvaluatorProvenance(
        evaluator_engine=latest_eval.evaluator_engine,
        model_name=latest_eval.model_name,
        model_version=latest_eval.model_version,
        prompt_version=latest_eval.prompt_version or "eval_v2.1",
        temperature=latest_eval.temperature or 0.0,
        seed=latest_eval.seed or 42,
    ) if latest_eval and latest_eval.spec_checksum else None

    if not latest_eval or status != ScreeningStatus.COMPLETED:
        return CandidateEvaluationResponse(
            candidate_resume_id=resume.id,
            job_description_id=resume.job_description_id,
            spec_version_id=latest_eval.spec_version_id if latest_eval else None,
            specification_version=latest_eval.specification_version if latest_eval else 2,
            status=status,
            review_reason=reason,
            evaluation_id=latest_eval.id if latest_eval else None,
            spec_checksum=latest_eval.spec_checksum if latest_eval else None,
            spec_outdated=outdated,
            provenance=provenance,
            has_resume_profile=bool(resume.screening_profile_json),
            runs=runs,
            override_history=history,
            overall_score=None,
            match_tier=None,
            candidate_profile=candidate_profile,
            must_haves_summary=None,
            preferred_summary=None,
            score_breakdown=None,
            created_at=resume.created_at,
            completed_at=latest_eval.completed_at if reason else None,
        )

    def _parse_req_evals(items: list) -> List[RequirementEvaluation]:
        result = []
        for item in (items or []):
            try:
                result.append(RequirementEvaluation(**item))
            except Exception:
                pass
        return result

    def _parse_checkpoints(items: list) -> List[ValidationCheckpoint]:
        result = []
        for item in (items or []):
            try:
                result.append(ValidationCheckpoint(**item))
            except Exception:
                pass
        return result

    mh = latest_eval.must_haves_summary or {}
    pf = latest_eval.preferred_summary or {}
    sb = latest_eval.score_breakdown or {}

    return CandidateEvaluationResponse(
        candidate_resume_id=resume.id,
        job_description_id=resume.job_description_id,
        evaluation_id=latest_eval.id,
        spec_version_id=latest_eval.spec_version_id,
        specification_version=latest_eval.specification_version,
        status=status,
        overall_score=latest_eval.overall_score,
        spec_checksum=latest_eval.spec_checksum,
        spec_outdated=outdated,
        has_resume_profile=bool(resume.screening_profile_json),
        can_override=not outdated and spec.lifecycle_status == JDLifecycleStatusEnum.FINALIZED and latest_eval is _get_latest_eval(resume),
        runs=runs,
        override_history=history,
        match_tier=latest_eval.match_tier,
        provenance=provenance,
        quote_verification_pass=latest_eval.quote_verification_pass,
        candidate_profile=candidate_profile,
        must_haves_summary=RequirementSummary(**mh) if mh else None,
        preferred_summary=RequirementSummary(**pf) if pf else None,
        score_breakdown=ScoreBreakdown(**sb) if sb else None,
        detailed_evaluations=_parse_req_evals(latest_eval.detailed_evaluations),
        validation_checkpoints=_parse_checkpoints(latest_eval.validation_checkpoints),
        timeline_observations=[
            note for note in (latest_eval.timeline_observations or [])
            if not note.lower().startswith(("career pause", "employment gap", "career gap"))
        ],
        tailored_interview_questions=latest_eval.tailored_interview_questions or [],
        recruiter_override_tier=latest_eval.recruiter_override_tier,
        recruiter_override_score=latest_eval.recruiter_override_score,
        override_reason=latest_eval.override_reason,
        overridden_by=latest_eval.overridden_by,
        overridden_at=latest_eval.overridden_at,
        created_at=latest_eval.created_at,
        completed_at=latest_eval.completed_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=BatchResumeUploadResponse, status_code=202)
async def upload_resumes(
    jd_id: str,
    files: List[UploadFile] = File(..., description="One or more resume files (.pdf, .docx, .txt)"),
    spec_version_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Upload one or more candidate resumes for a Job Description.
    - Validates file type, size, and magic bytes.
    - Computes SHA-256 hash for deduplication.
    - Runs parse quality gate immediately (flags unreadable PDFs at upload time).
    - Stores files locally and creates CandidateResume rows.
    - Evaluation is NOT triggered automatically — call /screen separately.
    """
    _get_jd_or_404(jd_id, db)

    uploaded: List[ResumeUploadResponse] = []
    failed: List[dict] = []

    for file in files:
        filename = Path(file.filename or "unknown").name
        ext = Path(filename).suffix.lower()

        if ext not in SUPPORTED_EXTENSIONS:
            failed.append({
                "filename": filename,
                "error": f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
            })
            continue

        content = await file.read(MAX_FILE_SIZE_BYTES + 1)

        if len(content) == 0:
            failed.append({"filename": filename, "error": "Empty file (0 bytes)."})
            continue

        if len(content) > MAX_FILE_SIZE_BYTES:
            failed.append({
                "filename": filename,
                "error": f"File exceeds the {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB limit.",
            })
            continue

        # Magic bytes check (security: prevent disguised executables)
        if ext in (".pdf", ".docx"):
            magic_err = _verify_file_magic(filename, content)
            if magic_err:
                failed.append({"filename": filename, "error": magic_err})
                continue

        # SHA-256 file hash for deduplication
        file_hash = compute_file_hash(content)

        # Store file on disk
        resume_id = gen_uuid()
        safe_name = f"{resume_id}_{filename}"
        file_path  = RESUME_STORAGE_DIR / safe_name
        # Run parse quality gate immediately on upload for fast user feedback
        try:
            parsed_text = parse_document(filename, content)
            quality = check_parse_quality(parsed_text)
            quality["failure_reason"] = resume_parse_issue(parsed_text)
            quality["passed"] = quality["failure_reason"] is None
            quality["status"] = "QUEUED" if quality["passed"] else "NEEDS_REVIEW"
        except DocumentParseError:
            parsed_text = ""
            quality = {
                "passed": False,
                "text_length": 0,
                "word_count": 0,
                "alpha_ratio": 0.0,
                "failure_reason": "No readable text was extracted. Upload a text-searchable copy.",
                "status": "PARSE_FAILED",
            }

        # Serialize the duplicate check and insert for this JD. Parse first so other
        # requests need only wait for the short file and database write.
        lock_specification_revision(db, jd_id)
        existing_hash = db.query(CandidateResume).filter_by(job_description_id=jd_id, file_hash=file_hash).first()
        if existing_hash:
            failed.append({
                "filename": filename,
                "error": f"Duplicate file already uploaded to this JD as '{existing_hash.filename}'.",
                "existing_candidate_resume_id": existing_hash.id,
            })
            db.rollback()
            continue

        resume = CandidateResume(
            id=resume_id,
            job_description_id=jd_id,
            filename=filename,
            file_size_bytes=len(content),
            file_key=str(file_path),
            file_hash=file_hash,
            parsed_text=parsed_text or None,
            parse_quality_check=quality,
        )
        try:
            file_path.write_bytes(content)
            db.add(resume)
            db.commit()
        except (OSError, SQLAlchemyError):
            db.rollback()
            try:
                file_path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Failed to clean up an incomplete resume upload %s", resume_id)
            failed.append({"filename": filename, "error": "Resume could not be stored. Retry the upload."})
            continue

        status = ScreeningStatus(quality["status"])
        uploaded.append(ResumeUploadResponse(
            candidate_resume_id=resume_id,
            filename=filename,
            file_size_bytes=len(content),
            status=status,
            parse_quality=ParseQualityCheck(**quality),
            message=(
                "Uploaded successfully. Call /screen to start evaluation."
                if quality["passed"]
                else f"Parse quality gate FAILED: {quality['failure_reason']} Manual review required."
            ),
        ))

    return BatchResumeUploadResponse(
        uploaded=uploaded,
        failed=failed,
        total_queued=sum(1 for u in uploaded if u.status == ScreeningStatus.QUEUED),
    )


def _queue_evaluations(
    db: Session, jd_id: str, resumes: list[CandidateResume], spec_id: Optional[str],
    profile_batch_id: str | None = None,
) -> ScreeningTriggerResponse:
    versions = specifications_for_jd(db, jd_id)
    spec = versions.first()
    if spec_id and (not spec or spec.id != spec_id):
        if not versions.filter(JobSpecificationVersion.id == spec_id).first():
            raise HTTPException(404, "Specification is not part of this JD.")
        raise HTTPException(409, "The specification changed. Reload and screen against the current version.")
    if not spec or spec.lifecycle_status != JDLifecycleStatusEnum.FINALIZED:
        raise HTTPException(409, "Finalize the current job specification before screening resumes.")

    digest = specification_checksum(spec)
    model = configured_model()
    queued_ids = []
    for resume in resumes:
        run_key = checksum(f"{resume.id}:{spec.id}:{digest}:{EVALUATOR_ENGINE}:{PROMPT_VERSION}:{model}")
        evaluation = db.query(CandidateEvaluation).filter_by(active_run_key=run_key).first()
        if evaluation is None:
            evaluation = CandidateEvaluation(
                candidate_resume_id=resume.id, job_description_id=jd_id,
                spec_version_id=spec.id, specification_version=spec.specification_version,
                spec_checksum=digest, active_run_key=run_key,
                profile_batch_id=profile_batch_id,
                evaluator_engine=EVALUATOR_ENGINE, prompt_version=PROMPT_VERSION,
                model_name=model, temperature=0.0, seed=SEED,
                status=ScreeningStatusEnum.QUEUED, created_at=datetime.now(timezone.utc),
            )
            try:
                with db.begin_nested():
                    db.add(evaluation)
                    db.flush()
            except IntegrityError:
                evaluation = db.query(CandidateEvaluation).filter_by(active_run_key=run_key).first()
                if evaluation is None:
                    raise
        queued_ids.append(evaluation.id)

    db.commit()
    for evaluation_id in queued_ids:
        screening_queue.enqueue(evaluation_id)
    return ScreeningTriggerResponse(
        queued_count=len(queued_ids), candidate_resume_ids=queued_ids,
        message=f"Screening requested for {len(queued_ids)} candidate(s) against specification v{spec.specification_version}.",
    )


@router.post("/screen", response_model=ScreeningTriggerResponse, status_code=202)
def trigger_screening(jd_id: str, body: ScreeningTriggerRequest = ScreeningTriggerRequest(), db: Session = Depends(get_db)):
    _get_jd_or_404(jd_id, db)
    lock_specification_revision(db, jd_id)
    query = db.query(CandidateResume).filter_by(job_description_id=jd_id)
    if body.candidate_resume_ids is not None:
        query = query.filter(CandidateResume.id.in_(body.candidate_resume_ids))
    resumes = query.all()
    if not resumes:
        raise HTTPException(404, "No candidate resumes found for this JD. Upload resumes first.")
    return _queue_evaluations(db, jd_id, resumes, body.spec_version_id,
                              str(body.profile_batch_id) if body.profile_batch_id else None)


@router.get("", response_model=ScreeningLeaderboardResponse)
def get_leaderboard(jd_id: str, db: Session = Depends(get_db)):
    _get_jd_or_404(jd_id, db)
    spec = specifications_for_jd(db, jd_id).first()
    digest = specification_checksum(spec) if spec else None
    summaries = selectinload(CandidateResume.evaluations).load_only(
        CandidateEvaluation.created_at, CandidateEvaluation.status, CandidateEvaluation.error_message,
        CandidateEvaluation.spec_version_id, CandidateEvaluation.spec_checksum,
        CandidateEvaluation.evaluator_engine, CandidateEvaluation.prompt_version, CandidateEvaluation.model_name,
        CandidateEvaluation.overall_score, CandidateEvaluation.match_tier, CandidateEvaluation.score_breakdown,
        CandidateEvaluation.recruiter_override_score, CandidateEvaluation.recruiter_override_tier,
        CandidateEvaluation.must_haves_summary, CandidateEvaluation.validation_checkpoints,
    )
    resumes = db.query(CandidateResume).options(summaries).filter_by(
        job_description_id=jd_id,
    ).order_by(CandidateResume.created_at).all()

    # Historic duplicates can predate upload-time SHA-256 deduplication.
    deduped = {}
    for resume in resumes:
        key = resume.file_hash or resume.id
        previous = deduped.get(key)
        if previous is None or (bool(resume.parsed_text), len(resume.evaluations)) > (
            bool(previous.parsed_text), len(previous.evaluations),
        ):
            deduped[key] = resume
    items = [_build_leaderboard_item(resume, spec, digest) for resume in deduped.values()]
    items.sort(key=lambda item: (item.overall_score is None, _tier_sort_key(item.effective_tier), -(item.overall_score or 0)))
    for rank, item in enumerate(items, start=1):
        if item.overall_score is None:
            break
        item.rank = rank
    return ScreeningLeaderboardResponse(
        job_description_id=jd_id, total_candidates=len(items), candidates=items,
        spec_version_id=spec.id if spec else None,
        specification_version=spec.specification_version if spec else None,
        spec_finalized=bool(spec and spec.lifecycle_status == JDLifecycleStatusEnum.FINALIZED),
        criteria=screening_criteria(spec.canonical_json) if spec else [],
    )


@router.get("/status")
def get_screening_status(jd_id: str, db: Session = Depends(get_db)):
    leaderboard = get_leaderboard(jd_id, db)
    keys = {"candidate_resume_id", "filename", "status", "overall_score", "effective_tier", "parse_failed", "spec_outdated"}
    return {"job_description_id": jd_id, "candidates": [row.model_dump(include=keys) for row in leaderboard.candidates]}


@router.put("/policy")
def update_screening_policy(jd_id: str, body: ScreeningPolicyUpdate, db: Session = Depends(get_db)):
    jd = _get_jd_or_404(jd_id, db)
    lock_specification_revision(db, jd_id)
    spec = specifications_for_jd(db, jd_id).first()
    if not spec or spec.id != body.spec_version_id or spec.lifecycle_status != JDLifecycleStatusEnum.FINALIZED:
        raise HTTPException(409, "The specification changed. Reload the current finalized specification.")
    choices = {item["requirement_id"]: item["critical"] for item in screening_criteria(spec.canonical_json)}
    selected = set(body.critical_requirement_ids)
    if selected - choices.keys():
        raise HTTPException(422, "Critical requirements must be scorable must-haves in this specification.")
    previous = {key for key, critical in choices.items() if critical}
    if selected == previous:
        db.commit()
        return {"spec_version_id": spec.id, "specification_version": spec.specification_version}

    version = spec.specification_version + 1
    payload = copy.deepcopy(spec.canonical_json)
    payload["metadata"] = {**(payload.get("metadata") or {}), "specification_version": version}
    for criterion in payload.get("evidence_requirements", []):
        if criterion.get("requirement_id") in choices:
            criterion["critical"] = criterion["requirement_id"] in selected
    canonical = JobEvaluationSpecification.model_validate(payload)
    master = JDMasterContext.model_validate(spec.master_context_json) if spec.master_context_json else None
    if master:
        for requirement in _flatten_requirements(master.requirements):
            requirement.is_critical = requirement.id in selected
    storage = get_storage()
    json_key = build_key(str(jd.project_id), jd_id, version, "json")
    md_key = build_key(str(jd.project_id), jd_id, version, "markdown")
    storage.put_text(json_key, json.dumps(payload, ensure_ascii=False, indent=2), "application/json")
    storage.put_text(md_key, render_markdown(canonical), "text/markdown")
    revision = JobSpecificationVersion(
        job_description_version_id=spec.job_description_version_id, specification_version=version,
        parent_specification_version_id=spec.id, canonical_json=payload,
        master_context_json=master.model_dump(mode="json") if master else None,
        lifecycle_status=JDLifecycleStatusEnum.FINALIZED, s3_json_key=json_key, s3_markdown_key=md_key,
        prompt_version=spec.prompt_version, model_version=spec.model_version,
        is_valid=spec.is_valid, needs_review=spec.needs_review,
    )
    db.add(revision)
    db.flush()
    if spec.enrichment_report_json:
        try:
            report = TAEnrichmentReport.model_validate(spec.enrichment_report_json)
        except ValueError:
            logger.warning("Could not carry forward enrichment for specification %s", spec.id)
        else:
            report.source_specification_version_id = revision.id
            report.source_specification_version = version
            enriched_key = build_key(str(jd.project_id), jd_id, version, "enriched_markdown")
            storage.put_text(enriched_key, render_markdown(canonical, enrichment_report=report), "text/markdown")
            revision.enrichment_report_json = report.model_dump(mode="json")
            revision.s3_enriched_markdown_key = enriched_key
    db.add(AuditEvent(
        entity_type="job_specification_version", entity_id=revision.id, action="screening_policy_changed",
        details={"previous_critical_requirement_ids": sorted(previous), "critical_requirement_ids": sorted(selected)},
    ))
    db.commit()
    return {"spec_version_id": revision.id, "specification_version": revision.specification_version}


@router.get("/{resume_id}", response_model=CandidateEvaluationResponse)
def get_candidate_detail(jd_id: str, resume_id: str, evaluation_id: Optional[str] = None, db: Session = Depends(get_db)):
    resume = _get_resume_or_404(jd_id, resume_id, db)
    evaluation = _get_latest_eval(resume)
    if evaluation_id:
        evaluation = next((run for run in resume.evaluations if run.id == evaluation_id), None)
        if evaluation is None:
            raise HTTPException(404, "Screening run not found for this candidate.")
    return _build_evaluation_response(db, resume, evaluation, specifications_for_jd(db, jd_id).first())


@router.get("/{resume_id}/profile/{file_format}")
def download_resume_profile(jd_id: str, resume_id: str, file_format: Literal["json", "md"], db: Session = Depends(get_db)):
    resume = _get_resume_or_404(jd_id, resume_id, db)
    if not resume.screening_profile_json or not resume.screening_profile_markdown:
        raise HTTPException(404, "Screen this resume to generate its profile files.")
    if file_format == "json":
        content = json.dumps(resume.screening_profile_json, ensure_ascii=False, indent=2) + "\n"
        media_type = "application/json"
    else:
        content = resume.screening_profile_markdown
        media_type = "text/markdown"
    return Response(content, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="resume-{resume.id}.{file_format}"',
        "Cache-Control": "no-store",
    })


@router.post("/{resume_id}/override", response_model=RecruiterOverrideResponse)
def override_candidate_tier(jd_id: str, resume_id: str, body: RecruiterOverrideRequest, db: Session = Depends(get_db)):
    resume = _get_resume_or_404(jd_id, resume_id, db)
    lock_specification_revision(db, jd_id)
    evaluation = _get_latest_eval(resume)
    spec = specifications_for_jd(db, jd_id).first()
    if (
        not evaluation or evaluation.id != body.evaluation_id or not spec
        or spec.lifecycle_status != JDLifecycleStatusEnum.FINALIZED
        or _status_and_review_reason(evaluation, resume)[0] != ScreeningStatus.COMPLETED
        or _is_outdated(evaluation, spec, specification_checksum(spec))
    ):
        raise HTTPException(409, "Only the current completed run can be overridden. Refresh or rerun screening.")

    overridden_at = datetime.now(timezone.utc)
    evaluation.recruiter_override_tier = MatchTierEnum(body.override_tier.value)
    evaluation.recruiter_override_score = body.override_score
    evaluation.override_reason = body.reason
    evaluation.overridden_by = body.overridden_by
    evaluation.overridden_at = overridden_at
    db.add(AuditEvent(
        entity_type="candidate_evaluation", entity_id=evaluation.id, action="recruiter_override", created_at=overridden_at,
        details={"tier": body.override_tier.value, "score": body.override_score, "reason": body.reason, "reviewer": body.overridden_by},
    ))
    db.commit()
    return RecruiterOverrideResponse(
        evaluation_id=evaluation.id, candidate_resume_id=resume.id, job_description_id=jd_id,
        recruiter_override_tier=body.override_tier, recruiter_override_score=body.override_score,
        override_reason=body.reason, overridden_by=body.overridden_by, overridden_at=overridden_at,
        message="Recruiter override recorded.",
    )


@router.post("/{resume_id}/re-screen", response_model=ScreeningTriggerResponse, status_code=202)
def re_screen_candidate(jd_id: str, resume_id: str, spec_version_id: Optional[str] = None, db: Session = Depends(get_db)):
    lock_specification_revision(db, jd_id)
    resume = _get_resume_or_404(jd_id, resume_id, db)
    return _queue_evaluations(db, jd_id, [resume], spec_version_id)


@router.delete("/{resume_id}", status_code=204)
def delete_candidate(
    jd_id: str,
    resume_id: str,
    db: Session = Depends(get_db),
):
    """Delete a candidate and their screening records for this JD."""
    try:
        remove_candidate_data(db, jd_id, resume_id)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(404, str(exc)) from exc
    except ResumeInUseError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except (OSError, ValueError, SQLAlchemyError) as exc:
        db.rollback()
        logger.warning("Could not remove candidate data for resume %s", resume_id)
        raise HTTPException(503, "Candidate data could not be removed. Check the configured resume storage and retry.") from exc
