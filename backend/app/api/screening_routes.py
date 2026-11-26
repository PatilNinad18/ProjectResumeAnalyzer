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

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.db_models import JobDescription, gen_uuid
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
    ScreeningStatus,
    ScreeningTriggerRequest,
    ScreeningTriggerResponse,
    ValidationCheckpoint,
)
<<<<<<< HEAD
from app.services.document_parser import DocumentParseError, SUPPORTED_EXTENSIONS
from app.services.resume.evaluator import NO_EVALUATION_CRITERIA
from app.workers.screening_worker import NO_CRITERIA_REVIEW, screening_queue
=======
from app.services.document_parser import SUPPORTED_EXTENSIONS, parse_document
from app.services.resume.evaluator import check_parse_quality
from app.services.resume.profiler import compute_file_hash
from app.workers.screening_worker import screening_queue
>>>>>>> smartleaven_work/main

logger = logging.getLogger("jd_agent.screening_routes")

router = APIRouter(prefix="/api/jds/{jd_id}/resumes", tags=["screening"])

# --- Local resume storage directory ---
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
RESUME_STORAGE_DIR = Path(os.getenv("RESUME_STORAGE_DIR", str(BACKEND_DIR / "data" / "resumes"))).resolve()
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


<<<<<<< HEAD
def _get_latest_eval(resume: CandidateResume) -> Optional[CandidateEvaluation]:
    return max(resume.evaluations, key=lambda e: e.created_at or datetime.min, default=None)


def _status_and_review_reason(evaluation: Optional[CandidateEvaluation]) -> tuple[ScreeningStatus, Optional[str]]:
    if evaluation is None:
        return ScreeningStatus.QUEUED, None
    if evaluation.status == ScreeningStatusEnum.COMPLETED and (
        (evaluation.score_breakdown or {}).get("warning") == NO_EVALUATION_CRITERIA
        or evaluation.overall_score is None
    ):
        return ScreeningStatus.NEEDS_REVIEW, NO_CRITERIA_REVIEW
    status = ScreeningStatus(evaluation.status.value)
    reason = evaluation.error_message if status in (ScreeningStatus.PARSE_FAILED, ScreeningStatus.NEEDS_REVIEW) else None
    return status, reason


def _build_leaderboard_item(resume: CandidateResume) -> ScreeningLeaderboardItem:
    latest_eval = _get_latest_eval(resume)
    status, reason = _status_and_review_reason(latest_eval)
    scored = latest_eval if status == ScreeningStatus.COMPLETED else None
    mh_summary = (scored.must_haves_summary or {}) if scored else {}
=======
def _get_best_eval(resume: CandidateResume) -> Optional[CandidateEvaluation]:
    if not resume.evaluations:
        return None
    # Return the latest evaluation by created_at so live QUEUED/ANALYZING status is shown
    return sorted(resume.evaluations, key=lambda e: e.created_at or datetime.min, reverse=True)[0]


def _effective_tier(eval_: Optional[CandidateEvaluation]) -> Optional[MatchTierEnum]:
    """Return recruiter override tier if present, otherwise computed tier."""
    if not eval_:
        return None
    return eval_.recruiter_override_tier or eval_.match_tier


def _build_leaderboard_item(rank: int, resume: CandidateResume) -> ScreeningLeaderboardItem:
    latest_eval = _get_best_eval(resume)
    mh_summary  = latest_eval.must_haves_summary if latest_eval and latest_eval.must_haves_summary else {}
    status = ScreeningStatus(latest_eval.status.value) if latest_eval else ScreeningStatus.QUEUED
    eff_tier = _effective_tier(latest_eval)
>>>>>>> smartleaven_work/main
    return ScreeningLeaderboardItem(
        rank=None,
        candidate_resume_id=resume.id,
        filename=resume.filename,
        candidate_name=resume.candidate_name,
        email=resume.email,
        total_experience_years=resume.total_experience_years,
<<<<<<< HEAD
        overall_score=scored.overall_score if scored else None,
        match_tier=scored.match_tier if scored else None,
        must_haves_met=mh_summary.get("met", 0),
        must_haves_partially_met=mh_summary.get("partially_met", 0),
        must_haves_total=mh_summary.get("total", 0),
        not_evidenced_count=mh_summary.get("not_evidenced", 0),
        validation_checkpoints_count=len(scored.validation_checkpoints or []) if scored else 0,
        status=status,
        review_reason=reason,
=======
        overall_score=latest_eval.recruiter_override_score or latest_eval.overall_score if latest_eval else None,
        match_tier=latest_eval.match_tier if latest_eval else None,
        effective_tier=eff_tier,
        must_haves_met=mh_summary.get("met", 0) + mh_summary.get("partially_met", 0),
        must_haves_total=mh_summary.get("total", 0),
        not_evidenced_count=mh_summary.get("not_evidenced", 0),
        validation_checkpoints_count=len(latest_eval.validation_checkpoints or []) if latest_eval else 0,
        status=status,
        parse_failed=status == ScreeningStatus.PARSE_FAILED,
        spec_outdated=latest_eval.spec_outdated if latest_eval else False,
>>>>>>> smartleaven_work/main
        created_at=resume.created_at,
    )


def _build_evaluation_response(resume: CandidateResume) -> CandidateEvaluationResponse:
    latest_eval = _get_latest_eval(resume)
    status, reason = _status_and_review_reason(latest_eval)
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

    if not latest_eval or status != ScreeningStatus.COMPLETED:
        return CandidateEvaluationResponse(
            candidate_resume_id=resume.id,
            job_description_id=resume.job_description_id,
            spec_version_id=latest_eval.spec_version_id if latest_eval else None,
            specification_version=latest_eval.specification_version if latest_eval else 2,
            status=status,
            review_reason=reason,
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

    provenance = None
    if latest_eval.evaluator_engine:
        provenance = EvaluatorProvenance(
            evaluator_engine=latest_eval.evaluator_engine,
            model_name=latest_eval.model_name,
            model_version=latest_eval.model_version,
            prompt_version=latest_eval.prompt_version or "eval_v2.1",
            temperature=latest_eval.temperature or 0.0,
            seed=latest_eval.seed or 42,
        )

    return CandidateEvaluationResponse(
        candidate_resume_id=resume.id,
        job_description_id=resume.job_description_id,
        spec_version_id=latest_eval.spec_version_id,
        specification_version=latest_eval.specification_version,
<<<<<<< HEAD
        status=status,
        overall_score=latest_eval.overall_score,
=======
        spec_outdated=latest_eval.spec_outdated or False,
        status=ScreeningStatus(latest_eval.status.value),
        overall_score=latest_eval.recruiter_override_score or latest_eval.overall_score,
>>>>>>> smartleaven_work/main
        match_tier=latest_eval.match_tier,
        provenance=provenance,
        quote_verification_pass=latest_eval.quote_verification_pass,
        candidate_profile=candidate_profile,
        must_haves_summary=RequirementSummary(**mh) if mh else None,
        preferred_summary=RequirementSummary(**pf) if pf else None,
        score_breakdown=ScoreBreakdown(**sb) if sb else None,
        detailed_evaluations=_parse_req_evals(latest_eval.detailed_evaluations),
        validation_checkpoints=_parse_checkpoints(latest_eval.validation_checkpoints),
        timeline_observations=latest_eval.timeline_observations or [],
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
        filename = file.filename or "unknown"
        ext = Path(filename).suffix.lower()

        if ext not in SUPPORTED_EXTENSIONS:
            failed.append({
                "filename": filename,
                "error": f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
            })
            continue

        content = await file.read()

        if len(content) == 0:
            failed.append({"filename": filename, "error": "Empty file (0 bytes)."})
            continue

        if len(content) > MAX_FILE_SIZE_BYTES:
            failed.append({
                "filename": filename,
                "error": f"File too large ({len(content) // 1024}KB). Maximum: {MAX_FILE_SIZE_BYTES // 1024}KB.",
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

        # Duplicate detection: same hash + same JD = likely re-upload
        existing_hash = (
            db.query(CandidateResume)
            .filter(
                CandidateResume.job_description_id == jd_id,
                CandidateResume.file_hash == file_hash,
            )
            .first()
        )
        if existing_hash:
            failed.append({
                "filename": filename,
                "error": f"Duplicate file detected (SHA-256 matches existing resume '{existing_hash.filename}'). Delete it first or upload a different file.",
            })
            continue

        # Store file on disk
        resume_id = gen_uuid()
        safe_name = f"{resume_id}_{filename}"
        file_path  = RESUME_STORAGE_DIR / safe_name
        file_path.write_bytes(content)

        # Run parse quality gate immediately on upload for fast user feedback
        try:
            parsed_text = parse_document(filename, content)
            quality = check_parse_quality(parsed_text)
        except Exception as e:
            parsed_text = ""
            quality = {
                "passed": False,
                "text_length": 0,
                "word_count": 0,
                "alpha_ratio": 0.0,
                "failure_reason": f"Document parsing failed: {str(e)[:200]}",
            }

        # Create DB record
        resume = CandidateResume(
            id=resume_id,
            job_description_id=jd_id,
            filename=filename,
            file_size_bytes=len(content),
            file_key=str(file_path),
            file_hash=file_hash,
            parsed_text=parsed_text if quality["passed"] else None,
            parse_quality_check=quality,
        )
        db.add(resume)
        db.flush()

        status = ScreeningStatus.QUEUED if quality["passed"] else ScreeningStatus.PARSE_FAILED
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

    db.commit()

    return BatchResumeUploadResponse(
        uploaded=uploaded,
        failed=failed,
        total_queued=sum(1 for u in uploaded if u.status == ScreeningStatus.QUEUED),
    )


@router.post("/screen", response_model=ScreeningTriggerResponse, status_code=202)
def trigger_screening(
    jd_id: str,
    body: ScreeningTriggerRequest = ScreeningTriggerRequest(),
    db: Session = Depends(get_db),
):
    """
    Trigger grounded evaluation of uploaded resumes against the JD's Specification v2.
    - Skips resumes that failed the parse quality gate (PARSE_FAILED).
    - Enqueues CandidateEvaluation tasks into the background screening worker.
    - Returns immediately with a list of queued evaluation IDs.
    """
    _get_jd_or_404(jd_id, db)

    if body.candidate_resume_ids:
        resumes = (
            db.query(CandidateResume)
            .filter(
                CandidateResume.job_description_id == jd_id,
                CandidateResume.id.in_(body.candidate_resume_ids),
            )
            .all()
        )
    else:
        resumes = (
            db.query(CandidateResume)
            .filter(CandidateResume.job_description_id == jd_id)
            .all()
        )

    if not resumes:
        raise HTTPException(
            status_code=404,
            detail="No candidate resumes found for this JD. Upload resumes first.",
        )

    queued_ids: List[str] = []
    skipped_parse_failed: List[str] = []

    for resume in resumes:
        # Skip resumes that failed parse quality gate
        pq = resume.parse_quality_check or {}
        if pq and not pq.get("passed", True):
            skipped_parse_failed.append(resume.filename)
            continue

        existing = (
            db.query(CandidateEvaluation)
            .filter(
                CandidateEvaluation.candidate_resume_id == resume.id,
                CandidateEvaluation.job_description_id == jd_id,
            )
            .order_by(CandidateEvaluation.created_at.desc())
            .first()
        )
        if existing:
<<<<<<< HEAD
            # Keep an active run pinned to its current inputs.
            db.query(CandidateEvaluation).filter(
                CandidateEvaluation.id == existing.id,
                CandidateEvaluation.status.notin_((ScreeningStatusEnum.QUEUED, ScreeningStatusEnum.ANALYZING)),
            ).update({
                "status": ScreeningStatusEnum.QUEUED,
                "spec_version_id": body.spec_version_id,
                "error_message": None,
            }, synchronize_session=False)
=======
            existing.status = ScreeningStatusEnum.QUEUED
            existing.spec_version_id = body.spec_version_id
            existing.error_message = None
            existing.overall_score = None
            existing.match_tier = None
            existing.must_haves_summary = None
            existing.preferred_summary = None
            existing.detailed_evaluations = None
            existing.score_breakdown = None
            existing.timeline_observations = None
            existing.completed_at = None
>>>>>>> smartleaven_work/main
            queued_ids.append(existing.id)
            continue

        evaluation = CandidateEvaluation(
            candidate_resume_id=resume.id,
            job_description_id=jd_id,
            spec_version_id=body.spec_version_id,
            specification_version=2,
            status=ScreeningStatusEnum.QUEUED,
        )
        db.add(evaluation)
        db.flush()
        queued_ids.append(evaluation.id)

    # Commit BEFORE enqueueing so worker thread sees committed rows
    db.commit()

    for qid in queued_ids:
        screening_queue.enqueue(qid)

    skip_msg = f" ({len(skipped_parse_failed)} skipped: unreadable PDFs)" if skipped_parse_failed else ""
    return ScreeningTriggerResponse(
        queued_count=len(queued_ids),
        candidate_resume_ids=queued_ids,
        message=f"{len(queued_ids)} candidate evaluation(s) queued{skip_msg}. Poll GET /resumes for results.",
    )


@router.get("", response_model=ScreeningLeaderboardResponse)
def get_leaderboard(
    jd_id: str,
    db: Session = Depends(get_db),
):
    """
    Fetch the ranked candidate leaderboard for a Job Description.
    Sort order: effective_tier (STRONG first) → overall_score descending.
    PARSE_FAILED candidates appear at the bottom regardless of score.
    """
    _get_jd_or_404(jd_id, db)

    resumes = (
        db.query(CandidateResume)
        .filter(CandidateResume.job_description_id == jd_id)
        .order_by(CandidateResume.created_at.asc())
        .all()
    )

<<<<<<< HEAD
    items = [_build_leaderboard_item(resume) for resume in resumes]
    items.sort(key=lambda item: (item.overall_score is None, _tier_sort_key(item.match_tier), -(item.overall_score or 0)))
    for rank, item in enumerate(items, start=1):
        if item.overall_score is None:
            break
        item.rank = rank
=======
    # Deduplicate exact duplicate files by SHA-256 file_hash within the same JD.
    # Different candidates sharing a common filename (e.g. 'resume.pdf') have distinct file_hashes
    # and MUST NOT be collapsed.
    deduped: dict[str, CandidateResume] = {}
    for r in resumes:
        key = r.file_hash if r.file_hash else r.id
        if key not in deduped:
            deduped[key] = r
        else:
            prev = deduped[key]
            prev_score = (bool(prev.parsed_text), len(prev.evaluations), prev.created_at or datetime.min)
            curr_score = (bool(r.parsed_text), len(r.evaluations), r.created_at or datetime.min)
            if curr_score > prev_score:
                deduped[key] = r
    resumes = list(deduped.values())

    def sort_key(r: CandidateResume):
        latest_eval = _get_best_eval(r)
        # Push PARSE_FAILED to end
        if latest_eval and latest_eval.status == ScreeningStatusEnum.PARSE_FAILED:
            return (99, 0)
        eff_tier = _effective_tier(latest_eval)
        score = (latest_eval.recruiter_override_score or latest_eval.overall_score or -1) if latest_eval else -1
        return (_tier_sort_key(eff_tier), -(score or 0))

    sorted_resumes = sorted(resumes, key=sort_key)
    items = [_build_leaderboard_item(rank + 1, r) for rank, r in enumerate(sorted_resumes)]
>>>>>>> smartleaven_work/main

    return ScreeningLeaderboardResponse(
        job_description_id=jd_id,
        total_candidates=len(items),
        candidates=items,
    )


@router.get("/status")
def get_screening_status(
    jd_id: str,
    db: Session = Depends(get_db),
):
    """
    Lightweight polling endpoint: returns only resume IDs, filenames,
    scores, tiers, and statuses. Suitable for frequent frontend polling.
    """
    _get_jd_or_404(jd_id, db)
    resumes = (
        db.query(CandidateResume)
        .filter(CandidateResume.job_description_id == jd_id)
        .all()
    )
    # Deduplicate exact duplicate files by SHA-256 file_hash within the same JD
    deduped: dict[str, CandidateResume] = {}
    for r in resumes:
        key = r.file_hash if r.file_hash else r.id
        if key not in deduped:
            deduped[key] = r
        else:
            prev = deduped[key]
            prev_score = (bool(prev.parsed_text), len(prev.evaluations), prev.created_at or datetime.min)
            curr_score = (bool(r.parsed_text), len(r.evaluations), r.created_at or datetime.min)
            if curr_score > prev_score:
                deduped[key] = r
    resumes = list(deduped.values())
    items = []
    for r in resumes:
        e = _get_best_eval(r)
        items.append({
            "candidate_resume_id": r.id,
            "filename":            r.filename,
            "status":              e.status.value if e else "QUEUED",
            "overall_score":       e.recruiter_override_score or e.overall_score if e else None,
            "effective_tier":      (_effective_tier(e).value if _effective_tier(e) else None),
            "parse_failed":        (e.status == ScreeningStatusEnum.PARSE_FAILED) if e else False,
        })
    return {"job_description_id": jd_id, "candidates": items}


@router.get("/{resume_id}", response_model=CandidateEvaluationResponse)
def get_candidate_detail(
    jd_id: str,
    resume_id: str,
    db: Session = Depends(get_db),
):
    """
    Fetch the full deep-dive evaluation report for a specific candidate.
    Includes evaluator provenance, verbatim evidence quotes with verification status,
    validation checkpoints, timeline observations, and tailored interview questions.
    """
    resume = _get_resume_or_404(jd_id, resume_id, db)
    return _build_evaluation_response(resume)


@router.post("/{resume_id}/override", response_model=RecruiterOverrideResponse)
def override_candidate_tier(
    jd_id: str,
    resume_id: str,
    body: RecruiterOverrideRequest,
    db: Session = Depends(get_db),
):
    """
    Recruiter override: manually adjust a candidate's match tier and/or score.

    - Requires a mandatory justification reason (minimum 10 characters).
    - The original algorithmic evaluation is preserved; override is stored separately.
    - Builds an audit trail (overridden_by, overridden_at, override_reason).
    - The effective_tier in leaderboard and responses reflects the override.

    This endpoint enforces the principle: the tool provides advisory recommendations
    only. No candidate is ever auto-rejected; human judgment is always the final call.
    """
    resume = _get_resume_or_404(jd_id, resume_id, db)
    evaluation = _get_best_eval(resume)

    if not evaluation:
        raise HTTPException(
            status_code=404,
            detail="No evaluation found for this candidate. Run screening first.",
        )
    if evaluation.status not in (ScreeningStatusEnum.COMPLETED, ScreeningStatusEnum.FAILED):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot override evaluation in status '{evaluation.status.value}'. Wait for COMPLETED.",
        )

    evaluation.recruiter_override_tier  = body.override_tier
    evaluation.recruiter_override_score = body.override_score
    evaluation.override_reason          = body.reason
    evaluation.overridden_by            = body.overridden_by
    evaluation.overridden_at            = datetime.now(timezone.utc)
    db.commit()

    logger.info(
        "Recruiter override for resume %s: tier=%s reason='%s' by='%s'",
        resume_id, body.override_tier, body.reason[:80], body.overridden_by,
    )

    return RecruiterOverrideResponse(
        candidate_resume_id=resume_id,
        job_description_id=jd_id,
        recruiter_override_tier=body.override_tier,
        recruiter_override_score=body.override_score,
        override_reason=body.reason,
        overridden_by=body.overridden_by,
        overridden_at=evaluation.overridden_at,
        message=f"Override applied. Effective tier is now '{body.override_tier.value}'.",
    )


@router.post("/{resume_id}/re-screen", response_model=ScreeningTriggerResponse, status_code=202)
def re_screen_candidate(
    jd_id: str,
    resume_id: str,
    spec_version_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Re-trigger screening for a single candidate (e.g. after the JD spec was updated).
    Resets the existing evaluation to QUEUED and re-enqueues.
    """
    resume = _get_resume_or_404(jd_id, resume_id, db)

    pq = resume.parse_quality_check or {}
    if pq and not pq.get("passed", True):
        raise HTTPException(
            status_code=422,
            detail="Cannot re-screen a resume that failed the parse quality gate. Upload a text-based PDF or DOCX instead.",
        )

    evaluation = _get_best_eval(resume)
    if evaluation:
        evaluation.status           = ScreeningStatusEnum.QUEUED
        evaluation.spec_version_id  = spec_version_id
        evaluation.error_message    = None
        evaluation.spec_outdated    = False
    else:
        evaluation = CandidateEvaluation(
            candidate_resume_id=resume.id,
            job_description_id=jd_id,
            spec_version_id=spec_version_id,
            specification_version=2,
            status=ScreeningStatusEnum.QUEUED,
        )
        db.add(evaluation)
        db.flush()

    db.commit()
    screening_queue.enqueue(evaluation.id)

    return ScreeningTriggerResponse(
        queued_count=1,
        candidate_resume_ids=[evaluation.id],
        message=f"Candidate re-screening queued. Poll GET /resumes/{resume_id} for updated results.",
    )


@router.delete("/{resume_id}", status_code=204)
def delete_candidate(
    jd_id: str,
    resume_id: str,
    db: Session = Depends(get_db),
):
    """
    Delete a candidate resume and all their evaluations for this JD.
    Also removes the stored resume file from disk (GDPR-compatible hard delete).
    """
    resume = _get_resume_or_404(jd_id, resume_id, db)

    if resume.file_key:
        try:
            Path(resume.file_key).unlink(missing_ok=True)
        except Exception as e:
            logger.warning("Could not delete resume file %s: %s", resume.file_key, e)

    db.delete(resume)
    db.commit()
