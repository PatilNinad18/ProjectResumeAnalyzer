"""
Deterministic missing information detection service.

Identifies information absent from JD that may be relevant for candidate evaluation:
- Missing conventional parameters (location, work mode, experience, etc.)
- Missing technical specifications
- Missing role context or scope
- Missing compensation or benefits information
- Missing team structure or reporting details

Design principles:
- Distinguish missing vs ambiguous vs conflicting information
- Do not classify every absent field as blocking
- Do not fabricate values for missing information
- Conservative detection (only flag truly relevant gaps)
- Evidence-based findings (report what is NOT present)
- Support downstream prioritization by Intern 2

Key distinctions:
- AMBIGUOUS: Information present but multiple interpretations possible
- MISSING: Information not stated in JD
- CONFLICT: Contradictory statements present
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from app.schemas.master_context import (
    ExtractedParameter,
    JDSection,
    StructuredRequirement,
    SourceReference,
)

logger = logging.getLogger("jd_agent.missing_info_detector")


@dataclass
class MissingInformation:
    """
    Information absent from JD.
    
    Internal finding structure for missing information.
    Does NOT modify shared schema (master_context.py).
    """
    missing_id: str
    category: str  # "parameter", "technical", "role_context", etc.
    parameter_name: str
    reason: str
    impact: str  # "high", "medium", "low"
    suggested_question: str
    is_blocking: bool = False  # Should this block finalization?
    
    def __post_init__(self):
        """Validate missing information."""
        valid_categories = [
            "parameter", "technical", "role_context", 
            "compensation", "team_structure"
        ]
        if self.category not in valid_categories:
            raise ValueError(f"Invalid category: {self.category}")
        
        valid_impacts = ["high", "medium", "low"]
        if self.impact not in valid_impacts:
            raise ValueError(f"Invalid impact: {self.impact}")


class MissingInfoDetector:
    """
    Deterministic missing information detection engine.
    
    Identifies relevant information gaps in JD without
    treating every missing field as a critical problem.
    """
    
    def __init__(self):
        # Define relevant parameters to check
        self.relevant_parameters = {
            "location": ("high", "Location determines candidate pool and logistics"),
            "work_mode": ("high", "Work arrangement affects candidate availability"),
            "employment_type": ("medium", "Employment type affects candidate interest"),
            "min_experience_years": ("high", "Experience requirement affects candidate screening"),
            "job_title": ("medium", "Job title provides role context"),
            "education_level": ("medium", "Education requirement affects candidate pool"),
            "travel_requirement": ("low", "Travel affects candidate preference"),
            "relocation_assistance": ("low", "Relocation affects candidate decisions"),
        }
    
    def detect_all_missing(
        self,
        jd_text: str,
        parameters: List[ExtractedParameter],
        requirements: List[StructuredRequirement],
        sections: List[JDSection],
        clarification_context: Optional[Dict[str, str]] = None
    ) -> List[MissingInformation]:
        """
        Detect all missing information in JD.
        
        Args:
            jd_text: Full JD text
            parameters: Extracted parameters
            requirements: Extracted requirements
            sections: Parsed sections
            clarification_context: Optional dict of provided clarifications
        
        Returns:
            List of missing information findings
        """
        missing_info: List[MissingInformation] = []
        
        # Detect missing parameters
        missing_info.extend(
            self.detect_missing_parameters(parameters)
        )
        
        # Detect missing technical specifications
        missing_info.extend(
            self.detect_missing_technical_specs(requirements)
        )
        
        # Detect missing role context
        missing_info.extend(
            self.detect_missing_role_context(sections, requirements)
        )
        
        # Filter based on clarification context if provided
        if clarification_context:
            missing_info = self._filter_clarified(missing_info, clarification_context)
        
        logger.info(
            "[MissingInfoDetector] Detected %d missing information items",
            len(missing_info)
        )
        return missing_info
    
    def detect_missing_parameters(
        self,
        parameters: List[ExtractedParameter]
    ) -> List[MissingInformation]:
        """
        Detect missing conventional JD parameters.
        
        Only flags parameters that are truly relevant for this role,
        not every possible parameter.
        """
        missing_info: List[MissingInformation] = []
        
        # Build set of extracted parameter names
        extracted_params = {param.parameter_name for param in parameters}
        
        # Check each relevant parameter
        for param_name, (impact, reason) in self.relevant_parameters.items():
            if param_name not in extracted_params:
                # Parameter is missing
                
                # Determine if blocking based on impact
                is_blocking = (impact == "high")
                
                missing_info.append(MissingInformation(
                    missing_id=f"missing_{len(missing_info) + 1:03d}_{param_name}",
                    category="parameter",
                    parameter_name=param_name,
                    reason=reason,
                    impact=impact,
                    suggested_question=self._generate_parameter_question(param_name),
                    is_blocking=is_blocking
                ))
                
                logger.debug(
                    "[MissingInfoDetector] Missing parameter: %s (impact: %s)",
                    param_name, impact
                )
        
        return missing_info
    
    def detect_missing_technical_specs(
        self,
        requirements: List[StructuredRequirement]
    ) -> List[MissingInformation]:
        """
        Detect missing technical specifications.
        
        Example: "Database experience required" but no specific database mentioned.
        
        IMPORTANT: Do not treat EKG entity presence as proof of requirement.
        Only flag if text suggests specificity but doesn't provide it.
        """
        missing_info: List[MissingInformation] = []
        
        # Generic technical terms that usually need specification
        generic_terms = {
            'database': 'specific database system',
            'programming': 'programming language',
            'framework': 'specific framework',
            'cloud': 'cloud platform',
            'version control': 'version control system',
            'testing': 'testing framework or methodology',
            'ci/cd': 'CI/CD tools',
            'monitoring': 'monitoring tools',
        }
        
        for req in requirements:
            text_lower = req.text.lower()
            
            # Check for generic technical terms
            for term, specification_needed in generic_terms.items():
                if term in text_lower:
                    # Check if specification is provided
                    # Simple heuristic: if EKG matched entities, likely specified
                    if not req.matched_entities or len(req.matched_entities) == 0:
                        # No specific tools identified
                        
                        # Check if this is truly asking for specifics
                        if any(word in text_lower for word in ['experience', 'knowledge', 'proficiency', 'skill']):
                            missing_info.append(MissingInformation(
                                missing_id=f"missing_{len(missing_info) + 1:03d}_spec",
                                category="technical",
                                parameter_name=f"{term}_specification",
                                reason=f"Generic '{term}' mentioned without specific {specification_needed}",
                                impact="medium",
                                suggested_question=f"Which {specification_needed} is required for this role?",
                                is_blocking=False
                            ))
                            
                            logger.debug(
                                "[MissingInfoDetector] Missing technical spec: %s in '%s'",
                                term, req.text[:50]
                            )
                            break
        
        return missing_info
    
    def detect_missing_role_context(
        self,
        sections: List[JDSection],
        requirements: List[StructuredRequirement]
    ) -> List[MissingInformation]:
        """
        Detect missing role context or scope information.
        
        Example: No section describing company, team, or role overview.
        """
        missing_info: List[MissingInformation] = []
        
        # Check for key sections
        section_types = {section.section_type for section in sections}
        
        # Check for "about" or company section
        if not any(stype in ['about', 'company', 'organization'] for stype in section_types):
            missing_info.append(MissingInformation(
                missing_id=f"missing_{len(missing_info) + 1:03d}_context",
                category="role_context",
                parameter_name="company_description",
                reason="No company or role context section found",
                impact="low",
                suggested_question="Can you provide context about the company and this role?",
                is_blocking=False
            ))
        
        # Check for responsibilities section
        if not any(stype in ['responsibilities', 'duties'] for stype in section_types):
            # Also check if any requirements are classified as responsibilities
            has_responsibilities = any(
                req.clause_type.value == 'RESPONSIBILITY'
                for req in requirements
            )
            
            if not has_responsibilities:
                missing_info.append(MissingInformation(
                    missing_id=f"missing_{len(missing_info) + 1:03d}_context",
                    category="role_context",
                    parameter_name="responsibilities",
                    reason="No job responsibilities or duties described",
                    impact="medium",
                    suggested_question="What are the primary responsibilities for this role?",
                    is_blocking=False
                ))
        
        # Check for requirements section
        if not any(stype in ['requirements', 'qualifications', 'skills'] for stype in section_types):
            missing_info.append(MissingInformation(
                missing_id=f"missing_{len(missing_info) + 1:03d}_context",
                category="role_context",
                parameter_name="requirements_section",
                reason="No requirements or qualifications section found",
                impact="medium",
                suggested_question="What are the required qualifications for this role?",
                is_blocking=False
            ))
        
        return missing_info
    
    def _generate_parameter_question(self, param_name: str) -> str:
        """Generate clarification question for missing parameter."""
        
        questions = {
            "location": "What is the job location or locations for this role?",
            "work_mode": "What is the work arrangement (remote, onsite, or hybrid)?",
            "employment_type": "What is the employment type (full-time, part-time, contract, etc.)?",
            "min_experience_years": "How many years of experience are required for this role?",
            "job_title": "What is the official job title for this position?",
            "education_level": "What level of education is required (Bachelor's, Master's, PhD)?",
            "travel_requirement": "Does this role require travel? If so, how much?",
            "relocation_assistance": "Is relocation assistance available for this role?",
        }
        
        return questions.get(
            param_name,
            f"Please provide information about: {param_name.replace('_', ' ')}"
        )
    
    def _filter_clarified(
        self,
        missing_info: List[MissingInformation],
        clarification_context: Dict[str, str]
    ) -> List[MissingInformation]:
        """
        Filter out missing information that has been clarified.
        
        This supports re-analysis after TA/HR provides information.
        """
        still_missing = []
        
        for info in missing_info:
            # Check if this missing info has been addressed
            # Look for clarification by missing_id or parameter_name
            is_clarified = (
                info.missing_id in clarification_context or
                info.parameter_name in clarification_context
            )
            
            if is_clarified:
                logger.debug(
                    "[MissingInfoDetector] Missing info %s clarified",
                    info.missing_id
                )
                continue
            
            # Still missing
            still_missing.append(info)
        
        logger.info(
            "[MissingInfoDetector] %d items remain after filtering clarified",
            len(still_missing)
        )
        return still_missing
    
    def prioritize_missing_info(
        self,
        missing_info: List[MissingInformation]
    ) -> Dict[str, List[MissingInformation]]:
        """
        Prioritize missing information by impact level.
        
        Returns:
            Dict mapping impact level to list of missing info items
        """
        prioritized = {
            "high": [],
            "medium": [],
            "low": []
        }
        
        for info in missing_info:
            prioritized[info.impact].append(info)
        
        logger.info(
            "[MissingInfoDetector] Prioritized: %d high, %d medium, %d low",
            len(prioritized["high"]),
            len(prioritized["medium"]),
            len(prioritized["low"])
        )
        
        return prioritized
    
    def should_block_finalization(
        self,
        missing_info: List[MissingInformation]
    ) -> Tuple[bool, List[str]]:
        """
        Determine if missing information should block JD finalization.
        
        Returns:
            Tuple of (should_block, list of blocking reasons)
        """
        blocking_items = [
            info for info in missing_info
            if info.is_blocking
        ]
        
        if blocking_items:
            reasons = [
                f"{info.parameter_name}: {info.reason}"
                for info in blocking_items
            ]
            logger.info(
                "[MissingInfoDetector] %d blocking items prevent finalization",
                len(blocking_items)
            )
            return True, reasons
        
        return False, []


def create_missing_info_detector() -> MissingInfoDetector:
    """Factory function to create missing info detector instance."""
    return MissingInfoDetector()
