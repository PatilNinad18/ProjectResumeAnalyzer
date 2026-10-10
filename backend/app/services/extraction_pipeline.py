"""
Main extraction pipeline orchestrator.

Coordinates EKG, deterministic extraction, and interpretation services
to produce complete ExtractionResult objects.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

from app.schemas.master_context import ExtractionResult
from app.services.deterministic import create_extractor
from app.services.interpretation import create_interpreter

logger = logging.getLogger("jd_agent.extraction_pipeline")


class ExtractionPipeline:
    """
    Main pipeline for Intern 1: Extraction & Domain Intelligence Engine.
    
    Orchestrates:
    1. Section identification
    2. Requirement extraction with EKG entity matching
    3. Parameter extraction
    4. Disjunction detection
    5. Ambiguity detection
    6. Three-tier responsibility interpretation
    """
    
    def __init__(self, llm_enabled: bool = False):
        """
        Initialize pipeline.
        
        Args:
            llm_enabled: Whether to enable LLM-assisted extraction.
                        Currently only deterministic mode is implemented.
        """
        self.llm_enabled = llm_enabled
        self.extractor = create_extractor()
        self.interpreter = create_interpreter()
        
        if llm_enabled:
            logger.warning(
                "[Pipeline] LLM-assisted mode requested but not yet implemented. "
                "Using deterministic mode."
            )
            self.llm_enabled = False
    
    def process_jd(self, jd_text: str) -> ExtractionResult:
        """
        Process a job description and return structured extraction result.
        
        Args:
            jd_text: Raw job description text
        
        Returns:
            ExtractionResult with all extracted information
        """
        logger.info("[Pipeline] Starting JD extraction (deterministic mode)")
        
        # Step 1: Extract sections
        sections = self.extractor.extract_sections(jd_text)
        
        # Step 2: Extract requirements with EKG matching
        requirements = self.extractor.extract_requirements(jd_text, sections)
        
        # Step 3: Extract parameters
        parameters = self.extractor.extract_parameters(jd_text, sections)
        
        # Step 4: Detect disjunction groups
        disjunction_groups = self.extractor.detect_disjunctions(requirements)
        
        # Step 5: Detect ambiguities
        ambiguities = self.extractor.detect_ambiguities(jd_text, requirements)
        
        # Step 6: Interpret responsibilities
        responsibilities = self.interpreter.interpret_responsibilities(
            requirements, jd_text
        )
        
        # Calculate EKG statistics
        total_reqs = len(requirements)
        reqs_with_entities = sum(
            1 for req in requirements if req.matched_entities
        )
        total_entities_matched = sum(
            len(req.matched_entities) for req in requirements
        )
        ekg_coverage = reqs_with_entities / total_reqs if total_reqs > 0 else 0.0
        
        # Assemble result
        result = ExtractionResult(
            sections=sections,
            requirements=requirements,
            disjunction_groups=disjunction_groups,
            responsibilities=responsibilities,
            parameters=parameters,
            ambiguities=ambiguities,
            extraction_mode="deterministic",
            llm_enabled=self.llm_enabled,
            ekg_entities_matched=total_entities_matched,
            ekg_coverage_score=ekg_coverage
        )
        
        logger.info(
            "[Pipeline] Extraction complete: %d sections, %d requirements, "
            "%d responsibilities, %d parameters, %d ambiguities, "
            "EKG coverage: %.1f%%",
            len(sections), len(requirements), len(responsibilities),
            len(parameters), len(ambiguities), ekg_coverage * 100
        )
        
        return result

    def reanalyze_with_clarifications(
        self,
        jd_text: str,
        original_result: ExtractionResult,
        clarification_context: Dict[str, str],
    ) -> ExtractionResult:
        """
        Re-analyze JD combining original evidence with TA/HR clarifications.

        This allows upstream (Intern 2) to supply answered questions and safely
        merge them without polluting the original JD evidence.
        
        Args:
            jd_text: Original raw JD text
            original_result: Previous extraction result containing the original AST
            clarification_context: Dict mapping `ambiguity_id`, `missing_id`, or
                                   `responsibility_id` to the TA/HR answer.

        Returns:
            A new ExtractionResult with updated ambiguities and responsibilities.
            Original parameters/requirements are preserved verbatim.
        """
        logger.info(
            "[Pipeline] Re-analyzing JD with %d clarification answers",
            len(clarification_context),
        )

        # 1. Re-evaluate ambiguities
        # Re-detect ambiguities (fresh pass). In a full implementation, the
        # ambiguity detector would filter out resolved findings based on
        # clarification_context. For now, we do a fresh detection.
        updated_ambiguities = self.extractor.detect_ambiguities(
            jd_text=jd_text,
            requirements=original_result.requirements,
        )
        
        # Filter out ambiguities that were answered in clarification_context
        # (This is a conservative approach: if ambiguity_id is in clarifications,
        # assume it was resolved by TA and don't include it in updated list)
        if clarification_context:
            updated_ambiguities = [
                amb for amb in updated_ambiguities
                if amb.ambiguity_id not in clarification_context
            ]

        # 2. Re-interpret Responsibilities (Tier 3 application)
        # Pass clarifications so TA facts can be ingested without altering 
        # the literal evidence arrays.
        updated_responsibilities = self.interpreter.interpret_responsibilities(
            requirements=original_result.requirements,
            jd_text=jd_text,
            clarification_context=clarification_context,
        )

        # 3. Create updated ExtractionResult
        new_result = ExtractionResult(
            sections=original_result.sections,
            requirements=original_result.requirements,       # Unchanged evidence
            disjunction_groups=original_result.disjunction_groups, # Unchanged
            responsibilities=updated_responsibilities,       # Updated w/ Tier 3
            parameters=original_result.parameters,           # Unchanged evidence
            ambiguities=updated_ambiguities,                 # Resolved items removed
            extraction_mode=original_result.extraction_mode,
            llm_enabled=original_result.llm_enabled,
            ekg_entities_matched=original_result.ekg_entities_matched,
            ekg_coverage_score=original_result.ekg_coverage_score,
        )

        return new_result


def process_job_description(
    jd_text: str,
    llm_enabled: bool = False
) -> ExtractionResult:
    """
    Convenience function to process a JD.
    
    Args:
        jd_text: Raw job description text
        llm_enabled: Whether to use LLM assistance (not yet implemented)
    
    Returns:
        ExtractionResult
    """
    pipeline = ExtractionPipeline(llm_enabled=llm_enabled)
    return pipeline.process_jd(jd_text)
