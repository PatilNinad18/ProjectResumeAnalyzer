"""
Background worker for asynchronous JD processing.

Preferred backend: AWS SQS. A Redis+RQ/Celery equivalent would implement the
same `process_job_description_version` function as its task body -- only the
queue plumbing (this file's `poll_loop`) differs, so business logic never
needs to change if the queue backend changes.

Flow per message:
  UPLOADED -> PARSING -> UNDERSTANDING -> VALIDATING -> GENERATING -> READY
                                                             |
                                                             +-> NEEDS_REVIEW (validation warnings)
                                                             +-> FAILED (unrecoverable error, after retries)
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models.db_models import (
    JobDescriptionVersion,
    JobSpecificationVersion,
    ProcessingJob,
    ProcessingStatusEnum,
)
from app.services.agent import JDUnderstandingAgent, JDUnderstandingError
from app.services.json_serializer import to_json_dict, to_json_str
from app.services.markdown_renderer import render_markdown
from app.services.storage import build_key, get_storage
from app.services.validation import validate_payload

logger = logging.getLogger("jd_agent.worker")
settings = get_settings()


def process_job_description_version(db: Session, jd_version_id: str) -> None:
    """The full PARSING -> READY/NEEDS_REVIEW/FAILED pipeline for one JD version."""
    jd_version = db.query(JobDescriptionVersion).get(jd_version_id)
    if jd_version is None:
        logger.error("JobDescriptionVersion %s not found", jd_version_id)
        return

    job = ProcessingJob(job_description_version_id=jd_version_id, status=ProcessingStatusEnum.PARSING)
    db.add(job)
    db.commit()

    storage = get_storage()

    try:
        job.status = ProcessingStatusEnum.PARSING
        job.started_at = datetime.now(timezone.utc)
        db.commit()
        raw_text = storage.get_text(jd_version.s3_raw_key)

        job.status = ProcessingStatusEnum.UNDERSTANDING
        db.commit()
        agent = JDUnderstandingAgent()
        spec, llm_result = agent.understand(
            jd_text=raw_text,
            jd_id=str(jd_version.job_description_id),
            jd_version=jd_version.version,
            specification_version=1,
        )

        job.status = ProcessingStatusEnum.VALIDATING
        db.commit()
        _, report = validate_payload(to_json_dict(spec))
        needs_review = not report.valid or any(i.severity == "warning" for i in report.issues)

        job.status = ProcessingStatusEnum.GENERATING
        db.commit()
        markdown = render_markdown(spec)
        json_str = to_json_str(spec)

        project_id = "unknown"  # would be resolved via jd_version.job_description.project_id in a full impl
        json_key = build_key(project_id, str(jd_version.job_description_id), jd_version.version, "json")
        md_key = build_key(project_id, str(jd_version.job_description_id), jd_version.version, "markdown")
        storage.put_text(json_key, json_str, "application/json")
        storage.put_text(md_key, markdown, "text/markdown")

        spec_version = JobSpecificationVersion(
            job_description_version_id=jd_version_id,
            specification_version=1,
            s3_json_key=json_key,
            s3_markdown_key=md_key,
            canonical_json=json.loads(json_str),
            prompt_version=spec.metadata.prompt_version or "",
            model_version=spec.metadata.model_version or "",
            input_tokens=llm_result.usage.input_tokens,
            output_tokens=llm_result.usage.output_tokens,
            latency_ms=int(llm_result.usage.latency_ms),
            estimated_cost_usd=int(llm_result.usage.estimated_cost_usd * 1_000_000),
            is_valid=report.valid,
            needs_review=needs_review,
        )
        db.add(spec_version)

        job.status = ProcessingStatusEnum.NEEDS_REVIEW if needs_review else ProcessingStatusEnum.READY
        job.finished_at = datetime.now(timezone.utc)
        db.commit()

    except JDUnderstandingError as exc:
        logger.exception("JD understanding failed for %s", jd_version_id)
        job.status = ProcessingStatusEnum.FAILED
        job.error_message = str(exc)
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected worker failure for %s", jd_version_id)
        job.status = ProcessingStatusEnum.FAILED
        job.error_message = f"Unexpected error: {exc}"
        job.finished_at = datetime.now(timezone.utc)
        db.commit()


def poll_loop_sqs() -> None:  # pragma: no cover - infra glue, not unit tested
    import boto3

    sqs = boto3.client("sqs", region_name=settings.aws_region)
    logger.info("Worker polling SQS queue: %s", settings.sqs_queue_url)
    while True:
        resp = sqs.receive_message(
            QueueUrl=settings.sqs_queue_url, MaxNumberOfMessages=5, WaitTimeSeconds=10
        )
        for message in resp.get("Messages", []):
            body = json.loads(message["Body"])
            jd_version_id = body["jd_version_id"]
            db = SessionLocal()
            try:
                process_job_description_version(db, jd_version_id)
            finally:
                db.close()
            sqs.delete_message(QueueUrl=settings.sqs_queue_url, ReceiptHandle=message["ReceiptHandle"])
        time.sleep(1)


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    if settings.queue_backend == "sqs":
        poll_loop_sqs()
    else:
        logger.info(
            "QUEUE_BACKEND=%s -- no standalone worker needed for local dev. "
            "The API (app.main) already processes each JD synchronously when "
            "you call POST /api/jds/{id}/analyze, so you can just run "
            "`uvicorn app.main:app --reload` and skip this script. "
            "Set QUEUE_BACKEND=sqs (and SQS_QUEUE_URL) if you want this "
            "worker to poll a real SQS queue instead.",
            settings.queue_backend,
        )
