"""
Deterministic JD extraction service.

Extracts structured information from raw JD text WITHOUT using LLMs:
- Section identification and parsing
- Requirement extraction
- Parameter extraction (location, work mode, etc.)
- Ambiguity detection
- Boolean requirement groups (OR logic)

Design principles:
- Pure deterministic extraction using regex, heuristics, keyword matching
- Conservative classification (avoid false positives)
- EKG-backed entity recognition
- Provenance tracking for all extractions
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Dict, List, Optional, Set, Tuple

from app.schemas.master_context import (
    ClauseType,
    DetectedAmbiguity,
    ExtractedParameter,
    JDSection,
    RequirementPriority,
    SourceReference,
    StructuredRequirement,
    DisjunctionGroup,
)
from app.services.ekg import get_ekg
from app.services.deterministic.classifier import create_classifier
from app.services.deterministic.boolean_parser import create_boolean_parser
from app.services.deterministic.parameter_extractor import create_parameter_extractor
from app.services.deterministic.ambiguity_detector import create_ambiguity_detector
from app.services.deterministic.missing_info_detector import create_missing_info_detector

logger = logging.getLogger("jd_agent.deterministic")


class DeterministicExtractor:
    """
    Deterministic JD extraction engine.
    
    Operates in pure deterministic mode without LLM assistance.
    """
    
    def __init__(self):
        self.ekg = get_ekg()
        self.classifier = create_classifier()
        self.boolean_parser = create_boolean_parser()
        self.parameter_extractor = create_parameter_extractor()
        self.ambiguity_detector = create_ambiguity_detector()
        self.missing_info_detector = create_missing_info_detector()
    
    def extract_sections(self, jd_text: str) -> List[JDSection]:
        """
        Identify and extract sections from JD text.
        
        Looks for common section headers and boundaries.
        """
        sections: List[JDSection] = []
        lines = jd_text.split('\n')
        
        # Section header patterns
        section_patterns = [
            (r'^\s*(requirements?|qualifications?)\s*:?\s*$', 'requirements'),
            (r'^\s*(responsibilities?|duties)\s*:?\s*$', 'responsibilities'),
            (r'^\s*(about|company|organization)\s*:?\s*$', 'about'),
            (r'^\s*(skills?|technical skills?)\s*:?\s*$', 'skills'),
            (r'^\s*(experience|background)\s*:?\s*$', 'experience'),
            (r'^\s*(education|qualifications?)\s*:?\s*$', 'education'),
            (r'^\s*(nice to have|preferred|bonus)\s*:?\s*$', 'preferred'),
            (r'^\s*(location|work mode|work arrangement)\s*:?\s*$', 'location'),
        ]
        
        current_section: Optional[Dict] = None
        current_content: List[str] = []
        
        for line_num, line in enumerate(lines, start=1):
            # Check if line is a section header
            matched_section = None
            for pattern, section_type in section_patterns:
                if re.match(pattern, line.strip(), re.IGNORECASE):
                    matched_section = section_type
                    break
            
            if matched_section:
                # Save previous section
                if current_section:
                    current_section['content'] = '\n'.join(current_content).strip()
                    current_section['line_end'] = line_num - 1
                    if current_section['content']:
                        sections.append(JDSection(**current_section))
                
                # Start new section
                current_section = {
                    'section_id': f"sec_{len(sections) + 1}",
                    'title': line.strip().rstrip(':'),
                    'section_type': matched_section,
                    'line_start': line_num,
                    'content': ''
                }
                current_content = []
            else:
                # Add line to current section content
                current_content.append(line)
        
        # Save last section
        if current_section:
            current_section['content'] = '\n'.join(current_content).strip()
            current_section['line_end'] = len(lines)
            if current_section['content']:
                sections.append(JDSection(**current_section))
        
        # If no sections found, treat entire text as single section
        if not sections:
            sections.append(JDSection(
                section_id="sec_1",
                title=None,
                content=jd_text.strip(),
                section_type="general",
                line_start=1,
                line_end=len(lines)
            ))
        
        logger.info("[Deterministic] Extracted %d sections", len(sections))
        return sections
    
    def extract_requirements(
        self,
        jd_text: str,
        sections: List[JDSection]
    ) -> List[StructuredRequirement]:
        """
        Extract structured requirements from JD text.
        
        Uses:
        - Sentence splitting
        - Keyword-based classification
        - EKG entity matching
        - Priority detection
        """
        requirements: List[StructuredRequirement] = []
        
        # Process each section
        for section in sections:
            section_reqs = self._extract_from_section(section)
            requirements.extend(section_reqs)
        
        logger.info("[Deterministic] Extracted %d requirements", len(requirements))
        return requirements
    
    def _extract_from_section(self, section: JDSection) -> List[StructuredRequirement]:
        """Extract requirements from a single section."""
        requirements: List[StructuredRequirement] = []
        
        # Split into sentences/clauses
        clauses = self._split_into_clauses(section.content)
        
        for clause_text in clauses:
            if not clause_text.strip() or len(clause_text) < 10:
                continue
            
            # Classify clause
            clause_type = self._classify_clause(clause_text, section.section_type)
            
            # Determine priority
            priority = self._detect_priority(clause_text, section.section_type)
            
            # Match EKG entities
            entity_matches = self.ekg.match_entities(clause_text)
            matched_entities = [entity_id for entity_id, _ in entity_matches]
            entity_confidence = {
                entity_id: conf for entity_id, conf in entity_matches
            }
            
            # Check if requirement is explicit or derived
            is_explicit = self._is_explicit_requirement(clause_text)
            
            # Create structured requirement
            req = StructuredRequirement(
                requirement_id=f"req_{uuid.uuid4().hex[:8]}",
                text=clause_text.strip(),
                clause_type=clause_type,
                priority=priority,
                matched_entities=matched_entities,
                entity_confidence=entity_confidence,
                source=SourceReference(
                    text=clause_text.strip(),
                    section=section.section_type,
                    line_number=section.line_start
                ),
                is_explicit=is_explicit,
                requires_clarification=False
            )
            
            requirements.append(req)
        
        return requirements
    
    def _split_into_clauses(self, text: str) -> List[str]:
        """
        Split text into atomic clauses.
        
        Similar to RAG query_generator but adapted for requirement extraction.
        """
        # Split by sentence endings
        sentences = re.split(r'[.!?]+', text)
        
        clauses: List[str] = []
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            
            # Further split by common delimiters
            parts = re.split(r'[;,]\s*(?=[A-Z]|and\s|or\s)', sent)
            for part in parts:
                part = part.strip()
                if len(part) > 10:  # Minimum clause length
                    clauses.append(part)
        
        return clauses
    
    def _classify_clause(self, text: str, section_type: str) -> ClauseType:
        """
        Conservatively classify clause type.
        
        Uses keyword signals and section context.
        """
        lower = text.lower()
        
        # Responsibility indicators
        responsibility_keywords = [
            'design', 'develop', 'build', 'implement', 'maintain',
            'lead', 'manage', 'own', 'responsible for', 'drive',
            'collaborate', 'work with', 'support'
        ]
        
        # Requirement indicators
        requirement_keywords = [
            'must have', 'required', 'minimum', 'years of experience',
            'proficiency in', 'knowledge of', 'experience with',
            'bachelor', 'degree', 'certification'
        ]
        
        # Context indicators
        context_keywords = [
            'company', 'team', 'culture', 'environment',
            'startup', 'enterprise', 'industry'
        ]
        
        # Check patterns
        if any(kw in lower for kw in responsibility_keywords):
            return ClauseType.RESPONSIBILITY
        
        if any(kw in lower for kw in requirement_keywords):
            return ClauseType.REQUIREMENT
        
        if any(kw in lower for kw in context_keywords):
            return ClauseType.CONTEXT
        
        # Use section context as fallback
        if section_type in ['responsibilities', 'duties']:
            return ClauseType.RESPONSIBILITY
        elif section_type in ['requirements', 'qualifications', 'skills', 'experience']:
            return ClauseType.REQUIREMENT
        elif section_type in ['about', 'company']:
            return ClauseType.CONTEXT
        
        # Default to ambiguous if unclear
        return ClauseType.AMBIGUOUS
    
    def _detect_priority(
        self,
        text: str,
        section_type: str
    ) -> RequirementPriority:
        """
        Detect requirement priority using improved classifier.
        
        Handles negation, conditional requirements, and mixed signals.
        """
        # Use the new classifier for improved priority detection
        classification = self.classifier.classify(text, section_type)
        
        # Log if negation or conditional detected
        if classification.is_negated:
            logger.debug(
                "[Extractor] Negated requirement detected: %s",
                text[:60]
            )
        
        if classification.is_conditional:
            logger.debug(
                "[Extractor] Conditional requirement detected: %s",
                text[:60]
            )
        
        return classification.priority
    
    def _is_explicit_requirement(self, text: str) -> bool:
        """
        Determine if requirement is explicitly stated vs inferred.
        
        Explicit: directly states a requirement
        Inferred: derived from context or implications
        """
        # For now, treat all deterministically extracted clauses as explicit
        # since we're not doing inference yet
        return True
    
    def detect_disjunctions(
        self,
        requirements: List[StructuredRequirement]
    ) -> List[DisjunctionGroup]:
        """
        Detect Boolean OR groups using improved Boolean parser.
        
        Handles:
        - Simple OR: "Python or Java"
        - List OR: "Python, Java, or Go"
        - Slash OR: "Python/Java"
        
        Creates individual atomic requirements for each option.
        """
        # Use the new Boolean parser for improved disjunction detection
        groups = self.boolean_parser.parse_disjunctions(requirements)
        
        # Also detect AND relationships (for documentation)
        and_groups = self.boolean_parser.detect_and_relationships(requirements)
        
        if and_groups:
            logger.info(
                "[Deterministic] Note: %d AND relationships detected but not "
                "structured (schema limitation - preserved in requirement text)",
                len(and_groups)
            )
        
        return groups
    
    def detect_ambiguities(
        self,
        jd_text: str,
        requirements: List[StructuredRequirement]
    ) -> List[DetectedAmbiguity]:
        """
        Detect ambiguous statements requiring clarification.
        
        Conservative detection - only flag clear ambiguities.
        """
        ambiguities: List[DetectedAmbiguity] = []
        
        # Ambiguity patterns
        patterns = [
            (r'\d+\s*\+\s*years?', 'vague_experience', 'Experience range unclear (e.g., "5+ years")'),
            (r'(?:strong|good|solid|deep)\s+(?:knowledge|understanding|experience)',
             'subjective_requirement', 'Subjective qualifier without objective criteria'),
            (r'(?:familiar|familiarity)\s+with',
             'vague_proficiency', 'Vague proficiency level'),
            (r'(?:some|basic)\s+(?:knowledge|experience)',
             'undefined_level', 'Undefined minimum proficiency level'),
        ]
        
        for req in requirements:
            for pattern, reason_code, reason_text in patterns:
                if re.search(pattern, req.text, re.IGNORECASE):
                    ambiguity = DetectedAmbiguity(
                        ambiguity_id=f"amb_{uuid.uuid4().hex[:8]}",
                        text=req.text,
                        reason=reason_text,
                        suggested_interpretations=[],
                        requires_ta_confirmation=True,
                        source=req.source
                    )
                    ambiguities.append(ambiguity)
                    
                    # Mark requirement as needing clarification
                    req.requires_clarification = True
                    break  # One ambiguity per requirement
        
        logger.info("[Deterministic] Detected %d ambiguities", len(ambiguities))
        return ambiguities
    
    def extract_parameters(
        self,
        jd_text: str,
        sections: List[JDSection]
    ) -> List[ExtractedParameter]:
        """
        Extract job parameters using enhanced parameter extractor.
        
        Delegates to ParameterExtractor from Stage 3 for comprehensive
        parameter extraction with evidence preservation.
        """
        # Use Stage 3 parameter extractor
        parameters = self.parameter_extractor.extract_all_parameters(jd_text, sections)
        
        logger.info("[Deterministic] Extracted %d parameters", len(parameters))
        return parameters


def create_extractor() -> DeterministicExtractor:
    """Factory function to create extractor instance."""
    return DeterministicExtractor()
