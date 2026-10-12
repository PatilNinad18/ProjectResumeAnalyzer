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
            (r'^(?:qualifications?\s*(?:&|and)\s*requirements?|requirements?\s*(?:&|and)\s*qualifications?)\s*:?$', 'requirements'),
            (r'^(?:(?:key|minimum|basic|job|core|technical|must[- ]have|required)\s+)*(?:technical\s+)?requirements?\s*:?$', 'requirements'),
            (r'^(?:(?:key|minimum|basic|job|core|technical|must[- ]have|required)\s+)*(?:technical\s+)?skills?\s*:?$', 'requirements'),
            (r'^(?:minimum\s+|basic\s+|required\s+|desired\s+)?qualifications?\s*:?$', 'requirements'),
            (r'^(?:what\s+(?:we(?:\x27re|\s+are)?\s+looking\s+for|you(?:\x27ll)?\s+need|you\s+bring|we\s+expect))\s*:?$', 'requirements'),
            (r'^(?:candidate\s+profile|eligibility(?:\s+criteria)?|must\s+haves?)\s*:?$', 'requirements'),
            (r'^(?:key\s+|primary\s+|core\s+|role\s*(?:&|and)\s*)?responsibilities?\s*:?$', 'responsibilities'),
            (r'^(?:duties|role\s+overview|what\s+you\s+will\s+do|scope\s+of\s+work|your\s+role)\s*:?$', 'responsibilities'),
            (r'^(?:preferred\s+|nice\s+to\s+have|bonus\s+points?|plus|good\s+to\s+have|desired\s+)(?:skills?|qualifications?|requirements?)?\s*:?$', 'preferred'),
            (r'^(?:tech\s+stack|tools\s*(?:&|and)\s*technologies)\s*:?$', 'requirements'),
            (r'^(?:education(?:al)?(?:\s+background|\s+qualifications?)?|academic\s+background)\s*:?$', 'education'),
            (r'^(?:experience|background|relevant\s+experience)\s*:?$', 'experience'),
            (r'^(?:project\s+experience|soft\s+skills)\s*:?$', 'skills'),
            (r'^(?:position\s+summary|role\s+summary|job\s+summary)\s*:?$', 'about'),
            (r'^(?:expected\s+deliverables|key\s+deliverables|deliverables)\s*:?$', 'responsibilities'),
            (r'^(?:growth\s+path|career\s+path|growth\s+opportunities)\s*:?$', 'about'),
            (r'^(?:about\s+(?:us|the\s+company|the\s+role|the\s+team)|company\s+overview|who\s+we\s+are)\s*:?$', 'about'),
            (r'^(?:location|work\s+mode|work\s+arrangement|workplace\s+type)\s*:?$', 'location'),
        ]
        
        current_section: Optional[Dict] = None
        current_content: List[str] = []
        
        for line_num, line in enumerate(lines, start=1):
            clean_line = re.sub(r'^[#*_\-\s•]+|[#*_\-\s:]+$', '', line).strip()
            # Check if line is a section header (headers are short and not full sentences)
            matched_section = None
            if clean_line and len(clean_line) <= 60 and not clean_line.endswith(('.', ';')):
                for pattern, section_type in section_patterns:
                    if re.search(pattern, clean_line, re.IGNORECASE):
                        matched_section = section_type
                        break
            
            if matched_section:
                # Save previous section
                if current_section:
                    current_section['content'] = '\n'.join(current_content).strip()
                    current_section['line_end'] = line_num - 1
                    if current_section['content']:
                        sections.append(JDSection(**current_section))
                elif current_content and any(c.strip() for c in current_content):
                    # Save initial content appearing before first explicit section header
                    sections.append(JDSection(
                        section_id=f"sec_{len(sections) + 1}",
                        title="Overview",
                        section_type="general",
                        line_start=1,
                        line_end=line_num - 1,
                        content='\n'.join(current_content).strip(),
                    ))
                
                # Start new section
                current_section = {
                    'section_id': f"sec_{len(sections) + 1}",
                    'title': clean_line,
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
        elif current_content and any(c.strip() for c in current_content):
            sections.append(JDSection(
                section_id="sec_1",
                title=None,
                content='\n'.join(current_content).strip(),
                section_type="general",
                line_start=1,
                line_end=len(lines)
            ))
        
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
        
        job_title = None
        try:
            params = self.parameter_extractor.extract_parameters(jd_text, sections)
            job_title = next((str(p.value).strip().lower() for p in params if p.parameter_name == "job_title"), None)
        except Exception:
            pass

        has_dedicated_req_sections = any(
            s.section_type in ("requirements", "skills", "responsibilities", "preferred", "education", "experience")
            for s in sections
        )

        # Process each section
        for section in sections:
            # When explicit technical/skills/responsibility sections exist, skip overview/about/location
            if has_dedicated_req_sections and section.section_type in ("about", "general", "location"):
                continue
            section_reqs = self._extract_from_section(section, job_title=job_title)
            requirements.extend(section_reqs)
        
        logger.info("[Deterministic] Extracted %d requirements", len(requirements))
        return requirements
    
    def _extract_from_section(self, section: JDSection, job_title: Optional[str] = None) -> List[StructuredRequirement]:
        """Extract requirements from a single section."""
        requirements: List[StructuredRequirement] = []
        
        # Split into sentences/clauses
        clauses = self._split_into_clauses(section.content, job_title=job_title)
        
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
    
    def _split_into_clauses(self, text: str, job_title: Optional[str] = None) -> List[str]:
        """
        Split text into atomic clauses by line and sentence.
        Preserves degree qualifications, lists of technologies, and decimal numbers.
        Filters out embedded headings like 'Project Experience' and metadata lines.
        """
        raw_lines = text.split('\n')
        clauses: List[str] = []

        subhead_pattern = re.compile(
            r'^(?:project\s+experience|soft\s+skills|technical\s+skills|required\s+technical\s+skills|'
            r'preferred\s+skills|good\s+to\s+have|key\s+skills|core\s+competencies|role\s+summary|'
            r'position\s+summary|job\s+summary|expected\s+deliverables|key\s+deliverables|deliverables|'
            r'growth\s+path|career\s+path|overview|summary|job\s+title|location|responsibilities|'
            r'qualifications|requirements|education)\s*:?$',
            re.IGNORECASE
        )

        metadata_pattern = re.compile(
            r'^(?:job\s+title|role(?:\s+type)?|priority|experience\s+level|seniority|location(?:\s*/\s*work\s+mode)?|'
            r'work\s+mode|salary|department|company|employment\s+type|reporting\s+(?:to|structure)|team\s+size)\s*:',
            re.IGNORECASE
        )

        for line in raw_lines:
            # Strip markdown and bullet decorators (preserve years like 8+ years)
            clean = re.sub(r'^[#*_\-\s•]+', '', line).strip()
            clean = re.sub(r'^\d+[\.\)\-\]]\s*', '', clean).strip()
            clean = re.sub(r'[*_]+$', '', clean).strip()

            if not clean or len(clean) < 6:
                continue

            # Skip lines matching job title or metadata headers
            if job_title and clean.lower() == job_title:
                continue

            if subhead_pattern.match(clean) or metadata_pattern.match(clean):
                continue

            # Split sentences on period only when followed by whitespace and capital letter
            # (protects decimals like TLM 2.0, Python 3.11, 8.5+ years)
            sentences = re.split(r'(?<=[a-zA-Z0-9])\.\s+(?=[A-Z])', clean)

            for sent in sentences:
                sent = sent.strip()
                if not sent or len(sent) < 8:
                    continue

                if job_title and sent.lower() == job_title:
                    continue

                # Filter out dangling fragmented prepositions/conjunctions
                lower_sent = sent.lower()
                if lower_sent.startswith(("or ", "and ", "in ", "with ", "to ", "for ", "of ")) and len(sent) < 30:
                    continue

                clauses.append(sent)

        return clauses

    def _classify_clause(self, text: str, section_type: str) -> ClauseType:
        """
        Conservatively classify clause type using section context and keyword signals.
        Section context takes precedence for dedicated requirements/responsibilities sections.
        """
        lower = text.lower()

        # Section context is the strongest indicator
        if section_type in ['responsibilities', 'duties']:
            return ClauseType.RESPONSIBILITY
        elif section_type in ['requirements', 'qualifications', 'skills', 'experience', 'education', 'preferred']:
            return ClauseType.REQUIREMENT
        elif section_type in ['about', 'company', 'location']:
            return ClauseType.CONTEXT

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
            'bachelor', 'degree', 'certification', 'hands-on', 'proficient'
        ]

        # Context indicators
        context_keywords = [
            'company', 'team', 'culture', 'environment',
            'startup', 'enterprise', 'industry'
        ]

        if any(kw in lower for kw in requirement_keywords):
            return ClauseType.REQUIREMENT

        if any(kw in lower for kw in responsibility_keywords):
            return ClauseType.RESPONSIBILITY

        if any(kw in lower for kw in context_keywords):
            return ClauseType.CONTEXT

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
