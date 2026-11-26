"""Preview or apply a retention period for the candidates uploaded to one JD."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run(jd_id: str, older_than_days: int, apply: bool) -> dict:
    from sqlalchemy.exc import SQLAlchemyError

    from app.db import SessionLocal
    from app.models.db_models import JobDescription
    from app.models.screening_models import CandidateResume
    from app.services.resume.storage import ResumeInUseError, remove_candidate_data

    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    with SessionLocal() as db:
        if not db.get(JobDescription, jd_id):
            raise ValueError("No JD matches the supplied ID in this database.")
        ids = db.query(CandidateResume.id).filter(
            CandidateResume.job_description_id == jd_id, CandidateResume.created_at < cutoff,
        ).all()
    result = {"mode": "apply" if apply else "preview", "older_than_days": older_than_days,
              "matching": len(ids), "removed": 0, "in_use": 0, "failed": 0}
    if apply:
        with SessionLocal() as db:
            for (resume_id,) in ids:
                try:
                    remove_candidate_data(db, jd_id, resume_id)
                except ResumeInUseError:
                    db.rollback()
                    result["in_use"] += 1
                except LookupError:
                    db.rollback()
                except (OSError, ValueError, SQLAlchemyError):
                    db.rollback()
                    result["failed"] += 1
                else:
                    result["removed"] += 1
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jd-id", required=True)
    parser.add_argument("--older-than-days", type=int, required=True)
    parser.add_argument("--apply", action="store_true", help="Remove matched records. Omit to count them without deleting.")
    args = parser.parse_args()
    if args.older_than_days < 1:
        parser.error("The retention period in days must be positive.")
    try:
        result = run(args.jd_id, args.older_than_days, args.apply)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    if result["in_use"] or result["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
