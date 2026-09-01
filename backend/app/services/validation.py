"""
Validation layer used after: LLM structured output, and after Markdown -> JSON
conversion. Wraps Pydantic validation errors into a structured, API-friendly
shape, and adds a few cross-field consistency checks beyond what Pydantic
alone enforces.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from pydantic import ValidationError

from app.schemas.canonical import JobEvaluationSpecification


@dataclass
class ValidationIssue:
    field: str
    message: str
    severity: str = "error"  # error | warning


@dataclass
class ValidationReport:
    valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)


def validate_payload(payload: dict) -> tuple[JobEvaluationSpecification | None, ValidationReport]:
    try:
        spec = JobEvaluationSpecification.model_validate(payload)
    except ValidationError as exc:
        issues = [
            ValidationIssue(field=".".join(str(p) for p in e["loc"]), message=e["msg"])
            for e in exc.errors()
        ]
        return None, ValidationReport(valid=False, issues=issues)

    issues = _cross_field_checks(spec)
    return spec, ValidationReport(valid=not any(i.severity == "error" for i in issues), issues=issues)


def _cross_field_checks(spec: JobEvaluationSpecification) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []

    must_have_names = {m.lower() for m in spec.must_have_requirements}
    preferred_names = {p.lower() for p in spec.preferred_requirements}
    overlap = must_have_names & preferred_names
    if overlap:
        issues.append(
            ValidationIssue(
                field="must_have_requirements/preferred_requirements",
                message=f"Requirement(s) listed as both MUST_HAVE and PREFERRED: {sorted(overlap)}",
                severity="warning",
            )
        )

    for skill in spec.conventional_requirements.technical_skills:
        if skill.priority.value == "MUST_HAVE" and skill.name.lower() in preferred_names:
            issues.append(
                ValidationIssue(
                    field=f"conventional_requirements.technical_skills[{skill.name}]",
                    message=f"'{skill.name}' is MUST_HAVE in technical_skills but appears in preferred_requirements.",
                    severity="warning",
                )
            )

    for ambiguity in spec.ambiguities:
        if not ambiguity.ta_confirmation_required:
            issues.append(
                ValidationIssue(
                    field="ambiguities",
                    message=f"Ambiguity '{ambiguity.statement}' does not require TA confirmation -- verify this is intentional.",
                    severity="warning",
                )
            )

    for mi in spec.missing_information:
        if not mi.field or not mi.why_it_matters:
            issues.append(
                ValidationIssue(
                    field="missing_information",
                    message="A missing_information entry has an empty 'field' or 'why_it_matters' — check for fabricated or empty entries.",
                    severity="warning",
                )
            )

    return issues
