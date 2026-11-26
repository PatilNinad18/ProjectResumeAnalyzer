"""
Resume Screening REST API (Phase 4)
====================================
Endpoints for uploading candidate resumes, triggering evaluation, and
fetching ranked results for a Job Description.

All endpoints are nested under /api/jds/{jd_id}/resumes to keep them
scoped to a specific JD (and its Specification v2).

Endpoints:
  POST   /api/jds/{jd_id}/resumes             Upload 1-N resume files
  POST   /api/jds/{jd_id}/resumes/screen      Trigger evaluation (batch or specific)
  GET    /api/jds/{jd_id}/resumes             Leaderboard (ranked list)
  GET    /api/jds/{jd_id}/resumes/{resume_id} Full evaluation deep-dive
  DELETE /api/jds/{jd_id}/resumes/{resume_id} Delete a candidate and their evaluation
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, BackgroundTasks
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
from app.services.document_parser import DocumentParseError, SUPPORTED_EXTENSIONS
from app.services.resume.evaluator import NO_EVALUATION_CRITERIA
from app.workers.screening_worker import NO_CRITERIA_REVIEW, screening_queue

logger = logging.getLogger("jd_agent.screening_routes")

router = APIRouter(prefix="/api/jds/{jd_id}/resumes", tags=["screening"])

# --- Local resume storage directory ---
RESUME_STORAGE_DIR = Path(os.getenv("RESUME_STORAGE_DIR", "data/resumes"))
RESUME_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


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


def _tier_sort_key(tier: Optional[str]) -> int:
    order = {"STRONG_MATCH": 0, "POTENTIAL_MATCH": 1, "NOT_A_FIT": 2}
    return order.get(tier or "", 3)


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
    return ScreeningLeaderboardItem(
        rank=None,
        candidate_resume_id=resume.id,
        filename=resume.filename,
        candidate_name=resume.candidate_name,
        email=resume.email,
        total_experience_years=resume.total_experience_years,
        overall_score=scored.overall_score if scored else None,
        match_tier=scored.match_tier if scored else None,
        must_haves_met=mh_summary.get("met", 0),
        must_haves_partially_met=mh_summary.get("partially_met", 0),
        must_haves_total=mh_summary.get("total", 0),
        not_evidenced_count=mh_summary.get("not_evidenced", 0),
        validation_checkpoints_count=len(scored.validation_checkpoints or []) if scored else 0,
        status=status,
        review_reason=reason,
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

    return CandidateEvaluationResponse(
        candidate_resume_id=resume.id,
        job_description_id=resume.job_description_id,
        spec_version_id=latest_eval.spec_version_id,
        specification_version=latest_eval.specification_version,
        status=status,
        overall_score=latest_eval.overall_score,
        match_tier=latest_eval.match_tier,
        candidate_profile=candidate_profile,
        must_haves_summary=RequirementSummary(**mh) if mh else None,
        preferred_summary=RequirementSummary(**pf) if pf else None,
        score_breakdown=ScoreBreakdown(**{k: v for k, v in sb.items() if k != "warning"}) if sb else None,
        detailed_evaluations=_parse_req_evals(latest_eval.detailed_evaluations),
        validation_checkpoints=_parse_checkpoints(latest_eval.validation_checkpoints),
        red_flags=latest_eval.red_flags or [],
        tailored_interview_questions=latest_eval.tailored_interview_questions or [],
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
    Files are stored locally and CandidateResume rows are created immediately.
    Evaluation is NOT triggered automatically — call /screen separately.
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

        # Store file on disk
        resume_id = gen_uuid()
        safe_name = f"{resume_id}_{filename}"
        file_path  = RESUME_STORAGE_DIR / safe_name
        file_path.write_bytes(content)

        # Create DB record
        resume = CandidateResume(
            id=resume_id,
            job_description_id=jd_id,
            filename=filename,
            file_size_bytes=len(content),
            file_key=str(file_path),
        )
        db.add(resume)
        db.flush()

        uploaded.append(ResumeUploadResponse(
            candidate_resume_id=resume_id,
            filename=filename,
            file_size_bytes=len(content),
            status=ScreeningStatus.QUEUED,
            message="Uploaded successfully. Call /screen to start evaluation.",
        ))

    db.commit()

    return BatchResumeUploadResponse(
        uploaded=uploaded,
        failed=failed,
        total_queued=len(uploaded),
    )


@router.post("/screen", response_model=ScreeningTriggerResponse, status_code=202)
def trigger_screening(
    jd_id: str,
    body: ScreeningTriggerRequest = ScreeningTriggerRequest(),
    db: Session = Depends(get_db),
):
    """
    Trigger grounded evaluation of uploaded resumes against the JD's Specification v2.
    Enqueues CandidateEvaluation tasks into the background screening worker.
    Returns immediately with a list of queued evaluation IDs.
    """
    _get_jd_or_404(jd_id, db)

    # Determine which resumes to screen
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

    for resume in resumes:
        # Check if an evaluation already exists for this resume and JD
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
            # Keep an active run pinned to its current inputs.
            db.query(CandidateEvaluation).filter(
                CandidateEvaluation.id == existing.id,
                CandidateEvaluation.status.notin_((ScreeningStatusEnum.QUEUED, ScreeningStatusEnum.ANALYZING)),
            ).update({
                "status": ScreeningStatusEnum.QUEUED,
                "spec_version_id": body.spec_version_id,
                "error_message": None,
            }, synchronize_session=False)
            queued_ids.append(existing.id)
            continue

        # Create new evaluation row
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

    # Commit to database FIRST before worker attempts to read
    db.commit()

    # Enqueue to screening queue
    for qid in queued_ids:
        screening_queue.enqueue(qid)

    return ScreeningTriggerResponse(
        queued_count=len(queued_ids),
        candidate_resume_ids=queued_ids,
        message=f"{len(queued_ids)} candidate evaluation(s) queued. Poll GET /resumes for results.",
    )


@router.get("", response_model=ScreeningLeaderboardResponse)
def get_leaderboard(
    jd_id: str,
    db: Session = Depends(get_db),
):
    """
    Fetch the ranked candidate leaderboard for a Job Description.
    Candidates are sorted by: match_tier (STRONG first) then overall_score descending.
    """
    _get_jd_or_404(jd_id, db)

    resumes = (
        db.query(CandidateResume)
        .filter(CandidateResume.job_description_id == jd_id)
        .order_by(CandidateResume.created_at.asc())
        .all()
    )

    items = [_build_leaderboard_item(resume) for resume in resumes]
    items.sort(key=lambda item: (item.overall_score is None, _tier_sort_key(item.match_tier), -(item.overall_score or 0)))
    for rank, item in enumerate(items, start=1):
        if item.overall_score is None:
            break
        item.rank = rank

    return ScreeningLeaderboardResponse(
        job_description_id=jd_id,
        total_candidates=len(items),
        candidates=items,
    )


@router.get("/{resume_id}", response_model=CandidateEvaluationResponse)
def get_candidate_detail(
    jd_id: str,
    resume_id: str,
    db: Session = Depends(get_db),
):
    """
    Fetch the full deep-dive evaluation report for a specific candidate.
    Includes verbatim evidence quotes, validation checkpoints, red flags,
    and tailored interview questions.
    """
    resume = _get_resume_or_404(jd_id, resume_id, db)
    return _build_evaluation_response(resume)


@router.delete("/{resume_id}", status_code=204)
def delete_candidate(
    jd_id: str,
    resume_id: str,
    db: Session = Depends(get_db),
):
    """
    Delete a candidate resume and all their evaluations for this JD.
    Also removes the stored resume file from disk.
    """
    resume = _get_resume_or_404(jd_id, resume_id, db)

    # Delete file from disk
    if resume.file_key:
        try:
            Path(resume.file_key).unlink(missing_ok=True)
        except Exception as e:
            logger.warning("Could not delete resume file %s: %s", resume.file_key, e)

    db.delete(resume)
    db.commit()
