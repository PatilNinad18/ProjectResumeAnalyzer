"""
Pydantic schemas for the Resume Screening Agent API.

All enum values are consistent with the EvaluationStatusEnum, MatchTierEnum,
and ScreeningStatusEnum defined in screening_models.py.
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
    QUEUED    = "QUEUED"
    ANALYZING = "ANALYZING"
    COMPLETED = "COMPLETED"
    FAILED    = "FAILED"
    PARSE_FAILED = "PARSE_FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


# ---------------------------------------------------------------------------
# Resume upload
# ---------------------------------------------------------------------------

class ResumeUploadResponse(BaseModel):
    """Returned immediately after a resume file is uploaded and queued."""
    candidate_resume_id: str
    filename: str
    file_size_bytes: Optional[int]
    status: ScreeningStatus
    message: str


class BatchResumeUploadResponse(BaseModel):
    uploaded: List[ResumeUploadResponse]
    failed: List[Dict[str, str]]   # [{filename: str, error: str}]
    total_queued: int


# ---------------------------------------------------------------------------
# Per-requirement evaluation result
# ---------------------------------------------------------------------------

class RequirementEvaluation(BaseModel):
    """
    Evaluation of a single requirement from the Job Evaluation Specification v2.
    Every MET or PARTIALLY_MET claim MUST carry a verbatim evidence_quote from the resume.
    """
    requirement: str
    category: str = Field(description="'must_have' or 'preferred'")
    status: EvaluationStatus
    score_weight: float = Field(
        ge=0.0,
        le=1.0,
        description="1.0 for MET, 0.5 for PARTIALLY_MET, 0.0 for NOT_EVIDENCED",
    )
    evidence_quote: Optional[str] = Field(
        None,
        description="Verbatim excerpt quoted directly from the resume text. Required if status is MET or PARTIALLY_MET.",
    )
    evidence_quotes: List[str] = Field(default_factory=list)
    reasoning: str = Field(description="Brief explanation of why this status was assigned.")


# ---------------------------------------------------------------------------
# Validation checkpoint (unevidenced must-have -> interview question)
# ---------------------------------------------------------------------------

class ValidationCheckpoint(BaseModel):
    """An unevidenced or partially-met must-have that the recruiter must verify via interview."""
    requirement: str
    status: EvaluationStatus
    interview_question: str


# ---------------------------------------------------------------------------
# Score breakdown
# ---------------------------------------------------------------------------

class ScoreBreakdown(BaseModel):
    must_have_subscore:   float
    preferred_subscore:   float
    tenure_subscore:      float
    active_weight_total:  float
    must_have_base_weight: float
    preferred_base_weight: float
    tenure_base_weight:   float
    tenure_evidence:      List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Must-haves / preferred summary counts
# ---------------------------------------------------------------------------

class RequirementSummary(BaseModel):
    total:        int
    met:          int
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
# Full evaluation response
# ---------------------------------------------------------------------------

class CandidateEvaluationResponse(BaseModel):
    """Full deep-dive evaluation for a single candidate, returned from GET /resumes/{candidate_id}."""
    candidate_resume_id:  str
    job_description_id:   str
    spec_version_id:      Optional[str]
    specification_version: int

    status:        ScreeningStatus
    review_reason: Optional[str] = None
    overall_score: Optional[int]
    match_tier:    Optional[MatchTier]

    candidate_profile: Optional[CandidateProfile]

    must_haves_summary:  Optional[RequirementSummary]
    preferred_summary:   Optional[RequirementSummary]
    score_breakdown:     Optional[ScoreBreakdown]

    detailed_evaluations:        List[RequirementEvaluation] = []
    validation_checkpoints:      List[ValidationCheckpoint]  = []
    red_flags:                   List[str] = []
    tailored_interview_questions: List[str] = []

    created_at:   Optional[datetime]
    completed_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Leaderboard (compact list item for the ranking table)
# ---------------------------------------------------------------------------

class ScreeningLeaderboardItem(BaseModel):
    """Compact candidate entry for the recruiter leaderboard table."""
    rank:                   Optional[int]
    candidate_resume_id:    str
    filename:               str
    candidate_name:         Optional[str]
    email:                  Optional[str]
    total_experience_years: Optional[float]
    overall_score:          Optional[int]
    match_tier:             Optional[MatchTier]
    must_haves_met:         int
    must_haves_partially_met: int
    must_haves_total:       int
    not_evidenced_count:    int
    validation_checkpoints_count: int
    status:                 ScreeningStatus
    review_reason:          Optional[str] = None
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
    """Body for POST /api/jds/{jd_id}/resumes/screen."""
    spec_version_id: Optional[str] = Field(
        None,
        description="Specific JobSpecificationVersion UUID to evaluate against. Defaults to latest finalized v2.",
    )
    candidate_resume_ids: Optional[List[str]] = Field(
        None,
        description="Specific subset of resume IDs to screen. If omitted, screens all uploaded candidates for this JD.",
    )


class ScreeningTriggerResponse(BaseModel):
    queued_count: int
    candidate_resume_ids: List[str]
    message: str
