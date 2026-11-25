"""
Pydantic schemas for the Resume Screening Agent API — v2.1

All enum values are consistent with EvaluationStatusEnum, MatchTierEnum,
and ScreeningStatusEnum defined in screening_models.py.

Changes from v2.0:
  - ScreeningStatus: Added PARSE_FAILED
  - RequirementEvaluation: Added quote_verified, searched_keywords fields
  - CandidateEvaluationResponse: Added evaluator provenance fields,
    quote_verification_pass, timeline_observations, spec_outdated,
    recruiter_override fields
  - ScreeningLeaderboardItem: Added parse_failed flag, spec_outdated
  - New: RecruiterOverrideRequest schema
  - New: ParseQualityCheck schema
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Shared enum mirrors (string values match DB enums)
# ---------------------------------------------------------------------------

class EvaluationStatus(str, enum.Enum):
    MET           = "MET"
    PARTIALLY_MET = "PARTIALLY_MET"
    NOT_EVIDENCED = "NOT_EVIDENCED"


class MatchTier(str, enum.Enum):
    STRONG_MATCH    = "STRONG_MATCH"
    POTENTIAL_MATCH = "POTENTIAL_MATCH"
    NOT_A_FIT       = "NOT_A_FIT"


class ScreeningStatus(str, enum.Enum):
    QUEUED       = "QUEUED"
    ANALYZING    = "ANALYZING"
    COMPLETED    = "COMPLETED"
    FAILED       = "FAILED"
    PARSE_FAILED = "PARSE_FAILED"


# ---------------------------------------------------------------------------
# Parse quality gate result
# ---------------------------------------------------------------------------

class ParseQualityCheck(BaseModel):
    """Result of the parse quality gate applied to the extracted resume text."""
    passed:         bool
    text_length:    int
    word_count:     int
    alpha_ratio:    float
    failure_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Resume upload
# ---------------------------------------------------------------------------

class ResumeUploadResponse(BaseModel):
    """Returned immediately after a resume file is uploaded and queued."""
    candidate_resume_id: str
    filename:            str
    file_size_bytes:     Optional[int]
    status:              ScreeningStatus
    parse_quality:       Optional[ParseQualityCheck] = None
    message:             str


class BatchResumeUploadResponse(BaseModel):
    uploaded:     List[ResumeUploadResponse]
    failed:       List[Dict[str, str]]   # [{filename: str, error: str}]
    total_queued: int


# ---------------------------------------------------------------------------
# Per-requirement evaluation result
# ---------------------------------------------------------------------------

class RequirementEvaluation(BaseModel):
    """
    Evaluation of a single requirement from the Job Evaluation Specification v2.

    Invariants:
    - Every MET or PARTIALLY_MET claim MUST carry an evidence_quote that was
      verified to exist in the original parsed_text (quote_verified=True).
    - If quote_verified=False, the status was downgraded to NOT_EVIDENCED.
    - NOT_EVIDENCED entries carry searched_keywords for full audit transparency.
    """
    requirement: str
    category:    str = Field(description="'must_have' or 'preferred'")
    status:      EvaluationStatus
    score_weight: float = Field(
        ge=0.0,
        le=1.0,
        description="1.0=MET, 0.5=PARTIALLY_MET, 0.0=NOT_EVIDENCED",
    )
    evidence_quote:    Optional[str] = Field(
        None,
        description="Verbatim excerpt from resume text, verified present in parsed_text.",
    )
    quote_verified:    Optional[bool] = Field(
        None,
        description="True if evidence_quote was confirmed in parsed_text. None for NOT_EVIDENCED.",
    )
    searched_keywords: List[str] = Field(
        default_factory=list,
        description="Keywords searched during classification — audit trail for NOT_EVIDENCED.",
    )
    reasoning: str = Field(description="Brief explanation of the assigned status.")


# ---------------------------------------------------------------------------
# Validation checkpoint (unevidenced/partial must-have -> interview question)
# ---------------------------------------------------------------------------

class ValidationCheckpoint(BaseModel):
    """An unevidenced or partially-met must-have that the recruiter must verify via interview."""
    requirement:        str
    status:             EvaluationStatus
    interview_question: str


# ---------------------------------------------------------------------------
# Score breakdown
# ---------------------------------------------------------------------------

class ScoreBreakdown(BaseModel):
    must_have_subscore:    float
    preferred_subscore:    float
    tenure_subscore:       float
    active_weight_total:   float
    must_have_base_weight: float
    preferred_base_weight: float
    tenure_base_weight:    float
    warning:               Optional[str] = None   # e.g. "NO_EVALUATION_CRITERIA_DEFINED"


# ---------------------------------------------------------------------------
# Must-haves / preferred summary counts
# ---------------------------------------------------------------------------

class RequirementSummary(BaseModel):
    total:         int
    met:           int
    partially_met: int
    not_evidenced: int


# ---------------------------------------------------------------------------
# Candidate profile (extracted from resume)
# ---------------------------------------------------------------------------

class CandidateProfile(BaseModel):
    candidate_name:         Optional[str]
    email:                  Optional[str]
    phone:                  Optional[str]
    total_experience_years: Optional[float]
    skills:                 List[str] = []
    companies:              List[str] = []
    current_or_last_title:  Optional[str]


# ---------------------------------------------------------------------------
# Evaluator provenance (audit & reproducibility)
# ---------------------------------------------------------------------------

class EvaluatorProvenance(BaseModel):
    """Audit record of which engine, model, and parameters produced this evaluation."""
    evaluator_engine: str   # "deterministic_v1" | "ollama_qwen3_4b"
    model_name:       Optional[str]
    model_version:    Optional[str]
    prompt_version:   str
    temperature:      float
    seed:             int


# ---------------------------------------------------------------------------
# Recruiter override
# ---------------------------------------------------------------------------

class RecruiterOverrideRequest(BaseModel):
    """Body for POST /api/jds/{jd_id}/resumes/{resume_id}/override."""
    override_tier:  MatchTier = Field(description="Recruiter's corrected match tier.")
    override_score: Optional[int] = Field(
        None, ge=0, le=100,
        description="Recruiter's corrected score (0-100). Optional.",
    )
    reason: str = Field(
        min_length=10,
        description="Mandatory justification for the override (minimum 10 characters).",
    )
    overridden_by: Optional[str] = Field(
        None,
        description="Identifier of the recruiter making this override (email, name, or user ID).",
    )


class RecruiterOverrideResponse(BaseModel):
    candidate_resume_id:    str
    job_description_id:     str
    recruiter_override_tier: MatchTier
    recruiter_override_score: Optional[int]
    override_reason:         str
    overridden_by:           Optional[str]
    overridden_at:           datetime
    message:                 str


# ---------------------------------------------------------------------------
# Full evaluation response
# ---------------------------------------------------------------------------

class CandidateEvaluationResponse(BaseModel):
    """Full deep-dive evaluation for a single candidate."""
    candidate_resume_id:   str
    job_description_id:    str
    spec_version_id:       Optional[str]
    specification_version: int
    spec_outdated:         bool = False

    status:        ScreeningStatus
    overall_score: Optional[int]
    match_tier:    Optional[MatchTier]

    # Evaluator provenance
    provenance: Optional[EvaluatorProvenance] = None

    # Quote integrity
    quote_verification_pass: Optional[bool] = None

    candidate_profile: Optional[CandidateProfile]

    must_haves_summary: Optional[RequirementSummary]
    preferred_summary:  Optional[RequirementSummary]
    score_breakdown:    Optional[ScoreBreakdown]

    detailed_evaluations:         List[RequirementEvaluation] = []
    validation_checkpoints:       List[ValidationCheckpoint]  = []
    timeline_observations:        List[str] = []   # Neutral notes (NOT penalties)
    tailored_interview_questions: List[str] = []

    # Recruiter override fields (None if no override applied)
    recruiter_override_tier:  Optional[MatchTier] = None
    recruiter_override_score: Optional[int]       = None
    override_reason:          Optional[str]       = None
    overridden_by:            Optional[str]       = None
    overridden_at:            Optional[datetime]  = None

    created_at:   Optional[datetime]
    completed_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Leaderboard (compact list item for the ranking table)
# ---------------------------------------------------------------------------

class ScreeningLeaderboardItem(BaseModel):
    """Compact candidate entry for the recruiter leaderboard table."""
    rank:                   int
    candidate_resume_id:    str
    filename:               str
    candidate_name:         Optional[str]
    email:                  Optional[str]
    total_experience_years: Optional[float]
    overall_score:          Optional[int]
    match_tier:             Optional[MatchTier]
    must_haves_met:         int
    must_haves_total:       int
    not_evidenced_count:    int
    validation_checkpoints_count: int
    status:                 ScreeningStatus
    parse_failed:           bool = False    # True if PARSE_FAILED status
    spec_outdated:          bool = False    # True if evaluated against an older spec
    # Show effective tier (recruiter override wins if present)
    effective_tier:         Optional[MatchTier] = None
    created_at:             Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class ScreeningLeaderboardResponse(BaseModel):
    job_description_id: str
    total_candidates:   int
    candidates:         List[ScreeningLeaderboardItem]


# ---------------------------------------------------------------------------
# Trigger screening request
# ---------------------------------------------------------------------------

class ScreeningTriggerRequest(BaseModel):
    """Body for POST /api/jds/{jd_id}/screen."""
    spec_version_id: Optional[str] = Field(
        None,
        description="Specific JobSpecificationVersion UUID. Defaults to latest finalized v2.",
    )
    candidate_resume_ids: Optional[List[str]] = Field(
        None,
        description="Subset of resume IDs to screen. If omitted, screens all uploaded candidates.",
    )


class ScreeningTriggerResponse(BaseModel):
    queued_count:         int
    candidate_resume_ids: List[str]
    message:              str
