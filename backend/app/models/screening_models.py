"""
Candidate Resume Screening Database Models — v2.1

Changes from v2.0:
  - ScreeningStatusEnum: Added PARSE_FAILED status for unreadable/scanned PDFs
  - CandidateResume: Added parse_quality_check JSON, file_hash (SHA-256) for dedup,
    file_key renamed clarified as local FS path
  - CandidateEvaluation: Added evaluator_engine, model_name, model_version,
    prompt_version, temperature, seed for full auditability;
    Added recruiter_override fields for human-in-the-loop;
    Added quote_verification_pass flag; renamed red_flags -> timeline_observations;
    Added spec_outdated flag

Tables:
  candidate_resumes      -- uploaded resume files and extracted candidate profiles
  candidate_evaluations  -- evaluation results of a candidate against a JobSpecificationVersion

Relationship chain:
  JobDescription -> CandidateResume (via job_description_id)
  CandidateResume -> CandidateEvaluation (many, one per jd+spec_version combination)
  One resume CAN be evaluated against multiple JDs or spec revisions.
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
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    func,
)
from sqlalchemy.orm import relationship

from app.models.db_models import Base, UUID_COL, gen_uuid


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ScreeningStatusEnum(str, enum.Enum):
    """Processing state of a candidate evaluation run."""
<<<<<<< HEAD
    QUEUED     = "QUEUED"
    ANALYZING  = "ANALYZING"
    COMPLETED  = "COMPLETED"
    FAILED     = "FAILED"
    PARSE_FAILED = "PARSE_FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
=======
    QUEUED       = "QUEUED"
    ANALYZING    = "ANALYZING"
    COMPLETED    = "COMPLETED"
    FAILED       = "FAILED"
    PARSE_FAILED = "PARSE_FAILED"   # Unreadable PDF/DOCX (scanned image, corrupted)
>>>>>>> smartleaven_work/main


class MatchTierEnum(str, enum.Enum):
    """
    High-level match classification against the Job Evaluation Specification v2.

    Tier rules (applied in order):
      STRONG_MATCH:    score >= 75 AND 0 NOT_EVIDENCED must-haves
      POTENTIAL_MATCH: score >= 50 AND <= 1 NOT_EVIDENCED must-have
                       OR score >= 75 but 1 NOT_EVIDENCED must-have (capped)
      NOT_A_FIT:       score < 50 OR >= 2 NOT_EVIDENCED must-haves
    """
    STRONG_MATCH    = "STRONG_MATCH"
    POTENTIAL_MATCH = "POTENTIAL_MATCH"
    NOT_A_FIT       = "NOT_A_FIT"


class EvaluationStatusEnum(str, enum.Enum):
    """
    Standardized per-requirement evaluation status.

    - MET:            Strong, verifiable evidence in candidate's work/projects.
                      Score weight: 1.0
    - PARTIALLY_MET:  Adjacent exposure, coursework, or theoretical knowledge found.
                      Score weight: 0.5
    - NOT_EVIDENCED:  No mention or verifiable signal in the provided resume.
                      Score weight: 0.0
                      Does NOT mean the candidate lacks the skill — it triggers an
                      interview verification checkpoint instead of a hard rejection.
    """
    MET           = "MET"
    PARTIALLY_MET = "PARTIALLY_MET"
    NOT_EVIDENCED = "NOT_EVIDENCED"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CandidateResume(Base):
    """
    Stores an uploaded candidate resume and the structured profile extracted from it.

    Design notes:
    - Not tied to a specific JD. The same resume can be evaluated against multiple JDs.
    - file_hash (SHA-256) enables duplicate detection before heavy parsing.
    - parse_quality_check stores the quality gate result:
        { "passed": bool, "text_length": int, "word_count": int,
          "alpha_ratio": float, "failure_reason": str | null }
    - If parse_quality_check.passed is False, the status of related evaluations
      is set to PARSE_FAILED and the resume is excluded from the leaderboard.
    """
    __tablename__ = "candidate_resumes"

    id = Column(UUID_COL, primary_key=True, default=gen_uuid)

    # Which JD/project context this resume was uploaded under
    job_description_id = Column(UUID_COL, ForeignKey("job_descriptions.id"), nullable=False, index=True)

    # --- Raw file storage ---
    filename        = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=True)
    file_key        = Column(String, nullable=True)   # local FS path: uploads/resumes/{jd_id}/{resume_id}_{filename}
    file_hash       = Column(String(64), nullable=True, index=True)  # SHA-256 hex for deduplication

    # --- Parse quality gate result ---
    # { "passed": bool, "text_length": int, "word_count": int,
    #   "alpha_ratio": float, "failure_reason": str | null }
    parse_quality_check = Column(JSON, nullable=True)

    # --- Extracted contact & profile metadata ---
    candidate_name         = Column(String, nullable=True)
    email                  = Column(String, nullable=True)
    phone                  = Column(String, nullable=True)
    total_experience_years = Column(Float, nullable=True)   # sum of deduped job+internship date ranges only

    # --- Full text & structured profile ---
    parsed_text         = Column(Text, nullable=True)   # raw clean text from parser (plain-text only)
    parsed_profile_json = Column(JSON, nullable=True)   # structured: work_history, skills, education, projects

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # --- Relationships ---
    evaluations     = relationship("CandidateEvaluation", back_populates="resume", cascade="all, delete-orphan")
    job_description = relationship("JobDescription")


class CandidateEvaluation(Base):
    """
    Grounded evaluation result of a CandidateResume against a specific JobSpecificationVersion.

    Key design decisions:
    - detailed_evaluations: JSON array where each RequirementEvaluation carries
      a verbatim quote verified to exist in parsed_text.
    - quote_verification_pass: False means at least one claimed evidence quote
      was not found in parsed_text (possible LLM hallucination — quote cleared).
    - Scoring is deterministic: derived only from evidenced criteria and formula constants.
    - match_tier has guardrails: score can be capped at POTENTIAL_MATCH even if high.
    - timeline_observations replaces red_flags: neutral notes only, never scoring penalties.
    - Recruiter overrides: allow human correction with mandatory audit reason.
    - Evaluator provenance: captures engine, model, prompt version, temp, seed for reproducibility.
    """
    __tablename__ = "candidate_evaluations"

    id = Column(UUID_COL, primary_key=True, default=gen_uuid)

    candidate_resume_id = Column(
        UUID_COL, ForeignKey("candidate_resumes.id"), nullable=False, index=True
    )
    job_description_id = Column(
        UUID_COL, ForeignKey("job_descriptions.id"), nullable=False, index=True
    )
    # The specific spec version UUID evaluated against
    spec_version_id      = Column(UUID_COL, nullable=True)
    specification_version = Column(Integer, nullable=False, default=2)

    # Is this evaluation against an outdated spec? Set True when a newer spec version exists.
    spec_outdated = Column(Boolean, nullable=False, default=False)

    # --- Processing state ---
    status = Column(
        Enum(ScreeningStatusEnum),
        nullable=False,
        default=ScreeningStatusEnum.QUEUED,
    )
    error_message = Column(Text, nullable=True)

    # --- Evaluator provenance (audit & reproducibility) ---
    # "deterministic_v1" for the keyword anchor engine (no LLM)
    # "ollama_qwen3_4b" for the deep semantic LLM-assisted engine
    evaluator_engine = Column(String(64), nullable=False, default="deterministic_v1")
    model_name       = Column(String(128), nullable=True)   # e.g. "qwen3:4b"
    model_version    = Column(String(64), nullable=True)    # e.g. "4b-q4_0"
    prompt_version   = Column(String(32), nullable=False, default="eval_v2.1")
    temperature      = Column(Float, nullable=False, default=0.0)
    seed             = Column(Integer, nullable=False, default=42)

    # --- Quote integrity check ---
    # True if all evidence_quote values were verified against parsed_text.
    # False if any quote could not be found (possible hallucination; quote was cleared).
    quote_verification_pass = Column(Boolean, nullable=True)

    # --- Scoring results ---
    overall_score = Column(Integer, nullable=True)   # 0-100, set after COMPLETED
    match_tier    = Column(Enum(MatchTierEnum), nullable=True)

    # --- Detailed per-requirement results ---
    # Schema: { "total": int, "met": int, "partially_met": int, "not_evidenced": int }
    must_haves_summary = Column(JSON, nullable=True)
    preferred_summary  = Column(JSON, nullable=True)

    # JSON array of RequirementEvaluation dicts:
    # [{
    #   "requirement": str,
    #   "category": "must_have" | "preferred",
    #   "status": "MET" | "PARTIALLY_MET" | "NOT_EVIDENCED",
    #   "score_weight": 1.0 | 0.5 | 0.0,
<<<<<<< HEAD
    #   "evidence_quote": str | null,  # verbatim excerpt from resume
    #   "evidence_quotes": list[str],  # all supporting verbatim excerpts
=======
    #   "evidence_quote": str | null,      # verbatim excerpt verified in parsed_text
    #   "quote_verified": bool | null,     # True if quote found in parsed_text
    #   "searched_keywords": List[str],    # terms searched (audit trail for NOT_EVIDENCED)
>>>>>>> smartleaven_work/main
    #   "reasoning": str,
    # }, ...]
    detailed_evaluations = Column(JSON, nullable=True)

    # JSON array: unevidenced/partial must-haves flagged for recruiter follow-up (never scoring)
    # [{
    #   "requirement": str,
    #   "status": "NOT_EVIDENCED" | "PARTIALLY_MET",
    #   "interview_question": str,
    # }, ...]
    validation_checkpoints = Column(JSON, nullable=True)

    # JSON array: neutral timeline observations (NOT penalties, NOT score modifiers)
    # e.g. career pauses, concurrent roles, overlapping dates
    # Renamed from red_flags — gaps are NOT negative signals, just notes for interview
    timeline_observations = Column(JSON, nullable=True)

    # JSON array of 3-5 tailored technical interview question strings
    tailored_interview_questions = Column(JSON, nullable=True)

    # Score breakdown for full transparency
    # {
    #   "must_have_subscore": float,   "preferred_subscore": float,
    #   "tenure_subscore": float,      "active_weight_total": float,
    #   "must_have_base_weight": float, "preferred_base_weight": float,
    #   "tenure_base_weight": float,
    # }
    score_breakdown = Column(JSON, nullable=True)

    # --- Recruiter override (human-in-the-loop) ---
    # Recruiters may override tier/score with a mandatory reason. Tool provides
    # advisory recommendations only; nothing is ever auto-rejected.
    recruiter_override_tier  = Column(Enum(MatchTierEnum), nullable=True)
    recruiter_override_score = Column(Integer, nullable=True)
    override_reason          = Column(Text, nullable=True)
    overridden_by            = Column(String(255), nullable=True)   # user identifier
    overridden_at            = Column(DateTime(timezone=True), nullable=True)

    started_at   = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    # --- Relationships ---
    resume          = relationship("CandidateResume", back_populates="evaluations")
    job_description = relationship("JobDescription")
