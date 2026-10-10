"""
Deterministic extraction services.

Pure deterministic JD parsing without LLM assistance.

Modules:
- extractor: Main extraction orchestrator
- classifier: Conservative requirement priority classifier
- boolean_parser: Boolean logic (AND/OR) parser
- parameter_extractor: Comprehensive parameter extraction (Stage 3)
- ambiguity_detector: Ambiguity detection and clarification (Stage 3)
- missing_info_detector: Missing information detection (Stage 3)
- source_spans: Source evidence tracking utilities
"""
from .extractor import DeterministicExtractor, create_extractor
from .classifier import RequirementClassifier, create_classifier
from .boolean_parser import BooleanParser, create_boolean_parser
from .parameter_extractor import ParameterExtractor, create_parameter_extractor
from .ambiguity_detector import AmbiguityDetector, create_ambiguity_detector
from .missing_info_detector import MissingInfoDetector, create_missing_info_detector

__all__ = [
    "DeterministicExtractor",
    "create_extractor",
    "RequirementClassifier",
    "create_classifier",
    "BooleanParser",
    "create_boolean_parser",
    "ParameterExtractor",
    "create_parameter_extractor",
    "AmbiguityDetector",
    "create_ambiguity_detector",
    "MissingInfoDetector",
    "create_missing_info_detector",
]
