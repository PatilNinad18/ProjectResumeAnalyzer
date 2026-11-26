"""Look up specification revisions and identify their exact evaluation inputs."""
import json

from sqlalchemy.orm import Session

from app.models.db_models import JobDescription, JobDescriptionVersion, JobSpecificationVersion
from app.services.storage import checksum


def specifications_for_jd(db: Session, jd_id: str):
    return (
        db.query(JobSpecificationVersion)
        .join(JobDescriptionVersion)
        .filter(JobDescriptionVersion.job_description_id == jd_id)
        .order_by(
            JobSpecificationVersion.specification_version.desc(),
            JobSpecificationVersion.created_at.desc(),
            JobSpecificationVersion.id.desc(),
        )
    )


def specification_checksum(spec: JobSpecificationVersion) -> str:
    return checksum(json.dumps(spec.canonical_json, sort_keys=True, separators=(",", ":")))


def lock_specification_revision(db: Session, jd_id: str) -> None:
    # Lock the JD for the transaction. The update also acquires the write lock on SQLite.
    db.query(JobDescription).filter_by(id=jd_id).update(
        {JobDescription.current_version: JobDescription.current_version}, synchronize_session=False,
    )
