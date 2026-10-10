"""
Deterministic ambiguity detection service.

Identifies wording that can materially change JD interpretation or candidate evaluation:
- Vague skill requirements ("strong knowledge")
- Unspecified technical tools
- Unclear experience scope
- Ambiguous seniority expectations
- Unclear responsibility boundaries
- Conflicting or contradictory requirements
- Ambiguous AND/OR groupings
- Conditional requirements with unclear conditions
- Missing qualifiers that affect interpretation

Design principles:
- Deterministic pattern matching only (no LLM)
- Evidence-grounded findings
- Structured, actionable clarification questions
- Conservative detection (avoid false positives)
- Preserve original text and source spans
- Support re-analysis with clarification context
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from app.schemas.master_context import (
    DetectedAmbiguity,
    SourceReference,
    StructuredRequirement,
    JDSection,
)

logger = logging.getLogger("jd_agent.ambiguity_detector")


@dataclass
class AmbiguityCategory:
    """Category of ambiguity for severity/priority."""
    name: str
    severity: str  # "high", "medium", "low"
    description: str


# Define ambiguity categories
AMBIGUITY_CATEGORIES = {
    "vague_qualifier": AmbiguityCategory(
        "vague_qualifier",
        "medium",
        "Subjective qualifier without measurable criteria"
    ),
    "unspecified_tool": AmbiguityCategory(
        "unspecified_tool",
        "high",
        "Technical tool or technology not specified"
    ),
    "unclear_experience": AmbiguityCategory(
        "unclear_experience",
        "high",
        "Experience requirement lacks clear scope or measurement"
    ),
    "ambiguous_seniority": AmbiguityCategory(
        "ambiguous_seniority",
        "medium",
        "Seniority level not clearly defined"
    ),
    "unclear_responsibility": AmbiguityCategory(
        "unclear_responsibility",
        "medium",
        "Responsibility boundaries not clear"
    ),
    "conflicting_requirement": AmbiguityCategory(
        "conflicting_requirement",
        "high",
        "Contradictory or mutually exclusive requirements"
    ),
    "ambiguous_boolean": AmbiguityCategory(
        "ambiguous_boolean",
        "medium",
        "AND/OR relationship unclear"
    ),
    "unclear_condition": AmbiguityCategory(
        "unclear_condition",
        "medium",
        "Conditional requirement with vague condition"
    ),
    "missing_qualifier": AmbiguityCategory(
        "missing_qualifier",
        "low",
        "Missing detail that could affect interpretation"
    ),
}


class AmbiguityDetector:
    """
    Deterministic ambiguity detection engine.
    
    Identifies ambiguous wording that requires clarification
    before accurate candidate evaluation.
    """
    
    def __init__(self):
        self._compile_patterns()
        self._detected_ids: Set[str] = set()
    
    def _compile_patterns(self):
        """Compile regex patterns for ambiguity detection."""
        
        # Vague qualifiers
        self.vague_qualifiers = [
            'strong', 'good', 'excellent', 'solid', 'deep',
            'thorough', 'extensive', 'proficient', 'expert',
            'advanced', 'intermediate', 'basic', 'familiarity',
            'working knowledge', 'understanding of', 'experience with'
        ]
        
        # Unspecified tool indicators
        self.tool_indicators = [
            'tools', 'technologies', 'frameworks', 'libraries',
            'platforms', 'software', 'systems', 'applications'
        ]
        
        # Seniority terms
        self.seniority_terms = [
            'senior', 'junior', 'mid-level', 'lead', 'principal',
            'staff', 'entry-level', 'experienced'
        ]
        
        # Conditional patterns
        self.conditional_pattern = re.compile(
            r'\b(if|when|in\s+case|for\s+those|depending\s+on)\b',
            re.IGNORECASE
        )
        
        # Conflict indicators
        self.conflict_indicators = [
            (r'\b(must|required)\b.*\b(not\s+required|optional)\b', 'requirement_conflict'),
            (r'\b(remote)\b.*\b(onsite|in-office)\b', 'location_conflict'),
            (r'\bonly\b.*\b(?:also|or|and)\b', 'exclusivity_conflict'),
        ]
        
        # Compile conflict patterns
        self.conflict_patterns = [
            (re.compile(pattern, re.IGNORECASE), conflict_type)
            for pattern, conflict_type in self.conflict_indicators
        ]
    
    def detect_all_ambiguities(
        self,
        jd_text: str,
        requirements: List[StructuredRequirement],
        sections: List[JDSection],
        clarification_context: Optional[Dict[str, str]] = None
    ) -> List[DetectedAmbiguity]:
        """
        Detect all ambiguities in JD.
        
        Args:
            jd_text: Full JD text
            requirements: Extracted structured requirements
            sections: Parsed sections
            clarification_context: Optional dict of answered clarifications
                                 Format: {"ambiguity_id": "clarification_answer"}
        
        Returns:
            List of detected ambiguities
        """
        self._detected_ids.clear()
        ambiguities: List[DetectedAmbiguity] = []
        
        # Detect various ambiguity types
        ambiguities.extend(self.detect_vague_qualifiers(requirements))
        ambiguities.extend(self.detect_unspecified_tools(requirements))
        ambiguities.extend(self.detect_unclear_experience(requirements))
        ambiguities.extend(self.detect_ambiguous_seniority(jd_text, requirements))
        ambiguities.extend(self.detect_unclear_responsibilities(requirements))
        ambiguities.extend(self.detect_conflicts(requirements))
        ambiguities.extend(self.detect_ambiguous_boolean(requirements))
        ambiguities.extend(self.detect_unclear_conditions(requirements))
        
        # Filter resolved ambiguities if clarification context provided
        if clarification_context:
            ambiguities = self._filter_resolved(ambiguities, clarification_context)
        
        logger.info(
            "[AmbiguityDetector] Detected %d ambiguities",
            len(ambiguities)
        )
        return ambiguities
    
    def detect_vague_qualifiers(
        self,
        requirements: List[StructuredRequirement]
    ) -> List[DetectedAmbiguity]:
        """
        Detect vague qualifiers like "strong knowledge" or "good understanding".
        
        Example: "Strong Python skills" → What does "strong" mean?
        """
        ambiguities: List[DetectedAmbiguity] = []
        
        for req in requirements:
            text_lower = req.text.lower()
            
            # Check for vague qualifiers
            for qualifier in self.vague_qualifiers:
                if qualifier in text_lower:
                    # Extract the skill/technology being qualified
                    # Simple heuristic: word after qualifier
                    pattern = re.compile(
                        rf'\b{re.escape(qualifier)}\s+(\w+(?:\s+\w+)?)',
                        re.IGNORECASE
                    )
                    match = pattern.search(req.text)
                    
                    if match:
                        skill = match.group(1)
                        
                        ambiguity_id = f"amb_{len(self._detected_ids) + 1:03d}_vague"
                        if ambiguity_id not in self._detected_ids:
                            ambiguities.append(DetectedAmbiguity(
                                ambiguity_id=ambiguity_id,
                                text=req.text,
                                reason=f"Vague qualifier '{qualifier}' without measurable criteria",
                                suggested_interpretations=[
                                    f"Specific years of {skill} experience (e.g., '3+ years')",
                                    f"Specific {skill} projects or outcomes",
                                    f"Certification or formal training in {skill}",
                                ],
                                requires_ta_confirmation=True,
                                source=req.source
                            ))
                            self._detected_ids.add(ambiguity_id)
                            logger.debug(
                                "[AmbiguityDetector] Vague qualifier: %s",
                                req.text[:60]
                            )
                    break
        
        return ambiguities
    
    def detect_unspecified_tools(
        self,
        requirements: List[StructuredRequirement]
    ) -> List[DetectedAmbiguity]:
        """
        Detect unspecified technical tools.
        
        Example: "Experience with semiconductor design tools" → Which tools?
        """
        ambiguities: List[DetectedAmbiguity] = []
        
        for req in requirements:
            text_lower = req.text.lower()
            
            # Check for tool indicators without specific names
            for indicator in self.tool_indicators:
                if indicator in text_lower:
                    # Check if specific tool names are present (via EKG matches)
                    if not req.matched_entities or len(req.matched_entities) == 0:
                        # No specific tools identified
                        
                        ambiguity_id = f"amb_{len(self._detected_ids) + 1:03d}_tool"
                        if ambiguity_id not in self._detected_ids:
                            ambiguities.append(DetectedAmbiguity(
                                ambiguity_id=ambiguity_id,
                                text=req.text,
                                reason=f"Technical {indicator} mentioned but not specified",
                                suggested_interpretations=[],
                                requires_ta_confirmation=True,
                                source=req.source
                            ))
                            self._detected_ids.add(ambiguity_id)
                            logger.debug(
                                "[AmbiguityDetector] Unspecified tool: %s",
                                req.text[:60]
                            )
                    break
        
        return ambiguities
    
    def detect_unclear_experience(
        self,
        requirements: List[StructuredRequirement]
    ) -> List[DetectedAmbiguity]:
        """
        Detect unclear experience requirements.
        
        Example: "Significant experience" → How many years?
        """
        ambiguities: List[DetectedAmbiguity] = []
        
        vague_exp_terms = [
            'significant', 'substantial', 'considerable', 'extensive',
            'proven', 'demonstrated', 'track record', 'history of'
        ]
        
        for req in requirements:
            text_lower = req.text.lower()
            
            # Check for vague experience terms without specific years
            if 'experience' in text_lower:
                # Check if years are specified
                has_years = re.search(r'\d+\s*\+?\s*years?', req.text, re.IGNORECASE)
                
                if not has_years:
                    # Check for vague terms
                    for term in vague_exp_terms:
                        if term in text_lower:
                            ambiguity_id = f"amb_{len(self._detected_ids) + 1:03d}_exp"
                            if ambiguity_id not in self._detected_ids:
                                ambiguities.append(DetectedAmbiguity(
                                    ambiguity_id=ambiguity_id,
                                    text=req.text,
                                    reason="Experience requirement without specific years or scope",
                                    suggested_interpretations=[
                                        "Specify minimum years of experience (e.g., '3+ years')",
                                        "Define experience level (entry/mid/senior)",
                                        "Specify relevant experience scope",
                                    ],
                                    requires_ta_confirmation=True,
                                    source=req.source
                                ))
                                self._detected_ids.add(ambiguity_id)
                            break
        
        return ambiguities
    
    def detect_ambiguous_seniority(
        self,
        jd_text: str,
        requirements: List[StructuredRequirement]
    ) -> List[DetectedAmbiguity]:
        """
        Detect ambiguous seniority expectations.
        
        Example: "Senior" without defining what makes someone senior.
        """
        ambiguities: List[DetectedAmbiguity] = []
        
        for term in self.seniority_terms:
            pattern = re.compile(rf'\b{term}\b', re.IGNORECASE)
            match = pattern.search(jd_text)
            
            if match:
                # Check if seniority is defined (look for years or specific criteria)
                context_start = max(0, match.start() - 100)
                context_end = min(len(jd_text), match.end() + 100)
                context = jd_text[context_start:context_end]
                
                # Look for years or specific criteria in context
                has_definition = re.search(r'\d+\s*\+?\s*years?', context, re.IGNORECASE)
                
                if not has_definition:
                    ambiguity_id = f"amb_{len(self._detected_ids) + 1:03d}_seniority"
                    if ambiguity_id not in self._detected_ids:
                        ambiguities.append(DetectedAmbiguity(
                            ambiguity_id=ambiguity_id,
                            text=match.group(0),
                            reason=f"Seniority level '{term}' without clear definition",
                            suggested_interpretations=[
                                f"Define '{term}' with minimum years of experience",
                                f"Specify expected skill level for '{term}' role",
                                f"Clarify responsibilities that make this '{term}' level",
                            ],
                            requires_ta_confirmation=True,
                            source=SourceReference(
                                text=context.strip(),
                                section="metadata"
                            )
                        ))
                        self._detected_ids.add(ambiguity_id)
                # Only detect first seniority term
                break
        
        return ambiguities
    
    def detect_unclear_responsibilities(
        self,
        requirements: List[StructuredRequirement]
    ) -> List[DetectedAmbiguity]:
        """
        Detect unclear responsibility boundaries.
        
        Example: "Support team" → What kind of support?
        """
        ambiguities: List[DetectedAmbiguity] = []
        
        vague_responsibility_terms = [
            'support', 'assist', 'help', 'contribute', 'participate',
            'collaborate', 'work with', 'engage'
        ]
        
        for req in requirements:
            if req.clause_type.value != 'RESPONSIBILITY':
                continue
            
            text_lower = req.text.lower()
            
            # Check for vague responsibility terms
            for term in vague_responsibility_terms:
                if term in text_lower:
                    # Check if specifics are provided (look for "by", "through", "via")
                    has_specifics = any(
                        word in text_lower
                        for word in ['by', 'through', 'via', 'including', 'such as']
                    )
                    
                    if not has_specifics:
                        ambiguity_id = f"amb_{len(self._detected_ids) + 1:03d}_resp"
                        if ambiguity_id not in self._detected_ids:
                            ambiguities.append(DetectedAmbiguity(
                                ambiguity_id=ambiguity_id,
                                text=req.text,
                                reason=f"Responsibility '{term}' without clear scope or methods",
                                suggested_interpretations=[
                                    "Specify concrete actions or deliverables",
                                    "Define scope and boundaries of responsibility",
                                    "Clarify expected outcomes or metrics",
                                ],
                                requires_ta_confirmation=True,
                                source=req.source
                            ))
                            self._detected_ids.add(ambiguity_id)
                    break
        
        return ambiguities
    
    def detect_conflicts(
        self,
        requirements: List[StructuredRequirement]
    ) -> List[DetectedAmbiguity]:
        """
        Detect conflicting or contradictory requirements.
        
        Example: "Remote only" and "Must be in office daily"
        """
        ambiguities: List[DetectedAmbiguity] = []
        
        # Check each requirement against patterns
        for req in requirements:
            for pattern, conflict_type in self.conflict_patterns:
                match = pattern.search(req.text)
                if match:
                    ambiguity_id = f"amb_{len(self._detected_ids) + 1:03d}_conflict"
                    if ambiguity_id not in self._detected_ids:
                        ambiguities.append(DetectedAmbiguity(
                            ambiguity_id=ambiguity_id,
                            text=req.text,
                            reason=f"Potential conflict: {conflict_type.replace('_', ' ')}",
                            suggested_interpretations=[
                                "Clarify which requirement takes precedence",
                                "Resolve contradictory statements",
                                "Provide consistent guidance",
                            ],
                            requires_ta_confirmation=True,
                            source=req.source
                        ))
                        self._detected_ids.add(ambiguity_id)
                        logger.debug(
                            "[AmbiguityDetector] Conflict detected: %s",
                            req.text[:60]
                        )
        
        return ambiguities
    
    def detect_ambiguous_boolean(
        self,
        requirements: List[StructuredRequirement]
    ) -> List[DetectedAmbiguity]:
        """
        Detect ambiguous AND/OR relationships.
        
        Example: "Python, Java, Go experience" → All required or one of?
        """
        ambiguities: List[DetectedAmbiguity] = []
        
        for req in requirements:
            # Look for comma-separated lists without explicit "and" or "or"
            if ',' in req.text and 'or' not in req.text.lower() and 'and' not in req.text.lower():
                # Count items in list
                items = [item.strip() for item in req.text.split(',')]
                if len(items) >= 2:
                    # Check if these are technologies/skills (via EKG matches)
                    if len(req.matched_entities) >= 2:
                        ambiguity_id = f"amb_{len(self._detected_ids) + 1:03d}_bool"
                        if ambiguity_id not in self._detected_ids:
                            ambiguities.append(DetectedAmbiguity(
                                ambiguity_id=ambiguity_id,
                                text=req.text,
                                reason="Comma-separated list without clear AND/OR operator",
                                suggested_interpretations=[
                                    "All items required (AND)",
                                    "Any one item sufficient (OR)",
                                    "Specific combination required",
                                ],
                                requires_ta_confirmation=True,
                                source=req.source
                            ))
                            self._detected_ids.add(ambiguity_id)
        
        return ambiguities
    
    def detect_unclear_conditions(
        self,
        requirements: List[StructuredRequirement]
    ) -> List[DetectedAmbiguity]:
        """
        Detect conditional requirements with unclear conditions.
        
        Example: "Python required if working on team X" → What is team X?
        """
        ambiguities: List[DetectedAmbiguity] = []
        
        for req in requirements:
            match = self.conditional_pattern.search(req.text)
            if match:
                # Found conditional requirement
                # Check if the condition is clear
                condition_start = match.start()
                condition = req.text[condition_start:].strip()
                
                # Simple heuristic: condition is unclear if it's very short
                # or contains vague terms
                is_vague = (
                    len(condition) < 20 or
                    any(term in condition.lower() for term in ['certain', 'some', 'specific', 'particular'])
                )
                
                if is_vague:
                    ambiguity_id = f"amb_{len(self._detected_ids) + 1:03d}_cond"
                    if ambiguity_id not in self._detected_ids:
                        ambiguities.append(DetectedAmbiguity(
                            ambiguity_id=ambiguity_id,
                            text=req.text,
                            reason="Conditional requirement with unclear condition",
                            suggested_interpretations=[
                                "Specify exact conditions when this applies",
                                "Define criteria for the conditional case",
                                "Clarify if this is optional or context-dependent",
                            ],
                            requires_ta_confirmation=True,
                            source=req.source
                        ))
                        self._detected_ids.add(ambiguity_id)
        
        return ambiguities
    
    def _filter_resolved(
        self,
        ambiguities: List[DetectedAmbiguity],
        clarification_context: Dict[str, str]
    ) -> List[DetectedAmbiguity]:
        """
        Filter ambiguities resolved by TA/HR clarification answers.

        Uses category-aware validation: whether an answer adequately addresses
        the *type* of finding, not merely whether it is long enough.

        Rules per ambiguity suffix category:
        - ``_vague``    : answer must contain a measurable criterion (years,
                          count, or a concrete skill term — not just another
                          vague qualifier)
        - ``_tool``     : answer must name at least one specific tool (proper
                          noun pattern or version string, e.g. "KiCad 7" / "Jira")
        - ``_exp``      : answer must contain a digit or an explicit level term
                          (junior / mid / senior / lead / principal / entry)
        - ``_bool``     : answer must contain "and" or "or" making the
                          relationship explicit
        - ``_conflict`` : answer must choose one option (single coherent
                          statement without contradictory qualifiers)
        - ``_seniority``: answer must define level with years or standard term
        - ``_resp``     : answer must describe concrete actions/deliverables
                          (heuristic: ≥ 2 verb-like words or colon/list marker)
        - ``_cond``     : answer must specify explicit conditions (heuristic:
                          contains "when", "if", "unless", "for", or ≥ 20 chars)
        - all others    : generic substantive-length check (≥ 15 chars, not a
                          placeholder)

        Additionally, if a TA answer itself introduces a new Boolean ambiguity
        (e.g. "Python or Java") that ambiguity is logged for downstream detection
        but NOT re-inserted here (that belongs in a full re-analysis run).
        """
        unresolved: List[DetectedAmbiguity] = []

        for ambiguity in ambiguities:
            answer = clarification_context.get(ambiguity.ambiguity_id)

            if answer is None:
                unresolved.append(ambiguity)
                continue

            resolved, reason = self._validate_answer_for_category(
                ambiguity.ambiguity_id, answer
            )

            if resolved:
                logger.debug(
                    "[AmbiguityDetector] Ambiguity %s resolved: %s",
                    ambiguity.ambiguity_id, answer[:60],
                )
                # Check whether the TA answer itself introduces a new ambiguity
                self._check_answer_introduces_boolean(
                    ambiguity.ambiguity_id, answer
                )
            else:
                logger.debug(
                    "[AmbiguityDetector] Ambiguity %s NOT resolved (%s): '%s'",
                    ambiguity.ambiguity_id, reason, answer[:60],
                )
                unresolved.append(ambiguity)

        logger.info(
            "[AmbiguityDetector] %d ambiguities remain after re-analysis filtering",
            len(unresolved),
        )
        return unresolved

    def _validate_answer_for_category(
        self,
        ambiguity_id: str,
        answer: str,
    ) -> Tuple[bool, str]:
        """
        Category-aware answer validation.

        Returns (is_resolved, failure_reason).
        """
        stripped = answer.strip()
        lower = stripped.lower()

        # --- Universal reject rules ---
        _placeholders = {
            "skip", "unknown", "unclear", "n/a", "not applicable",
            "no answer", "none", "not sure", "tbd", "to be determined",
            "not provided", "no comment",
        }
        if not stripped:
            return False, "Answer is empty"
        if lower in _placeholders:
            return False, f"Answer is a placeholder: '{stripped}'"
        if len(stripped) < 8:
            return False, f"Answer too short: '{stripped}'"

        # --- Infer category from ID suffix ---
        suffix = ambiguity_id.rsplit("_", 1)[-1]  # e.g. "vague", "tool", "exp"

        if suffix == "vague":
            # Must contain a measurable marker: digits or a concrete skill term
            has_digit = bool(re.search(r'\d', stripped))
            concrete_terms = [
                "years", "months", "projects", "certification",
                "degree", "coursework", "portfolio", "proficiency at",
            ]
            has_concrete = any(t in lower for t in concrete_terms)
            if not (has_digit or has_concrete):
                return False, "Vague qualifier answer lacks measurable criteria"

        elif suffix == "tool":
            # Must contain a specific tool name (proper noun or version)
            has_tool = bool(
                re.search(r'\b[A-Z][A-Za-z0-9+#.\-]{2,}\b|\b\d+\.\d+\b', stripped)
            )
            if not has_tool:
                return False, "Tool answer lacks specific tool name or version"

        elif suffix == "exp":
            # Must contain a digit or explicit level term
            has_years_or_level = bool(
                re.search(
                    r'\b\d+\b|junior|mid|senior|lead|principal|entry|intern|graduate',
                    stripped, re.IGNORECASE,
                )
            )
            if not has_years_or_level:
                return False, "Experience answer lacks quantity or level"

        elif suffix == "bool":
            # Must make the AND/OR relationship explicit
            has_connector = bool(
                re.search(r'\band\b|\bor\b|\ball\b|\bany\b|\beither\b', lower)
            )
            if not has_connector:
                return False, "Boolean answer does not clarify AND/OR relationship"

        elif suffix == "conflict":
            # Must pick one coherent option — reject if contradictory qualifiers remain
            contradictions = [
                (r'\bboth\b.*\band\b.*\bnot\b', "still contradictory"),
                (r'\brequired\b.*\boptional\b', "still contradictory"),
                (r'\bmust\b.*\bnot\s+required\b', "still contradictory"),
            ]
            for pattern, msg in contradictions:
                if re.search(pattern, lower):
                    return False, f"Conflict answer is {msg}"
            if len(stripped) < 15:
                return False, "Conflict answer too brief to be definitive"

        elif suffix == "seniority":
            # Must define level with years or standard seniority term
            has_years_or_level = bool(
                re.search(
                    r'\b\d+\b|junior|mid|senior|lead|principal|staff|entry',
                    stripped, re.IGNORECASE,
                )
            )
            if not has_years_or_level:
                return False, "Seniority answer lacks years or standard level term"

        elif suffix == "resp":
            # Must describe concrete actions (heuristic: colon, list, or verb phrase)
            has_actions = bool(
                re.search(
                    r':\s|\bincluding\b|\bspecifically\b|\bsuch as\b'
                    r'|\bresponsible for\b|\bwill\b|\bshould\b',
                    lower,
                )
            )
            if not has_actions and len(stripped) < 20:
                return False, "Responsibility answer lacks concrete action description"

        elif suffix == "cond":
            # Must specify explicit condition
            has_condition_marker = bool(
                re.search(
                    r'\bwhen\b|\bif\b|\bunless\b|\bfor\b|\bapplies to\b|\bonly if\b',
                    lower,
                )
            )
            if not has_condition_marker and len(stripped) < 20:
                return False, "Condition answer lacks explicit condition specification"

        else:
            # Generic: minimum substantive length
            if len(stripped) < 15:
                return False, f"Answer too short ({len(stripped)} chars)"

        return True, ""

    def _check_answer_introduces_boolean(
        self,
        ambiguity_id: str,
        answer: str,
    ) -> None:
        """
        Log a warning if a TA answer itself contains an un-clarified OR that
        could introduce a new Boolean ambiguity.

        This is informational only — the new ambiguity is NOT inserted here.
        A full re-analysis run (extraction_pipeline.reanalyze_with_clarifications)
        will detect it via the normal detect_ambiguous_boolean path.
        """
        # Detect "X or Y" patterns where X and Y look like technologies
        or_pattern = re.compile(
            r'\b([A-Z][A-Za-z0-9+#]{1,})\s+or\s+([A-Z][A-Za-z0-9+#]{1,})\b'
        )
        if or_pattern.search(answer):
            logger.warning(
                "[AmbiguityDetector] Clarification answer for %s may introduce "
                "a new OR ambiguity: '%s' — schedule re-analysis.",
                ambiguity_id, answer[:80],
            )


    
    def generate_clarification_question(
        self,
        ambiguity: DetectedAmbiguity
    ) -> str:
        """
        Generate a specific, neutral clarification question for TA/HR.
        
        Args:
            ambiguity: The detected ambiguity
        
        Returns:
            Clear, actionable question string
        """
        # Extract category from ambiguity_id
        if '_vague' in ambiguity.ambiguity_id:
            return f"What specific level or measurement defines the requirement: '{ambiguity.text}'?"
        elif '_tool' in ambiguity.ambiguity_id:
            return f"Which specific tools or technologies are required for: '{ambiguity.text}'?"
        elif '_exp' in ambiguity.ambiguity_id:
            return f"How many years of experience are required for: '{ambiguity.text}'?"
        elif '_seniority' in ambiguity.ambiguity_id:
            return f"What criteria define the '{ambiguity.text}' level for this role?"
        elif '_resp' in ambiguity.ambiguity_id:
            return f"What specific actions or deliverables are expected for: '{ambiguity.text}'?"
        elif '_conflict' in ambiguity.ambiguity_id:
            return f"How should this apparent conflict be resolved: '{ambiguity.text}'?"
        elif '_bool' in ambiguity.ambiguity_id:
            return f"Are all items required (AND) or is any one sufficient (OR): '{ambiguity.text}'?"
        elif '_cond' in ambiguity.ambiguity_id:
            return f"Under what specific conditions does this apply: '{ambiguity.text}'?"
        else:
            return f"Please clarify: '{ambiguity.text}'"


def create_ambiguity_detector() -> AmbiguityDetector:
    """Factory function to create ambiguity detector instance."""
    return AmbiguityDetector()
