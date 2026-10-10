"""
master_context.py — Authoritative persistent domain model for the JD Lifecycle.

Invariants enforced here:
  1. Traceable Origin: Every requirement carries a ProvenanceRecord.
  2. Dual-Confidence: entity_match_confidence and interpretation_confidence are
     always tracked independently.
  3. Lossless Internal State: This schema stores ALL internal state (graph
     bindings, Q&A audit history, clarification loop). It is never lossy.
  4. Intern 1 Boundary: Intern 1 must produce StructuredRequirement,
     DisjunctionGroup, and ResponsibilityContext conforming to this file.
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
    """Atomic requirement classification."""
    MUST_HAVE = "MUST_HAVE"
    PREFERRED = "PREFERRED"
    INFORMATIONAL = "INFORMATIONAL"
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


class SourceSpan(_Base):
    """Precise pointer back to the verbatim JD text."""
    raw_text: str = Field("", description="Verbatim text from the JD that produced this datum.")
    section: Optional[str] = Field(None, description="JD section (e.g. 'Requirements', 'Responsibilities').")
    start_char: Optional[int] = Field(None, description="Character offset of the start of the span.")
    end_char: Optional[int] = Field(None, description="Character offset of the end of the span (exclusive).")


class ProvenanceRecord(_Base):
    """
    Immutable audit trail entry for a single datum.
    Every requirement, interpretation, and clarification answer must carry one.
    """
    origin_type: OriginType
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


# ---------------------------------------------------------------------------
# Extraction-Layer Models (Intern 1 produces these)
# ---------------------------------------------------------------------------

class StructuredRequirement(_Base):
    """
    INTERN 1 BOUNDARY: Intern 1's extraction layer must produce instances of
    this class for every atomic requirement identified in the JD.

    One StructuredRequirement = one atomic requirement clause (no compound clauses).
    Experience years are scoped to the DOMAIN they were stated with; skills
    mentioned in the same clause receive min_years=None unless stated explicitly.
    """
    id: str = Field(default_factory=_new_id)
    text: str = Field(..., description="Clean atomic requirement text, one concept per instance.")
    priority: RequirementPriority = RequirementPriority.UNRESOLVED
    confidence: ConfidenceBreakdown = Field(default_factory=ConfidenceBreakdown)
    provenance: ProvenanceRecord
    ekg_node_ids: List[str] = Field(
        default_factory=list,
        description="EKG node IDs matched to entities in this requirement.",
    )
    is_mandatory: bool = Field(
        False,
        description=(
            "True ONLY when origin_type is EXPLICIT_JD or TA_CONFIRMED. "
            "EKG_DERIVED and LLM_HYPOTHESIS origins MUST always be False here. "
            "This is the Traceable Origin Invariant."
        ),
    )
    # Structured experience scoping
    min_years: Optional[float] = Field(
        None,
        description=(
            "Minimum years required for THIS specific requirement's domain. "
            "E.g. '5+ years backend' sets min_years=5.0 on the backend requirement only; "
            "Python mentioned in the same clause gets min_years=None."
        ),
    )
    max_years: Optional[float] = None
    negated: bool = Field(
        False,
        description="True when the clause contains negation scoping this requirement (e.g. 'Python is not mandatory').",
    )

    @model_validator(mode="after")
    def _enforce_traceable_origin_invariant(self) -> "StructuredRequirement":
        """
        Traceable Origin Invariant check:
        EKG_DERIVED and LLM_HYPOTHESIS sources must NEVER mark is_mandatory=True.
        """
        unsafe_origins = {OriginType.EKG_DERIVED, OriginType.LLM_HYPOTHESIS}
        if self.provenance.origin_type in unsafe_origins and self.is_mandatory:
            raise ValueError(
                f"Traceable Origin Invariant violated: origin_type={self.provenance.origin_type!r} "
                f"cannot set is_mandatory=True. Only EXPLICIT_JD or TA_CONFIRMED may."
            )
        return self


class DisjunctionGroup(_Base):
    """
    INTERN 1 BOUNDARY: Represents a boolean logic group (OR/AND).
    E.g. '(Verilog OR VHDL)' is preserved as a DisjunctionGroup with operator=OR,
    NOT flattened into two separate StructuredRequirements.
    """
    id: str = Field(default_factory=_new_id)
    operator: LogicOperator
    requirements: List[Union[StructuredRequirement, "DisjunctionGroup"]] = Field(
        ...,
        description="Members of the logic group. May be nested DisjunctionGroups.",
        min_length=2,
    )
    provenance: ProvenanceRecord


# Required for the self-referential model
DisjunctionGroup.model_rebuild()


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


class ResponsibilityContext(_Base):
    """
    INTERN 1 BOUNDARY: One responsibility statement from the JD with full
    3-tier interpretation context.

    Tier 1 (Deterministic): matched_entities and graph_derived_activities — from EKG.
    Tier 2 (Optional LLM): llm_hypothesis — disabled by default.
    Tier 3 (TA Confirmed): interpretation_status upgraded to TA_CONFIRMED.
    """
    id: str = Field(default_factory=_new_id)
    raw_statement: str = Field(..., description="Verbatim responsibility statement from the JD.")
    source_span: SourceSpan

    # Tier 1 — EKG outputs (Intern 1 populates these)
    matched_entities: List[MatchedEntity] = Field(default_factory=list)
    graph_derived_activities: List[GraphActivity] = Field(
        default_factory=list,
        description=(
            "EKG-derived activities implied by this responsibility. "
            "These are NEVER copied into must_have_requirements; "
            "they are context only."
        ),
    )

    # Tier 2 — LLM hypothesis (disabled by default, Intern 1 populates if enabled)
    llm_hypothesis: Optional[str] = Field(
        None,
        description="LLM-suggested interpretation. Only present when ENABLE_LLM_INTERPRETATION=True.",
    )
    requires_ta_confirmation: bool = False

    # Tier 3 — TA confirmation (Intern 2 clarification updater sets this)
    interpretation_status: InterpretationStatus = InterpretationStatus.NOT_INTERPRETED
    confidence: ConfidenceBreakdown = Field(default_factory=ConfidenceBreakdown)
    provenance: List[ProvenanceRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Clarification Layer (Intern 2 owns fully)
# ---------------------------------------------------------------------------

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
    provenance: ProvenanceRecord


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
    # These two carry explicit-unspecified tracking
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
