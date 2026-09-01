"""
Canonical Object -> JSON serializer.

Thin wrapper -- Pydantic already gives us a schema-validated, deterministic
JSON representation. This module exists so callers have one obvious place
to import from, and so we can enforce consistent formatting (sorted keys
off, indent=2, ISO datetimes) across the codebase.
"""
from __future__ import annotations

import json

from app.schemas.canonical import JobEvaluationSpecification


def to_json_str(spec: JobEvaluationSpecification, indent: int = 2) -> str:
    return spec.model_dump_json(indent=indent)


def to_json_dict(spec: JobEvaluationSpecification) -> dict:
    return json.loads(spec.model_dump_json())
