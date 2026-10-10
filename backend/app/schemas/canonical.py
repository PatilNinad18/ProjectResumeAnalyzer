"""
Canonical Candidate Evaluation Specification schema.

This is the SINGLE SOURCE OF TRUTH for the JD Understanding pipeline.
- The LLM is prompted to produce this object.
- job_specification.md is rendered FROM this object.
- job_specification.json is serialized FROM this object.

Robustness note
---------------
Small local models (e.g. qwen3:4b) routinely get shapes slightly wrong:
objects inside list[str], "title" instead of "job_title", null for lists,
"Required" instead of "MUST_HAVE", and so on. Instead of failing the whole
analysis with a ValidationError, every field here has a *before* validator
that coerces the common mistakes into the canonical shape. Unknown keys are
ignored, empty/meaningless items are pruned, and nothing is invented.
"""
from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from functools import lru_cache
from typing import Annotated, Any, Callable, Dict, List, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator


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
# Coercion helpers
# ---------------------------------------------------------------------------

_TEXT_KEYS = ("description", "name", "text", "value", "statement", "requirement", "title", "language", "skill", "category")
_LANG_KEYS = ("language", "name", "category", "description", "text")


def _pick(item: Any, keys=_TEXT_KEYS) -> str:
    """Turn anything (str / number / dict / list) into a clean string."""
    if item is None:
        return ""
    if isinstance(item, str):
        s = item.strip()
        # The model sometimes echoes a prompt placeholder such as "<skill or technology>".
        return "" if (s.startswith("<") and s.endswith(">")) else s
    if isinstance(item, bool):
        return str(item).lower()
    if isinstance(item, (int, float)):
        return str(item)
    if isinstance(item, dict):
        for k in keys:
            val = item.get(k)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return "; ".join(s for s in (_pick(v, keys) for v in item.values()) if s)
    if isinstance(item, (list, tuple, set)):
        return "; ".join(s for s in (_pick(v, keys) for v in item) if s)
    return str(item)


def _to_str(v: Any) -> str:
    return _pick(v)


def _to_opt_str(v: Any) -> Optional[str]:
    return _pick(v) or None


def _str_list(keys=_TEXT_KEYS) -> Callable[[Any], List[str]]:
    def _v(v: Any) -> List[str]:
        if v is None:
            return []
        if not isinstance(v, (list, tuple, set)):
            v = [v]
        out: List[str] = []
        seen = set()
        for item in v:
            s = _pick(item, keys)
            k = s.lower()
            if s and k not in seen:  # also de-duplicates repeated items
                seen.add(k)
                out.append(s)
        return out
    return _v


def _to_float(v: Any) -> Optional[float]:
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"\d+(?:\.\d+)?", str(v))
    return float(m.group()) if m else None


def _to_bool(v: Any) -> Optional[bool]:
    if v is None or isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "yes", "y", "required", "1"):
        return True
    if s in ("false", "no", "n", "not required", "0"):
        return False
    return None


def _to_source(v: Any) -> Any:
    if v is None or v == "":
        return None
    if isinstance(v, dict):
        return v
    return {"text": _pick(v)}


def _enum(enum_cls, default, aliases: Optional[Dict[str, Any]] = None) -> Callable[[Any], Any]:
    aliases = {k.upper().replace("-", "_").replace(" ", "_"): v for k, v in (aliases or {}).items()}

    def _v(v: Any):
        if isinstance(v, enum_cls):
            return v
        if v is None:
            return default
        s = str(v).strip()
        for m in enum_cls:
            if s.lower() in (m.value.lower(), m.name.lower()):
                return m
        return aliases.get(s.upper().replace("-", "_").replace(" ", "_"), default)
    return _v


_PRIORITY_ALIASES = {
    "REQUIRED": Priority.MUST_HAVE, "MANDATORY": Priority.MUST_HAVE, "ESSENTIAL": Priority.MUST_HAVE,
    "MUST": Priority.MUST_HAVE, "CRITICAL": Priority.MUST_HAVE, "HIGH": Priority.MUST_HAVE,
    "NICE_TO_HAVE": Priority.PREFERRED, "OPTIONAL": Priority.PREFERRED, "BONUS": Priority.PREFERRED,
    "PLUS": Priority.PREFERRED, "DESIRABLE": Priority.PREFERRED, "PREFERABLE": Priority.PREFERRED,
    "MEDIUM": Priority.PREFERRED, "LOW": Priority.INFORMATIONAL,
}
_WORKMODE_ALIASES = {
    "ON_SITE": WorkMode.ONSITE, "ON-SITE": WorkMode.ONSITE, "OFFICE": WorkMode.ONSITE,
    "IN_OFFICE": WorkMode.ONSITE, "WFH": WorkMode.REMOTE, "WORK_FROM_HOME": WorkMode.REMOTE,
    "HYBRID_WORK": WorkMode.HYBRID, "NOT_SPECIFIED": WorkMode.UNSPECIFIED, "UNKNOWN": WorkMode.UNSPECIFIED,
}

Str = Annotated[str, BeforeValidator(_to_str)]
OptStr = Annotated[Optional[str], BeforeValidator(_to_opt_str)]
StrList = Annotated[List[str], BeforeValidator(_str_list())]
LangList = Annotated[List[str], BeforeValidator(_str_list(_LANG_KEYS))]
OptFloat = Annotated[Optional[float], BeforeValidator(_to_float)]
OptBool = Annotated[Optional[bool], BeforeValidator(_to_bool)]
PriorityT = Annotated[Priority, BeforeValidator(_enum(Priority, Priority.AMBIGUOUS, _PRIORITY_ALIASES))]
ExplicitT = Annotated[ExplicitOrDerived, BeforeValidator(_enum(ExplicitOrDerived, ExplicitOrDerived.DERIVED))]
ConfidenceT = Annotated[ConfidenceLevel, BeforeValidator(_enum(ConfidenceLevel, ConfidenceLevel.MEDIUM))]
WorkModeT = Annotated[WorkMode, BeforeValidator(_enum(WorkMode, WorkMode.UNSPECIFIED, _WORKMODE_ALIASES))]


def _items(builder: Callable[[str], Dict[str, Any]]) -> Callable[[Any], List[Dict[str, Any]]]:
    """List of objects; bare strings are promoted to objects, junk is dropped."""
    def _v(v: Any) -> List[Dict[str, Any]]:
        if v is None:
            return []
        if isinstance(v, (str, dict)):
            v = [v]
        if not isinstance(v, (list, tuple)):
            return []
        out: List[Dict[str, Any]] = []
        for it in v:
            if isinstance(it, dict):
                out.append(it)
            elif hasattr(it, "model_dump"):
                out.append(it.model_dump())
            elif isinstance(it, str) and it.strip():
                out.append(builder(it.strip()))
        return out
    return _v


def _obj(builder: Optional[Callable[[str], Dict[str, Any]]] = None) -> Callable[[Any], Dict[str, Any]]:
    def _v(v: Any) -> Dict[str, Any]:
        if isinstance(v, dict):
            return v
        if isinstance(v, str) and v.strip() and builder:
            return builder(v.strip())
        return {}
    return _v


def _alias(d: Dict[str, Any], target: str, *names: str) -> None:
    if d.get(target) in (None, "", []):
        for n in names:
            if d.get(n) not in (None, "", []):
                d[target] = d[n]
                return


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------

class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class SourceRef(_Base):
    """Traceability back to the raw JD text."""
    text: Str = Field("", description="Verbatim (or lightly trimmed) source snippet from the JD.")
    section: OptStr = Field(None, description="JD section this snippet was found in, if identifiable.")
    location: OptStr = Field(None, description="Page/line/offset hint, if available.")


OptSource = Annotated[Optional[SourceRef], BeforeValidator(_to_source)]


class EvidenceSpec(_Base):
    """What candidate evidence downstream Candidate Analysis should look for and how to weigh it."""
    requirement: Str = ""
    priority: PriorityT = Priority.AMBIGUOUS
    explicit_or_derived: ExplicitT = ExplicitOrDerived.DERIVED
    evidence_to_look_for: StrList = Field(default_factory=list)
    strong_evidence: OptStr = None
    moderate_evidence: OptStr = None
    weak_evidence: OptStr = None
    insufficient_evidence: OptStr = Field(
        None, description="What counts as insufficient evidence -> should yield UNSCORED."
    )
    prohibited_inference: OptStr = Field(
        None, description="Explicit statement of what must NOT be inferred for this requirement."
    )
    confidence: ConfidenceT = ConfidenceLevel.MEDIUM
    source: OptSource = None

    @model_validator(mode="before")
    @classmethod
    def _fix(cls, d: Any) -> Any:
        if isinstance(d, dict):
            d = dict(d)
            _alias(d, "requirement", "description", "name", "title")
        return d


class RequirementInterpretation(_Base):
    """Explicit JD requirement vs. the derived evaluation interpretation."""
    explicit_requirement: Str = ""
    derived_interpretation: StrList = Field(default_factory=list)
    rationale: OptStr = None
    source: OptSource = None

    @model_validator(mode="before")
    @classmethod
    def _fix(cls, d: Any) -> Any:
        if isinstance(d, dict):
            d = dict(d)
            _alias(d, "explicit_requirement", "requirement", "statement", "description")
            _alias(d, "derived_interpretation", "interpretation", "interpretations", "derived")
        return d


class ResponsibilityRequirementMapping(_Base):
    responsibility: Str = ""
    required_capabilities: StrList = Field(default_factory=list)
    rationale: OptStr = None
    source: OptSource = None

    @model_validator(mode="before")
    @classmethod
    def _fix(cls, d: Any) -> Any:
        if isinstance(d, dict):
            d = dict(d)
            _alias(d, "responsibility", "requirement", "description")
            _alias(d, "required_capabilities", "capabilities", "requirements", "skills")
        return d


class NonConventionalParameter(_Base):
    parameter_name: Str = ""
    category: Str = ""
    why_it_is_relevant: Str = ""
    jd_evidence: Str = ""
    explicit_or_derived: ExplicitT = ExplicitOrDerived.DERIVED
    evaluation_guidance: Str = ""
    evidence_to_look_for: StrList = Field(default_factory=list)
    strong_evidence: OptStr = None
    moderate_evidence: OptStr = None
    weak_evidence: OptStr = None
    prohibited_inference: OptStr = None
    confidence: ConfidenceT = ConfidenceLevel.MEDIUM
    unscored_if: OptStr = Field(
        None, description="Condition under which this parameter should resolve to UNSCORED."
    )
    source: OptSource = None

    @model_validator(mode="before")
    @classmethod
    def _fix(cls, d: Any) -> Any:
        if isinstance(d, dict):
            d = dict(d)
            _alias(d, "parameter_name", "name", "parameter", "title")
        return d


class Ambiguity(_Base):
    statement: Str = ""
    why_ambiguous: Str = ""
    suggested_interpretation: OptStr = None
    evidence_required: StrList = Field(default_factory=list)
    ta_confirmation_required: bool = True
    source: OptSource = None

    @model_validator(mode="before")
    @classmethod
    def _fix(cls, d: Any) -> Any:
        if isinstance(d, dict):
            d = dict(d)
            _alias(d, "statement", "description", "text", "issue")
            _alias(d, "why_ambiguous", "reason", "rationale")
            if "ta_confirmation_required" in d:
                d["ta_confirmation_required"] = _to_bool(d["ta_confirmation_required"]) is not False
        return d


class ComplianceFlag(_Base):
    flagged_text: Str = ""
    concern: Str = Field("", description="e.g. 'possible age proxy via graduation year'")
    category: Str = Field("other", description="e.g. age, gender, disability, marital_status, other")
    recommended_action: Str = "Flag for TA review. Do not use in automated scoring."
    source: OptSource = None

    @model_validator(mode="before")
    @classmethod
    def _fix(cls, d: Any) -> Any:
        if isinstance(d, dict):
            d = dict(d)
            _alias(d, "flagged_text", "text", "statement", "description")
            if not d.get("recommended_action"):
                d.pop("recommended_action", None)
            if not d.get("category"):
                d.pop("category", None)
        return d


class RoleInfo(_Base):
    job_title: OptStr = None
    role: OptStr = None
    department: OptStr = None
    seniority: OptStr = None
    employment_type: OptStr = None
    reporting_structure: OptStr = None
    team_context: OptStr = None

    @model_validator(mode="before")
    @classmethod
    def _fix(cls, d: Any) -> Any:
        if isinstance(d, dict):
            d = dict(d)
            _alias(d, "job_title", "title", "position", "role_title", "name")
            _alias(d, "role", "description", "summary", "role_overview")
            _alias(d, "employment_type", "type", "job_type")
            _alias(d, "team_context", "team")
        return d


class ExperienceRequirement(_Base):
    description: Str = ""
    min_years: OptFloat = None
    max_years: OptFloat = None
    priority: PriorityT = Priority.MUST_HAVE
    explicit_or_derived: ExplicitT = ExplicitOrDerived.EXPLICIT
    source: OptSource = None

    @model_validator(mode="before")
    @classmethod
    def _fix(cls, d: Any) -> Any:
        if isinstance(d, dict):
            d = dict(d)
            _alias(d, "min_years", "years", "minimum_years")
        return d


class TechnicalSkill(_Base):
    name: Str = ""
    category: Str = Field("tool", description="language | framework | library | database | cloud | infra | tool | platform | methodology")
    priority: PriorityT = Priority.AMBIGUOUS
    explicit_or_derived: ExplicitT = ExplicitOrDerived.EXPLICIT
    source: OptSource = None

    @model_validator(mode="before")
    @classmethod
    def _fix(cls, d: Any) -> Any:
        if isinstance(d, dict):
            d = dict(d)
            _alias(d, "name", "skill", "technology", "tool", "description")
            if not d.get("category"):
                d.pop("category", None)
        return d


class EducationRequirement(_Base):
    description: Str = ""
    priority: PriorityT = Priority.AMBIGUOUS
    source: OptSource = None


class CertificationRequirement(_Base):
    description: Str = ""
    priority: PriorityT = Priority.AMBIGUOUS
    source: OptSource = None


class LocationInfo(_Base):
    country: OptStr = None
    city: OptStr = None
    work_mode: WorkModeT = WorkMode.UNSPECIFIED
    office_attendance: OptStr = Field(None, description="e.g. '4 days/week onsite'")
    relocation_required: OptBool = None
    source: OptSource = None


class TravelInfo(_Base):
    required: OptBool = None
    description: OptStr = None
    source: OptSource = None


class OtherRequirement(_Base):
    category: Str = Field("misc", description="languages | shift | availability | work_authorization | domain_knowledge | client_facing | communication | misc")
    description: Str = ""
    priority: PriorityT = Priority.AMBIGUOUS
    source: OptSource = None

    @model_validator(mode="before")
    @classmethod
    def _fix(cls, d: Any) -> Any:
        if isinstance(d, dict):
            d = dict(d)
            if not d.get("category"):
                d.pop("category", None)
        return d


class ConventionalRequirements(_Base):
    experience: Annotated[List[ExperienceRequirement], BeforeValidator(_items(lambda s: {"description": s}))] = Field(default_factory=list)
    technical_skills: Annotated[List[TechnicalSkill], BeforeValidator(_items(lambda s: {"name": s}))] = Field(default_factory=list)
    education: Annotated[List[EducationRequirement], BeforeValidator(_items(lambda s: {"description": s}))] = Field(default_factory=list)
    certifications: Annotated[List[CertificationRequirement], BeforeValidator(_items(lambda s: {"description": s}))] = Field(default_factory=list)
    domain: StrList = Field(default_factory=list)
    location: Annotated[LocationInfo, BeforeValidator(_obj(lambda s: {"city": s}))] = Field(default_factory=LocationInfo)
    work_mode: WorkModeT = WorkMode.UNSPECIFIED
    travel: Annotated[TravelInfo, BeforeValidator(_obj(lambda s: {"description": s}))] = Field(default_factory=TravelInfo)
    languages: LangList = Field(default_factory=list)
    other: Annotated[List[OtherRequirement], BeforeValidator(_items(lambda s: {"description": s}))] = Field(default_factory=list)

    @model_validator(mode="after")
    def _tidy(self) -> "ConventionalRequirements":
        self.experience = [x for x in self.experience if x.description]
        self.technical_skills = [x for x in self.technical_skills if x.name]
        self.education = [x for x in self.education if x.description]
        self.certifications = [x for x in self.certifications if x.description]
        self.other = [x for x in self.other if x.description]
        # Keep top-level work_mode and location.work_mode consistent.
        if self.work_mode == WorkMode.UNSPECIFIED and self.location.work_mode != WorkMode.UNSPECIFIED:
            self.work_mode = self.location.work_mode
        elif self.location.work_mode == WorkMode.UNSPECIFIED and self.work_mode != WorkMode.UNSPECIFIED:
            self.location.work_mode = self.work_mode
        return self


class Responsibility(_Base):
    description: Str = ""
    kind: Str = Field("primary", description="primary | secondary | ownership | leadership | collaboration")
    source: OptSource = None

    @model_validator(mode="before")
    @classmethod
    def _fix(cls, d: Any) -> Any:
        if isinstance(d, dict):
            d = dict(d)
            _alias(d, "description", "responsibility", "text")
            if not d.get("kind"):
                d["kind"] = "primary"
        return d


class MetadataInfo(_Base):
    jd_id: Optional[str] = None
    jd_version: Optional[int] = None
    specification_version: Optional[int] = None
    prompt_version: Optional[str] = None
    model_version: Optional[str] = None
    generated_at: Optional[datetime] = None


class JobContext(_Base):
    company_context: OptStr = None
    business_context: OptStr = None
    team_size: OptStr = None
    environment: OptStr = Field(None, description="e.g. 'fast-paced startup'")

    @model_validator(mode="before")
    @classmethod
    def _fix(cls, d: Any) -> Any:
        """Small models invent keys like company_type / platform_type; fold them in."""
        if not isinstance(d, dict):
            return d
        d = dict(d)
        name = _pick(d.get("company_name") or d.get("company") or d.get("organization"))
        ctype = _pick(d.get("company_type") or d.get("industry"))
        if not d.get("company_context"):
            d["company_context"] = " - ".join(x for x in (name, ctype) if x) or None
        if not d.get("business_context"):
            bits = [_pick(d.get(k)) for k in ("platform_type", "target_audience", "key_value_proposition", "mission", "product")]
            d["business_context"] = "; ".join(b for b in bits if b) or None
        _alias(d, "team_size", "team")
        _alias(d, "environment", "work_environment", "culture")
        return d


class MissingInfo(_Base):
    """Information absent from the JD and NOT inferred or fabricated."""
    field: Str = Field("", description="The parameter that is absent, e.g. 'salary range'.")
    why_it_matters: Str = Field("", description="Why its absence is noteworthy for evaluation.")
    suggested_action: OptStr = Field(None, description="e.g. 'Ask TA to confirm'.")

    @model_validator(mode="before")
    @classmethod
    def _fix(cls, d: Any) -> Any:
        if isinstance(d, dict):
            d = dict(d)
            _alias(d, "field", "field_name", "parameter", "name", "missing")
            _alias(d, "why_it_matters", "reason", "why", "rationale")
        return d


class JobEvaluationSpecification(_Base):
    """The canonical Candidate Evaluation Specification (only source of truth)."""
    metadata: MetadataInfo = Field(default_factory=MetadataInfo)
    role: Annotated[RoleInfo, BeforeValidator(_obj(lambda s: {"job_title": s}))] = Field(default_factory=RoleInfo)
    job_context: Annotated[JobContext, BeforeValidator(_obj(lambda s: {"company_context": s}))] = Field(default_factory=JobContext)
    responsibilities: Annotated[List[Responsibility], BeforeValidator(_items(lambda s: {"description": s}))] = Field(default_factory=list)
    conventional_requirements: Annotated[ConventionalRequirements, BeforeValidator(_obj())] = Field(default_factory=ConventionalRequirements)

    must_have_requirements: StrList = Field(default_factory=list)
    preferred_requirements: StrList = Field(default_factory=list)

    responsibility_requirement_mapping: Annotated[List[ResponsibilityRequirementMapping], BeforeValidator(_items(lambda s: {"responsibility": s}))] = Field(default_factory=list)
    requirement_interpretations: Annotated[List[RequirementInterpretation], BeforeValidator(_items(lambda s: {"explicit_requirement": s}))] = Field(default_factory=list)
    evidence_requirements: Annotated[List[EvidenceSpec], BeforeValidator(_items(lambda s: {"requirement": s}))] = Field(default_factory=list)
    non_conventional_parameters: Annotated[List[NonConventionalParameter], BeforeValidator(_items(lambda s: {"parameter_name": s}))] = Field(default_factory=list)

    evaluation_rules: StrList = Field(default_factory=list)
    unscored_rules: StrList = Field(default_factory=list)
    prohibited_inferences: StrList = Field(default_factory=list)
    compliance_flags: Annotated[List[ComplianceFlag], BeforeValidator(_items(lambda s: {"flagged_text": s}))] = Field(default_factory=list)
    ambiguities: Annotated[List[Ambiguity], BeforeValidator(_items(lambda s: {"statement": s}))] = Field(default_factory=list)
    missing_information: Annotated[List[MissingInfo], BeforeValidator(_items(lambda s: {"field": s}))] = Field(
        default_factory=list,
        description="JD parameters that are absent/unspecified — never fabricated.",
    )
    ta_confirmation_required: StrList = Field(default_factory=list)
    candidate_analysis_instructions: StrList = Field(default_factory=list)

    model_config = ConfigDict(use_enum_values=False, extra="ignore", populate_by_name=True)

    @model_validator(mode="after")
    def _prune_empty(self) -> "JobEvaluationSpecification":
        self.responsibilities = [x for x in self.responsibilities if x.description]
        self.responsibility_requirement_mapping = [x for x in self.responsibility_requirement_mapping if x.responsibility]
        self.requirement_interpretations = [x for x in self.requirement_interpretations if x.explicit_requirement]
        self.evidence_requirements = [x for x in self.evidence_requirements if x.requirement]
        self.non_conventional_parameters = [x for x in self.non_conventional_parameters if x.parameter_name]
        self.compliance_flags = [x for x in self.compliance_flags if x.flagged_text]
        self.ambiguities = [x for x in self.ambiguities if x.statement]
        self.missing_information = [x for x in self.missing_information if x.field]
        return self


# ---------------------------------------------------------------------------
# Schema handed to the LLM (Ollama structured outputs)
# ---------------------------------------------------------------------------

# `source` quotes are expensive in output tokens; keep them only where they matter.
_KEEP_SOURCE = {"Responsibility", "TechnicalSkill"}


@lru_cache(maxsize=1)
def llm_json_schema() -> Dict[str, Any]:
    """
    JSON Schema used to constrain the model's output so it cannot invent field
    names. `metadata` is set by code, never by the LLM, and most `source`
    objects are removed to cut generation time on local models.
    """
    schema = JobEvaluationSpecification.model_json_schema()
    schema["properties"].pop("metadata", None)
    schema["required"] = list(schema["properties"].keys())
    for name, definition in schema.get("$defs", {}).items():
        if name not in _KEEP_SOURCE:
            definition.get("properties", {}).pop("source", None)
        for field in _NON_EMPTY_FIELDS.get(name, ()):
            prop = definition.get("properties", {}).get(field)
            if isinstance(prop, dict):
                prop["minLength"] = 1
    _forbid_empty_strings_in_lists(schema)
    return schema


# Identifying fields that must never be blank (blank = the model echoed the skeleton).
_NON_EMPTY_FIELDS = {
    "Responsibility": ("description",),
    "TechnicalSkill": ("name",),
    "ExperienceRequirement": ("description",),
    "EducationRequirement": ("description",),
    "CertificationRequirement": ("description",),
    "OtherRequirement": ("description",),
    "EvidenceSpec": ("requirement",),
    "ResponsibilityRequirementMapping": ("responsibility",),
    "RequirementInterpretation": ("explicit_requirement",),
    "NonConventionalParameter": ("parameter_name",),
    "Ambiguity": ("statement",),
    "ComplianceFlag": ("flagged_text",),
    "MissingInfo": ("field",),
}


def _forbid_empty_strings_in_lists(node: Any) -> None:
    """Every array-of-strings in the schema gets items.minLength = 1."""
    if isinstance(node, dict):
        items = node.get("items")
        if node.get("type") == "array" and isinstance(items, dict) and items.get("type") == "string":
            items["minLength"] = 1
        for v in node.values():
            _forbid_empty_strings_in_lists(v)
    elif isinstance(node, list):
        for v in node:
            _forbid_empty_strings_in_lists(v)