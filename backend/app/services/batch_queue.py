"""Persistent, bounded background queue for multi-JD batches."""
from __future__ import annotations

import logging
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models.db_models import (
    JobDescriptionBatch,
    JobDescriptionBatchTask,
    JobSpecificationVersion,
    ProcessingJob,
    ProcessingStatusEnum,
)
from app.services.storage import get_storage

logger = logging.getLogger("jd_agent.batch_queue")
_TERMINAL_TASK_STATUSES = {"COMPLETED", "FAILED", "CANCELLED"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class JDBatchQueue:
    """Runs persisted batch tasks on a bounded thread pool and recovers on restart."""

    def __init__(self) -> None:
        settings = get_settings()
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, settings.jd_processing_concurrency),
            thread_name_prefix="jd-batch",
        )
        self._lock = threading.Lock()
        self._submitted: set[str] = set()
        self._started = False

    def start(self) -> None:
        """Recover interrupted tasks, then dispatch every persisted queued task."""
        with self._lock:
            if self._started:
                return
            self._started = True

        with SessionLocal() as db:
            interrupted = (
                db.query(JobDescriptionBatchTask)
                .filter(JobDescriptionBatchTask.status == "PROCESSING")
                .all()
            )
            for task in interrupted:
                stale_jobs = (
                    db.query(ProcessingJob)
                    .filter(
                        ProcessingJob.job_description_version_id == task.job_description_version_id,
                        ProcessingJob.status.notin_(
                            [ProcessingStatusEnum.READY, ProcessingStatusEnum.NEEDS_REVIEW, ProcessingStatusEnum.FAILED]
                        ),
                    )
                    .all()
                )
                for job in stale_jobs:
                    job.status = ProcessingStatusEnum.FAILED
                    job.error_message = "Worker stopped before completing the task; task was recovered."
                    job.finished_at = _now()
                if task.cancel_requested:
                    task.status = "CANCELLED"
                    task.stage = "CANCELLED"
                    task.stage_label = "Cancelled during service restart"
                    task.finished_at = _now()
                else:
                    task.status = "QUEUED"
                    task.stage = "QUEUED"
                    task.stage_label = "Recovered after service restart"
                    task.progress_percent = 0
                    task.started_at = None
            db.commit()
            queued_ids = [
                task.id for task in db.query(JobDescriptionBatchTask.id)
                .filter(JobDescriptionBatchTask.status == "QUEUED")
                .all()
            ]
            batch_ids = {
                batch_id for (batch_id,) in db.query(JobDescriptionBatchTask.batch_id).all()
            }
            for batch_id in batch_ids:
                self._refresh_batch_status(db, batch_id)
            db.commit()

        self.enqueue(queued_ids)

    def enqueue(self, task_ids: Iterable[str]) -> None:
        for task_id in task_ids:
            with self._lock:
                if task_id in self._submitted:
                    continue
                self._submitted.add(task_id)
            try:
                self._executor.submit(self._run_task, task_id)
            except RuntimeError:
                with self._lock:
                    self._submitted.discard(task_id)
                logger.exception("Could not submit persisted JD batch task %s", task_id)
                raise

    def cancel(self, batch_id: str, task_id: str) -> str:
        with SessionLocal() as db:
            task = (
                db.query(JobDescriptionBatchTask)
                .filter(
                    JobDescriptionBatchTask.id == task_id,
                    JobDescriptionBatchTask.batch_id == batch_id,
                )
                .first()
            )
            if task is None:
                return "not_found"
            if task.status == "QUEUED":
                task.status = "CANCELLED"
                task.stage = "CANCELLED"
                task.stage_label = "Cancelled before processing"
                task.error_message = "Cancelled by user."
                task.finished_at = _now()
                result = "cancelled"
            elif task.status == "PROCESSING":
                task.cancel_requested = True
                task.stage_label = "Cancellation requested; waiting for a safe checkpoint"
                result = "cancellation_requested"
            else:
                return "not_running"
            self._refresh_batch_status(db, batch_id)
            db.commit()
            return result

    def retry(self, batch_id: str, task_id: str) -> str:
        with SessionLocal() as db:
            task = (
                db.query(JobDescriptionBatchTask)
                .filter(
                    JobDescriptionBatchTask.id == task_id,
                    JobDescriptionBatchTask.batch_id == batch_id,
                )
                .first()
            )
            if task is None:
                return "not_found"
            if task.status not in {"FAILED", "CANCELLED"}:
                return "not_retryable"
            task.status = "QUEUED"
            task.stage = "QUEUED"
            task.stage_label = "Retry queued"
            task.progress_percent = 0
            task.error_message = None
            task.cancel_requested = False
            task.started_at = None
            task.finished_at = None
            task.markdown_path = None
            task.json_path = None
            self._refresh_batch_status(db, batch_id)
            db.commit()
        self.enqueue([task_id])
        return "queued"

    def refresh_completed_artifacts(self, batch_id: str, task_id: str) -> str:
        """Copy the latest resolved specification into this JD's batch artifacts."""
        with SessionLocal() as db:
            task = (
                db.query(JobDescriptionBatchTask)
                .filter(
                    JobDescriptionBatchTask.id == task_id,
                    JobDescriptionBatchTask.batch_id == batch_id,
                )
                .first()
            )
            if task is None:
                return "not_found"
            if task.status != "COMPLETED":
                return "not_completed"

            specification = (
                db.query(JobSpecificationVersion)
                .filter(
                    JobSpecificationVersion.job_description_version_id
                    == task.job_description_version_id
                )
                .order_by(JobSpecificationVersion.created_at.desc())
                .first()
            )
            if specification is None:
                return "no_specification"

            storage = get_storage()
            markdown_key = specification.s3_enriched_markdown_key or specification.s3_markdown_key
            markdown = storage.get_text(markdown_key)
            json_content = storage.get_text(specification.s3_json_key)
            output_dir = Path(__file__).resolve().parents[3] / "outputs" / batch_id / task.job_description_id
            output_dir.mkdir(parents=True, exist_ok=True)
            markdown_path = Path(task.markdown_path) if task.markdown_path else output_dir / "job_specification.md"
            json_path = Path(task.json_path) if task.json_path else output_dir / "job_specification.json"

            self._atomic_write(markdown_path, markdown)
            self._atomic_write(json_path, json_content)
            task.markdown_path = str(markdown_path.resolve())
            task.json_path = str(json_path.resolve())
            db.commit()
            return "refreshed"

    def _is_cancelled(self, task_id: str) -> bool:
        with SessionLocal() as db:
            task = db.get(JobDescriptionBatchTask, task_id)
            return task is None or task.cancel_requested or task.status == "CANCELLED"

    def _set_stage(self, task_id: str, stage: str, label: str, percent: int) -> None:
        with SessionLocal() as db:
            task = db.get(JobDescriptionBatchTask, task_id)
            if task is None or task.status != "PROCESSING":
                return
            if task.cancel_requested:
                return
            task.stage = stage
            task.stage_label = label
            task.progress_percent = max(task.progress_percent, min(95, percent))
            self._refresh_batch_status(db, task.batch_id)
            db.commit()

    def _run_task(self, task_id: str) -> None:
        try:
            with SessionLocal() as db:
                task = db.get(JobDescriptionBatchTask, task_id)
                if task is None or task.status != "QUEUED":
                    return
                task.status = "PROCESSING"
                task.stage = "PARSING"
                task.stage_label = "Starting JD processing"
                task.progress_percent = max(task.progress_percent, 5)
                task.attempt_count += 1
                task.started_at = _now()
                task.error_message = None
                batch_id = task.batch_id
                jd_id = task.job_description_id
                version_id = task.job_description_version_id
                self._refresh_batch_status(db, batch_id)
                db.commit()

            from app.workers.worker import process_job_description_version

            with SessionLocal() as db:
                process_job_description_version(
                    db,
                    version_id,
                    on_stage=lambda stage, label, percent: self._set_stage(
                        task_id, stage, label, percent
                    ),
                    is_cancelled=lambda: self._is_cancelled(task_id),
                )

            self._finish_from_worker(task_id, batch_id, jd_id, version_id)
        except Exception as exc:
            logger.exception("JD batch task %s failed", task_id)
            self._mark_failed(task_id, str(exc) or exc.__class__.__name__)
        finally:
            with self._lock:
                self._submitted.discard(task_id)
            try:
                with SessionLocal() as db:
                    task = db.get(JobDescriptionBatchTask, task_id)
                    retry_was_queued_while_worker_was_exiting = (
                        task is not None and task.status == "QUEUED"
                    )
                if retry_was_queued_while_worker_was_exiting:
                    self.enqueue([task_id])
            except Exception:
                logger.exception("Could not dispatch JD batch retry %s", task_id)

    def _finish_from_worker(self, task_id: str, batch_id: str, jd_id: str, version_id: str) -> None:
        with SessionLocal() as db:
            task = db.get(JobDescriptionBatchTask, task_id)
            if task is None:
                return
            if task.cancel_requested or task.status == "CANCELLED":
                task.status = "CANCELLED"
                task.stage = "CANCELLED"
                task.stage_label = "Cancelled at a safe processing checkpoint"
                task.error_message = "Cancelled by user."
                task.finished_at = _now()
                self._refresh_batch_status(db, batch_id)
                db.commit()
                return

            processing_job = (
                db.query(ProcessingJob)
                .filter(ProcessingJob.job_description_version_id == version_id)
                .order_by(ProcessingJob.created_at.desc())
                .first()
            )
            if processing_job is None or processing_job.status not in {
                ProcessingStatusEnum.READY,
                ProcessingStatusEnum.NEEDS_REVIEW,
            }:
                task.status = "FAILED"
                task.stage = "FAILED"
                task.stage_label = "JD processing failed"
                task.error_message = (
                    processing_job.error_message if processing_job else "Worker did not create a processing record."
                )
                task.finished_at = _now()
                self._refresh_batch_status(db, batch_id)
                db.commit()
                return

            specification = (
                db.query(JobSpecificationVersion)
                .filter(JobSpecificationVersion.job_description_version_id == version_id)
                .order_by(JobSpecificationVersion.created_at.desc())
                .first()
            )
            if specification is None:
                task.status = "FAILED"
                task.stage = "FAILED"
                task.stage_label = "Specification artifacts were not generated"
                task.error_message = "No specification version was persisted by the worker."
                task.finished_at = _now()
                self._refresh_batch_status(db, batch_id)
                db.commit()
                return

            storage = get_storage()
            markdown_key = specification.s3_enriched_markdown_key or specification.s3_markdown_key
            markdown = storage.get_text(markdown_key)
            json_content = storage.get_text(specification.s3_json_key)
            output_dir = Path(__file__).resolve().parents[3] / "outputs" / batch_id / jd_id
            output_dir.mkdir(parents=True, exist_ok=True)
            md_path = output_dir / "job_specification.md"
            json_path = output_dir / "job_specification.json"
            self._atomic_write(md_path, markdown)
            try:
                self._atomic_write(json_path, json_content)
            except Exception:
                md_path.unlink(missing_ok=True)
                raise

            task.status = "COMPLETED"
            task.stage = "COMPLETED"
            task.stage_label = "Specification ready"
            task.progress_percent = 100
            task.error_message = None
            task.markdown_path = str(md_path.resolve())
            task.json_path = str(json_path.resolve())
            task.finished_at = _now()
            self._refresh_batch_status(db, batch_id)
            db.commit()
            logger.info("Batch task %s completed for JD %s", task_id, jd_id)

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(content, encoding="utf-8")
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _mark_failed(self, task_id: str, error: str) -> None:
        with SessionLocal() as db:
            task = db.get(JobDescriptionBatchTask, task_id)
            if task is None or task.status in _TERMINAL_TASK_STATUSES:
                return
            task.status = "FAILED"
            task.stage = "FAILED"
            task.stage_label = "JD processing failed"
            task.error_message = error[:4000]
            task.finished_at = _now()
            self._refresh_batch_status(db, task.batch_id)
            db.commit()

    @staticmethod
    def _refresh_batch_status(db: Session, batch_id: str) -> None:
        batch = db.get(JobDescriptionBatch, batch_id)
        if batch is None:
            return
        statuses = [
            status for (status,) in db.query(JobDescriptionBatchTask.status)
            .filter(JobDescriptionBatchTask.batch_id == batch_id)
            .all()
        ]
        if statuses and all(status in _TERMINAL_TASK_STATUSES for status in statuses):
            batch.status = "FAILED" if any(status != "COMPLETED" for status in statuses) else "COMPLETED"
        elif any(status == "PROCESSING" for status in statuses):
            batch.status = "PROCESSING"
        else:
            batch.status = "QUEUED"


jd_batch_queue = JDBatchQueue()
