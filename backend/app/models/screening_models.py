"""
Candidate Resume Screening Database Models.

Tables:
  candidate_resumes      -- uploaded resume files and extracted candidate profiles
  candidate_evaluations  -- evaluation results of a candidate against a JobSpecificationVersion

Relationship chain:
  JobDescription -> CandidateResume (via job_description_id)
  CandidateResume -> CandidateEvaluation (one-to-one per jd spec version)
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
    QUEUED     = "QUEUED"
    ANALYZING  = "ANALYZING"
    COMPLETED  = "COMPLETED"
    FAILED     = "FAILED"
    PARSE_FAILED = "PARSE_FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class MatchTierEnum(str, enum.Enum):
    """High-level match classification against the Job Evaluation Specification v2."""
    STRONG_MATCH    = "STRONG_MATCH"      # >= 80% and no unevidenced must-haves
    POTENTIAL_MATCH = "POTENTIAL_MATCH"   # 60-79%, or >= 80% but has 1 unevidenced must-have
    NOT_A_FIT       = "NOT_A_FIT"         # < 60%, or >= 2 unevidenced must-haves


class EvaluationStatusEnum(str, enum.Enum):
    """
    Standardized per-requirement evaluation status.

    - MET:            Strong, verifiable evidence found with verbatim quote.
    - PARTIALLY_MET:  Adjacent exposure or theoretical knowledge found, verbatim quote cited.
    - NOT_EVIDENCED:  No mention or verifiable signal in the resume.
                      Does NOT mean the candidate lacks the skill — it triggers an
                      interview verification question instead of a hard rejection.
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
    Not tied to a specific JD — the same resume can be evaluated against multiple JDs.
    """
    __tablename__ = "candidate_resumes"

    id = Column(UUID_COL, primary_key=True, default=gen_uuid)

    # Which JD/project context this resume was uploaded under
    job_description_id = Column(UUID_COL, ForeignKey("job_descriptions.id"), nullable=False, index=True)

    # --- Raw file storage ---
    filename        = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=True)
    file_key        = Column(String, nullable=True)   # local FS path or S3 key

    # --- Extracted contact & profile metadata ---
    candidate_name           = Column(String, nullable=True)
    email                    = Column(String, nullable=True)
    phone                    = Column(String, nullable=True)
    total_experience_years   = Column(Float, nullable=True)   # calculated from date ranges

    # --- Full text & structured profile ---
    parsed_text         = Column(Text, nullable=True)   # raw clean text from parser
    parsed_profile_json = Column(JSON, nullable=True)   # structured: work_history, skills, education, projects

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # --- Relationships ---
    evaluations   = relationship("CandidateEvaluation", back_populates="resume", cascade="all, delete-orphan")
    job_description = relationship("JobDescription")


class CandidateEvaluation(Base):
    """
    Stores the grounded evaluation result of a CandidateResume against a JobSpecificationVersion.

    Key design decisions:
    - detailed_evaluations: JSON array where each element is a RequirementEvaluation with
      verbatim quote evidence cited directly from the resume text.
    - Scores are deterministic: derived only from evidenced criteria, never hallucinated.
    - match_tier has guardrails: a candidate can be capped at POTENTIAL_MATCH even with
      a high numeric score if critical must-haves are NOT_EVIDENCED.
    """
    __tablename__ = "candidate_evaluations"

    id = Column(UUID_COL, primary_key=True, default=gen_uuid)

    candidate_resume_id = Column(
        UUID_COL, ForeignKey("candidate_resumes.id"), nullable=False, index=True
    )
    job_description_id = Column(
        UUID_COL, ForeignKey("job_descriptions.id"), nullable=False, index=True
    )
    # The specific spec version evaluated against (should reference job_specification_versions)
    spec_version_id = Column(UUID_COL, nullable=True)
    specification_version = Column(Integer, nullable=False, default=2)

    # --- Processing state ---
    status = Column(
        Enum(ScreeningStatusEnum),
        nullable=False,
        default=ScreeningStatusEnum.QUEUED,
    )
    error_message = Column(Text, nullable=True)

    # --- Scoring results ---
    overall_score = Column(Integer, nullable=True)   # 0-100, set after COMPLETED
    match_tier    = Column(Enum(MatchTierEnum), nullable=True)

    # --- Detailed per-requirement results ---
    # Schema: { "total": int, "met": int, "partially_met": int, "not_evidenced": int }
    must_haves_summary    = Column(JSON, nullable=True)
    # Schema: { "total": int, "met": int, "partially_met": int, "not_evidenced": int }
    preferred_summary     = Column(JSON, nullable=True)

    # JSON array of RequirementEvaluation dicts:
    # [{
    #   "requirement": str,
    #   "category": "must_have" | "preferred",
    #   "status": "MET" | "PARTIALLY_MET" | "NOT_EVIDENCED",
    #   "score_weight": 1.0 | 0.5 | 0.0,
    #   "evidence_quote": str | null,  # verbatim excerpt from resume
    #   "evidence_quotes": list[str],  # all supporting verbatim excerpts
    #   "reasoning": str,
    # }, ...]
    detailed_evaluations = Column(JSON, nullable=True)

    # JSON array: unevidenced/partial must-haves flagged for human recruiter follow-up
    # [{
    #   "requirement": str,
    #   "status": "NOT_EVIDENCED" | "PARTIALLY_MET",
    #   "interview_question": str,
    # }, ...]
    validation_checkpoints = Column(JSON, nullable=True)

    # JSON array: detected anomalies in the resume itself
    # e.g. tenure gaps > 6 months, conflicting date ranges, inflated titles
    red_flags = Column(JSON, nullable=True)

    # JSON array of 3-5 tailored technical interview question strings
    tailored_interview_questions = Column(JSON, nullable=True)

    # Score breakdown for transparency
    # { "must_have_subscore": float, "preferred_subscore": float,
    #   "tenure_subscore": float, "active_weight_total": float }
    score_breakdown = Column(JSON, nullable=True)

    started_at   = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    # --- Relationships ---
    resume = relationship("CandidateResume", back_populates="evaluations")
    job_description = relationship("JobDescription")
