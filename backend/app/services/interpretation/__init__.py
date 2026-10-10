"""
Interpretation services for JD understanding.

Three-tier responsibility interpretation and capability mapping.
"""
from .responsibility_interpreter import (
    ResponsibilityInterpreter,
    create_interpreter,
    RichResponsibilityContext,
    TierEvidence,
    EntityMatch,
    LLMHypothesis,
    TAConfirmedFact,
)

__all__ = [
    "ResponsibilityInterpreter", 
    "create_interpreter",
    "RichResponsibilityContext",
    "TierEvidence",
    "EntityMatch",
    "LLMHypothesis",
    "TAConfirmedFact",
]
