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
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models.db_models import (
    JDLifecycleStatusEnum,
    JobDescriptionVersion,
    JobSpecificationVersion,
    ProcessingJob,
    ProcessingStatusEnum,
)
from app.services.agent import JDUnderstandingAgent, JDUnderstandingError
from app.services.extraction_pipeline import ExtractionPipeline
from app.services.json_serializer import to_json_dict, to_json_str
from app.services.markdown_renderer import render_markdown
from app.services.projection.canonical_projector import project_to_canonical
from app.services.storage import build_key, get_storage
from app.services.validation import validate_payload

logger = logging.getLogger("jd_agent.worker")
settings = get_settings()


class JobProcessingCancelled(Exception):
    """Raised at a safe pipeline boundary after a batch task is cancelled."""


def process_job_description_version(
    db: Session,
    jd_version_id: str,
    on_stage: Optional[Callable[[str, str, int], None]] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
) -> None:
    """The full PARSING -> READY/NEEDS_REVIEW/FAILED pipeline for one JD version."""
    jd_version = db.get(JobDescriptionVersion, jd_version_id)
    if jd_version is None:
        logger.error("JobDescriptionVersion %s not found", jd_version_id)
        return

    job = ProcessingJob(job_description_version_id=jd_version_id, status=ProcessingStatusEnum.PARSING)
    db.add(job)
    db.commit()

    storage = get_storage()

    def stage(name: str, label: str, percent: int) -> None:
        if on_stage is not None:
            on_stage(name, label, percent)
        if is_cancelled is not None and is_cancelled():
            raise JobProcessingCancelled("Processing cancelled by user.")

    try:
        stage("PARSING", "Reading uploaded job description", 15)
        job.status = ProcessingStatusEnum.PARSING
        job.started_at = datetime.now(timezone.utc)
        db.commit()
        raw_text = storage.get_text(jd_version.s3_raw_key)

        stage("UNDERSTANDING", "Extracting requirements and matching EKG concepts", 35)
        job.status = ProcessingStatusEnum.UNDERSTANDING
        db.commit()

        # Unconditionally deterministic baseline analysis
        start_proc = time.perf_counter()
        pipeline = ExtractionPipeline(llm_enabled=False)
        extraction_result = pipeline.process_jd(raw_text)
        master_context = extraction_result.to_master_context(
            jd_id=str(jd_version.job_description_id),
            raw_jd_text=raw_text,
        )
        spec = project_to_canonical(
            master_context,
            jd_id=str(jd_version.job_description_id),
            specification_version=1,
        )
        latency_ms = int((time.perf_counter() - start_proc) * 1000)
        spec.metadata.prompt_version = "deterministic_v1"
        spec.metadata.model_version = "deterministic_ekg"

        # Generate clarification questions on master context
        from app.services.clarification.engine import generate_clarification_questions
        job_context = master_context.job_context
        team_size_unspecified = job_context.team_size_explicitly_unspecified
        salary_unspecified = job_context.salary_explicitly_unspecified
        try:
            # Optional metadata and generic disclaimers are not clarification tasks.
            job_context.team_size_explicitly_unspecified = True
            job_context.salary_explicitly_unspecified = True
            master_context = generate_clarification_questions(master_context, actor="worker_baseline")
        finally:
            job_context.team_size_explicitly_unspecified = team_size_unspecified
            job_context.salary_explicitly_unspecified = salary_unspecified

        if not master_context.clarification_history:
            from app.services.clarification.updater import attempt_finalization

            master_context = attempt_finalization(master_context, actor="worker_baseline")

        stage("VALIDATING", "Validating the canonical specification", 70)
        job.status = ProcessingStatusEnum.VALIDATING
        db.commit()
        _, report = validate_payload(to_json_dict(spec))
        needs_review = not report.valid or any(i.severity == "warning" for i in report.issues)

        job.status = ProcessingStatusEnum.GENERATING
        db.commit()
        stage("GENERATING", "Generating Markdown and JSON artifacts", 85)

        # Attempt automatic Ollama enrichment; fall back cleanly to deterministic baseline on any failure
        from app.services.enrichment.ta_enrichment_service import get_enrichment_service
        enricher = get_enrichment_service()
        enrichment_report = None
        enriched_md = None
        enriched_key = None

        if enricher.check_ollama_available():
            try:
                from app.schemas.master_context import ClauseType
                from app.services.projection.canonical_projector import _flatten_requirements
                resp_descs = {
                    (r.raw_statement if hasattr(r, "raw_statement") else str(r)).strip().lower()
                    for r in master_context.responsibilities
                    if getattr(r, "raw_statement", None)
                }
                flat_reqs = _flatten_requirements(master_context.requirements)
                requirements_to_enrich = [
                    {
                        "requirement_id": r.id,
                        "text": r.text,
                        "priority": r.priority.value if hasattr(r.priority, "value") else str(r.priority or "MUST_HAVE"),
                    }
                    for r in flat_reqs
                    if getattr(r, "text", None)
                    and getattr(r, "clause_type", None) != ClauseType.RESPONSIBILITY
                    and (not r.source or getattr(r.source, "section", "") not in (
                        "responsibilities", "duties", "deliverables", "key_responsibilities", "expected_deliverables"
                    ))
                    and r.text.strip().lower() not in resp_descs
                ]
                if not requirements_to_enrich and spec.evidence_requirements:
                    requirements_to_enrich = [
                        {
                            "requirement_id": ev.requirement_id,
                            "text": ev.requirement,
                            "priority": ev.priority if isinstance(ev.priority, str) else ev.priority.value,
                        }
                        for ev in spec.evidence_requirements
                        if ev.requirement
                    ]

                role_context = {
                    "role_title": getattr(master_context.role_overview, "job_title", None) or getattr(master_context.role_overview, "title", None) or (spec.role.job_title if hasattr(spec, "role") and spec.role else ""),
                    "team_size": master_context.job_context.team_size,
                    "salary_range": getattr(master_context.job_context, "salary_range", None),
                    "work_mode": getattr(master_context.role_overview, "work_mode", "UNSPECIFIED"),
                }

                if requirements_to_enrich:
                    enrichment_report = enricher.generate_enrichment_report(
                        spec_version_id="temp",
                        specification_version=1,
                        source_checksum=jd_version.raw_text_checksum,
                        requirements=requirements_to_enrich,
                        role_context=role_context,
                        raw_jd_text=raw_text,
                    )
                    enriched_md = render_markdown(spec, enrichment_report=enrichment_report)
            except Exception as exc:
                logger.warning("Automatic Ollama enrichment failed; falling back to deterministic baseline: %s", exc)
                enrichment_report = None
                enriched_md = None

        baseline_markdown = render_markdown(spec)
        json_str = to_json_str(spec)

        stage("GENERATING", "Saving independent specification artifacts", 95)
        project_id = str(jd_version.job_description.project_id) if jd_version.job_description else "unknown"
        json_key = build_key(project_id, str(jd_version.job_description_id), jd_version.version, "json")
        md_key = build_key(project_id, str(jd_version.job_description_id), jd_version.version, "markdown")
        storage.put_text(json_key, json_str, "application/json")
        storage.put_text(md_key, baseline_markdown, "text/markdown")

        if enriched_md:
            enriched_key = build_key(project_id, str(jd_version.job_description_id), jd_version.version, "enriched_markdown")
            storage.put_text(enriched_key, enriched_md, "text/markdown")

        spec_version = JobSpecificationVersion(
            job_description_version_id=jd_version_id,
            specification_version=1,
            s3_json_key=json_key,
            s3_markdown_key=md_key,
            canonical_json=json.loads(json_str),
            master_context_json=master_context.model_dump(mode="json"),
            enrichment_report_json=enrichment_report.model_dump(mode="json") if enrichment_report else None,
            s3_enriched_markdown_key=enriched_key,
            lifecycle_status=JDLifecycleStatusEnum(master_context.lifecycle_status.value),
            prompt_version=spec.metadata.prompt_version or "deterministic_v1",
            model_version=spec.metadata.model_version or "deterministic_ekg",
            input_tokens=0,
            output_tokens=0,
            latency_ms=latency_ms,
            estimated_cost_usd=0,
            is_valid=report.valid,
            needs_review=needs_review,
        )
        db.add(spec_version)
        db.flush()

        from app.models.db_models import ClarificationQuestion, ClarificationQuestionPriorityEnum, ClarificationQuestionStatusEnum
        for q in master_context.clarification_history:
            db.add(
                ClarificationQuestion(
                    job_specification_version_id=spec_version.id,
                    question_key=q.question_key,
                    category=q.category.value if hasattr(q.category, "value") else str(q.category),
                    priority=ClarificationQuestionPriorityEnum(q.priority.value),
                    is_blocking=q.is_blocking,
                    question_text=q.question_text,
                    rationale=q.rationale or "",
                    field_target=q.field_target,
                    status=ClarificationQuestionStatusEnum(q.status.value),
                    answer_text=q.answer_text,
                )
            )

        job.status = ProcessingStatusEnum.NEEDS_REVIEW if needs_review else ProcessingStatusEnum.READY
        job.finished_at = datetime.now(timezone.utc)
        db.commit()

    except JobProcessingCancelled as exc:
        logger.info("JD processing cancelled for %s", jd_version_id)
        job.status = ProcessingStatusEnum.FAILED
        job.error_message = str(exc)
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
