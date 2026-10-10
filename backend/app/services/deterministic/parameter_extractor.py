"""
Deterministic parameter extraction service.

Extracts conventional JD parameters with evidence preservation:
- Job title and role
- Years of experience (min, max, range, relevant vs total)
- Skills and technologies
- Education and qualifications
- Location
- Work arrangements (onsite, hybrid, remote)
- Employment type
- Travel requirements
- Relocation requirements

Design principles:
- Deterministic pattern matching only (no LLM)
- Preserve original text and source spans
- Normalize only when safe
- Do not infer missing values
- Handle Unicode, punctuation, line endings
- Distinguish explicit vs inferred parameters
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from app.schemas.master_context import ExtractedParameter, JDSection, SourceReference
from app.services.deterministic.source_spans import SpanBuilder

logger = logging.getLogger("jd_agent.parameter_extractor")


class ParameterExtractor:
    """
    Deterministic parameter extraction engine.
    
    Extracts structured job parameters from JD text using
    conservative pattern matching.
    """
    
    def __init__(self):
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for parameter extraction."""
        
        # Job title patterns
        self.title_patterns = [
            re.compile(r'(?:job\s+title|position|role)\s*:?\s*([^\n.,]+)', re.IGNORECASE),
            re.compile(r'^([A-Z][A-Za-z\s&/]+(?:Engineer|Developer|Manager|Analyst|Designer|Architect))\s*$', re.MULTILINE),
        ]
        
        # Experience patterns - minimum
        self.exp_min_patterns = [
            re.compile(r'(\d+)\+\s*years?\s+(?:of\s+)?experience', re.IGNORECASE),
            re.compile(r'(?:at\s+least|minimum\s+(?:of\s+)?|min\.?)\s*(\d+)\s*years?', re.IGNORECASE),
            re.compile(r'(\d+)\s*years?\s+(?:or\s+more|minimum)', re.IGNORECASE),
        ]
        
        # Experience patterns - range
        self.exp_range_patterns = [
            re.compile(r'(\d+)\s*[-–—to]\s*(\d+)\s*years?', re.IGNORECASE),
            re.compile(r'between\s+(\d+)\s+and\s+(\d+)\s*years?', re.IGNORECASE),
        ]
        
        # Experience scope patterns (relevant vs total)
        self.exp_scope_patterns = [
            re.compile(r'(\d+)\+?\s*years?\s+of\s+relevant\s+experience', re.IGNORECASE),
            re.compile(r'(\d+)\+?\s*years?\s+of\s+experience\s+in\s+([^.,\n]+)', re.IGNORECASE),
            re.compile(r'(\d+)\+?\s*years?\s+of\s+total\s+experience', re.IGNORECASE),
        ]
        
        # Location patterns
        self.location_patterns = [
            re.compile(r'(?:location|based\s+in|located\s+in)\s*:?\s*([^.,\n]+)', re.IGNORECASE),
            re.compile(r'(?:office\s+location|work\s+location)\s*:?\s*([^.,\n]+)', re.IGNORECASE),
        ]
        
        # Work mode patterns
        self.work_mode_patterns = [
            (re.compile(r'\b(?:remote|work\s+from\s+home|wfh|fully\s+remote)\b', re.IGNORECASE), 'remote'),
            (re.compile(r'\b(?:onsite|on-site|in-office|office-based)\b', re.IGNORECASE), 'onsite'),
            (re.compile(r'\b(?:hybrid)\b', re.IGNORECASE), 'hybrid'),
        ]
        
        # Employment type patterns
        self.employment_patterns = [
            (re.compile(r'\b(?:full-time|full\s+time|fulltime)\b', re.IGNORECASE), 'full-time'),
            (re.compile(r'\b(?:part-time|part\s+time|parttime)\b', re.IGNORECASE), 'part-time'),
            (re.compile(r'\b(?:contract|contractor)\b', re.IGNORECASE), 'contract'),
            (re.compile(r'\b(?:temporary|temp)\b', re.IGNORECASE), 'temporary'),
            (re.compile(r'\b(?:intern|internship)\b', re.IGNORECASE), 'internship'),
        ]
        
        # Travel patterns
        self.travel_patterns = [
            re.compile(r'(?:travel|travelling)\s+(?:required|up\s+to)\s*:?\s*([^.,\n]+)', re.IGNORECASE),
            re.compile(r'(\d+)%\s+travel', re.IGNORECASE),
            re.compile(r'\b(?:no\s+travel|minimal\s+travel)\b', re.IGNORECASE),
        ]
        
        # Relocation patterns
        self.relocation_patterns = [
            re.compile(r'\b(?:relocation\s+(?:assistance|support|package)|willing\s+to\s+relocate)\b', re.IGNORECASE),
            re.compile(r'\b(?:no\s+relocation|relocation\s+not\s+provided)\b', re.IGNORECASE),
        ]
        
        # Education patterns
        self.education_patterns = [
            re.compile(r"\b(Bachelor'?s?|BS|BA|B\.S\.|B\.A\.)\s+(?:degree\s+)?(?:in\s+)?([^.,\n]+)?", re.IGNORECASE),
            re.compile(r"\b(Master'?s?|MS|MA|M\.S\.|M\.A\.)\s+(?:degree\s+)?(?:in\s+)?([^.,\n]+)?", re.IGNORECASE),
            re.compile(r"\b(PhD|Ph\.D\.|Doctorate)\s+(?:degree\s+)?(?:in\s+)?([^.,\n]+)?", re.IGNORECASE),
        ]
    
    def extract_all_parameters(
        self,
        jd_text: str,
        sections: List[JDSection]
    ) -> List[ExtractedParameter]:
        """
        Extract all supported parameters from JD.
        
        Args:
            jd_text: Full JD text
            sections: Parsed sections
        
        Returns:
            List of extracted parameters with evidence
        """
        parameters: List[ExtractedParameter] = []
        
        # Extract each parameter type
        parameters.extend(self.extract_job_title(jd_text))
        parameters.extend(self.extract_experience(jd_text))
        parameters.extend(self.extract_location(jd_text))
        parameters.extend(self.extract_work_mode(jd_text))
        parameters.extend(self.extract_employment_type(jd_text))
        parameters.extend(self.extract_travel(jd_text))
        parameters.extend(self.extract_relocation(jd_text))
        parameters.extend(self.extract_education(jd_text))
        
        logger.info("[ParameterExtractor] Extracted %d parameters", len(parameters))
        return parameters
    
    def extract_job_title(self, jd_text: str) -> List[ExtractedParameter]:
        """Extract job title/role."""
        parameters: List[ExtractedParameter] = []
        
        for pattern in self.title_patterns:
            match = pattern.search(jd_text)
            if match:
                title = match.group(1).strip()
                
                # Validate title (not too short, not all caps)
                if len(title) > 3 and not title.isupper():
                    parameters.append(ExtractedParameter(
                        parameter_name="job_title",
                        value=title,
                        category="role",
                        is_explicit=True,
                        source=SourceReference(
                            text=match.group(0),
                            section="metadata"
                        )
                    ))
                    break
        
        return parameters
    
    def extract_experience(self, jd_text: str) -> List[ExtractedParameter]:
        """
        Extract experience requirements.
        
        Handles:
        - Minimum years: "3+ years"
        - Ranges: "2-5 years"
        - Relevant vs total experience
        - Experience in specific domain
        """
        parameters: List[ExtractedParameter] = []
        
        # Check for range first (more specific)
        for pattern in self.exp_range_patterns:
            match = pattern.search(jd_text)
            if match:
                min_years = match.group(1)
                max_years = match.group(2)
                
                parameters.append(ExtractedParameter(
                    parameter_name="experience_range_min",
                    value=min_years,
                    category="experience",
                    is_explicit=True,
                    source=SourceReference(
                        text=match.group(0),
                        section="experience"
                    )
                ))
                
                parameters.append(ExtractedParameter(
                    parameter_name="experience_range_max",
                    value=max_years,
                    category="experience",
                    is_explicit=True,
                    source=SourceReference(
                        text=match.group(0),
                        section="experience"
                    )
                ))
                
                # Found range, don't look for minimum
                logger.debug(
                    "[ParameterExtractor] Experience range: %s-%s years",
                    min_years, max_years
                )
                return parameters
        
        # Check for scope-specific experience
        for pattern in self.exp_scope_patterns:
            match = pattern.search(jd_text)
            if match:
                years = match.group(1)
                
                # Determine if relevant or total
                text_lower = match.group(0).lower()
                if 'relevant' in text_lower:
                    param_name = "relevant_experience_years"
                elif 'total' in text_lower:
                    param_name = "total_experience_years"
                elif 'in' in text_lower and len(match.groups()) > 1:
                    param_name = "domain_experience_years"
                    # Also extract domain if present
                    domain = match.group(2).strip() if len(match.groups()) > 1 else None
                    if domain:
                        parameters.append(ExtractedParameter(
                            parameter_name="experience_domain",
                            value=domain,
                            category="experience",
                            is_explicit=True,
                            source=SourceReference(
                                text=match.group(0),
                                section="experience"
                            )
                        ))
                else:
                    param_name = "min_experience_years"
                
                parameters.append(ExtractedParameter(
                    parameter_name=param_name,
                    value=years,
                    category="experience",
                    is_explicit=True,
                    source=SourceReference(
                        text=match.group(0),
                        section="experience"
                    )
                ))
                
                return parameters
        
        # Check for minimum years (most general)
        for pattern in self.exp_min_patterns:
            match = pattern.search(jd_text)
            if match:
                years = match.group(1)
                
                parameters.append(ExtractedParameter(
                    parameter_name="min_experience_years",
                    value=years,
                    category="experience",
                    is_explicit=True,
                    source=SourceReference(
                        text=match.group(0),
                        section="experience"
                    )
                ))
                break
        
        return parameters
    
    def extract_location(self, jd_text: str) -> List[ExtractedParameter]:
        """Extract job location."""
        parameters: List[ExtractedParameter] = []
        
        for pattern in self.location_patterns:
            match = pattern.search(jd_text)
            if match:
                location = match.group(1).strip()
                
                # Validate location (not too short)
                if len(location) > 2:
                    parameters.append(ExtractedParameter(
                        parameter_name="location",
                        value=location,
                        category="location",
                        is_explicit=True,
                        source=SourceReference(
                            text=match.group(0),
                            section="metadata"
                        )
                    ))
                    break
        
        return parameters
    
    def extract_work_mode(self, jd_text: str) -> List[ExtractedParameter]:
        """Extract work arrangement (remote/onsite/hybrid)."""
        parameters: List[ExtractedParameter] = []
        
        for pattern, mode in self.work_mode_patterns:
            match = pattern.search(jd_text)
            if match:
                parameters.append(ExtractedParameter(
                    parameter_name="work_mode",
                    value=mode,
                    category="work_arrangement",
                    is_explicit=True,
                    source=SourceReference(
                        text=match.group(0),
                        section="metadata"
                    )
                ))
                break
        
        return parameters
    
    def extract_employment_type(self, jd_text: str) -> List[ExtractedParameter]:
        """Extract employment type (full-time, part-time, contract, etc.)."""
        parameters: List[ExtractedParameter] = []
        
        for pattern, emp_type in self.employment_patterns:
            match = pattern.search(jd_text)
            if match:
                parameters.append(ExtractedParameter(
                    parameter_name="employment_type",
                    value=emp_type,
                    category="employment",
                    is_explicit=True,
                    source=SourceReference(
                        text=match.group(0),
                        section="metadata"
                    )
                ))
                break
        
        return parameters
    
    def extract_travel(self, jd_text: str) -> List[ExtractedParameter]:
        """Extract travel requirements."""
        parameters: List[ExtractedParameter] = []
        
        for pattern in self.travel_patterns:
            match = pattern.search(jd_text)
            if match:
                # Extract percentage if present
                if match.lastindex and match.lastindex > 0:
                    travel_value = match.group(1).strip()
                else:
                    travel_value = match.group(0).strip()
                
                parameters.append(ExtractedParameter(
                    parameter_name="travel_requirement",
                    value=travel_value,
                    category="work_conditions",
                    is_explicit=True,
                    source=SourceReference(
                        text=match.group(0),
                        section="metadata"
                    )
                ))
                break
        
        return parameters
    
    def extract_relocation(self, jd_text: str) -> List[ExtractedParameter]:
        """Extract relocation requirements or assistance."""
        parameters: List[ExtractedParameter] = []
        
        for pattern in self.relocation_patterns:
            match = pattern.search(jd_text)
            if match:
                text_lower = match.group(0).lower()
                
                if 'not' in text_lower or 'no' in text_lower:
                    reloc_value = "not provided"
                else:
                    reloc_value = "available"
                
                parameters.append(ExtractedParameter(
                    parameter_name="relocation_assistance",
                    value=reloc_value,
                    category="benefits",
                    is_explicit=True,
                    source=SourceReference(
                        text=match.group(0),
                        section="metadata"
                    )
                ))
                break
        
        return parameters
    
    def extract_education(self, jd_text: str) -> List[ExtractedParameter]:
        """
        Extract education requirements.
        
        IMPORTANT: Distinguish years of education from years of experience.
        Only extract degree requirements, not years.
        """
        parameters: List[ExtractedParameter] = []
        
        for pattern in self.education_patterns:
            match = pattern.search(jd_text)
            if match:
                degree_level = match.group(1)
                field = match.group(2).strip() if match.lastindex > 1 and match.group(2) else None
                
                # Normalize degree level
                degree_normalized = self._normalize_degree(degree_level)
                
                parameters.append(ExtractedParameter(
                    parameter_name="education_level",
                    value=degree_normalized,
                    category="education",
                    is_explicit=True,
                    source=SourceReference(
                        text=match.group(0),
                        section="education"
                    )
                ))
                
                # Add field if present
                if field and len(field) > 2:
                    # Clean up field (remove "degree", "in", etc.)
                    field_clean = re.sub(r'\b(?:degree|in)\b', '', field, flags=re.IGNORECASE).strip()
                    if field_clean:
                        parameters.append(ExtractedParameter(
                            parameter_name="education_field",
                            value=field_clean,
                            category="education",
                            is_explicit=True,
                            source=SourceReference(
                                text=match.group(0),
                                section="education"
                            )
                        ))
                
                # Only extract first education requirement
                break
        
        return parameters
    
    def _normalize_degree(self, degree: str) -> str:
        """Normalize degree level to standard format."""
        degree_lower = degree.lower().replace('.', '').replace("'", '')
        
        if degree_lower in ['bachelor', 'bachelors', 'bs', 'ba']:
            return "Bachelor's"
        elif degree_lower in ['master', 'masters', 'ms', 'ma']:
            return "Master's"
        elif degree_lower in ['phd', 'doctorate']:
            return "PhD"
        
        return degree


def create_parameter_extractor() -> ParameterExtractor:
    """Factory function to create parameter extractor instance."""
    return ParameterExtractor()
