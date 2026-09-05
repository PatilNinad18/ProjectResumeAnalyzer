"""
REST API for the JD Understanding Agent.

Uploading/enqueuing (POST /jds, POST /jds/{id}/analyze) is intentionally
lightweight: the actual LLM work happens in the background worker so the
API never blocks on long-running LLM calls.
"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.db_models import (
    JobDescription,
    JobDescriptionVersion,
    JobSpecificationVersion,
    ProcessingJob,
    ProcessingStatusEnum,
)
from app.services.agent import JDUnderstandingAgent, JDUnderstandingError
from app.services.json_serializer import to_json_dict, to_json_str
from app.services.markdown_renderer import render_markdown
from app.services.markdown_to_json import markdown_to_spec
from app.services.storage import build_key, checksum, get_storage
from app.services.validation import validate_payload

router = APIRouter(prefix="/api", tags=["jds"])
storage = get_storage()


def _queue_processing(jd_version_id: str) -> None:
    """
    Enqueue via SQS in production. For local/dev/demo (and in this
    reference implementation's synchronous test paths) we fall back to
    running the pipeline inline through the same worker function, so the
    API contract is identical either way.
    """
    from app.db import SessionLocal
    from app.workers.worker import process_job_description_version

    db = SessionLocal()
    try:
        process_job_description_version(db, jd_version_id)
    finally:
        db.close()


@router.post("/jds")
def upload_jd(
    project_id: str = Form(...),
    title: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    if not file and not text:
        raise HTTPException(400, "Provide either a file or raw text.")
    raw_text = text or (file.file.read().decode("utf-8") if file else "")
    if not raw_text.strip():
        raise HTTPException(400, "JD content is empty.")

    jd = JobDescription(project_id=project_id, title=title, current_version=1)
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

    return {"jd_id": jd.id, "jd_version_id": jd_version.id, "version": 1, "status": "UPLOADED"}


@router.get("/jds/{jd_id}")
def get_jd(jd_id: str, db: Session = Depends(get_db)):
    jd = db.query(JobDescription).get(jd_id)
    if not jd:
        raise HTTPException(404, "JD not found")
    return {"jd_id": jd.id, "title": jd.title, "current_version": jd.current_version}


@router.post("/jds/{jd_id}/analyze")
def analyze_jd(jd_id: str, db: Session = Depends(get_db)):
    jd_version = (
        db.query(JobDescriptionVersion)
        .filter(JobDescriptionVersion.job_description_id == jd_id)
        .order_by(JobDescriptionVersion.version.desc())
        .first()
    )
    if not jd_version:
        raise HTTPException(404, "No JD version found")

    _queue_processing(jd_version.id)
    return {"jd_id": jd_id, "jd_version_id": jd_version.id, "status": "queued"}


@router.get("/jds/{jd_id}/analysis")
def get_analysis(jd_id: str, db: Session = Depends(get_db)):
    latest_job = (
        db.query(ProcessingJob)
        .join(JobDescriptionVersion)
        .filter(JobDescriptionVersion.job_description_id == jd_id)
        .order_by(ProcessingJob.created_at.desc())
        .first()
    )
    if not latest_job:
        raise HTTPException(404, "No processing job found")
    return {
        "status": latest_job.status.value if hasattr(latest_job.status, "value") else latest_job.status,
        "error_message": latest_job.error_message,
        "started_at": latest_job.started_at,
        "finished_at": latest_job.finished_at,
    }


def _latest_spec_version(jd_id: str, db: Session) -> JobSpecificationVersion:
    spec = (
        db.query(JobSpecificationVersion)
        .join(JobDescriptionVersion)
        .filter(JobDescriptionVersion.job_description_id == jd_id)
        .order_by(JobSpecificationVersion.created_at.desc())
        .first()
    )
    if not spec:
        raise HTTPException(404, "No specification generated yet")
    return spec


@router.get("/jds/{jd_id}/markdown")
def get_markdown(jd_id: str, db: Session = Depends(get_db)):
    spec_version = _latest_spec_version(jd_id, db)
    markdown = storage.get_text(spec_version.s3_markdown_key)
    return {"markdown": markdown, "specification_version": spec_version.specification_version}


@router.get("/jds/{jd_id}/json")
def get_json(jd_id: str, db: Session = Depends(get_db)):
    spec_version = _latest_spec_version(jd_id, db)
    return {"json": spec_version.canonical_json, "specification_version": spec_version.specification_version}


@router.post("/jds/{jd_id}/markdown-to-json")
def markdown_to_json_endpoint(jd_id: str, markdown: str = Form(...)):
    result = markdown_to_spec(markdown)
    spec_dict = to_json_dict(result.spec)
    validated_spec, report = validate_payload(spec_dict)
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


from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str
    markdown: Optional[str] = None


@router.post("/jds/{jd_id}/chat")
def chat_jd(jd_id: str, request: ChatRequest, db: Session = Depends(get_db)):
    if not request.question or not request.question.strip():
        raise HTTPException(400, "Question is empty")

    markdown_content = request.markdown
    if not markdown_content:
        try:
            spec_version = _latest_spec_version(jd_id, db)
            markdown_content = storage.get_text(spec_version.s3_markdown_key)
        except HTTPException:
            jd_version = (
                db.query(JobDescriptionVersion)
                .filter(JobDescriptionVersion.job_description_id == jd_id)
                .order_by(JobDescriptionVersion.version.desc())
                .first()
            )
            if jd_version:
                markdown_content = storage.get_text(jd_version.s3_raw_key)

    if not markdown_content:
        raise HTTPException(400, "No JD Markdown context found for this job description.")

    from app.services.llm_service import LLMService

    llm = LLMService()
    answer = llm.chat_with_jd_context(markdown_context=markdown_content, question=request.question)
    return {"answer": answer, "jd_id": jd_id}


@router.post("/chat")
def chat_direct(request: ChatRequest):
    if not request.question or not request.question.strip():
        raise HTTPException(400, "Question is empty")
    if not request.markdown or not request.markdown.strip():
        raise HTTPException(400, "Markdown context is empty")

    from app.services.llm_service import LLMService

    llm = LLMService()
    answer = llm.chat_with_jd_context(markdown_context=request.markdown, question=request.question)
    return {"answer": answer}

