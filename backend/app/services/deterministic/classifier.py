"""
Conservative deterministic requirement classifier.

Implements fine-grained classification for:
- Explicit mandatory requirements
- Preferred/optional requirements
- Negated requirements ("not required", "must not use")
- Conditional requirements ("if working on X team")
- Uncertain/ambiguous requirements

Design principles:
- Small, clearly named rules with documented precedence
- Conservative classification (uncertainty over guessing)
- Proper negation scope handling
- No silent treatment of negation as positive requirement
- Preserve exact original text and source evidence
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.schemas.master_context import RequirementPriority

logger = logging.getLogger("jd_agent.classifier")


@dataclass
class ClassificationResult:
    """Result of requirement classification."""
    priority: RequirementPriority
    is_negated: bool = False
    is_conditional: bool = False
    condition: Optional[str] = None
    confidence: float = 1.0  # 0.0-1.0
    reasoning: str = ""


class RequirementClassifier:
    """
    Conservative deterministic classifier for requirement priority.
    
    Distinguishes:
    - MANDATORY: "must have", "required", "essential"
    - PREFERRED: "preferred", "nice to have", "advantage"
    - CONTEXTUAL: unclear priority or context-dependent
    
    Handles:
    - Negation: "not required", "must not use"
    - Conditional: "if working on team X"
    - Mixed priority: "Python required, Java preferred"
    """
    
    def __init__(self):
        # Compile patterns once for efficiency
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for classification rules."""
        
        # Mandatory indicators (strong signals)
        self.mandatory_strong = re.compile(
            r'\b(must\s+have|required|essential|mandatory|critical|necessary)\b',
            re.IGNORECASE
        )
        
        # Mandatory indicators (moderate signals)
        self.mandatory_moderate = re.compile(
            r'\b(need|needs|needed|minimum|prerequisite|core)\b',
            re.IGNORECASE
        )
        
        # Preferred indicators
        self.preferred_signals = re.compile(
            r'\b(preferred|nice\s+to\s+have|bonus|plus|advantage|desirable|'
            r'ideal|would\s+be|beneficial|helpful|asset)\b',
            re.IGNORECASE
        )
        
        # Optional indicators
        self.optional_signals = re.compile(
            r'\b(optional|not\s+required|not\s+mandatory|not\s+necessary|'
            r'not\s+essential)\b',
            re.IGNORECASE
        )
        
        # Negation indicators (prohibition)
        self.negation_strong = re.compile(
            r'\b(must\s+not|should\s+not|cannot|prohibited|forbidden|excluded)\b',
            re.IGNORECASE
        )
        
        # Conditional indicators
        self.conditional_pattern = re.compile(
            r'\b(if|when|in\s+case|for\s+those|depending\s+on)\b',
            re.IGNORECASE
        )
        
        # Uncertain indicators
        self.uncertain_signals = re.compile(
            r'\b(may|might|could|possibly|potentially|sometimes)\b',
            re.IGNORECASE
        )
    
    def classify(self, text: str, section_type: Optional[str] = None) -> ClassificationResult:
        """
        Classify requirement priority from text.
        
        Args:
            text: Requirement text to classify
            section_type: Optional section context
        
        Returns:
            ClassificationResult with priority and metadata
        """
        # Rule precedence (highest to lowest):
        # 1. Negation/prohibition
        # 2. Optional/not required
        # 3. Conditional requirements
        # 4. Strong mandatory
        # 5. Preferred signals
        # 6. Moderate mandatory
        # 7. Section context
        # 8. Uncertain (default to CONTEXTUAL)
        
        # Check for negation first (highest precedence)
        negation_result = self._check_negation(text)
        if negation_result:
            return negation_result
        
        # Check for "not required" / "optional"
        optional_result = self._check_optional(text)
        if optional_result:
            return optional_result
        
        # Check for conditional requirements
        conditional_result = self._check_conditional(text)
        if conditional_result:
            return conditional_result
        
        # Check strong mandatory signals
        if self.mandatory_strong.search(text):
            return ClassificationResult(
                priority=RequirementPriority.MANDATORY,
                confidence=0.95,
                reasoning="Strong mandatory signal detected"
            )
        
        # Check preferred signals
        if self.preferred_signals.search(text):
            return ClassificationResult(
                priority=RequirementPriority.PREFERRED,
                confidence=0.90,
                reasoning="Preferred signal detected"
            )
        
        # Check moderate mandatory signals
        if self.mandatory_moderate.search(text):
            # Lower confidence for moderate signals
            return ClassificationResult(
                priority=RequirementPriority.MANDATORY,
                confidence=0.70,
                reasoning="Moderate mandatory signal detected"
            )
        
        # Use section context if available
        if section_type:
            section_result = self._classify_by_section(section_type)
            if section_result:
                return section_result
        
        # Check for uncertainty
        if self.uncertain_signals.search(text):
            return ClassificationResult(
                priority=RequirementPriority.CONTEXTUAL,
                confidence=0.50,
                reasoning="Uncertain language detected"
            )
        
        # Default to contextual (unknown priority)
        return ClassificationResult(
            priority=RequirementPriority.CONTEXTUAL,
            confidence=0.30,
            reasoning="No clear priority signals detected"
        )
    
    def _check_negation(self, text: str) -> Optional[ClassificationResult]:
        """
        Check for negation or prohibition.
        
        Examples:
        - "Candidates must not use tool X"
        - "Should not have experience with Y"
        """
        if self.negation_strong.search(text):
            return ClassificationResult(
                priority=RequirementPriority.CONTEXTUAL,
                is_negated=True,
                confidence=0.95,
                reasoning="Prohibition/negation detected - not a positive requirement"
            )
        return None
    
    def _check_optional(self, text: str) -> Optional[ClassificationResult]:
        """
        Check for optional or "not required" statements.
        
        Examples:
        - "Python is not required"
        - "Java is optional"
        
        Important: Verify negation scope to avoid false positives like:
        - "Python is not required, but Java is mandatory"
        """
        match = self.optional_signals.search(text)
        if not match:
            return None
        
        # Check if the "not required" applies to the whole clause
        # or just part of it
        matched_text = match.group(0).lower()
        
        # If we find other strong signals after the "not required",
        # it might be a compound statement
        after_match = text[match.end():]
        if self.mandatory_strong.search(after_match):
            # Mixed signals - be conservative
            return ClassificationResult(
                priority=RequirementPriority.CONTEXTUAL,
                confidence=0.40,
                reasoning="Mixed signals: 'not required' but also mandatory indicators present"
            )
        
        # Clear optional/not required signal
        if "not" in matched_text:
            return ClassificationResult(
                priority=RequirementPriority.CONTEXTUAL,
                is_negated=True,
                confidence=0.85,
                reasoning="Explicitly marked as not required"
            )
        else:
            return ClassificationResult(
                priority=RequirementPriority.PREFERRED,
                confidence=0.80,
                reasoning="Marked as optional"
            )
    
    def _check_conditional(self, text: str) -> Optional[ClassificationResult]:
        """
        Check for conditional requirements.
        
        Examples:
        - "Python required if working on automation team"
        - "Java needed for backend role"
        """
        match = self.conditional_pattern.search(text)
        if not match:
            return None
        
        # Extract the condition
        condition_start = match.start()
        condition = text[condition_start:].strip()
        
        # Conditional requirements are context-dependent
        return ClassificationResult(
            priority=RequirementPriority.CONTEXTUAL,
            is_conditional=True,
            condition=condition,
            confidence=0.75,
            reasoning="Conditional requirement detected"
        )
    
    def _classify_by_section(self, section_type: str) -> Optional[ClassificationResult]:
        """
        Use section context as fallback classification.
        
        Note: Section-based classification has lower confidence
        because clause text overrides section context.
        """
        if section_type in ['preferred', 'nice_to_have', 'bonus']:
            return ClassificationResult(
                priority=RequirementPriority.PREFERRED,
                confidence=0.60,
                reasoning=f"Section context: {section_type}"
            )
        elif section_type in ['requirements', 'qualifications', 'required_skills']:
            return ClassificationResult(
                priority=RequirementPriority.MANDATORY,
                confidence=0.50,
                reasoning=f"Section context: {section_type}"
            )
        
        return None
    
    def classify_batch(
        self,
        texts: List[str],
        section_type: Optional[str] = None
    ) -> List[ClassificationResult]:
        """
        Classify multiple requirements in batch.
        
        Useful for detecting patterns across related requirements.
        """
        return [self.classify(text, section_type) for text in texts]


def create_classifier() -> RequirementClassifier:
    """Factory function to create classifier instance."""
    return RequirementClassifier()
