"""
Screening Worker (v2.1)
========================
Asynchronous background worker that processes candidate resume evaluations.

Runs in a background thread (same in-process model as the existing JD worker).
Picks up CandidateEvaluation rows in QUEUED status and runs the full pipeline:
  QUEUED -> ANALYZING -> COMPLETED, NEEDS_REVIEW, PARSE_FAILED, or FAILED

Runs in a background thread (same in-process model as the existing JD worker).
State machine:
  QUEUED -> ANALYZING -> COMPLETED
  QUEUED -> ANALYZING -> PARSE_FAILED  (unreadable resume)
  QUEUED -> ANALYZING -> FAILED        (unexpected error)
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.db_models import JobSpecificationVersion
from app.models.screening_models import (
    CandidateEvaluation,
    CandidateResume,
    ScreeningStatusEnum,
)
from app.services.document_parser import DocumentParseError, parse_document
from app.services.resume.profiler import profile_resume, resume_parse_issue
from app.services.resume.evaluator import EVALUATOR_ENGINE, PROMPT_VERSION, evaluate_candidate
from app.services.resume.storage import resume_file_path
from app.services.specification_versions import specification_checksum

logger = logging.getLogger("jd_agent.screening_worker")
NO_CRITERIA_REVIEW = "The job specification has no usable screening criteria. Review the finalized JD and rerun screening."


# ---------------------------------------------------------------------------
# Single evaluation pipeline
# ---------------------------------------------------------------------------

def _finish_without_score(db: Session, evaluation: CandidateEvaluation, status: ScreeningStatusEnum, reason: str) -> None:
    evaluation.status = status
    evaluation.error_message = reason
    evaluation.completed_at = datetime.now(timezone.utc)
    evaluation.active_run_key = None
    db.commit()


def process_candidate_evaluation(db: Session, evaluation_id: str) -> None:
    """
    Full pipeline for a single candidate evaluation:
      1. Load CandidateResume and CandidateEvaluation from DB.
      2. Parse resume file (if not already parsed) using document_parser.
      3. Run parse quality gate — set PARSE_FAILED if text is unreadable.
      4. Run profiler to extract structured candidate profile.
      5. Load Spec v2 canonical_json.
      6. Run grounded evaluator (quote verification, injection scan, scoring).
      7. Persist results (provenance, timeline_observations, quote_verification_pass).
    """
    claimed = db.query(CandidateEvaluation).filter(
        CandidateEvaluation.id == evaluation_id,
        CandidateEvaluation.status == ScreeningStatusEnum.QUEUED,
    ).update({
        "status": ScreeningStatusEnum.ANALYZING,
        "started_at": datetime.now(timezone.utc),
    }, synchronize_session=False)
    db.commit()
    if not claimed:
        return
    evaluation = db.get(CandidateEvaluation, evaluation_id)
    if evaluation is None:
        return

    try:
        spec = db.get(JobSpecificationVersion, evaluation.spec_version_id) if evaluation.spec_version_id else None
        if (
            not spec or spec.jd_version.job_description_id != evaluation.job_description_id
            or specification_checksum(spec) != evaluation.spec_checksum
            or evaluation.evaluator_engine != EVALUATOR_ENGINE
            or evaluation.prompt_version != PROMPT_VERSION
        ):
            _finish_without_score(
                db, evaluation, ScreeningStatusEnum.NEEDS_REVIEW,
                "The pinned specification or evaluator is unavailable. Rerun screening for a current result.",
            )
            return
        spec_json = spec.canonical_json

        resume: Optional[CandidateResume] = db.get(CandidateResume, evaluation.candidate_resume_id)
        if not resume:
            raise ValueError(f"CandidateResume {evaluation.candidate_resume_id} not found")

        # --- Step 1: Parse resume text ---
        if not resume.parsed_text:
            if not resume.file_key:
                raise ValueError("No file_key set on CandidateResume — cannot parse document")
            file_path = resume_file_path(resume.file_key)
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

        # --- Step 5: Grounded evaluation ---
        result = evaluate_candidate(resume.parsed_text, parsed_profile, spec_json)
        if result["overall_score"] is None:
            _finish_without_score(db, evaluation, ScreeningStatusEnum.NEEDS_REVIEW, NO_CRITERIA_REVIEW)
            return

        # --- Step 6: Persist results ---
        evaluation.overall_score            = result["overall_score"]
        evaluation.match_tier               = result["match_tier"]
        evaluation.must_haves_summary       = result["must_haves_summary"]
        evaluation.preferred_summary        = result["preferred_summary"]
        evaluation.detailed_evaluations     = result["detailed_evaluations"]
        evaluation.validation_checkpoints   = result["validation_checkpoints"]
        evaluation.timeline_observations    = result["timeline_observations"]   # renamed from red_flags
        evaluation.tailored_interview_questions = result["tailored_interview_questions"]
        evaluation.score_breakdown          = result["score_breakdown"]
        evaluation.quote_verification_pass  = result.get("quote_verification_pass", True)
        evaluation.status                   = ScreeningStatusEnum.COMPLETED
        evaluation.completed_at             = datetime.now(timezone.utc)
        evaluation.active_run_key           = None

        db.commit()
        logger.info(
            "Evaluation %s COMPLETED: score=%s tier=%s quotes_verified=%s",
            evaluation_id, result["overall_score"], result["match_tier"],
            result.get("quote_verification_pass"),
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

    One screening thread processes evaluation runs per process. SQLite
    serializes database writes from the worker and API requests.
    """

    def __init__(self):
        self._queue: list[str] = []
        self._lock  = threading.Lock()
        self._event = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def enqueue(self, evaluation_id: str) -> None:
        self.start()
        with self._lock:
            if evaluation_id not in self._queue:
                self._queue.append(evaluation_id)
        self._event.set()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name="screening-worker")
            self._thread.start()
        logger.info("Screening worker thread started")

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._stop.set()
            self._event.set()
        if thread:
            thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._event.wait(timeout=2)
                self._event.clear()
                if self._stop.is_set():
                    break

                # Active database recovery: pick up any QUEUED evaluations missed in-memory
                try:
                    with SessionLocal() as db_recover:
                        pending = db_recover.query(CandidateEvaluation.id).filter_by(status=ScreeningStatusEnum.QUEUED).all()
                    with self._lock:
                        for (evaluation_id,) in pending:
                            if evaluation_id not in self._queue:
                                self._queue.append(evaluation_id)
                except Exception as e:
                    logger.warning("Error recovering queued evaluations: %s", e)

                while not self._stop.is_set():
                    with self._lock:
                        if not self._queue:
                            break
                        evaluation_id = self._queue.pop(0)

                    db: Session = SessionLocal()
                    try:
                        process_candidate_evaluation(db, evaluation_id)
                    except Exception as err:
                        logger.exception("Screening worker uncaught error on eval %s: %s", evaluation_id, err)
                    finally:
                        try:
                            db.close()
                        except Exception:
                            pass
            except Exception as loop_err:
                logger.exception("ScreeningQueue worker loop exception: %s", loop_err)
                time.sleep(1)


# Singleton queue — imported by main.py and screening_routes.py
screening_queue = ScreeningQueue()
