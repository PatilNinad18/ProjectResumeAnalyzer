"""
REST API for the JD Understanding Agent.

POST /jds/{id}/analyze returns immediately (202). The LLM work runs in a
background task and the client polls GET /jds/{id}/analysis until the status is
READY / NEEDS_REVIEW / FAILED.

The two other slow LLM operations work the same way:
  POST /jds/{id}/enrich                  -> 202, then poll GET /jds/{id}/tasks/enrich
  POST /jds/{id}/clarifications/resolve  -> 202, then poll GET /jds/{id}/tasks/resolve
When a task is "done" the client fetches the result with GET /markdown, /json and
/clarifications (the new specification version is simply the latest one).

Ollama inference is bounded by the shared configurable semaphore. Batch task
state is persisted in the database; legacy enrichment/clarification task
deduplication remains in-process.

NOTE: in-flight tracking is in-process memory, which is correct for a single
uvicorn worker (local Ollama). For multi-worker production, replace
_inflight/_errors/_tasks with a Redis key or a status column and use SQS/Celery
instead of BackgroundTasks.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import io
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.db_models import (
    Agent,
    AuditEvent,
    JobDescription,
    JobDescriptionBatch,
    JobDescriptionBatchTask,
    JobDescriptionVersion,
    JobSpecificationVersion,
    ProcessingJob,
    gen_uuid,
)
from app.services.document_parser import DocumentParseError, parse_document
from app.services.json_serializer import to_json_dict, to_json_str
from app.services.markdown_renderer import render_markdown
from app.services.markdown_to_json import markdown_to_spec
from app.services.storage import build_key, checksum, get_storage
from app.services.validation import validate_payload

logger = logging.getLogger("jd_agent.api")

router = APIRouter(prefix="/api", tags=["jds"])
storage = get_storage()

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
TERMINAL_STATUSES = {"READY", "NEEDS_REVIEW", "FAILED"}

# ---------------------------------------------------------------------------
# Background processing state
# ---------------------------------------------------------------------------
_state_lock = threading.Lock()
_inflight: Dict[str, float] = {}   # jd_id -> start time (analysis)
_errors: Dict[str, str] = {}       # jd_id -> last failure message (analysis)

# Long-running LLM tasks other than the analysis ("enrich", "resolve").
# key = f"{kind}:{jd_id}" -> {"status": running|done|failed, "error": str|None, "started_at": float, "finished_at": float|None}
_tasks: Dict[str, Dict[str, Any]] = {}
TASK_KINDS = ("enrich", "resolve")

# Serialize mutations for one JD while allowing unrelated JDs to use the shared
# inference semaphore concurrently.
_jd_task_locks: Dict[str, threading.Lock] = {}


def _any_llm_job_running() -> bool:
    with _state_lock:
        return bool(_inflight) or any(t["status"] == "running" for t in _tasks.values())


def _run_processing(jd_id: str, jd_version_id: str) -> None:
    """Runs in a worker thread, with its own DB session."""
    from app.db import SessionLocal
    from app.workers.worker import process_job_description_version

    db = SessionLocal()
    try:
        process_job_description_version(db, jd_version_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Background analysis failed for jd_id=%s", jd_id)
        with _state_lock:
            _errors[jd_id] = str(exc) or exc.__class__.__name__
    finally:
        db.close()
        with _state_lock:
            started = _inflight.pop(jd_id, None)
        if started:
            logger.info("Analysis finished for jd_id=%s in %.1fs", jd_id, time.time() - started)


def _update_task_progress(key: str, stage: str, stage_label: str, progress_percent: int) -> None:
    with _state_lock:
        if key in _tasks:
            _tasks[key].update(
                stage=stage,
                stage_label=stage_label,
                progress_percent=progress_percent,
            )


def _task_runner(key: str, fn, jd_id: str, *args) -> None:
    """Runs `fn(db, jd_id, *args)` in a worker thread with its own DB session and records the outcome."""
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        with _state_lock:
            jd_lock = _jd_task_locks.setdefault(jd_id, threading.Lock())
        with jd_lock:
            fn(db, jd_id, *args)
        with _state_lock:
            _tasks[key].update(
                status="done",
                error=None,
                finished_at=time.time(),
                stage="DONE",
                stage_label="Task completed successfully",
                progress_percent=100,
            )
        logger.info("Task %s finished in %.1fs", key, time.time() - _tasks[key]["started_at"])
    except HTTPException as exc:
        db.rollback()
        logger.warning("Task %s failed: %s", key, exc.detail)
        with _state_lock:
            _tasks[key].update(
                status="failed",
                error=str(exc.detail),
                finished_at=time.time(),
                stage="FAILED",
                stage_label=f"Task failed: {exc.detail}",
                progress_percent=0,
            )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("Task %s crashed", key)
        with _state_lock:
            _tasks[key].update(
                status="failed",
                error=str(exc) or exc.__class__.__name__,
                finished_at=time.time(),
                stage="FAILED",
                stage_label=f"Task crashed: {exc}",
                progress_percent=0,
            )
    finally:
        db.close()


def _start_task(kind: str, jd_id: str, background_tasks: BackgroundTasks, fn, *args) -> Dict[str, Any]:
    key = f"{kind}:{jd_id}"
    with _state_lock:
        current = _tasks.get(key)
        if current and current["status"] == "running":
            return {"jd_id": jd_id, "task": kind, "status": "already_running"}
        _tasks[key] = {
            "status": "running",
            "error": None,
            "started_at": time.time(),
            "finished_at": None,
            "stage": "QUEUED",
            "stage_label": f"Queued {kind} task...",
            "progress_percent": 10,
        }
    background_tasks.add_task(_task_runner, key, fn, jd_id, *args)
    return {"jd_id": jd_id, "task": kind, "status": "queued"}


_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        from app.services.llm_service import LLMService
        _llm = LLMService()
    return _llm


def _status_str(job: ProcessingJob) -> str:
    return job.status.value if hasattr(job.status, "value") else str(job.status)


# ---------------------------------------------------------------------------
# JD CRUD
# ---------------------------------------------------------------------------
@router.get("/jds")
def list_jds(project_id: Optional[str] = None, db: Session = Depends(get_db)):
    """List all JDs with their latest processing status and specification summary."""
    query = db.query(JobDescription)
    if project_id:
        query = query.filter(JobDescription.project_id == project_id)
    jds = query.order_by(JobDescription.created_at.desc()).all()

    results = []
    for jd in jds:
        latest_spec = (
            db.query(JobSpecificationVersion)
            .join(JobDescriptionVersion)
            .filter(JobDescriptionVersion.job_description_id == jd.id)
            .order_by(JobSpecificationVersion.created_at.desc())
            .first()
        )
        latest_job = (
            db.query(ProcessingJob)
            .join(JobDescriptionVersion)
            .filter(JobDescriptionVersion.job_description_id == jd.id)
            .order_by(ProcessingJob.created_at.desc())
            .first()
        )
        status_val = _status_str(latest_job) if latest_job else "UPLOADED"
        with _state_lock:
            if jd.id in _inflight:
                status_val = "UNDERSTANDING"

        results.append({
            "jd_id": jd.id,
            "project_id": jd.project_id,
            "title": jd.title or "Untitled JD",
            "current_version": jd.current_version,
            "created_at": jd.created_at.isoformat() if jd.created_at else None,
            "status": status_val,
            "has_specification": latest_spec is not None,
            "specification_version": latest_spec.specification_version if latest_spec else None,
        })
    return results


@router.post("/jds")
def upload_jd(
    project_id: str = Form(...),
    title: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Upload a JD as raw text or a file (.txt, .pdf, .docx). Both normalize into raw_jd_text."""
    raw_text = ""
    inferred_title = title

    if text and text.strip():
        raw_text = text.strip()
    elif file is not None:
        try:
            file_bytes = file.file.read(MAX_UPLOAD_BYTES + 1)
            if len(file_bytes) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "File is too large (max 5 MB).")
            raw_text = parse_document(file.filename or "upload.txt", file_bytes)
            if not inferred_title and file.filename:
                inferred_title = file.filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()
        except HTTPException:
            raise
        except DocumentParseError as e:
            raise HTTPException(400, str(e))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"Error reading uploaded file: {e}")
    else:
        raise HTTPException(400, "Provide either a file (.txt, .pdf, .docx) or raw text.")

    if not raw_text or not raw_text.strip():
        raise HTTPException(400, "JD content is empty.")

    # The recruiter's explicit title is authoritative. Stamp it on the first line so the
    # analysis (and chat) use it instead of guessing one from the JD body.
    if title and title.strip() and not raw_text.lstrip().lower().startswith("job title:"):
        raw_text = f"Job Title: {title.strip()}\n\n{raw_text}"

    jd = JobDescription(project_id=project_id, title=inferred_title or "Untitled JD", current_version=1)
    db.add(jd)
    db.flush()

    key = build_key(project_id, jd.id, 1, "raw")
    storage.put_text(key, raw_text)

    jd_version = JobDescriptionVersion(
        job_description_id=jd.id,
        version=1,
        s3_raw_key=key,
        raw_text_checksum=checksum(raw_text),
    )
    db.add(jd_version)
    db.commit()

    return {
        "jd_id": jd.id,
        "jd_version_id": jd_version.id,
        "version": 1,
        "title": jd.title,
        "status": "UPLOADED",
    }


def _batch_task_payload(task: JobDescriptionBatchTask) -> Dict[str, Any]:
    jd = task.job_description
    return {
        "task_id": task.id,
        "jd_id": task.job_description_id,
        "title": jd.title if jd else task.source_filename,
        "filename": task.source_filename,
        "status": task.status,
        "stage": task.stage,
        "stage_label": task.stage_label,
        "progress_percent": task.progress_percent,
        "attempt_count": task.attempt_count,
        "cancel_requested": task.cancel_requested,
        "error_message": task.error_message,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "has_specification": task.status == "COMPLETED",
    }


def _batch_payload(batch: JobDescriptionBatch) -> Dict[str, Any]:
    tasks = [_batch_task_payload(task) for task in batch.tasks]
    return {
        "batch_id": batch.id,
        "project_id": batch.project_id,
        "status": batch.status,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "total": len(tasks),
        "completed": sum(task["status"] == "COMPLETED" for task in tasks),
        "failed": sum(task["status"] == "FAILED" for task in tasks),
        "cancelled": sum(task["status"] == "CANCELLED" for task in tasks),
        "processing": sum(task["status"] == "PROCESSING" for task in tasks),
        "queued": sum(task["status"] == "QUEUED" for task in tasks),
        "progress_percent": round(
            sum(task["progress_percent"] for task in tasks) / len(tasks)
        ) if tasks else 0,
        "tasks": tasks,
    }


@router.post("/batches", status_code=202)
def create_jd_batch(
    files: List[UploadFile] = File(...),
    project_id: str = Form("default-project"),
    db: Session = Depends(get_db),
):
    """Create a persisted batch and queue one independent task per uploaded JD."""
    if not files:
        raise HTTPException(400, "Upload at least one .pdf, .docx, or .txt file.")

    parsed_files = []
    for uploaded in files:
        filename = uploaded.filename or "upload.txt"
        try:
            file_bytes = uploaded.file.read(MAX_UPLOAD_BYTES + 1)
            if len(file_bytes) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, f"{filename}: file is too large (max 5 MB).")
            raw_text = parse_document(filename, file_bytes)
        except HTTPException:
            raise
        except DocumentParseError as exc:
            raise HTTPException(400, f"{filename}: {exc}") from exc
        except Exception as exc:
            raise HTTPException(400, f"{filename}: could not read uploaded file: {exc}") from exc
        parsed_files.append((filename, raw_text))

    batch = JobDescriptionBatch(
        id=gen_uuid(),
        project_id=project_id.strip() or "default-project",
        status="QUEUED",
    )
    db.add(batch)
    db.flush()
    task_ids = []
    for filename, raw_text in parsed_files:
        title = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip() or "Untitled JD"
        jd = JobDescription(project_id=batch.project_id, title=title, current_version=1)
        db.add(jd)
        db.flush()
        raw_key = build_key(batch.project_id, jd.id, 1, "raw")
        storage.put_text(raw_key, raw_text)
        jd_version = JobDescriptionVersion(
            job_description_id=jd.id,
            version=1,
            s3_raw_key=raw_key,
            raw_text_checksum=checksum(raw_text),
        )
        db.add(jd_version)
        db.flush()
        task = JobDescriptionBatchTask(
            id=gen_uuid(),
            batch_id=batch.id,
            job_description_id=jd.id,
            job_description_version_id=jd_version.id,
            source_filename=filename,
        )
        db.add(task)
        db.flush()
        task_ids.append(task.id)

    db.commit()
    try:
        from app.services.batch_queue import jd_batch_queue
        jd_batch_queue.enqueue(task_ids)
    except Exception as exc:
        logger.exception("Batch %s was persisted but queue submission failed", batch.id)
        raise HTTPException(
            503,
            "The batch was saved, but workers could not be started. It will be recovered when the backend restarts.",
        ) from exc

    db.refresh(batch)
    return _batch_payload(batch)


@router.get("/batches/{batch_id}")
def get_jd_batch(batch_id: str, db: Session = Depends(get_db)):
    batch = db.get(JobDescriptionBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "JD batch not found")
    return _batch_payload(batch)


@router.get("/batches")
def list_jd_batches(limit: int = 20, db: Session = Depends(get_db)):
    limit = max(1, min(limit, 100))
    batches = (
        db.query(JobDescriptionBatch)
        .order_by(JobDescriptionBatch.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_batch_payload(batch) for batch in batches]


@router.get("/batches/{batch_id}/jds")
def list_batch_jds(batch_id: str, db: Session = Depends(get_db)):
    batch = db.get(JobDescriptionBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "JD batch not found")
    return {"batch_id": batch.id, "status": batch.status, "jds": _batch_payload(batch)["tasks"]}


@router.get("/batches/{batch_id}/tasks/{task_id}")
def get_batch_task(batch_id: str, task_id: str, db: Session = Depends(get_db)):
    task = (
        db.query(JobDescriptionBatchTask)
        .filter(
            JobDescriptionBatchTask.batch_id == batch_id,
            JobDescriptionBatchTask.id == task_id,
        )
        .first()
    )
    if task is None:
        raise HTTPException(404, "JD batch task not found")
    return _batch_task_payload(task)


@router.post("/batches/{batch_id}/tasks/{task_id}/retry", status_code=202)
def retry_batch_task(batch_id: str, task_id: str, db: Session = Depends(get_db)):
    if db.get(JobDescriptionBatch, batch_id) is None:
        raise HTTPException(404, "JD batch not found")
    from app.services.batch_queue import jd_batch_queue
    result = jd_batch_queue.retry(batch_id, task_id)
    if result == "not_found":
        raise HTTPException(404, "JD batch task not found")
    if result == "not_retryable":
        raise HTTPException(409, "Only failed or cancelled tasks can be retried.")
    return {"batch_id": batch_id, "task_id": task_id, "status": result}


@router.post("/batches/{batch_id}/tasks/{task_id}/cancel")
def cancel_batch_task(batch_id: str, task_id: str, db: Session = Depends(get_db)):
    if db.get(JobDescriptionBatch, batch_id) is None:
        raise HTTPException(404, "JD batch not found")
    from app.services.batch_queue import jd_batch_queue
    result = jd_batch_queue.cancel(batch_id, task_id)
    if result == "not_found":
        raise HTTPException(404, "JD batch task not found")
    if result == "not_running":
        raise HTTPException(409, "This task is already finished.")
    return {"batch_id": batch_id, "task_id": task_id, "status": result}


@router.post("/batches/{batch_id}/tasks/{task_id}/refresh")
def refresh_batch_task_artifacts(batch_id: str, task_id: str, db: Session = Depends(get_db)):
    if db.get(JobDescriptionBatch, batch_id) is None:
        raise HTTPException(404, "JD batch not found")
    from app.services.batch_queue import jd_batch_queue

    result = jd_batch_queue.refresh_completed_artifacts(batch_id, task_id)
    if result == "not_found":
        raise HTTPException(404, "JD batch task not found")
    if result == "not_completed":
        raise HTTPException(409, "Only completed JD tasks can refresh their artifacts.")
    if result == "no_specification":
        raise HTTPException(404, "No specification is available for this JD.")
    return {"batch_id": batch_id, "task_id": task_id, "status": result}


def _get_batch_task_for_download(
    batch_id: str, jd_id: str, db: Session, artifact: str
) -> tuple[JobDescriptionBatchTask, Path]:
    task = (
        db.query(JobDescriptionBatchTask)
        .filter(
            JobDescriptionBatchTask.batch_id == batch_id,
            JobDescriptionBatchTask.job_description_id == jd_id,
        )
        .first()
    )
    if task is None:
        raise HTTPException(404, "JD batch task not found")
    if task.status != "COMPLETED":
        raise HTTPException(409, "This JD has not completed successfully.")
    stored_path = task.markdown_path if artifact == "md" else task.json_path
    if not stored_path:
        raise HTTPException(404, "The requested specification file is not available.")
    path = Path(stored_path).resolve()
    if not path.is_file():
        raise HTTPException(404, "The requested specification file is missing.")
    return task, path


@router.get("/batches/{batch_id}/jds/{jd_id}/downloads/{artifact}")
def download_batch_jd_artifact(
    batch_id: str,
    jd_id: str,
    artifact: str,
    db: Session = Depends(get_db),
):
    if artifact not in {"md", "json"}:
        raise HTTPException(404, "Artifact must be 'md' or 'json'.")
    task, path = _get_batch_task_for_download(batch_id, jd_id, db, artifact)
    media_type = "text/markdown" if artifact == "md" else "application/json"
    filename = "job_specification.md" if artifact == "md" else "job_specification.json"
    return FileResponse(path, media_type=media_type, filename=filename)


@router.get("/batches/{batch_id}/downloads.zip")
def download_batch_zip(batch_id: str, db: Session = Depends(get_db)):
    batch = db.get(JobDescriptionBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "JD batch not found")
    completed = [task for task in batch.tasks if task.status == "COMPLETED"]
    if not completed:
        raise HTTPException(409, "No completed JD specifications are available to download.")

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for task in completed:
            for path_value in (task.markdown_path, task.json_path):
                if not path_value:
                    continue
                path = Path(path_value).resolve()
                if not path.is_file():
                    logger.warning("Completed batch artifact is missing: %s", path)
                    continue
                zipped.write(path, arcname=f"{task.job_description_id}/{path.name}")
    archive.seek(0)
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="jd_batch_{batch_id}.zip"'},
    )


@router.get("/jds/{jd_id}")
def get_jd(jd_id: str, db: Session = Depends(get_db)):
    jd = db.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(404, "JD not found")
    return {"jd_id": jd.id, "title": jd.title, "current_version": jd.current_version}


# ---------------------------------------------------------------------------
# Analysis (non-blocking)
# ---------------------------------------------------------------------------
@router.post("/jds/{jd_id}/analyze", status_code=202)
def analyze_jd(jd_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    jd_version = (
        db.query(JobDescriptionVersion)
        .filter(JobDescriptionVersion.job_description_id == jd_id)
        .order_by(JobDescriptionVersion.version.desc())
        .first()
    )
    if not jd_version:
        raise HTTPException(404, "No JD version found")

    with _state_lock:
        if jd_id in _inflight:
            return {"jd_id": jd_id, "jd_version_id": jd_version.id, "status": "already_running"}
        _inflight[jd_id] = time.time()
        _errors.pop(jd_id, None)

    background_tasks.add_task(_run_processing, jd_id, jd_version.id)
    return {"jd_id": jd_id, "jd_version_id": jd_version.id, "status": "queued"}


def _get_analysis_progress(status: str) -> tuple[int, str]:
    stages = {
        "UPLOADED": (10, "Uploading & queueing analysis"),
        "PARSING": (25, "Parsing document structure & sections"),
        "UNDERSTANDING": (50, "Extracting domain requirements & EKG concepts"),
        "VALIDATING": (75, "Validating extracted constraints & schema"),
        "GENERATING": (90, "Synthesizing evaluation specification & guidance"),
        "READY": (100, "Analysis complete"),
        "NEEDS_REVIEW": (100, "Analysis complete (ready for review)"),
        "FAILED": (0, "Analysis failed"),
    }
    return stages.get(status, (20, f"Processing ({status})"))


@router.get("/jds/{jd_id}/analysis")
def get_analysis(jd_id: str, db: Session = Depends(get_db)):
    latest_job = (
        db.query(ProcessingJob)
        .join(JobDescriptionVersion)
        .filter(JobDescriptionVersion.job_description_id == jd_id)
        .order_by(ProcessingJob.created_at.desc())
        .first()
    )

    with _state_lock:
        started = _inflight.get(jd_id)
        error = _errors.get(jd_id)

    # Running now: never report a stale terminal status from a previous run.
    if started is not None:
        db_status = _status_str(latest_job) if latest_job else None
        status = db_status if db_status and db_status not in TERMINAL_STATUSES else "UNDERSTANDING"
        pct, label = _get_analysis_progress(status)
        return {
            "status": status,
            "error_message": None,
            "started_at": started,
            "finished_at": None,
            "elapsed_seconds": round(time.time() - started, 1),
            "progress_percent": pct,
            "stage_label": label,
            "current_stage": status,
        }

    # Crashed before the worker could record FAILED.
    if error:
        return {
            "status": "FAILED",
            "error_message": error,
            "started_at": None,
            "finished_at": None,
            "elapsed_seconds": None,
            "progress_percent": 0,
            "stage_label": "Analysis failed",
            "current_stage": "FAILED",
        }

    if not latest_job:
        if not db.get(JobDescription, jd_id):
            raise HTTPException(404, "JD not found")
        pct, label = _get_analysis_progress("UPLOADED")
        return {
            "status": "UPLOADED",
            "error_message": None,
            "started_at": None,
            "finished_at": None,
            "elapsed_seconds": None,
            "progress_percent": pct,
            "stage_label": label,
            "current_stage": "UPLOADED",
        }

    st = _status_str(latest_job)
    pct, label = _get_analysis_progress(st)
    return {
        "status": st,
        "error_message": latest_job.error_message,
        "started_at": latest_job.started_at,
        "finished_at": latest_job.finished_at,
        "elapsed_seconds": None,
        "progress_percent": pct,
        "stage_label": label,
        "current_stage": st,
    }


@router.post("/jds/{jd_id}/analysis/cancel")
def cancel_analysis(jd_id: str):
    """Cancel an in-flight analysis job."""
    with _state_lock:
        if jd_id in _inflight:
            _inflight.pop(jd_id, None)
            _errors[jd_id] = "Analysis was cancelled by user."
            return {"jd_id": jd_id, "status": "cancelled", "message": "Analysis cancelled successfully"}
    return {"jd_id": jd_id, "status": "not_running", "message": "Analysis not currently running"}


class _CancelOpPayload(BaseModel):
    operation: Optional[str] = "analysis"


@router.get("/jds/{jd_id}/progress")
def get_jd_progress(jd_id: str, operation: str = "analysis"):
    """Get unified real-time progress for JD operations from ProgressRegistry."""
    from app.core.progress import progress_registry
    p = progress_registry.get_progress(jd_id, operation)
    if not p:
        return {"stage": "IDLE", "percent": 0, "operation": operation, "jd_id": jd_id, "cancelled": False}
    return p if isinstance(p, dict) else p.to_dict()


@router.post("/jds/{jd_id}/cancel")
def cancel_jd_operation(jd_id: str, payload: Optional[_CancelOpPayload] = None):
    """Cancel in-flight JD operation in ProgressRegistry and in-flight tracking."""
    from app.core.progress import progress_registry
    op = (payload.operation if payload else None) or "analysis"
    progress_registry.cancel_progress(jd_id, op)
    with _state_lock:
        if jd_id in _inflight:
            _inflight.pop(jd_id, None)
            _errors[jd_id] = "Cancelled by user."
    return {"cancelled": True, "operation": op, "jd_id": jd_id}


@router.get("/jds/{jd_id}/tasks/{kind}")
def get_task_status(jd_id: str, kind: str):
    """Status of a long-running background task: kind = enrich | resolve."""
    if kind not in TASK_KINDS:
        raise HTTPException(404, f"Unknown task kind {kind!r}. Use one of {list(TASK_KINDS)}.")
    with _state_lock:
        t = _tasks.get(f"{kind}:{jd_id}")
        if not t:
            return {
                "kind": kind,
                "status": "idle",
                "error": None,
                "elapsed_seconds": None,
                "stage": "IDLE",
                "stage_label": "Idle",
                "progress_percent": 0,
            }
        end = t["finished_at"] if t["finished_at"] else time.time()
        return {
            "kind": kind,
            "status": t["status"],
            "error": t["error"],
            "elapsed_seconds": round(end - t["started_at"], 1),
            "stage": t.get("stage", "RUNNING" if t["status"] == "running" else t["status"].upper()),
            "stage_label": t.get("stage_label", "In progress" if t["status"] == "running" else t["status"]),
            "progress_percent": t.get("progress_percent", 100 if t["status"] == "done" else (0 if t["status"] == "failed" else 50)),
        }


@router.post("/jds/{jd_id}/tasks/{kind}/cancel")
def cancel_task(jd_id: str, kind: str):
    """Cancel an in-flight background task (enrich | resolve)."""
    if kind not in TASK_KINDS:
        raise HTTPException(404, f"Unknown task kind {kind!r}")
    key = f"{kind}:{jd_id}"
    with _state_lock:
        t = _tasks.get(key)
        if t and t["status"] == "running":
            t.update(
                status="failed",
                error="Task was cancelled by user.",
                finished_at=time.time(),
                stage="CANCELLED",
                stage_label="Cancelled by user",
                progress_percent=0,
            )
            return {"kind": kind, "status": "cancelled", "message": f"{kind} task cancelled successfully"}
    return {"kind": kind, "status": "not_running", "message": f"{kind} task not running"}


def _get_spec_version(jd_id: str, db: Session, version: Optional[int] = None) -> JobSpecificationVersion:
    query = (
        db.query(JobSpecificationVersion)
        .join(JobDescriptionVersion)
        .filter(JobDescriptionVersion.job_description_id == jd_id)
    )
    if version is not None:
        spec = query.filter(JobSpecificationVersion.specification_version == version).first()
        if not spec:
            raise HTTPException(404, f"Specification version {version} not found")
        return spec
    spec = query.order_by(JobSpecificationVersion.specification_version.desc()).first()
    if not spec:
        raise HTTPException(404, "No specification generated yet")
    return spec


def _latest_spec_version(jd_id: str, db: Session) -> JobSpecificationVersion:
    return _get_spec_version(jd_id, db, version=None)


@router.get("/jds/{jd_id}/markdown")
def get_markdown(
    jd_id: str,
    enriched: Optional[bool] = None,
    version: Optional[int] = None,
    db: Session = Depends(get_db),
):
    spec_version = _get_spec_version(jd_id, db, version=version)
    has_enriched = bool(spec_version.s3_enriched_markdown_key)
    # Priority is ALWAYS Ollama enriched markdown first.
    # Only if Ollama is unavailable/failed (not has_enriched) or caller explicitly asked for enriched=False do we return baseline.
    if enriched is False:
        use_enriched = False
    else:
        use_enriched = has_enriched

    key = spec_version.s3_enriched_markdown_key if use_enriched else spec_version.s3_markdown_key
    return {
        "markdown": storage.get_text(key),
        "specification_version": spec_version.specification_version,
        "is_enriched": use_enriched,
    }


@router.get("/jds/{jd_id}/enrich")
def get_enrichment(jd_id: str, db: Session = Depends(get_db)):
    spec_version = _latest_spec_version(jd_id, db)
    if not spec_version.enrichment_report_json:
        raise HTTPException(404, "No enrichment report exists for this JD")
    return spec_version.enrichment_report_json


def _do_enrich(db: Session, jd_id: str) -> None:
    """The slow part of enrichment (Ollama). Runs in a background thread; raises HTTPException on failure."""
    task_key = f"enrich:{jd_id}"
    _update_task_progress(task_key, "CHECKING_SERVICE", "Checking enrichment engine availability", 20)

    spec_version = _latest_spec_version(jd_id, db)
    jd = db.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(404, "JD not found")

    from app.services.enrichment import OllamaUnavailableError
    from app.services.enrichment.ta_enrichment_service import get_enrichment_service

    enricher = get_enrichment_service()
    if not enricher.check_ollama_available():
        raise HTTPException(
            status_code=503,
            detail="Ollama service is unavailable or target model is missing. Start Ollama and try again.",
        )

    requirements_to_enrich = []
    if spec_version.master_context_json and "requirements" in spec_version.master_context_json:
        mc_resps = {
            r.get("raw_statement", "").strip().lower()
            for r in spec_version.master_context_json.get("responsibilities", [])
            if r.get("raw_statement")
        }
        for req in spec_version.master_context_json["requirements"]:
            txt = (req.get("text") or "").strip()
            sec = req.get("source", {}).get("section", "") if isinstance(req.get("source"), dict) else ""
            ctype = str(req.get("clause_type") or "").lower()
            if (
                ctype != "responsibility"
                and sec not in ("responsibilities", "duties", "deliverables", "key_responsibilities", "expected_deliverables")
                and txt.lower() not in mc_resps
            ):
                requirements_to_enrich.append({
                    "requirement_id": req.get("id"),
                    "text": req.get("text"),
                    "priority": req.get("priority", "MUST_HAVE"),
                })
    elif spec_version.canonical_json and "evidence_requirements" in spec_version.canonical_json:
        for ev in spec_version.canonical_json["evidence_requirements"]:
            requirements_to_enrich.append({
                "requirement_id": ev.get("requirement_id"),
                "text": ev.get("requirement"),
                "priority": ev.get("priority", "MUST_HAVE"),
            })

    checksum_val = (
        spec_version.jd_version.raw_text_checksum
        if spec_version.jd_version
        else "unknown_checksum"
    )

    clarification_context = []
    role_context = {}
    if spec_version.master_context_json:
        mc = spec_version.master_context_json
        for q in mc.get("clarification_history", []):
            if q.get("status") == "ANSWERED" and q.get("answer_text"):
                clarification_context.append({
                    "question_key": q.get("question_key"),
                    "question_text": q.get("question_text"),
                    "answer_text": q.get("answer_text"),
                    "answered_by": q.get("answered_by", "TA"),
                })
        ro = mc.get("role_overview", {})
        jc = mc.get("job_context", {})
        loc = (mc.get("conventional_requirements") or {}).get("location", {})
        role_context = {
            "role_title": ro.get("job_title") or ro.get("title", ""),
            "team_size": jc.get("team_size"),
            "salary_range": jc.get("salary_range"),
            "work_mode": loc.get("work_mode"),
        }

    raw_jd = ""
    if spec_version.jd_version and spec_version.jd_version.s3_raw_key:
        try:
            raw_jd = storage.get_text(spec_version.jd_version.s3_raw_key)
        except Exception:
            raw_jd = ""

    try:
        report = enricher.generate_enrichment_report(
            spec_version_id=str(spec_version.id),
            specification_version=spec_version.specification_version,
            source_checksum=checksum_val,
            requirements=requirements_to_enrich,
            clarification_context=clarification_context,
            role_context=role_context,
            raw_jd_text=raw_jd,
        )
    except OllamaUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Enrichment generation failed for jd_id=%s", jd_id)
        raise HTTPException(status_code=500, detail=f"Enrichment failed: {exc}")

    # Generate and save enriched markdown without mutating baseline artifacts
    from app.schemas.canonical import JobEvaluationSpecification
    spec = JobEvaluationSpecification.model_validate(spec_version.canonical_json)
    enriched_md = render_markdown(spec, enrichment_report=report)

    enriched_key = build_key(str(jd.project_id), jd_id, spec_version.specification_version, "enriched_markdown")
    storage.put_text(enriched_key, enriched_md, "text/markdown")

    spec_version.enrichment_report_json = report.model_dump(mode="json")
    spec_version.s3_enriched_markdown_key = enriched_key
    db.commit()


@router.post("/jds/{jd_id}/enrich", status_code=202)
def enrich_jd(jd_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Returns immediately. Poll GET /jds/{id}/tasks/enrich, then GET /jds/{id}/markdown?enriched=true."""
    _latest_spec_version(jd_id, db)            # 404 fast if nothing to enrich
    if not db.get(JobDescription, jd_id):
        raise HTTPException(404, "JD not found")
    return _start_task("enrich", jd_id, background_tasks, _do_enrich)


class ResolveClarificationsRequest(BaseModel):
    answers: Dict[str, Any] = Field(default_factory=dict)
    answered_by: Optional[str] = "TA / Hiring Team"


def _do_resolve(db: Session, jd_id: str, answers: Dict[str, Any], answered_by: str) -> None:
    """Apply TA answers, build the next specification version (incl. the slow Ollama refinement)."""
    task_key = f"resolve:{jd_id}"
    _update_task_progress(task_key, "APPLYING_ANSWERS", "Applying TA answers to requirements", 25)

    spec_version = _latest_spec_version(jd_id, db)
    jd = db.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(404, "JD not found")

    if not spec_version.master_context_json:
        raise HTTPException(400, "No master context available to resolve clarifications")

    from app.schemas.master_context import JDMasterContext, QuestionStatus, JDLifecycleStatus
    from app.models.db_models import JDLifecycleStatusEnum
    from app.services.clarification.updater import submit_answer, attempt_finalization
    from app.services.projection.canonical_projector import project_to_canonical

    master = JDMasterContext.model_validate(spec_version.master_context_json)

    canonical_ambs = (spec_version.canonical_json or {}).get("ambiguities", [])

    # Apply answers to master context
    for q_key, ans_text in answers.items():
        if not ans_text:
            continue
        text_str = str(ans_text).strip()
        if not text_str:
            continue

        matched_statement = None
        if q_key.startswith("amb_"):
            try:
                idx = int(q_key.replace("amb_", ""))
                if idx < len(canonical_ambs):
                    matched_statement = canonical_ambs[idx].get("statement")
            except Exception:
                pass
        elif q_key.startswith("statement:"):
            matched_statement = q_key.replace("statement:", "").strip()

        try:
            master = submit_answer(
                master,
                question_key=q_key,
                answer_text=text_str,
                answered_by=answered_by,
                status=QuestionStatus.ANSWERED,
                target_statement=matched_statement,
            )
        except Exception as exc:
            logger.warning("Could not submit answer for question %s: %s", q_key, exc)

    # Attempt finalization
    try:
        master = attempt_finalization(master, actor=answered_by)
    except Exception as exc:
        logger.info("Finalization deferred: %s", exc)

    _update_task_progress(task_key, "UPDATING_CONTEXT", "Updating master domain context and provenance records", 45)

    next_version = spec_version.specification_version + 1
    _update_task_progress(task_key, "PROJECTING_SPEC", f"Projecting canonical specification v{next_version}", 65)

    new_spec = project_to_canonical(
        master,
        jd_id=jd_id,
        specification_version=next_version,
    )
    new_spec.metadata.prompt_version = "clarification_resolved_v1"
    new_spec.metadata.model_version = "deterministic_ekg"

    # Pass original JD, initial analysis, deterministic extraction results,
    # and updated clarification context back to Ollama to generate the final, refined Markdown.
    from app.schemas.enrichment import TAEnrichmentReport
    from app.services.enrichment.ta_enrichment_service import get_enrichment_service
    from app.services.projection.canonical_projector import _flatten_requirements

    clarification_context = [
        {
            "question_key": q.question_key,
            "question_text": q.question_text,
            "answer_text": q.answer_text,
            "answered_by": q.answered_by or answered_by,
        }
        for q in master.clarification_history
        if q.status == QuestionStatus.ANSWERED and q.answer_text
    ]

    raw_jd = ""
    if spec_version.jd_version and spec_version.jd_version.s3_raw_key:
        try:
            raw_jd = storage.get_text(spec_version.jd_version.s3_raw_key)
        except Exception:
            raw_jd = ""

    role_context = {
        "role_title": getattr(master.role_overview, "job_title", None) or getattr(master.role_overview, "title", None) or (new_spec.role.job_title if hasattr(new_spec, "role") and new_spec.role else ""),
        "team_size": master.job_context.team_size,
        "salary_range": getattr(master.job_context, "salary_range", None),
        "work_mode": getattr(master.role_overview, "work_mode", "UNSPECIFIED"),
    }

    resp_descs = {
        (r.raw_statement if hasattr(r, "raw_statement") else str(r)).strip().lower()
        for r in master.responsibilities
        if getattr(r, "raw_statement", None)
    }
    flat_reqs = _flatten_requirements(master.requirements)
    reqs = [
        {
            "requirement_id": r.id,
            "text": r.text,
            "priority": r.priority.value if hasattr(r.priority, "value") else str(r.priority or "MUST_HAVE"),
        }
        for r in flat_reqs
        if getattr(r, "text", None)
        and getattr(getattr(r, "clause_type", None), "value", str(getattr(r, "clause_type", ""))) != "responsibility"
        and (not r.source or getattr(r.source, "section", "") not in (
            "responsibilities", "duties", "deliverables", "key_responsibilities", "expected_deliverables"
        ))
        and r.text.strip().lower() not in resp_descs
    ]

    enrichment_report = None
    enriched_md = None
    enriched_key = None

    enricher = get_enrichment_service()
    if enricher.check_ollama_available():
        try:
            if reqs:
                enrichment_report = enricher.generate_enrichment_report(
                    spec_version_id=str(spec_version.id),
                    specification_version=next_version,
                    source_checksum=spec_version.jd_version.raw_text_checksum if spec_version.jd_version else "unknown",
                    requirements=reqs,
                    clarification_context=clarification_context,
                    role_context=role_context,
                    raw_jd_text=raw_jd,
                )
                enriched_md = render_markdown(new_spec, enrichment_report=enrichment_report)
        except Exception as exc:
            logger.warning("Ollama final refinement failed; falling back to deterministic baseline: %s", exc)
            enrichment_report = None
            enriched_md = None

    # Fallback to existing enrichment report if available and Ollama was unavailable
    if enriched_md is None and spec_version.enrichment_report_json:
        try:
            enrichment_report = TAEnrichmentReport.model_validate(spec_version.enrichment_report_json)
            enrichment_report.source_specification_version = next_version
            enriched_md = render_markdown(new_spec, enrichment_report=enrichment_report)
        except Exception as exc:
            logger.warning("Could not apply carried-forward enrichment report: %s", exc)

    _update_task_progress(task_key, "PERSISTING", f"Saving resolved specification artifacts v{next_version}", 95)
    base_md = render_markdown(new_spec)
    json_str = to_json_str(new_spec)

    project_id = str(jd.project_id)
    json_key = build_key(project_id, jd_id, next_version, "json")
    md_key = build_key(project_id, jd_id, next_version, "markdown")
    storage.put_text(json_key, json_str, "application/json")
    storage.put_text(md_key, base_md, "text/markdown")

    if enriched_md:
        enriched_key = build_key(project_id, jd_id, next_version, "enriched_markdown")
        storage.put_text(enriched_key, enriched_md, "text/markdown")

    new_spec_version = JobSpecificationVersion(
        job_description_version_id=spec_version.job_description_version_id,
        specification_version=next_version,
        parent_specification_version_id=spec_version.id,
        s3_json_key=json_key,
        s3_markdown_key=md_key,
        canonical_json=json.loads(json_str),
        master_context_json=master.model_dump(mode="json"),
        enrichment_report_json=enrichment_report.model_dump(mode="json") if enrichment_report else None,
        s3_enriched_markdown_key=enriched_key,
        lifecycle_status=JDLifecycleStatusEnum.FINALIZED if master.lifecycle_status == JDLifecycleStatus.FINALIZED else JDLifecycleStatusEnum.ANALYZED,
        prompt_version="clarification_resolved_v1",
        model_version="deterministic_ekg",
        input_tokens=0,
        output_tokens=0,
        latency_ms=0,
        estimated_cost_usd=0,
        is_valid=True,
        needs_review=False,
    )
    db.add(new_spec_version)
    db.commit()


@router.post("/jds/{jd_id}/clarifications/resolve", status_code=202)
def resolve_clarifications(
    jd_id: str,
    payload: ResolveClarificationsRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Returns immediately. Poll GET /jds/{id}/tasks/resolve; when it is "done" fetch
    GET /jds/{id}/markdown, /json and /clarifications (the new version is the latest).
    """
    spec_version = _latest_spec_version(jd_id, db)
    if not db.get(JobDescription, jd_id):
        raise HTTPException(404, "JD not found")
    if not spec_version.master_context_json:
        raise HTTPException(400, "No master context available to resolve clarifications")
    return _start_task(
        "resolve", jd_id, background_tasks, _do_resolve,
        dict(payload.answers), payload.answered_by or "TA / Hiring Team",
    )


@router.get("/jds/{jd_id}/json")
def get_json(jd_id: str, version: Optional[int] = None, db: Session = Depends(get_db)):
    spec_version = _get_spec_version(jd_id, db, version=version)
    return {"json": spec_version.canonical_json, "specification_version": spec_version.specification_version}


@router.get("/jds/{jd_id}/compare")
@router.get("/jds/{jd_id}/comparison")
def compare_jd_contexts(
    jd_id: str,
    base: str = "baseline",
    target: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Compare Baseline, Enriched, and Ambiguity-Resolved JD contexts.
    Returns added, removed, modified, and unchanged requirements with source evidence
    and TA-confirmed facts clearly distinguished, plus resolved and unresolved ambiguities.
    """
    from app.services.comparison_service import build_comparison_payload
    return build_comparison_payload(jd_id, db, base_context=base, target_context=target)


@router.post("/jds/{jd_id}/markdown-to-json")
def markdown_to_json_endpoint(jd_id: str, markdown: str = Form(...)):
    result = markdown_to_spec(markdown)
    spec_dict = to_json_dict(result.spec)
    _validated, report = validate_payload(spec_dict)
    return {
        "json": spec_dict,
        "parse_warnings": result.warnings,
        "validation": {
            "valid": report.valid,
            "issues": [{"field": i.field, "message": i.message, "severity": i.severity} for i in report.issues],
        },
    }


@router.post("/jds/{jd_id}/json-to-markdown")
def json_to_markdown_endpoint(jd_id: str, payload: dict):
    from app.schemas.canonical import JobEvaluationSpecification

    spec = JobEvaluationSpecification.model_validate(payload)
    return {"markdown": render_markdown(spec)}


@router.get("/jds/{jd_id}/versions")
def get_versions(jd_id: str, db: Session = Depends(get_db)):
    versions = (
        db.query(JobSpecificationVersion)
        .join(JobDescriptionVersion)
        .filter(JobDescriptionVersion.job_description_id == jd_id)
        .order_by(JobSpecificationVersion.created_at.asc())
        .all()
    )
    return [
        {
            "specification_version": v.specification_version,
            "prompt_version": v.prompt_version,
            "model_version": v.model_version,
            "is_valid": v.is_valid,
            "needs_review": v.needs_review,
            "created_at": v.created_at,
        }
        for v in versions
    ]


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = ""

    @field_validator("content", mode="before")
    @classmethod
    def _trim(cls, v):
        # Truncate instead of rejecting: a long earlier answer must never break the next question.
        return str(v or "")[:1500]


class ChatRequest(BaseModel):
    question: str = Field(..., max_length=2000)
    markdown: Optional[str] = Field(None, max_length=200_000)
    history: List[ChatTurn] = Field(default_factory=list, max_length=12)


def _answer(markdown: str, question: str, history: List[ChatTurn], raw_jd: Optional[str]) -> str:
    llm = _get_llm()
    # A local model serves one request at a time; chat would queue behind a multi-minute LLM job.
    if llm.provider == "ollama" and _any_llm_job_running():
        raise HTTPException(503, "A job description is being processed right now. Chat will be available when it finishes.")
    try:
        return llm.chat_with_jd_context(
            markdown_context=markdown,
            question=question.strip(),
            history=[t.model_dump() for t in history],
            raw_jd=raw_jd,
        )
    except RuntimeError as exc:
        logger.error("Chat failed: %s", exc)
        raise HTTPException(503, f"The language model is unavailable: {exc}")


@router.post("/jds/{jd_id}/chat")
def chat_jd(jd_id: str, request: ChatRequest, db: Session = Depends(get_db)):
    if not request.question.strip():
        raise HTTPException(400, "Question is empty")

    jd_version = (
        db.query(JobDescriptionVersion)
        .filter(JobDescriptionVersion.job_description_id == jd_id)
        .order_by(JobDescriptionVersion.version.desc())
        .first()
    )
    raw_jd: Optional[str] = None
    if jd_version:
        try:
            raw_jd = storage.get_text(jd_version.s3_raw_key)
        except Exception:  # noqa: BLE001
            logger.warning("Could not load raw JD for jd_id=%s", jd_id)

    markdown_content = request.markdown
    if not markdown_content:
        try:
            latest_spec = _latest_spec_version(jd_id, db)
            spec_key = latest_spec.s3_enriched_markdown_key if latest_spec.s3_enriched_markdown_key else latest_spec.s3_markdown_key
            markdown_content = storage.get_text(spec_key)
        except HTTPException:
            markdown_content = raw_jd  # not analyzed yet: answer from the raw JD

    if not markdown_content:
        raise HTTPException(400, "No JD context found for this job description.")

    return {"answer": _answer(markdown_content, request.question, request.history, raw_jd), "jd_id": jd_id}


@router.post("/chat")
def chat_direct(request: ChatRequest):
    if not request.question.strip():
        raise HTTPException(400, "Question is empty")
    if not request.markdown or not request.markdown.strip():
        raise HTTPException(400, "Markdown context is empty")
    return {"answer": _answer(request.markdown, request.question, request.history, None)}


# ===========================================================================
# INTERN 2 TRACK — New JD Lifecycle & Clarification Endpoints
# ===========================================================================
#
# These endpoints operate against JDMasterContext (the authoritative domain
# model). They do not depend on LLM; all logic is deterministic.
#
# Routes:
#   GET  /api/jds/{jd_id}/master-context     - Full JDMasterContext (rich internal state)
#   GET  /api/jds/{jd_id}/clarifications     - Clarification questions (with optional filter)
#   POST /api/jds/{jd_id}/clarifications     - Submit TA answer / skip
#   POST /api/jds/{jd_id}/finalize           - Finalize the JD (revalidation gate)
#   POST /api/jds/{jd_id}/grounded-chat      - Deterministic grounded Q&A
# ===========================================================================

from typing import Dict as _Dict, Union as _Union

from app.models.db_models import JDLifecycleStatusEnum as _JDLifecycleStatusEnum
from app.schemas.master_context import (
    ConfidenceBand as _ConfidenceBand,
    ConfidenceBreakdown as _ConfidenceBreakdown,
    DisjunctionGroup as _DisjunctionGroup,
    JDMasterContext as _JDMasterContext,
    JobContextInfo as _JobContextInfo,
    OriginType as _OriginType,
    ProvenanceRecord as _ProvenanceRecord,
    QuestionStatus as _QuestionStatus,
    RequirementPriority as _RequirementPriority,
    ResponsibilityContext as _ResponsibilityContext,
    RoleOverview as _RoleOverview,
    SourceSpan as _SourceSpan,
    StructuredRequirement as _StructuredRequirement,
)
from app.services.clarification.engine import generate_clarification_questions as _generate_clarification_questions
from app.services.clarification.updater import (
    ClarificationUpdateError,
    submit_answer as _submit_answer,
    attempt_finalization as _attempt_finalization,
)
from app.services.query_engine import answer_query as _answer_query


class _ClarificationAnswerRequest(BaseModel):
    question_key: str = Field(..., description="The stable question_key of the question to answer.")
    answer_text: str = Field("", description="TA answer text. Required when status=ANSWERED.")
    status: str = Field("ANSWERED", description="One of: ANSWERED, SKIPPED, EXPLICITLY_UNSPECIFIED")
    answered_by: str = Field("ta_reviewer", description="User ID of the answerer.")
    override_record: Optional[Dict] = Field(
        None,
        description="Required for BLOCKING+SKIPPED: {authorized_by, override_reason, timestamp}",
    )


class _FinalizeRequest(BaseModel):
    actor: Optional[str] = Field(None, description="User ID performing the finalization.")


class _GroundedChatRequest(BaseModel):
    question: str = Field(..., description="Natural language question about this JD.")


def _master_context_from_canonical(jd_id: str, canonical_dict: dict, raw_jd_text: str = "") -> _JDMasterContext:
    """Build a JDMasterContext from canonical_json when master context was not pre-populated."""
    role_dict = canonical_dict.get("role", {}) or {}
    job_ctx_dict = canonical_dict.get("job_context", {}) or {}
    conv_reqs = canonical_dict.get("conventional_requirements", {}) or {}
    loc_dict = conv_reqs.get("location", {}) or {}

    role_overview = _RoleOverview(
        job_title=role_dict.get("job_title") or "",
        seniority=role_dict.get("seniority"),
        department=role_dict.get("department"),
        location_city=loc_dict.get("city"),
        location_country=loc_dict.get("country"),
        work_mode=str(loc_dict.get("work_mode", "UNSPECIFIED")).upper(),
    )
    job_context = _JobContextInfo(
        company_context=job_ctx_dict.get("company_context"),
        business_context=job_ctx_dict.get("business_context"),
        environment=job_ctx_dict.get("environment"),
        team_size=job_ctx_dict.get("team_size"),
    )
    reqs: List[_Union[_StructuredRequirement, _DisjunctionGroup]] = []
    for item in canonical_dict.get("must_have_requirements", []) or []:
        reqs.append(
            _StructuredRequirement(
                text=item,
                priority=_RequirementPriority.MUST_HAVE,
                is_mandatory=True,
                provenance=_ProvenanceRecord(origin_type=_OriginType.EXPLICIT_JD, author="extractor"),
            )
        )
    for item in canonical_dict.get("preferred_requirements", []) or []:
        reqs.append(
            _StructuredRequirement(
                text=item,
                priority=_RequirementPriority.PREFERRED,
                is_mandatory=False,
                provenance=_ProvenanceRecord(origin_type=_OriginType.EXPLICIT_JD, author="extractor"),
            )
        )
    resps: List[_ResponsibilityContext] = []
    for r in canonical_dict.get("responsibilities", []) or []:
        statement = r.get("description", "") if isinstance(r, dict) else str(r)
        if statement:
            resps.append(
                _ResponsibilityContext(
                    raw_statement=statement,
                    source_span=_SourceSpan(raw_text=statement, section="Responsibilities"),
                )
            )

    master = _JDMasterContext(
        jd_id=jd_id,
        raw_jd_text=raw_jd_text or "",
        role_overview=role_overview,
        job_context=job_context,
        requirements=reqs,
        responsibilities=resps,
    )
    _generate_clarification_questions(master)
    return master


def _get_spec_version_row(jd_id: str, db: Session) -> JobSpecificationVersion:
    spec_version = (
        db.query(JobSpecificationVersion)
        .join(JobDescriptionVersion, JobSpecificationVersion.job_description_version_id == JobDescriptionVersion.id)
        .join(JobDescription, JobDescriptionVersion.job_description_id == JobDescription.id)
        .filter(JobDescription.id == jd_id)
        .order_by(JobSpecificationVersion.created_at.desc())
        .first()
    )
    if spec_version:
        return spec_version

    # Check if JobDescriptionVersion exists (uploaded but not analyzed)
    jd_version = (
        db.query(JobDescriptionVersion)
        .join(JobDescription, JobDescriptionVersion.job_description_id == JobDescription.id)
        .filter(JobDescription.id == jd_id)
        .order_by(JobDescriptionVersion.version.desc())
        .first()
    )
    if not jd_version:
        raise HTTPException(404, f"No job description found for jd_id={jd_id!r}.")

    # Auto-initialize initial spec_version and master context
    raw_jd = ""
    try:
        raw_jd = storage.get_text(jd_version.s3_raw_key)
    except Exception:
        pass

    project_id = "unknown"
    json_key = build_key(project_id, str(jd_id), jd_version.version, "json")
    md_key = build_key(project_id, str(jd_id), jd_version.version, "markdown")

    master = _master_context_from_canonical(jd_id, {}, raw_jd)
    from app.services.projection.canonical_projector import project_to_canonical
    spec = project_to_canonical(master)
    json_dict = to_json_dict(spec)
    markdown = render_markdown(spec)

    storage.put_text(json_key, json.dumps(json_dict), "application/json")
    storage.put_text(md_key, markdown, "text/markdown")

    spec_version = JobSpecificationVersion(
        job_description_version_id=jd_version.id,
        specification_version=1,
        s3_json_key=json_key,
        s3_markdown_key=md_key,
        canonical_json=json_dict,
        prompt_version="v1",
        model_version="deterministic-init",
        master_context_json=master.model_dump(mode="json"),
        lifecycle_status=_JDLifecycleStatusEnum(master.lifecycle_status.value),
        input_tokens=0,
        output_tokens=0,
        latency_ms=0,
        estimated_cost_usd=0,
        is_valid=True,
        needs_review=False,
    )
    db.add(spec_version)
    db.commit()
    db.refresh(spec_version)
    return spec_version


def _load_master_context(jd_id: str, db: Session) -> _JDMasterContext:
    spec_version = _get_spec_version_row(jd_id, db)
    if spec_version.master_context_json:
        return _JDMasterContext.model_validate(spec_version.master_context_json)

    # Dynamic fallback: build master context from canonical_json
    raw_jd = ""
    try:
        raw_jd = storage.get_text(spec_version.jd_version.s3_raw_key)
    except Exception:
        pass

    master = _master_context_from_canonical(jd_id, spec_version.canonical_json or {}, raw_jd)
    _save_master_context(spec_version, master, db)
    return master


def _save_master_context(spec_version: JobSpecificationVersion, master: _JDMasterContext, db: Session) -> None:
    spec_version.master_context_json = master.model_dump(mode="json")
    spec_version.lifecycle_status = _JDLifecycleStatusEnum(master.lifecycle_status.value)
    db.commit()


@router.get("/jds/{jd_id}/master-context", summary="Get full JDMasterContext")
def get_master_context(jd_id: str, db: Session = Depends(get_db)):
    """
    Returns the full JDMasterContext — the authoritative lossless domain model.
    Includes all requirements, responsibilities, clarification history, audit trail, etc.
    """
    master = _load_master_context(jd_id, db)
    return master.model_dump(mode="json")


@router.get("/jds/{jd_id}/clarifications", summary="Get clarification questions")
def get_clarifications(
    jd_id: str,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Returns clarification questions. Optional query params: status, priority.
    """
    spec_version = _get_spec_version_row(jd_id, db)
    master = _load_master_context(jd_id, db)
    questions = master.clarification_history
    if status:
        questions = [q for q in questions if q.status.value.upper() == status.upper()]
    if priority:
        questions = [q for q in questions if q.priority.value.upper() == priority.upper()]

    canonical = spec_version.canonical_json or {}
    ambiguities = canonical.get("ambiguities", [])
    missing_info = canonical.get("missing_information", [])

    return {
        "jd_id": jd_id,
        "lifecycle_status": master.lifecycle_status.value,
        "total_questions": len(master.clarification_history),
        "blocking_unresolved": len(master.unresolved_blocking_questions),
        "is_ready_to_finalize": master.is_ready_to_finalize,
        "questions": [q.model_dump(mode="json") for q in questions],
        "ambiguities": ambiguities,
        "missing_information": missing_info,
        "has_ambiguities": bool(questions or ambiguities or missing_info),
        "specification_version": spec_version.specification_version,
    }


@router.post("/jds/{jd_id}/clarifications", summary="Submit TA answer to a clarification question")
def submit_clarification_answer(
    jd_id: str,
    request: _ClarificationAnswerRequest,
    db: Session = Depends(get_db),
):
    """
    Submit a TA answer, skip, or explicit-unspecified for a clarification question.
    BLOCKING questions cannot be SKIPPED without an override_record.
    """
    try:
        question_status = _QuestionStatus(request.status)
    except ValueError:
        raise HTTPException(400, f"Invalid status {request.status!r}. Use ANSWERED, SKIPPED, or EXPLICITLY_UNSPECIFIED.")

    spec_version = _get_spec_version_row(jd_id, db)
    master = _load_master_context(jd_id, db)

    try:
        master = _submit_answer(
            master,
            question_key=request.question_key,
            answer_text=request.answer_text,
            answered_by=request.answered_by,
            status=question_status,
            override_record=request.override_record,
        )
    except ClarificationUpdateError as exc:
        raise HTTPException(400, str(exc))

    _save_master_context(spec_version, master, db)
    return {
        "jd_id": jd_id,
        "question_key": request.question_key,
        "new_status": request.status,
        "lifecycle_status": master.lifecycle_status.value,
        "blocking_unresolved": len(master.unresolved_blocking_questions),
        "is_ready_to_finalize": master.is_ready_to_finalize,
        "message": f"Answer submitted. Lifecycle is now {master.lifecycle_status.value}.",
    }


@router.post("/jds/{jd_id}/finalize", summary="Finalize the JD")
def finalize_jd(
    jd_id: str,
    request: _FinalizeRequest,
    db: Session = Depends(get_db),
):
    """
    Finalize the JD. Returns HTTP 400 if any BLOCKING question is unresolved.
    On success, locks lifecycle_status=FINALIZED and seals finalized_at.
    """
    spec_version = _get_spec_version_row(jd_id, db)
    master = _load_master_context(jd_id, db)

    try:
        master = _attempt_finalization(master, actor=request.actor)
    except ClarificationUpdateError as exc:
        raise HTTPException(400, str(exc))

    _save_master_context(spec_version, master, db)
    return {
        "jd_id": jd_id,
        "lifecycle_status": master.lifecycle_status.value,
        "version": master.version,
        "finalized_at": master.finalized_at.isoformat() if master.finalized_at else None,
        "must_have_count": len(master.must_have_requirements),
        "message": f"JD {jd_id!r} finalized at version {master.version}.",
    }


@router.post("/jds/{jd_id}/grounded-chat", summary="Grounded deterministic Q&A about a JD")
def grounded_chat(
    jd_id: str,
    request: _GroundedChatRequest,
    db: Session = Depends(get_db),
):
    """
    Answer a natural language question about the JD using the deterministic
    grounded query engine. Zero LLM calls. Zero fabrication.
    All answers include provenance labels.
    """
    if not request.question.strip():
        raise HTTPException(400, "Question is empty.")
    master = _load_master_context(jd_id, db)
    result = _answer_query(master, request.question)
    return {
        "jd_id": jd_id,
        "query": result.query,
        "query_type": result.query_type,
        "fabricated": result.fabricated,
        "summary": result.summary,
        "answers": [
            {
                "text": a.text,
                "provenance_label": a.provenance_label,
                "section": a.section,
                "source_quote": a.source_quote,
            }
            for a in result.answers
        ],
    }

# ===========================================================================
# Agent Management & Lifecycle (CRUD)
# ===========================================================================


class AgentCreateRequest(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    agentName: Optional[str] = None
    title: Optional[str] = ""
    company_name: Optional[str] = None
    department: Optional[str] = None
    project_name: Optional[str] = None
    companyDetails: Optional[Dict[str, Any]] = None
    job_description_id: Optional[str] = None
    jdId: Optional[str] = None
    status: Optional[str] = "ACTIVE"


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    agentName: Optional[str] = None
    title: Optional[str] = None
    company_name: Optional[str] = None
    department: Optional[str] = None
    project_name: Optional[str] = None
    companyDetails: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


def _serialize_agent(agent: Agent, db: Session) -> Dict[str, Any]:
    jd_id = str(agent.job_description_id)
    md_content = ""
    json_content: Dict[str, Any] = {}
    spec_ver = 1
    jd_text = ""

    try:
        spec = _latest_spec_version(jd_id, db)
        if spec:
            spec_ver = spec.specification_version
            key = spec.s3_enriched_markdown_key if spec.s3_enriched_markdown_key else spec.s3_markdown_key
            if key:
                try:
                    md_content = storage.get_text(key) or ""
                except Exception:
                    md_content = ""
            if spec.canonical_json:
                json_content = spec.canonical_json
    except Exception:
        pass

    try:
        latest_jd_v = (
            db.query(JobDescriptionVersion)
            .filter(JobDescriptionVersion.job_description_id == jd_id)
            .order_by(JobDescriptionVersion.version.desc())
            .first()
        )
        if latest_jd_v and latest_jd_v.s3_raw_key:
            try:
                jd_text = storage.get_text(latest_jd_v.s3_raw_key) or ""
            except Exception:
                jd_text = ""
    except Exception:
        pass

    created_str = agent.created_at.isoformat() if agent.created_at else ""
    updated_str = agent.updated_at.isoformat() if agent.updated_at else created_str

    comp_details = {
        "companyName": agent.company_name or "",
        "department": agent.department or "",
        "projectName": agent.project_name or "",
    }

    return {
        "id": agent.id,
        "name": agent.name,
        "agentName": agent.name,
        "title": agent.title or "",
        "company_name": agent.company_name or "",
        "department": agent.department or "",
        "project_name": agent.project_name or "",
        "companyDetails": comp_details,
        "job_description_id": jd_id,
        "jdId": jd_id,
        "jdText": jd_text,
        "markdown": md_content,
        "jsonData": json_content,
        "specificationVersion": spec_ver,
        "status": agent.status,
        "createdAt": created_str,
        "updatedAt": updated_str,
        "created_at": created_str,
        "updated_at": updated_str,
    }


@router.get("/agents", summary="List all created Agents")
def list_agents(db: Session = Depends(get_db)):
    """List all created agents with their latest specification version and configuration."""
    agents = db.query(Agent).order_by(Agent.created_at.desc()).all()
    return [_serialize_agent(a, db) for a in agents]


@router.get("/agents/{agent_id}", summary="Get an Agent by ID")
def get_agent(agent_id: str, db: Session = Depends(get_db)):
    """Get single agent details by ID."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found.")
    return _serialize_agent(agent, db)


@router.post("/agents", summary="Create or register an Agent for a Job Description")
def create_agent(request: AgentCreateRequest, db: Session = Depends(get_db)):
    """
    Create a new agent or register an existing one for a Job Description.
    Validates that the JD exists and records an AuditEvent.
    """
    jd_id = request.job_description_id or request.jdId
    if not jd_id:
        raise HTTPException(400, "job_description_id (or jdId) is required.")

    jd = db.query(JobDescription).filter(JobDescription.id == jd_id).first()
    if not jd:
        raise HTTPException(404, f"Job description '{jd_id}' not found.")

    agent_name = (request.name or request.agentName or "").strip()
    if not agent_name:
        agent_name = f"{request.title or 'JD'} Agent".strip()

    cd = request.companyDetails or {}
    company_name = request.company_name or cd.get("companyName") or ""
    department = request.department or cd.get("department") or ""
    project_name = request.project_name or cd.get("projectName") or ""

    agent_id = request.id or gen_uuid()
    existing = db.query(Agent).filter(Agent.id == agent_id).first()
    if existing:
        existing.name = agent_name
        existing.title = request.title or existing.title
        existing.company_name = company_name or existing.company_name
        existing.department = department or existing.department
        existing.project_name = project_name or existing.project_name
        existing.status = request.status or existing.status
        agent = existing
        action = "updated"
    else:
        agent = Agent(
            id=agent_id,
            name=agent_name,
            title=request.title or "",
            company_name=company_name,
            department=department,
            project_name=project_name,
            job_description_id=jd_id,
            status=request.status or "ACTIVE",
        )
        db.add(agent)
        action = "created"

    audit = AuditEvent(
        entity_type="agent",
        entity_id=agent.id,
        action=action,
        details={
            "agent_name": agent.name,
            "job_description_id": str(agent.job_description_id),
        },
    )
    db.add(audit)
    db.commit()
    db.refresh(agent)
    return _serialize_agent(agent, db)


@router.patch("/agents/{agent_id}", summary="Update Agent metadata")
def update_agent(agent_id: str, request: AgentUpdateRequest, db: Session = Depends(get_db)):
    """Update Agent configuration and metadata without altering underlying JD data."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found.")

    if request.name is not None:
        agent.name = request.name
    elif request.agentName is not None:
        agent.name = request.agentName

    if request.title is not None:
        agent.title = request.title

    cd = request.companyDetails or {}
    if request.company_name is not None:
        agent.company_name = request.company_name
    elif "companyName" in cd:
        agent.company_name = cd["companyName"]

    if request.department is not None:
        agent.department = request.department
    elif "department" in cd:
        agent.department = cd["department"]

    if request.project_name is not None:
        agent.project_name = request.project_name
    elif "projectName" in cd:
        agent.project_name = cd["projectName"]

    if request.status is not None:
        agent.status = request.status

    audit = AuditEvent(
        entity_type="agent",
        entity_id=agent.id,
        action="updated",
        details={"agent_name": agent.name, "job_description_id": str(agent.job_description_id)},
    )
    db.add(audit)
    db.commit()
    db.refresh(agent)
    return _serialize_agent(agent, db)


@router.delete("/agents/{agent_id}", summary="Delete an Agent while preserving underlying JD records")
def delete_agent(
    agent_id: str,
    cancel_active: bool = False,
    db: Session = Depends(get_db),
):
    """
    Delete an agent while preserving all underlying JobDescription, JobDescriptionVersion,
    JobSpecificationVersion, and ClarificationQuestion records according to data-retention rules.

    If an analysis or enrichment task is active for this agent's JD:
      - Returns 409 Conflict if cancel_active=False.
      - Safely cancels active tasks and proceeds if cancel_active=True.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found.")

    jd_id = str(agent.job_description_id)
    agent_name = agent.name

    with _state_lock:
        is_analysis_running = jd_id in _inflight
        running_tasks = [
            k for k in TASK_KINDS
            if _tasks.get(f"{k}:{jd_id}", {}).get("status") == "running"
        ]
        is_active = is_analysis_running or bool(running_tasks)

    if is_active and not cancel_active:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot delete agent '{agent_name}' ({agent_id}) while operation is active "
                f"for JD {jd_id} (analysis={is_analysis_running}, tasks={running_tasks}). "
                f"Cancel active operations first or pass cancel_active=true."
            ),
        )

    if is_active and cancel_active:
        with _state_lock:
            if is_analysis_running:
                _inflight.pop(jd_id, None)
                _errors[jd_id] = "Analysis cancelled due to agent deletion."
            for task_kind in running_tasks:
                t = _tasks.get(f"{task_kind}:{jd_id}")
                if t and t["status"] == "running":
                    t.update(
                        status="failed",
                        error="Task cancelled due to agent deletion.",
                        finished_at=time.time(),
                        stage="CANCELLED",
                        stage_label="Cancelled due to agent deletion",
                        progress_percent=0,
                    )

    # Strictly delete only the agent record; JobDescription & JobSpecificationVersion are preserved
    db.delete(agent)

    audit = AuditEvent(
        entity_type="agent",
        entity_id=agent_id,
        action="deleted",
        details={
            "agent_name": agent_name,
            "job_description_id": jd_id,
            "cancelled_active_operations": is_active,
            "job_description_retained": True,
        },
    )
    db.add(audit)
    db.commit()

    return {
        "agent_id": agent_id,
        "status": "deleted",
        "message": f"Agent '{agent_name}' successfully deleted.",
        "job_description_retained": True,
        "job_description_id": jd_id,
        "cancelled_active_operations": is_active,
    }
