"""Local resume files and deletion of candidate records for one JD."""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.db_models import AuditEvent
from app.models.screening_models import CandidateEvaluation, CandidateResume, ScreeningStatusEnum
from app.services.specification_versions import lock_specification_revision

RESUME_STORAGE_DIR = Path(os.getenv(
    "RESUME_STORAGE_DIR", str(Path(__file__).resolve().parents[3] / "data" / "resumes")
)).resolve()


class ResumeInUseError(Exception):
    pass


def resume_file_path(file_key: str) -> Path:
    path = Path(file_key)
    if not path.is_absolute():
        # Earlier local uploads stored paths relative to the API working directory.
        if ".." in path.parts or not path.name:
            raise ValueError("Invalid stored resume path.")
        path = RESUME_STORAGE_DIR / path.name
    resolved = path.resolve()
    if path.is_symlink() or not resolved.is_relative_to(RESUME_STORAGE_DIR) or resolved == RESUME_STORAGE_DIR:
        raise ValueError("The stored resume path is outside the configured storage directory.")
    return path


def remove_candidate_data(db: Session, jd_id: str, resume_id: str) -> None:
    """Remove the file, candidate, evaluations, and candidate-specific audit events."""
    lock_specification_revision(db, jd_id)
    resume = db.query(CandidateResume).filter_by(id=resume_id, job_description_id=jd_id).first()
    if not resume:
        raise LookupError("Resume not found for this JD.")
    if any(run.status in (ScreeningStatusEnum.QUEUED, ScreeningStatusEnum.ANALYZING) for run in resume.evaluations):
        raise ResumeInUseError("Screening is in progress. Retry deletion once it finishes.")

    path = resume_file_path(resume.file_key) if resume.file_key else None
    evaluation_ids = [run.id for run in resume.evaluations]
    if evaluation_ids:
        db.query(AuditEvent).filter(
            AuditEvent.entity_type == "candidate_evaluation", AuditEvent.entity_id.in_(evaluation_ids),
        ).delete(synchronize_session=False)
    db.delete(resume)
    db.flush()
    if path:
        # A failed unlink rolls back the database deletion. A missing file permits an idempotent retry.
        path.unlink(missing_ok=True)
    db.commit()
