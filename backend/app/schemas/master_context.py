"""
master_context.py — Authoritative persistent domain model for the JD Lifecycle.

Invariants enforced here:
  1. Traceable Origin: Every requirement carries a ProvenanceRecord.
  2. Dual-Confidence: entity_match_confidence and interpretation_confidence are
     always tracked independently.
  3. Lossless Internal State: This schema stores ALL internal state (graph
     bindings, Q&A audit history, clarification loop). It is never lossy.
  4. Intern 1 Boundary: Intern 1 produces extraction AST (StructuredRequirement,
     DisjunctionGroup, ResponsibilityContext, ExtractedParameter, DetectedAmbiguity,
     ExtractionResult) conforming to this file.
     Everything else (clarification, projection, finalization) is Intern 2.

IMPORTANT: Do not import from canonical.py here. This schema is upstream.
canonical.py is a downstream projection of this schema.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


# ---------------------------------------------------------------------------
# Core Enums
# ---------------------------------------------------------------------------

class JDLifecycleStatus(str, Enum):
    """Business-level lifecycle of a Job Description."""
    DRAFT = "DRAFT"
    ANALYZING = "ANALYZING"
    ANALYZED = "ANALYZED"
    AWAITING_CLARIFICATION = "AWAITING_CLARIFICATION"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    FINALIZED = "FINALIZED"
    FAILED = "FAILED"


class OriginType(str, Enum):
    """Provenance origin — how a datum entered the system."""
    EXPLICIT_JD = "EXPLICIT_JD"           # Verbatim text from the uploaded JD
    EKG_DERIVED = "EKG_DERIVED"           # Derived by EKG graph traversal (never MUST_HAVE)
    LLM_HYPOTHESIS = "LLM_HYPOTHESIS"    # LLM-suggested interpretation (never MUST_HAVE)
    TA_CONFIRMED = "TA_CONFIRMED"         # Explicitly confirmed by a TA
    TA_MANUAL_EDIT = "TA_MANUAL_EDIT"     # TA directly edited the field value


class RequirementPriority(str, Enum):
    """Atomic requirement classification (supports both Intern 1 & Intern 2 naming)."""
    MUST_HAVE = "MUST_HAVE"
    MANDATORY = "MANDATORY"              # Intern 1 synonym for MUST_HAVE
    PREFERRED = "PREFERRED"
    INFORMATIONAL = "INFORMATIONAL"
    CONTEXTUAL = "CONTEXTUAL"            # Intern 1 synonym for INFORMATIONAL/UNRESOLVED
    UNRESOLVED = "UNRESOLVED"            # Conservative fallback for ambiguous phrasing


class LogicOperator(str, Enum):
    """Boolean logic operator for disjunction/conjunction groups."""
    OR = "OR"
    AND = "AND"


class ConfidenceBand(str, Enum):
    """Ordinal confidence level."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


# ConfidenceLevel is an alias/enum matching ConfidenceBand for Intern 1 compatibility
class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class ClauseType(str, Enum):
    """Syntactic/semantic classification of a JD clause (Intern 1)."""
    REQUIREMENT = "REQUIREMENT"
    RESPONSIBILITY = "RESPONSIBILITY"
    CONTEXT = "CONTEXT"
    METADATA = "METADATA"
    AMBIGUOUS = "AMBIGUOUS"


class ResponsibilityTier(str, Enum):
    """Three-tier hierarchy for extracted responsibilities (Intern 1)."""
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    SITUATIONAL = "SITUATIONAL"


class EKGEntityType(str, Enum):
    """Ontology categories for the Enterprise Knowledge Graph (Intern 1)."""
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    TOOL = "tool"
    SKILL = "skill"
    DOMAIN = "domain"
    ROLE = "role"


class InterpretationStatus(str, Enum):
    """Status of a responsibility interpretation."""
    DETERMINISTIC_DERIVED = "DETERMINISTIC_DERIVED"  # From EKG traversal
    UNCONFIRMED_HYPOTHESIS = "UNCONFIRMED_HYPOTHESIS"  # LLM suggestion, needs TA
    TA_CONFIRMED = "TA_CONFIRMED"                     # Confirmed by TA
    NOT_INTERPRETED = "NOT_INTERPRETED"               # No interpretation attempted


class QuestionStatus(str, Enum):
    """Lifecycle state of a clarification question."""
    UNANSWERED = "UNANSWERED"
    ANSWERED = "ANSWERED"
    SKIPPED = "SKIPPED"                     # TA deliberately skipped
    EXPLICITLY_UNSPECIFIED = "EXPLICITLY_UNSPECIFIED"  # TA confirmed info does not exist


class QuestionPriority(str, Enum):
    """Tier classification of a clarification question."""
    BLOCKING = "BLOCKING"           # Must resolve to finalize
    RECOMMENDED = "RECOMMENDED"     # Non-blocking; has fallback if unanswered
    OPTIONAL = "OPTIONAL"           # Metadata; never blocks finalization


class QuestionCategory(str, Enum):
    """Domain category of the question."""
    CONTRADICTION = "CONTRADICTION"
    TECHNICAL_SCOPE = "TECHNICAL_SCOPE"
    ROLE_ALIGNMENT = "ROLE_ALIGNMENT"
    ORG_METADATA = "ORG_METADATA"
    COMPENSATION_LOGISTICS = "COMPENSATION_LOGISTICS"


# ---------------------------------------------------------------------------
# Shared Structural Models
# ---------------------------------------------------------------------------

class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class SourceReference(_Base):
    """Pointer to source evidence used across Intern 1 extraction components."""
    text: str = ""
    section: Optional[str] = None
    line_number: Optional[int] = None
    span_start: Optional[int] = None
    span_end: Optional[int] = None


class SourceSpan(_Base):
    """Precise pointer back to the verbatim JD text (Intern 2)."""
    raw_text: str = Field("", description="Verbatim text from the JD that produced this datum.")
    section: Optional[str] = Field(None, description="JD section (e.g. 'Requirements', 'Responsibilities').")
    start_char: Optional[int] = Field(None, description="Character offset of the start of the span.")
    end_char: Optional[int] = Field(None, description="Character offset of the end of the span (exclusive).")

    @property
    def text(self) -> str:
        return self.raw_text


class ProvenanceRecord(_Base):
    """
    Immutable audit trail entry for a single datum.
    Every requirement, interpretation, and clarification answer must carry one.
    """
    origin_type: OriginType = OriginType.EXPLICIT_JD
    source_span: Optional[SourceSpan] = None
    author: Optional[str] = Field(None, description="User ID, system name, or LLM model identifier.")
    timestamp: datetime = Field(default_factory=_utcnow)
    rule_id: Optional[str] = Field(None, description="Deterministic rule or EKG edge that produced this datum.")


class ConfidenceBreakdown(_Base):
    """
    Dual-confidence scoring.
    These two scores are kept strictly separate and NEVER conflated.
    """
    entity_match_confidence: ConfidenceBand = Field(
        ConfidenceBand.MEDIUM,
        description="How confident is the EKG entity resolution for the tokens in the source span.",
    )
    interpretation_confidence: ConfidenceBand = Field(
        ConfidenceBand.UNKNOWN,
        description="How confident is the functional interpretation of what this requirement implies.",
    )


class EKGEntity(_Base):
    """A node in the Enterprise Knowledge Graph (Intern 1)."""
    entity_id: str
    name: str
    entity_type: EKGEntityType
    aliases: List[str] = Field(default_factory=list)
    source: str = "seed_data_v1"
    confidence: float = 1.0


class JDSection(_Base):
    """A structural section of the JD extracted deterministically (Intern 1)."""
    section_id: str
    title: Optional[str] = None
    content: str = ""
    section_type: str = "general"
    line_start: int = 1
    line_end: int = 1


class ExtractedParameter(_Base):
    """A scalar job parameter extracted from JD text (Intern 1)."""
    parameter_name: str
    value: Any
    category: str = "general"
    is_explicit: bool = True
    source: Optional[Union[SourceReference, SourceSpan]] = None


class DetectedAmbiguity(_Base):
    """A detected ambiguity requiring TA/HR clarification (Intern 1)."""
    ambiguity_id: str
    text: str
    reason: str
    suggested_interpretations: List[str] = Field(default_factory=list)
    requires_ta_confirmation: bool = True
    source: Optional[Union[SourceReference, SourceSpan]] = None


class MatchedEntity(_Base):
    """An EKG entity matched to a token span in the JD text."""
    node_id: str
    node_type: str = Field(..., description="e.g. 'Language', 'Framework', 'Platform'")
    canonical_name: str
    match_confidence: ConfidenceBand = ConfidenceBand.MEDIUM
    aliases_matched: List[str] = Field(default_factory=list)


class GraphActivity(_Base):
    """An activity derived from EKG traversal (never a MUST_HAVE requirement)."""
    activity_description: str
    derived_from_node_id: str
    relation_type: str = Field(..., description="e.g. 'used_for', 'requires', 'related_to'")
    confidence: ConfidenceBand = ConfidenceBand.MEDIUM


# ---------------------------------------------------------------------------
# Extraction-Layer Models (Unifying Intern 1 & Intern 2)
# ---------------------------------------------------------------------------

class StructuredRequirement(_Base):
    """
    Authoritative requirement model.
    Satisfies both Intern 1's extraction pipeline output and Intern 2's master domain model.
    """
    id: str = Field(default_factory=_new_id)
    text: str = Field(..., description="Clean atomic requirement text, one concept per instance.")
    clause_type: Optional[ClauseType] = None
    priority: RequirementPriority = RequirementPriority.UNRESOLVED
    confidence: ConfidenceBreakdown = Field(default_factory=ConfidenceBreakdown)
    provenance: ProvenanceRecord = Field(default_factory=ProvenanceRecord)
    ekg_node_ids: List[str] = Field(
        default_factory=list,
        description="EKG node IDs matched to entities in this requirement.",
    )
    matched_entities: List[str] = Field(default_factory=list)
    entity_confidence: Dict[str, float] = Field(default_factory=dict)
    source: Optional[Union[SourceReference, SourceSpan]] = None
    is_explicit: bool = True
    requires_clarification: bool = False
    is_mandatory: bool = Field(
        False,
        description=(
            "True ONLY when origin_type is EXPLICIT_JD or TA_CONFIRMED. "
            "EKG_DERIVED and LLM_HYPOTHESIS origins MUST always be False here. "
            "This is the Traceable Origin Invariant."
        ),
    )
    min_years: Optional[float] = None
    max_years: Optional[float] = None
    negated: bool = False

    @model_validator(mode="before")
    @classmethod
    def _normalize_intern_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Map requirement_id to id
            if "requirement_id" in data and "id" not in data:
                data["id"] = data["requirement_id"]

            # Map matched_entities to ekg_node_ids
            if "matched_entities" in data and ("ekg_node_ids" not in data or not data["ekg_node_ids"]):
                data["ekg_node_ids"] = list(data["matched_entities"])

            # Map ekg_node_ids to matched_entities
            if "ekg_node_ids" in data and ("matched_entities" not in data or not data["matched_entities"]):
                data["matched_entities"] = list(data["ekg_node_ids"])

            # Build provenance from source if provenance is missing
            if "provenance" not in data or data["provenance"] is None:
                src = data.get("source")
                is_explicit = data.get("is_explicit", True)
                origin = OriginType.EXPLICIT_JD if is_explicit else OriginType.EKG_DERIVED
                source_span = None
                if src:
                    if isinstance(src, dict):
                        source_span = SourceSpan(
                            raw_text=src.get("text", ""),
                            section=src.get("section"),
                        )
                    elif hasattr(src, "text"):
                        source_span = SourceSpan(
                            raw_text=src.text,
                            section=getattr(src, "section", None),
                        )
                data["provenance"] = ProvenanceRecord(
                    origin_type=origin,
                    source_span=source_span,
                    rule_id="deterministic_extractor",
                )

            # Auto-assign is_mandatory if not explicitly given
            if "is_mandatory" not in data:
                p = data.get("priority")
                if p in (RequirementPriority.MUST_HAVE, RequirementPriority.MANDATORY, "MUST_HAVE", "MANDATORY"):
                    prov = data.get("provenance")
                    origin = getattr(prov, "origin_type", None) if not isinstance(prov, dict) else prov.get("origin_type")
                    if origin in (OriginType.EXPLICIT_JD, OriginType.TA_CONFIRMED, "EXPLICIT_JD", "TA_CONFIRMED"):
                        data["is_mandatory"] = True
                    else:
                        data["is_mandatory"] = False
                else:
                    data["is_mandatory"] = False
        return data

    @model_validator(mode="after")
    def _enforce_invariants_and_sync(self) -> "StructuredRequirement":
        """
        Enforce Traceable Origin Invariant and synchronize backward-compatible fields.
        """
        # Ensure source is always present for Intern 1 consumers
        if self.source is None:
            if self.provenance and self.provenance.source_span and self.provenance.source_span.raw_text:
                self.source = SourceReference(
                    text=self.provenance.source_span.raw_text,
                    section=self.provenance.source_span.section,
                )
            elif self.text:
                self.source = SourceReference(text=self.text)

        # Ensure matched_entities and ekg_node_ids stay synchronized
        if not self.matched_entities and self.ekg_node_ids:
            self.matched_entities = list(self.ekg_node_ids)
        elif not self.ekg_node_ids and self.matched_entities:
            self.ekg_node_ids = list(self.matched_entities)

        # Traceable Origin Invariant
        unsafe_origins = {OriginType.EKG_DERIVED, OriginType.LLM_HYPOTHESIS}
        if self.provenance.origin_type in unsafe_origins and self.is_mandatory:
            raise ValueError(
                f"Traceable Origin Invariant violated: origin_type={self.provenance.origin_type!r} "
                f"cannot set is_mandatory=True. Only EXPLICIT_JD or TA_CONFIRMED may."
            )
        return self

    @property
    def requirement_id(self) -> str:
        return self.id

    @requirement_id.setter
    def requirement_id(self, val: str) -> None:
        self.id = val


class DisjunctionGroup(_Base):
    """
    Represents a boolean logic group (OR/AND).
    Supports both Intern 1 list-of-strings and Intern 2 nested requirement objects.
    """
    id: str = Field(default_factory=_new_id)
    operator: Union[LogicOperator, str] = LogicOperator.OR
    requirements: List[Any] = Field(
        ...,
        description="Members of the logic group. May be requirement IDs or StructuredRequirement objects.",
        min_length=2,
    )
    interpretation: Optional[str] = None
    provenance: ProvenanceRecord = Field(default_factory=ProvenanceRecord)

    @model_validator(mode="before")
    @classmethod
    def _normalize_group(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "group_id" in data and "id" not in data:
                data["id"] = data["group_id"]
            if "provenance" not in data or data["provenance"] is None:
                data["provenance"] = ProvenanceRecord(
                    origin_type=OriginType.EXPLICIT_JD,
                    rule_id="boolean_parser",
                )
        return data

    @property
    def group_id(self) -> str:
        return self.id

    @group_id.setter
    def group_id(self, val: str) -> None:
        self.id = val


DisjunctionGroup.model_rebuild()


class ResponsibilityContext(_Base):
    """
    Authoritative responsibility statement with 3-tier interpretation context.
    Seamlessly satisfies both Intern 1 and Intern 2 schemas.
    """
    id: str = Field(default_factory=_new_id)
    raw_statement: str = Field("", description="Verbatim responsibility statement from the JD.")
    description: Optional[str] = Field(None, description="Description of the responsibility.")
    tier: ResponsibilityTier = ResponsibilityTier.PRIMARY
    required_capabilities: List[str] = Field(default_factory=list)
    rationale: str = ""
    source: Optional[Union[SourceReference, SourceSpan]] = None
    source_span: Optional[SourceSpan] = None
    interpretation_confidence: Optional[Union[ConfidenceLevel, ConfidenceBand, str]] = None

    # Tier 1 & 2 extra fields (Intern 2)
    matched_entities: List[Any] = Field(default_factory=list)
    graph_derived_activities: List[GraphActivity] = Field(default_factory=list)
    llm_hypothesis: Optional[str] = None
    requires_ta_confirmation: bool = False
    interpretation_status: InterpretationStatus = InterpretationStatus.NOT_INTERPRETED
    confidence: ConfidenceBreakdown = Field(default_factory=ConfidenceBreakdown)
    provenance: List[ProvenanceRecord] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_resp(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "responsibility_id" in data and "id" not in data:
                data["id"] = data["responsibility_id"]
            if "description" in data and ("raw_statement" not in data or not data["raw_statement"]):
                data["raw_statement"] = data["description"]
            elif "raw_statement" in data and ("description" not in data or not data["description"]):
                data["description"] = data["raw_statement"]

            # Map source / source_span
            src = data.get("source")
            span = data.get("source_span")
            if src and not span:
                raw_text = src.get("text", "") if isinstance(src, dict) else getattr(src, "text", "")
                section = src.get("section") if isinstance(src, dict) else getattr(src, "section", None)
                data["source_span"] = SourceSpan(raw_text=raw_text, section=section)
            elif span and not src:
                raw_text = span.get("raw_text", "") if isinstance(span, dict) else getattr(span, "raw_text", "")
                section = span.get("section") if isinstance(span, dict) else getattr(span, "section", None)
                data["source"] = SourceReference(text=raw_text, section=section)
        return data

    @model_validator(mode="after")
    def _sync_fields(self) -> "ResponsibilityContext":
        if not self.raw_statement and self.description:
            self.raw_statement = self.description
        if not self.description and self.raw_statement:
            self.description = self.raw_statement

        if self.source is None:
            if self.source_span:
                self.source = SourceReference(
                    text=self.source_span.raw_text,
                    section=self.source_span.section,
                )
            elif self.raw_statement:
                self.source = SourceReference(text=self.raw_statement)

        if self.source_span is None and self.source:
            self.source_span = SourceSpan(
                raw_text=self.source.text if hasattr(self.source, "text") else str(self.source),
                section=getattr(self.source, "section", None),
            )
        return self

    @property
    def responsibility_id(self) -> str:
        return self.id

    @responsibility_id.setter
    def responsibility_id(self, val: str) -> None:
        self.id = val


class ExtractionResult(_Base):
    """
    Complete typed extraction AST from Intern 1 extraction pipeline.
    Provides bridge to JDMasterContext for downstream processing.
    """
    sections: List[JDSection] = Field(default_factory=list)
    requirements: List[Any] = Field(default_factory=list)
    disjunction_groups: List[Any] = Field(default_factory=list)
    responsibilities: List[Any] = Field(default_factory=list)
    parameters: List[ExtractedParameter] = Field(default_factory=list)
    ambiguities: List[DetectedAmbiguity] = Field(default_factory=list)
    extraction_mode: str = "deterministic"
    llm_enabled: bool = False
    ekg_entities_matched: int = 0
    ekg_coverage_score: float = 0.0

    def to_master_context(self, jd_id: Optional[str] = None, raw_jd_text: str = "") -> "JDMasterContext":
        """
        Convert this ExtractionResult into an authoritative JDMasterContext.
        """
        if not raw_jd_text and self.sections:
            raw_jd_text = "\n\n".join(s.content for s in self.sections if s.content)

        role_overview = RoleOverview()
        job_context = JobContextInfo()

        for param in self.parameters:
            name = param.parameter_name.lower()
            val = str(param.value)
            if "title" in name:
                role_overview.job_title = val
            elif "location" in name:
                role_overview.location_city = val
            elif "work_mode" in name:
                role_overview.work_mode = val.upper()
            elif "seniority" in name:
                role_overview.seniority = val
            elif "department" in name:
                role_overview.department = val
            elif "company" in name:
                job_context.company_context = val
            elif "team_size" in name:
                job_context.team_size = val

        # Map requirements and disjunction groups
        master_reqs: List[Union[StructuredRequirement, DisjunctionGroup]] = []
        for req in self.requirements:
            if isinstance(req, StructuredRequirement):
                master_reqs.append(req)
            elif isinstance(req, dict):
                master_reqs.append(StructuredRequirement.model_validate(req))

        for dg in self.disjunction_groups:
            if isinstance(dg, DisjunctionGroup):
                master_reqs.append(dg)
            elif isinstance(dg, dict):
                master_reqs.append(DisjunctionGroup.model_validate(dg))

        # Map responsibilities
        master_resps: List[ResponsibilityContext] = []
        for resp in self.responsibilities:
            if isinstance(resp, ResponsibilityContext):
                master_resps.append(resp)
            elif isinstance(resp, dict):
                master_resps.append(ResponsibilityContext.model_validate(resp))

        # Map detected ambiguities
        master_ambs: List[DetectedAmbiguity] = []
        for amb in self.ambiguities:
            if isinstance(amb, DetectedAmbiguity):
                master_ambs.append(amb)
            elif isinstance(amb, dict):
                master_ambs.append(DetectedAmbiguity.model_validate(amb))

        master = JDMasterContext(
            jd_id=jd_id or _new_id(),
            raw_jd_text=raw_jd_text,
            role_overview=role_overview,
            job_context=job_context,
            requirements=master_reqs,
            responsibilities=master_resps,
            raw_ambiguities=master_ambs,
        )
        return master


# ---------------------------------------------------------------------------
# Clarification Layer (Intern 2 owns fully)
# ---------------------------------------------------------------------------

class ClarificationOptionSchema(_Base):
    """Structured option for a clarification question (label + explanation)."""
    label: str = Field(..., description="Short title of the option.")
    description: str = Field(..., description="Conversational explanation of what this option implies.")


class ClarificationQuestionSchema(_Base):
    """
    A single clarification question generated by Intern 2's clarification engine.
    Persisted in the DB via ClarificationQuestion table; this is the Pydantic view.
    """
    id: str = Field(default_factory=_new_id)
    question_key: str = Field(
        ...,
        description="Stable machine key, e.g. 'tech_scope_virtual_platform_0'. Used for idempotent updates.",
    )
    category: QuestionCategory
    priority: QuestionPriority
    is_blocking: bool = Field(
        ...,
        description="Computed. True iff priority=BLOCKING and status not in {ANSWERED, EXPLICITLY_UNSPECIFIED}.",
    )
    field_target: str = Field(..., description="JSON path in JDMasterContext this answer will patch.")
    question_text: str
    rationale: str = Field(..., description="Why this question is being asked.")
    suggested_options: List[str] = Field(default_factory=list)
    short_topic: Optional[str] = Field(None, description="Short topic name for tab navigation.")
    structured_options: List[ClarificationOptionSchema] = Field(default_factory=list, description="Structured options with label and description.")
    status: QuestionStatus = QuestionStatus.UNANSWERED
    answer_text: Optional[str] = None
    answered_by: Optional[str] = None
    answered_at: Optional[datetime] = None
    override_record: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Populated when a BLOCKING question is skipped with an authorized override. "
            "Must include: authorized_by, override_reason, timestamp."
        ),
    )
    created_at: datetime = Field(default_factory=_utcnow)


class AuditEntry(_Base):
    """Single chronological entry in the JDMasterContext audit trail."""
    event_type: str = Field(..., description="e.g. 'status_transition', 'clarification_answered', 'patch_applied'")
    description: str
    actor: Optional[str] = None
    timestamp: datetime = Field(default_factory=_utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ComplianceFlagContext(_Base):
    """A compliance issue detected in the JD with full provenance."""
    flagged_text: str
    concern: str
    category: str = Field("other", description="e.g. age, gender, disability, marital_status, other")
    recommended_action: str = "Flag for TA review. Do not use in automated scoring."
    provenance: ProvenanceRecord = Field(default_factory=ProvenanceRecord)


# ---------------------------------------------------------------------------
# Role & Job Context (Intern 1 populates; Intern 2 can patch via clarification)
# ---------------------------------------------------------------------------

class RoleOverview(_Base):
    """High-level role metadata extracted from the JD header/overview sections."""
    job_title: Optional[str] = None
    seniority: Optional[str] = None
    department: Optional[str] = None
    location_city: Optional[str] = None
    location_country: Optional[str] = None
    work_mode: str = "UNSPECIFIED"   # ONSITE | HYBRID | REMOTE | UNSPECIFIED
    office_attendance: Optional[str] = None
    relocation_required: Optional[bool] = None


class JobContextInfo(_Base):
    """Company and team context. team_size and salary are non-blocking optional."""
    company_context: Optional[str] = None
    business_context: Optional[str] = None
    environment: Optional[str] = None
    team_size: Optional[str] = None
    team_size_explicitly_unspecified: bool = False
    salary_range: Optional[str] = None
    salary_explicitly_unspecified: bool = False


# ---------------------------------------------------------------------------
# JDMasterContext — The Single Source of Truth
# ---------------------------------------------------------------------------

class JDMasterContext(_Base):
    """
    The authoritative, lossless persistent domain model for a Job Description.

    Lifecycle:
      DRAFT -> ANALYZING -> ANALYZED -> AWAITING_CLARIFICATION
            -> READY_FOR_REVIEW -> FINALIZED

    Invariants enforced:
      1. must_have_requirements only contains items with EXPLICIT_JD or TA_CONFIRMED provenance.
      2. EKG-derived and LLM-hypothesised data live ONLY in responsibilities[].graph_derived_activities
         and the INFORMATIONAL tier; they never enter must_have_requirements.
      3. Finalization is only permitted when no BLOCKING question is UNANSWERED or SKIPPED
         without an authorized override.
    """
    jd_id: str = Field(default_factory=_new_id)
    version: int = Field(1, description="Increments on each revision (v1, v2, ...).")
    lifecycle_status: JDLifecycleStatus = JDLifecycleStatus.DRAFT
    raw_jd_text: str = Field(..., description="The original full JD text, immutable after upload.")
    checksum: str = Field(
        "",
        description="SHA-256 of raw_jd_text. Computed on creation. Used for change-detection dedup.",
    )

    # --- Role & Context (Intern 1 extraction populates; Intern 2 can patch) ---
    role_overview: RoleOverview = Field(default_factory=RoleOverview)
    job_context: JobContextInfo = Field(default_factory=JobContextInfo)

    # --- Requirements (Intern 1 extraction populates) ---
    requirements: List[Union[StructuredRequirement, DisjunctionGroup]] = Field(
        default_factory=list,
        description=(
            "Flat list where each item is either a StructuredRequirement or a DisjunctionGroup. "
            "DisjunctionGroups preserve OR/AND boolean structure from the JD."
        ),
    )

    # --- Responsibilities (Intern 1 extraction populates) ---
    responsibilities: List[ResponsibilityContext] = Field(default_factory=list)

    # --- Detected Ambiguities (Intern 1 extraction populates) ---
    raw_ambiguities: List[DetectedAmbiguity] = Field(default_factory=list)

    # --- Clarification Loop (Intern 2 owns fully) ---
    clarification_history: List[ClarificationQuestionSchema] = Field(default_factory=list)

    # --- Compliance ---
    compliance_flags: List[ComplianceFlagContext] = Field(default_factory=list)

    # --- Audit ---
    audit_trail: List[AuditEntry] = Field(
        default_factory=list,
        description="Chronological, append-only log of all state-changing events.",
    )

    # --- Timestamps ---
    created_at: datetime = Field(default_factory=_utcnow)
    finalized_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _compute_checksum(self) -> "JDMasterContext":
        if not self.checksum and self.raw_jd_text:
            self.checksum = hashlib.sha256(self.raw_jd_text.encode("utf-8")).hexdigest()
        return self

    # ------------------------------------------------------------------
    # Convenience Properties
    # ------------------------------------------------------------------

    @property
    def must_have_requirements(self) -> List[StructuredRequirement]:
        """
        Returns ONLY requirements that pass the Traceable Origin Invariant:
        EXPLICIT_JD or TA_CONFIRMED provenance with is_mandatory=True.
        EKG-derived items are categorically excluded.
        """
        result: List[StructuredRequirement] = []
        for item in self.requirements:
            if isinstance(item, StructuredRequirement):
                if (
                    item.is_mandatory
                    and item.provenance.origin_type in {OriginType.EXPLICIT_JD, OriginType.TA_CONFIRMED}
                ):
                    result.append(item)
            elif isinstance(item, DisjunctionGroup):
                result.extend(_collect_mandatory_from_group(item))
        return result

    @property
    def unresolved_blocking_questions(self) -> List[ClarificationQuestionSchema]:
        """All BLOCKING questions that are not yet resolved."""
        return [
            q for q in self.clarification_history
            if q.priority == QuestionPriority.BLOCKING
            and q.status in {QuestionStatus.UNANSWERED, QuestionStatus.SKIPPED}
            and q.override_record is None
        ]

    @property
    def is_ready_to_finalize(self) -> bool:
        """True iff the JD has zero unresolved blocking questions."""
        return len(self.unresolved_blocking_questions) == 0

    def add_audit_entry(
        self,
        event_type: str,
        description: str,
        actor: Optional[str] = None,
        **metadata: Any,
    ) -> None:
        """Append a chronological audit event. Call before every state-changing operation."""
        self.audit_trail.append(AuditEntry(
            event_type=event_type,
            description=description,
            actor=actor,
            metadata=metadata,
        ))


def _collect_mandatory_from_group(group: DisjunctionGroup) -> List[StructuredRequirement]:
    """Recursively collect mandatory requirements from a DisjunctionGroup."""
    result: List[StructuredRequirement] = []
    for item in group.requirements:
        if isinstance(item, StructuredRequirement):
            if (
                item.is_mandatory
                and item.provenance.origin_type in {OriginType.EXPLICIT_JD, OriginType.TA_CONFIRMED}
            ):
                result.append(item)
        elif isinstance(item, DisjunctionGroup):
            result.extend(_collect_mandatory_from_group(item))
    return result
