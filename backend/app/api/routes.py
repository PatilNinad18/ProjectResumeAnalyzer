"""
REST API for the JD Understanding Agent.

POST /jds/{id}/analyze returns immediately (202). The LLM work runs in a
background task and the client polls GET /jds/{id}/analysis until the status is
READY / NEEDS_REVIEW / FAILED.

NOTE: in-flight tracking is in-process memory, which is correct for a single
uvicorn worker (local Ollama). For multi-worker production, replace
_inflight/_errors with a Redis key or a status column and use SQS/Celery
instead of BackgroundTasks.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.db_models import (
    JobDescription,
    JobDescriptionVersion,
    JobSpecificationVersion,
    ProcessingJob,
)
from app.services.document_parser import DocumentParseError, parse_document
from app.services.json_serializer import to_json_dict
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
_inflight: Dict[str, float] = {}   # jd_id -> start time
_errors: Dict[str, str] = {}       # jd_id -> last failure message


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
        return {"status": status, "error_message": None, "started_at": started,
                "finished_at": None, "elapsed_seconds": round(time.time() - started, 1)}

    # Crashed before the worker could record FAILED.
    if error:
        return {"status": "FAILED", "error_message": error, "started_at": None,
                "finished_at": None, "elapsed_seconds": None}

    if not latest_job:
        if not db.get(JobDescription, jd_id):
            raise HTTPException(404, "JD not found")
        return {"status": "UPLOADED", "error_message": None, "started_at": None,
                "finished_at": None, "elapsed_seconds": None}

    return {
        "status": _status_str(latest_job),
        "error_message": latest_job.error_message,
        "started_at": latest_job.started_at,
        "finished_at": latest_job.finished_at,
        "elapsed_seconds": None,
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
    return {"markdown": storage.get_text(spec_version.s3_markdown_key),
            "specification_version": spec_version.specification_version}


@router.get("/jds/{jd_id}/json")
def get_json(jd_id: str, db: Session = Depends(get_db)):
    spec_version = _latest_spec_version(jd_id, db)
    return {"json": spec_version.canonical_json, "specification_version": spec_version.specification_version}


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
    # A local model serves one request at a time; chat would queue behind a multi-minute analysis.
    with _state_lock:
        busy = bool(_inflight)
    if llm.provider == "ollama" and busy:
        raise HTTPException(503, "A job description is being analyzed right now. Chat will be available when it finishes.")
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
            markdown_content = storage.get_text(_latest_spec_version(jd_id, db).s3_markdown_key)
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
    import json
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
    master = _load_master_context(jd_id, db)
    questions = master.clarification_history
    if status:
        questions = [q for q in questions if q.status.value.upper() == status.upper()]
    if priority:
        questions = [q for q in questions if q.priority.value.upper() == priority.upper()]
    return {
        "jd_id": jd_id,
        "lifecycle_status": master.lifecycle_status.value,
        "total_questions": len(master.clarification_history),
        "blocking_unresolved": len(master.unresolved_blocking_questions),
        "is_ready_to_finalize": master.is_ready_to_finalize,
        "questions": [q.model_dump(mode="json") for q in questions],
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