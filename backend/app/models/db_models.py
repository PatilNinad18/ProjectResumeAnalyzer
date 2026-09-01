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
    UPLOADED = "UPLOADED"
    PARSING = "PARSING"
    UNDERSTANDING = "UNDERSTANDING"
    VALIDATING = "VALIDATING"
    GENERATING = "GENERATING"
    READY = "READY"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


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

    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    estimated_cost_usd = Column(Integer, nullable=True)  # stored as micro-USD (int) to avoid float drift

    is_valid = Column(Boolean, nullable=False, default=True)
    needs_review = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    jd_version = relationship("JobDescriptionVersion", back_populates="specification_versions")


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


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(UUID_COL, primary_key=True, default=gen_uuid)
    actor_user_id = Column(UUID_COL, ForeignKey("users.id"), nullable=True)
    entity_type = Column(String, nullable=False)  # e.g. "job_description", "job_specification_version"
    entity_id = Column(UUID_COL, nullable=False)
    action = Column(String, nullable=False)  # e.g. "created", "reprocessed", "reviewed"
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
