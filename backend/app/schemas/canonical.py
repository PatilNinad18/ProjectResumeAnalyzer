"""
Canonical Candidate Evaluation Specification schema.

This is the SINGLE SOURCE OF TRUTH for the JD Understanding pipeline.
- The LLM (via the JD Understanding Agent) is prompted to produce this object.
- job_specification.md is rendered FROM this object.
- job_specification.json is serialized FROM this object.
- Markdown -> JSON conversion re-parses Markdown back INTO this object
  (schema-aware, validated) so both artifacts always agree.

Nothing downstream should treat Markdown as authoritative; it is a
human/LLM-readable *view* of this schema.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Priority(str, Enum):
    MUST_HAVE = "MUST_HAVE"
    PREFERRED = "PREFERRED"
    CONTEXTUAL = "CONTEXTUAL"
    INFORMATIONAL = "INFORMATIONAL"
    AMBIGUOUS = "AMBIGUOUS"


class ExplicitOrDerived(str, Enum):
    EXPLICIT = "explicit"
    DERIVED = "derived"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class WorkMode(str, Enum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNSPECIFIED = "unspecified"


class ProcessingStatus(str, Enum):
    UPLOADED = "UPLOADED"
    PARSING = "PARSING"
    UNDERSTANDING = "UNDERSTANDING"
    VALIDATING = "VALIDATING"
    GENERATING = "GENERATING"
    READY = "READY"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------

class SourceRef(BaseModel):
    """Traceability back to the raw JD text."""
    text: str = Field(..., description="Verbatim (or lightly trimmed) source snippet from the JD.")
    section: Optional[str] = Field(None, description="JD section this snippet was found in, if identifiable.")
    location: Optional[str] = Field(None, description="Page/line/offset hint, if available.")


class EvidenceSpec(BaseModel):
    """
    Defines, for a single requirement, what candidate evidence
    downstream Candidate Analysis LLMs should look for and how to
    weigh it. This does NOT evaluate a candidate -- it defines the rules
    for evaluating one later.
    """
    requirement: str
    priority: Priority
    explicit_or_derived: ExplicitOrDerived
    evidence_to_look_for: List[str] = Field(default_factory=list)
    strong_evidence: Optional[str] = None
    moderate_evidence: Optional[str] = None
    weak_evidence: Optional[str] = None
    insufficient_evidence: Optional[str] = Field(
        None, description="What counts as insufficient evidence -> should yield UNCORED."
    )
    prohibited_inference: Optional[str] = Field(
        None, description="Explicit statement of what must NOT be inferred for this requirement."
    )
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    source: Optional[SourceRef] = None


class RequirementInterpretation(BaseModel):
    """
    Distinguishes an explicit JD requirement from the derived
    evaluation interpretation of what it actually means for scoring.
    """
    explicit_requirement: str
    derived_interpretation: List[str] = Field(default_factory=list)
    rationale: Optional[str] = None
    source: Optional[SourceRef] = None


class ResponsibilityRequirementMapping(BaseModel):
    responsibility: str
    required_capabilities: List[str] = Field(default_factory=list)
    rationale: Optional[str] = None
    source: Optional[SourceRef] = None


class NonConventionalParameter(BaseModel):
    parameter_name: str
    category: str
    why_it_is_relevant: str
    jd_evidence: str
    explicit_or_derived: ExplicitOrDerived
    evaluation_guidance: str
    evidence_to_look_for: List[str] = Field(default_factory=list)
    strong_evidence: Optional[str] = None
    moderate_evidence: Optional[str] = None
    weak_evidence: Optional[str] = None
    prohibited_inference: Optional[str] = None
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    unscored_if: Optional[str] = Field(
        None, description="Condition under which this parameter should resolve to UNCORED."
    )
    source: Optional[SourceRef] = None


class Ambiguity(BaseModel):
    statement: str
    why_ambiguous: str
    suggested_interpretation: Optional[str] = None
    evidence_required: List[str] = Field(default_factory=list)
    ta_confirmation_required: bool = True
    source: Optional[SourceRef] = None


class ComplianceFlag(BaseModel):
    flagged_text: str
    concern: str = Field(..., description="e.g. 'possible age proxy via graduation year'")
    category: str = Field(..., description="e.g. age, gender, disability, marital_status, other")
    recommended_action: str = "Flag for TA review. Do not use in automated scoring."
    source: Optional[SourceRef] = None


class RoleInfo(BaseModel):
    job_title: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    seniority: Optional[str] = None
    employment_type: Optional[str] = None
    reporting_structure: Optional[str] = None
    team_context: Optional[str] = None


class ExperienceRequirement(BaseModel):
    description: str
    min_years: Optional[float] = None
    max_years: Optional[float] = None
    priority: Priority = Priority.MUST_HAVE
    explicit_or_derived: ExplicitOrDerived = ExplicitOrDerived.EXPLICIT
    source: Optional[SourceRef] = None


class TechnicalSkill(BaseModel):
    name: str
    category: str = Field(..., description="language | framework | library | database | cloud | infra | tool | platform | methodology")
    priority: Priority
    explicit_or_derived: ExplicitOrDerived = ExplicitOrDerived.EXPLICIT
    source: Optional[SourceRef] = None


class EducationRequirement(BaseModel):
    description: str
    priority: Priority
    source: Optional[SourceRef] = None


class CertificationRequirement(BaseModel):
    description: str
    priority: Priority
    source: Optional[SourceRef] = None


class LocationInfo(BaseModel):
    country: Optional[str] = None
    city: Optional[str] = None
    work_mode: WorkMode = WorkMode.UNSPECIFIED
    office_attendance: Optional[str] = Field(None, description="e.g. '4 days/week onsite'")
    relocation_required: Optional[bool] = None
    source: Optional[SourceRef] = None


class TravelInfo(BaseModel):
    required: Optional[bool] = None
    description: Optional[str] = None
    source: Optional[SourceRef] = None


class OtherRequirement(BaseModel):
    category: str = Field(..., description="languages | shift | availability | work_authorization | domain_knowledge | client_facing | communication | misc")
    description: str
    priority: Priority
    source: Optional[SourceRef] = None


class ConventionalRequirements(BaseModel):
    experience: List[ExperienceRequirement] = Field(default_factory=list)
    technical_skills: List[TechnicalSkill] = Field(default_factory=list)
    education: List[EducationRequirement] = Field(default_factory=list)
    certifications: List[CertificationRequirement] = Field(default_factory=list)
    domain: List[str] = Field(default_factory=list)
    location: LocationInfo = Field(default_factory=LocationInfo)
    work_mode: WorkMode = WorkMode.UNSPECIFIED
    travel: TravelInfo = Field(default_factory=TravelInfo)
    languages: List[str] = Field(default_factory=list)
    other: List[OtherRequirement] = Field(default_factory=list)


class Responsibility(BaseModel):
    description: str
    kind: str = Field("primary", description="primary | secondary | ownership | leadership | collaboration")
    source: Optional[SourceRef] = None


class MetadataInfo(BaseModel):
    jd_id: Optional[str] = None
    jd_version: Optional[int] = None
    specification_version: Optional[int] = None
    prompt_version: Optional[str] = None
    model_version: Optional[str] = None
    generated_at: Optional[datetime] = None


class JobContext(BaseModel):
    company_context: Optional[str] = None
    business_context: Optional[str] = None
    team_size: Optional[str] = None
    environment: Optional[str] = Field(None, description="e.g. 'fast-paced startup'")


class MissingInfo(BaseModel):
    """
    Captures information that is absent from the JD and was NOT inferred
    or fabricated. Distinction matters: downstream users must know the
    difference between "not required" and "not specified".
    """
    field: str = Field(..., description="The parameter that is absent, e.g. 'salary range', 'work authorization'.")
    why_it_matters: str = Field(..., description="Why its absence is noteworthy for evaluation purposes.")
    suggested_action: Optional[str] = Field(None, description="e.g. 'Ask TA to confirm', 'Default to unspecified'.")


class JobEvaluationSpecification(BaseModel):
    """
    The canonical Candidate Evaluation Specification.
    This object is the ONLY source of truth. Markdown and JSON are
    both derived, deterministically, from an instance of this model.
    """
    metadata: MetadataInfo = Field(default_factory=MetadataInfo)
    role: RoleInfo = Field(default_factory=RoleInfo)
    job_context: JobContext = Field(default_factory=JobContext)
    responsibilities: List[Responsibility] = Field(default_factory=list)
    conventional_requirements: ConventionalRequirements = Field(default_factory=ConventionalRequirements)

    must_have_requirements: List[str] = Field(default_factory=list)
    preferred_requirements: List[str] = Field(default_factory=list)

    responsibility_requirement_mapping: List[ResponsibilityRequirementMapping] = Field(default_factory=list)
    requirement_interpretations: List[RequirementInterpretation] = Field(default_factory=list)
    evidence_requirements: List[EvidenceSpec] = Field(default_factory=list)
    non_conventional_parameters: List[NonConventionalParameter] = Field(default_factory=list)

    evaluation_rules: List[str] = Field(default_factory=list)
    unscored_rules: List[str] = Field(default_factory=list)
    prohibited_inferences: List[str] = Field(default_factory=list)
    compliance_flags: List[ComplianceFlag] = Field(default_factory=list)
    ambiguities: List[Ambiguity] = Field(default_factory=list)
    missing_information: List[MissingInfo] = Field(
        default_factory=list,
        description="JD parameters that are absent/unspecified — never fabricated.",
    )
    ta_confirmation_required: List[str] = Field(default_factory=list)
    candidate_analysis_instructions: List[str] = Field(default_factory=list)

    model_config = ConfigDict(use_enum_values=False)
