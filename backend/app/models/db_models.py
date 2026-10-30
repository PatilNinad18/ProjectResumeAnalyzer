"""
SQLAlchemy models. Works out of the box against SQLite (the local-dev
default -- zero setup, a single file) and against PostgreSQL/RDS in
production by just changing DATABASE_URL; nothing here is Postgres-specific.

Project
  -> JobDescription
       -> JobDescriptionVersion (raw text/file per edit)
            -> JobSpecificationVersion (canonical JSON + rendered MD + model/prompt version)
ProcessingJob tracks async worker state per JobDescriptionVersion.
AuditEvent records who/what/when for every state-changing action.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    func,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# Portable "UUID" column: a plain 36-char string. Works identically on
# SQLite and Postgres (unlike sqlalchemy.dialects.postgresql.UUID, which
# only works on Postgres). gen_uuid() below already produces str values.
UUID_COL = String(36)


def gen_uuid() -> str:
    return str(uuid.uuid4())


class RoleEnum(str, enum.Enum):
    ADMIN = "admin"
    TA_REVIEWER = "ta_reviewer"


class ProcessingStatusEnum(str, enum.Enum):
    """Worker-level processing state (transient, decoupled from JD business lifecycle)."""
    UPLOADED = "UPLOADED"
    PARSING = "PARSING"
    UNDERSTANDING = "UNDERSTANDING"
    VALIDATING = "VALIDATING"
    GENERATING = "GENERATING"
    READY = "READY"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


class JDLifecycleStatusEnum(str, enum.Enum):
    """Business-level JD lifecycle status (Problem 3 decoupled model)."""
    DRAFT = "DRAFT"
    ANALYZING = "ANALYZING"
    ANALYZED = "ANALYZED"
    AWAITING_CLARIFICATION = "AWAITING_CLARIFICATION"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    FINALIZED = "FINALIZED"
    FAILED = "FAILED"


class ClarificationQuestionStatusEnum(str, enum.Enum):
    UNANSWERED = "UNANSWERED"
    ANSWERED = "ANSWERED"
    SKIPPED = "SKIPPED"
    EXPLICITLY_UNSPECIFIED = "EXPLICITLY_UNSPECIFIED"


class ClarificationQuestionPriorityEnum(str, enum.Enum):
    BLOCKING = "BLOCKING"
    RECOMMENDED = "RECOMMENDED"
    OPTIONAL = "OPTIONAL"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID_COL, primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    auth_provider_id = Column(String, nullable=True, index=True)  # Supabase/Auth0/Cognito subject id
    role = Column(Enum(RoleEnum), nullable=False, default=RoleEnum.TA_REVIEWER)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    projects = relationship("Project", back_populates="owner")


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID_COL, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    owner_id = Column(UUID_COL, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="projects")
    job_descriptions = relationship("JobDescription", back_populates="project")


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id = Column(UUID_COL, primary_key=True, default=gen_uuid)
    project_id = Column(UUID_COL, ForeignKey("projects.id"), nullable=False)
    title = Column(String, nullable=True)
    current_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project", back_populates="job_descriptions")
    versions = relationship("JobDescriptionVersion", back_populates="job_description")


class JobDescriptionVersion(Base):
    __tablename__ = "job_description_versions"

    id = Column(UUID_COL, primary_key=True, default=gen_uuid)
    job_description_id = Column(UUID_COL, ForeignKey("job_descriptions.id"), nullable=False)
    version = Column(Integer, nullable=False)
    s3_raw_key = Column(String, nullable=False)  # private S3 object key for original JD file/text
    raw_text_checksum = Column(String, nullable=False)  # sha256, for change detection/dedup
    uploaded_by = Column(UUID_COL, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    job_description = relationship("JobDescription", back_populates="versions")
    specification_versions = relationship("JobSpecificationVersion", back_populates="jd_version")
    processing_jobs = relationship("ProcessingJob", back_populates="jd_version")


class JobSpecificationVersion(Base):
    __tablename__ = "job_specification_versions"

    id = Column(UUID_COL, primary_key=True, default=gen_uuid)
    job_description_version_id = Column(UUID_COL, ForeignKey("job_description_versions.id"), nullable=False)
    specification_version = Column(Integer, nullable=False)

    s3_json_key = Column(String, nullable=False)
    s3_markdown_key = Column(String, nullable=False)

    canonical_json = Column(JSON, nullable=False)  # denormalized copy for fast querying; S3 remains source of record
    prompt_version = Column(String, nullable=False)
    model_version = Column(String, nullable=False)

    # --- Intern 2: JD Business Lifecycle fields ---
    # Stores the full JDMasterContext as serialised JSON — the authoritative lossless state.
    master_context_json = Column(JSON, nullable=True)
    # Business-level lifecycle status (decoupled from worker ProcessingStatus).
    lifecycle_status = Column(
        Enum(JDLifecycleStatusEnum),
        nullable=False,
        default=JDLifecycleStatusEnum.DRAFT,
    )
    # Self-referential FK to prior version for revision lineage (v1 -> v2 audit trail).
    parent_specification_version_id = Column(
        UUID_COL,
        ForeignKey("job_specification_versions.id"),
        nullable=True,
    )
    # --- Grounded TA Evidence Enrichment fields ---
    enrichment_report_json = Column(JSON, nullable=True)
    s3_enriched_markdown_key = Column(String, nullable=True)

    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    estimated_cost_usd = Column(Integer, nullable=True)  # stored as micro-USD (int) to avoid float drift

    is_valid = Column(Boolean, nullable=False, default=True)
    needs_review = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    jd_version = relationship("JobDescriptionVersion", back_populates="specification_versions")
    clarification_questions = relationship(
        "ClarificationQuestion",
        back_populates="spec_version",
        cascade="all, delete-orphan",
    )
    prior_version = relationship(
        "JobSpecificationVersion",
        remote_side="JobSpecificationVersion.id",
        foreign_keys="[JobSpecificationVersion.parent_specification_version_id]",
        uselist=False,
    )


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id = Column(UUID_COL, primary_key=True, default=gen_uuid)
    job_description_version_id = Column(UUID_COL, ForeignKey("job_description_versions.id"), nullable=False)
    status = Column(Enum(ProcessingStatusEnum), nullable=False, default=ProcessingStatusEnum.UPLOADED)
    error_message = Column(Text, nullable=True)
    sqs_message_id = Column(String, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    jd_version = relationship("JobDescriptionVersion", back_populates="processing_jobs")


class JobDescriptionBatch(Base):
    __tablename__ = "job_description_batches"

    id = Column(UUID_COL, primary_key=True, default=gen_uuid)
    project_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="QUEUED", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tasks = relationship("JobDescriptionBatchTask", back_populates="batch", cascade="all, delete-orphan")


class JobDescriptionBatchTask(Base):
    __tablename__ = "job_description_batch_tasks"

    id = Column(UUID_COL, primary_key=True, default=gen_uuid)
    batch_id = Column(UUID_COL, ForeignKey("job_description_batches.id"), nullable=False, index=True)
    job_description_id = Column(UUID_COL, ForeignKey("job_descriptions.id"), nullable=False, index=True)
    job_description_version_id = Column(UUID_COL, ForeignKey("job_description_versions.id"), nullable=False)
    source_filename = Column(String, nullable=False)
    status = Column(String, nullable=False, default="QUEUED", index=True)
    stage = Column(String, nullable=False, default="QUEUED")
    stage_label = Column(String, nullable=False, default="Waiting for a worker")
    progress_percent = Column(Integer, nullable=False, default=0)
    attempt_count = Column(Integer, nullable=False, default=0)
    cancel_requested = Column(Boolean, nullable=False, default=False)
    error_message = Column(Text, nullable=True)
    markdown_path = Column(Text, nullable=True)
    json_path = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    batch = relationship("JobDescriptionBatch", back_populates="tasks")
    job_description = relationship("JobDescription")
    jd_version = relationship("JobDescriptionVersion")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(UUID_COL, primary_key=True, default=gen_uuid)
    actor_user_id = Column(UUID_COL, ForeignKey("users.id"), nullable=True)
    entity_type = Column(String, nullable=False)  # e.g. "job_description", "job_specification_version"
    entity_id = Column(UUID_COL, nullable=False)
    action = Column(String, nullable=False)  # e.g. "created", "reprocessed", "reviewed"
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ClarificationQuestion(Base):
    """
    Persistent store for clarification questions generated by the Clarification Engine.
    One row per question per JobSpecificationVersion.
    The question_key is stable and used for idempotent upserts.
    """
    __tablename__ = "clarification_questions"

    id = Column(UUID_COL, primary_key=True, default=gen_uuid)
    job_specification_version_id = Column(
        UUID_COL,
        ForeignKey("job_specification_versions.id"),
        nullable=False,
        index=True,
    )
    question_key = Column(String, nullable=False, index=True)  # e.g. "tech_scope_virtual_platform_0"
    category = Column(String, nullable=False)                  # QuestionCategory enum value
    priority = Column(
        Enum(ClarificationQuestionPriorityEnum),
        nullable=False,
        default=ClarificationQuestionPriorityEnum.RECOMMENDED,
    )
    is_blocking = Column(Boolean, nullable=False, default=False)
    field_target = Column(String, nullable=False)              # JSON path in JDMasterContext
    question_text = Column(Text, nullable=False)
    rationale = Column(Text, nullable=False)
    suggested_options = Column(JSON, nullable=True)            # List[str]
    status = Column(
        Enum(ClarificationQuestionStatusEnum),
        nullable=False,
        default=ClarificationQuestionStatusEnum.UNANSWERED,
    )
    answer_text = Column(Text, nullable=True)
    answered_by = Column(String, nullable=True)                # User ID or "system"
    answered_at = Column(DateTime(timezone=True), nullable=True)
    override_record = Column(JSON, nullable=True)              # {authorized_by, override_reason, timestamp}
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    spec_version = relationship("JobSpecificationVersion", back_populates="clarification_questions")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String(64), primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    title = Column(String, nullable=True)
    company_name = Column(String, nullable=True)
    department = Column(String, nullable=True)
    project_name = Column(String, nullable=True)
    job_description_id = Column(UUID_COL, ForeignKey("job_descriptions.id"), nullable=False)
    status = Column(String, nullable=False, default="ACTIVE")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Preserves JD upon agent deletion (no cascade delete of JobDescription)
    job_description = relationship("JobDescription")
