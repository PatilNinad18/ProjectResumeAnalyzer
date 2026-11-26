"""
Screening Worker (Phase 4)
==========================
Asynchronous background worker that processes candidate resume evaluations.

Runs in a background thread (same in-process model as the existing JD worker).
Picks up CandidateEvaluation rows in QUEUED status and runs the full pipeline:
  QUEUED -> ANALYZING -> COMPLETED, NEEDS_REVIEW, PARSE_FAILED, or FAILED

Integrates:
  - document_parser.parse_document()     (already in document_parser.py)
  - resume.profiler.profile_resume()     (Phase 2)
  - resume.evaluator.evaluate_candidate() (Phase 3)
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.screening_models import (
    CandidateEvaluation,
    CandidateResume,
    ScreeningStatusEnum,
)
from app.services.document_parser import DocumentParseError, parse_document
from app.services.resume.profiler import profile_resume, resume_parse_issue
from app.services.resume.evaluator import evaluate_candidate

logger = logging.getLogger("jd_agent.screening_worker")
NO_CRITERIA_REVIEW = "The job specification has no usable screening criteria. Review the finalized JD and rerun screening."


# ---------------------------------------------------------------------------
# Single evaluation pipeline
# ---------------------------------------------------------------------------

def _load_spec_canonical_json(db: Session, evaluation: CandidateEvaluation) -> Optional[dict]:
    """
    Load the canonical_json from the JobSpecificationVersion linked to this evaluation.
    Prefers the specific spec_version_id if set; otherwise falls back to the latest
    finalized version for the JD.
    """
    from app.models.db_models import JobSpecificationVersion, JobDescriptionVersion, JDLifecycleStatusEnum

    if evaluation.spec_version_id:
        spec = db.get(JobSpecificationVersion, evaluation.spec_version_id)
        if spec:
            return spec.canonical_json

    # Fallback: latest finalized spec for the JD
    jd_id = evaluation.job_description_id
    spec = (
        db.query(JobSpecificationVersion)
        .join(JobDescriptionVersion, JobSpecificationVersion.job_description_version_id == JobDescriptionVersion.id)
        .filter(JobDescriptionVersion.job_description_id == jd_id)
        .filter(JobSpecificationVersion.lifecycle_status == JDLifecycleStatusEnum.FINALIZED)
        .order_by(JobSpecificationVersion.specification_version.desc())
        .first()
    )
    if spec:
        return spec.canonical_json

    # Last resort: any spec for this JD
    spec = (
        db.query(JobSpecificationVersion)
        .join(JobDescriptionVersion, JobSpecificationVersion.job_description_version_id == JobDescriptionVersion.id)
        .filter(JobDescriptionVersion.job_description_id == jd_id)
        .order_by(JobSpecificationVersion.specification_version.desc())
        .first()
    )
    return spec.canonical_json if spec else None


def _finish_without_score(db: Session, evaluation: CandidateEvaluation, status: ScreeningStatusEnum, reason: str) -> None:
    evaluation.status = status
    evaluation.error_message = reason
    evaluation.completed_at = datetime.now(timezone.utc)
    db.commit()


def process_candidate_evaluation(db: Session, evaluation_id: str) -> None:
    """
    Full pipeline for a single candidate evaluation:
      1. Load CandidateResume and CandidateEvaluation from DB.
      2. Parse resume file (if not already parsed) using document_parser.
      3. Run profiler to extract structured candidate profile.
      4. Load Spec v2 canonical_json.
      5. Run grounded evaluator.
      6. Persist results back to DB.
    """
    claimed = db.query(CandidateEvaluation).filter(
        CandidateEvaluation.id == evaluation_id,
        CandidateEvaluation.status == ScreeningStatusEnum.QUEUED,
    ).update({
        "status": ScreeningStatusEnum.ANALYZING,
        "started_at": datetime.now(timezone.utc),
        "completed_at": None,
        "error_message": None,
        "overall_score": None,
        "match_tier": None,
        "must_haves_summary": None,
        "preferred_summary": None,
        "detailed_evaluations": None,
        "validation_checkpoints": None,
        "red_flags": None,
        "tailored_interview_questions": None,
        "score_breakdown": None,
    }, synchronize_session=False)
    db.commit()
    if not claimed:
        return
    evaluation = db.get(CandidateEvaluation, evaluation_id)
    if evaluation is None:
        return

    try:
        resume: Optional[CandidateResume] = db.get(CandidateResume, evaluation.candidate_resume_id)
        if not resume:
            raise ValueError(f"CandidateResume {evaluation.candidate_resume_id} not found")

        # --- Step 1: Parse resume text if not yet done ---
        if not resume.parsed_text:
            if not resume.file_key:
                raise ValueError("No file_key set on CandidateResume — cannot parse document")
            file_path = Path(resume.file_key)
            if not file_path.exists():
                raise FileNotFoundError(f"Resume file not found at: {file_path}")
            raw_bytes = file_path.read_bytes()
            resume.parsed_text = parse_document(resume.filename, raw_bytes)
            db.flush()

        if issue := resume_parse_issue(resume.parsed_text):
            _finish_without_score(db, evaluation, ScreeningStatusEnum.NEEDS_REVIEW, issue)
            return

        # --- Step 2: Profile candidate ---
        parsed_profile = profile_resume(resume.parsed_text)

        # Persist profile back to resume row
        resume.parsed_profile_json      = parsed_profile
        resume.candidate_name           = resume.candidate_name or parsed_profile.get("candidate_name")
        resume.email                    = resume.email or parsed_profile.get("email")
        resume.phone                    = resume.phone or parsed_profile.get("phone")
        resume.total_experience_years   = parsed_profile.get("total_experience_years") or 0.0
        db.flush()

        # --- Step 3: Load Spec v2 canonical_json ---
        spec_json = _load_spec_canonical_json(db, evaluation)
        if not spec_json:
            raise ValueError(
                f"No JobSpecificationVersion found for JD {evaluation.job_description_id}. "
                "Analyze and finalize the JD before screening candidates."
            )

        # --- Step 4: Grounded evaluation ---
        result = evaluate_candidate(resume.parsed_text, parsed_profile, spec_json)
        if result["overall_score"] is None:
            _finish_without_score(db, evaluation, ScreeningStatusEnum.NEEDS_REVIEW, NO_CRITERIA_REVIEW)
            return

        # --- Step 5: Persist results ---
        evaluation.overall_score               = result["overall_score"]
        evaluation.match_tier                  = result["match_tier"]
        evaluation.must_haves_summary          = result["must_haves_summary"]
        evaluation.preferred_summary           = result["preferred_summary"]
        evaluation.detailed_evaluations        = result["detailed_evaluations"]
        evaluation.validation_checkpoints      = result["validation_checkpoints"]
        evaluation.red_flags                   = result["red_flags"]
        evaluation.tailored_interview_questions = result["tailored_interview_questions"]
        evaluation.score_breakdown             = result["score_breakdown"]
        evaluation.status                      = ScreeningStatusEnum.COMPLETED
        evaluation.completed_at               = datetime.now(timezone.utc)

        db.commit()
        logger.info(
            "Evaluation %s completed: score=%s tier=%s",
            evaluation_id, result["overall_score"], result["match_tier"],
        )

    except DocumentParseError:
        db.rollback()
        _finish_without_score(
            db, evaluation, ScreeningStatusEnum.PARSE_FAILED,
            "No readable resume text could be extracted. Upload a text-searchable PDF, DOCX, or TXT file.",
        )
    except Exception as exc:
        logger.exception("Evaluation %s failed: %s", evaluation_id, exc)
        db.rollback()
        try:
            _finish_without_score(db, evaluation, ScreeningStatusEnum.FAILED, str(exc)[:1000])
        except Exception:
            db.rollback()


# ---------------------------------------------------------------------------
# Background screening queue
# ---------------------------------------------------------------------------

class ScreeningQueue:
    """
    Simple in-process FIFO queue for candidate evaluation tasks.
    Uses a daemon thread (same pattern as JD batch_queue) so it shuts down
    cleanly with the FastAPI process.
    """

    def __init__(self):
        self._queue: list[str] = []
        self._lock  = threading.Lock()
        self._event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def enqueue(self, evaluation_id: str) -> None:
        with self._lock:
            if evaluation_id not in self._queue:
                self._queue.append(evaluation_id)
        self._event.set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="screening-worker")
        self._thread.start()
        logger.info("Screening worker thread started")

    def _run(self) -> None:
        while True:
            self._event.wait(timeout=2)
            self._event.clear()

            # Active database recovery: check for any evaluations stuck in QUEUED
            try:
                db_recover: Session = SessionLocal()
                pending = (
                    db_recover.query(CandidateEvaluation)
                    .filter(CandidateEvaluation.status == ScreeningStatusEnum.QUEUED)
                    .all()
                )
                with self._lock:
                    for p in pending:
                        if p.id not in self._queue:
                            self._queue.append(p.id)
                db_recover.close()
            except Exception as e:
                logger.warning("Error recovering queued evaluations: %s", e)

            while True:
                with self._lock:
                    if not self._queue:
                        break
                    evaluation_id = self._queue.pop(0)

                db: Session = SessionLocal()
                try:
                    process_candidate_evaluation(db, evaluation_id)
                finally:
                    db.close()


# Singleton queue — imported by main.py and screening_routes.py
screening_queue = ScreeningQueue()
