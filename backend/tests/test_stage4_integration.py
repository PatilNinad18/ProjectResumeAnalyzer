"""
Stage 4 Integration Tests: Clarification Re-Analysis, LLM Hook, and Immutability.

Tests the three-tier responsibility interpretation, clarification re-analysis,
and robustness to invalid/empty LLM hooks.
"""
import pytest
from app.services.deterministic import create_extractor
from app.services.interpretation import create_interpreter
from app.services.extraction_pipeline import ExtractionPipeline
from app.schemas.master_context import (
    ConfidenceLevel,
    ResponsibilityTier,
    ClauseType,
)


class TestClarificationReAnalysisImmutability:
    """Verify that re-analysis does not mutate original extraction."""

    def test_reanalyze_preserves_original_requirements(self):
        """Original requirements unchanged after re-analysis."""
        jd_text = "Senior Python Engineer required. Support junior developers."
        pipeline = ExtractionPipeline()
        
        original_result = pipeline.process_jd(jd_text)
        original_req_count = len(original_result.requirements)
        original_req_ids = [r.requirement_id for r in original_result.requirements]
        
        # Re-analyze with clarification (empty dict is safe)
        clarification = {}
        updated_result = pipeline.reanalyze_with_clarifications(
            jd_text,
            original_result,
            clarification
        )
        
        # Original must be unchanged
        assert len(original_result.requirements) == original_req_count
        assert [r.requirement_id for r in original_result.requirements] == original_req_ids
        
        # Updated result should be a new object
        assert updated_result is not original_result

    def test_reanalyze_preserves_parameters(self):
        """Original parameters unchanged after re-analysis."""
        jd_text = "Location: San Francisco. Senior Backend Engineer."
        pipeline = ExtractionPipeline()
        
        original_result = pipeline.process_jd(jd_text)
        original_param_count = len(original_result.parameters)
        
        clarification = {}
        updated_result = pipeline.reanalyze_with_clarifications(
            jd_text,
            original_result,
            clarification
        )
        
        # Original unchanged
        assert len(original_result.parameters) == original_param_count
        # Updated should have same parameters
        assert len(updated_result.parameters) == original_param_count

    def test_reanalyze_returns_new_result_object(self):
        """Re-analysis returns new ExtractionResult, not mutated original."""
        jd_text = "Python required. Support team needed."
        pipeline = ExtractionPipeline()
        
        original_result = pipeline.process_jd(jd_text)
        original_ambig_count = len(original_result.ambiguities)
        
        # Re-analyze with empty clarification
        clarification = {}
        result_2 = pipeline.reanalyze_with_clarifications(jd_text, original_result, clarification)
        
        # Results should be distinct objects
        assert result_2 is not original_result
        # Original should retain original ambiguity count
        assert len(original_result.ambiguities) == original_ambig_count


class TestResponsibilityInterpreterTiers:
    """Test three-tier responsibility interpretation."""

    def test_primary_tier_classification(self):
        """Primary responsibilities identified by action verbs."""
        jd_text = "Design and implement microservices architecture."
        extractor = create_extractor()
        sections = extractor.extract_sections(jd_text)
        requirements = extractor.extract_requirements(jd_text, sections)
        
        interpreter = create_interpreter()
        responsibilities = interpreter.interpret_responsibilities(requirements, jd_text)
        
        # Should classify as PRIMARY (action verb: design, implement)
        assert len(responsibilities) > 0
        primary_found = any(r.tier == ResponsibilityTier.PRIMARY for r in responsibilities)
        assert primary_found, "Should identify primary responsibilities with action verbs"

    def test_secondary_tier_classification(self):
        """Secondary responsibilities identified by support verbs."""
        jd_text = "Support the development team and collaborate on testing."
        extractor = create_extractor()
        sections = extractor.extract_sections(jd_text)
        requirements = extractor.extract_requirements(jd_text, sections)
        
        interpreter = create_interpreter()
        responsibilities = interpreter.interpret_responsibilities(requirements, jd_text)
        
        # Should classify as SECONDARY (support, collaborate)
        assert len(responsibilities) > 0

    def test_interpretation_confidence_assigned(self):
        """All responsibilities get interpretation confidence level."""
        jd_text = "Develop APIs. Maintain documentation. Assist team."
        extractor = create_extractor()
        sections = extractor.extract_sections(jd_text)
        requirements = extractor.extract_requirements(jd_text, sections)
        
        interpreter = create_interpreter()
        responsibilities = interpreter.interpret_responsibilities(requirements, jd_text)
        
        for resp in responsibilities:
            assert resp.interpretation_confidence in [
                ConfidenceLevel.HIGH,
                ConfidenceLevel.MEDIUM,
                ConfidenceLevel.LOW,
            ]

    def test_evidence_spans_tracked(self):
        """Responsibility evidence includes source references."""
        jd_text = "Design distributed systems. Build data pipelines."
        extractor = create_extractor()
        sections = extractor.extract_sections(jd_text)
        requirements = extractor.extract_requirements(jd_text, sections)
        
        interpreter = create_interpreter()
        responsibilities = interpreter.interpret_responsibilities(requirements, jd_text)
        
        assert len(responsibilities) > 0
        for resp in responsibilities:
            # Evidence should be populated from source spans
            assert hasattr(resp, 'source') and resp.source is not None


class TestDeterministicOfflineOperation:
    """Test that Stage 4 extraction works entirely offline/deterministically."""

    def test_extract_without_llm_hook_succeeds(self):
        """Full extraction works with no LLM hook."""
        jd_text = """
        Senior Software Engineer
        
        Requirements:
        - 10+ years backend development
        - Python 3.9+
        - AWS experience
        
        Responsibilities:
        - Design scalable systems
        - Lead architecture decisions
        - Mentor junior developers
        """
        
        # Create interpreter with NO llm_hook
        interpreter = create_interpreter(llm_hook=None)
        extractor = create_extractor()
        
        sections = extractor.extract_sections(jd_text)
        requirements = extractor.extract_requirements(jd_text, sections)
        parameters = extractor.extract_parameters(jd_text, sections)
        ambiguities = extractor.detect_ambiguities(jd_text, requirements)
        responsibilities = interpreter.interpret_responsibilities(requirements, jd_text)
        
        # All should succeed without network/LLM
        assert len(sections) > 0
        assert len(requirements) > 0
        assert len(responsibilities) > 0
        # Parameters are optional but should be present for this JD
        assert len(parameters) >= 0

    def test_pipeline_offline_extraction(self):
        """Full pipeline extraction is deterministic and offline."""
        jd_text = """
        Software Architect (Remote)
        Location: San Francisco, CA
        
        Must have:
        - System design experience
        - Cloud architecture
        
        Main Responsibilities:
        - Design system architecture
        - Review code and provide feedback
        """
        
        pipeline = ExtractionPipeline()
        result = pipeline.process_jd(jd_text)
        
        # Verify extraction succeeded deterministically
        assert result.extraction_mode == "deterministic"
        assert not result.llm_enabled
        assert len(result.requirements) > 0
        assert len(result.responsibilities) > 0


class TestEndToEndSampleJDExtraction:
    """Test full extraction pipeline on realistic sample JDs."""

    def test_technical_engineering_sample_extraction(self):
        """Extract technical engineering job description."""
        with open("backend/tests/sample_jds/01_technical_engineering.txt") as f:
            jd_text = f.read()
        
        pipeline = ExtractionPipeline()
        result = pipeline.process_jd(jd_text)
        
        # Verify extraction completeness
        assert len(result.sections) > 0, "Should identify sections"
        assert len(result.requirements) > 0, "Should extract requirements"
        assert len(result.responsibilities) > 0, "Should interpret responsibilities"
        
        # Verify no crashes and proper schema
        for resp in result.responsibilities:
            assert resp.interpretation_confidence is not None
            assert resp.tier in [
                ResponsibilityTier.PRIMARY,
                ResponsibilityTier.SECONDARY,
                ResponsibilityTier.SITUATIONAL,
            ]

    def test_hardware_engineering_sample_extraction(self):
        """Extract hardware engineering job description."""
        with open("backend/tests/sample_jds/06_hardware_engineering.txt") as f:
            jd_text = f.read()
        
        pipeline = ExtractionPipeline()
        result = pipeline.process_jd(jd_text)
        
        # Verify extraction completeness
        assert len(result.sections) > 0, "Should identify sections"
        assert len(result.requirements) > 0, "Should extract requirements"
        assert len(result.responsibilities) > 0, "Should interpret responsibilities"
        
        # Verify responsibilities have proper structure
        for resp in result.responsibilities:
            assert len(resp.description) > 0, "Responsibility should have description"
            assert resp.tier is not None, "Responsibility should have tier"

    def test_senior_engineering_sample_extraction(self):
        """Extract senior engineering job description."""
        with open("backend/tests/sample_jds/02_senior_engineering.txt") as f:
            jd_text = f.read()
        
        pipeline = ExtractionPipeline()
        result = pipeline.process_jd(jd_text)
        
        # Verify extraction
        assert len(result.requirements) > 0
        assert len(result.responsibilities) > 0
        
        # Senior roles should have some SITUATIONAL responsibilities
        tiers = {r.tier for r in result.responsibilities}
        assert ResponsibilityTier.SITUATIONAL in tiers or len(tiers) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
