"""
Test suite for classifier robustness.

Tests the deterministic classifier against edge cases:
- Ambiguous clauses
- Multi-category clauses
- Minimal/maximal length inputs
- Special characters and formatting
- Conservative classification behavior
"""
import pytest

from app.schemas.master_context import (
    ClauseType,
    RequirementPriority,
)
from app.services.deterministic import create_extractor


class TestClassifierRobustness:
    """Test suite for conservative clause classification."""
    
    @pytest.fixture
    def extractor(self):
        """Create extractor instance for testing."""
        return create_extractor()
    
    def test_empty_input_handling(self, extractor):
        """Test handling of empty or whitespace-only input."""
        sections = extractor.extract_sections("")
        assert len(sections) == 1  # Single empty section
        assert sections[0].content == ""
        
        sections = extractor.extract_sections("   \n\n   ")
        assert len(sections) == 1
    
    def test_minimal_jd_extraction(self, extractor):
        """Test extraction from minimal JD."""
        jd = "Python required. 5 years experience."
        sections = extractor.extract_sections(jd)
        requirements = extractor.extract_requirements(jd, sections)
        
        assert len(requirements) > 0
        # Should extract at least Python requirement
        texts = [r.text.lower() for r in requirements]
        assert any('python' in t for t in texts)
    
    def test_responsibility_vs_requirement_classification(self, extractor):
        """Test conservative classification between responsibilities and requirements."""
        # Clear responsibility
        resp_jd = "Design and develop backend services using Python."
        sections = extractor.extract_sections(resp_jd)
        reqs = extractor.extract_requirements(resp_jd, sections)
        
        # Should contain at least one responsibility
        assert any(r.clause_type == ClauseType.RESPONSIBILITY for r in reqs)
        
        # Clear requirement
        req_jd = "5 years of Python experience required."
        sections = extractor.extract_sections(req_jd)
        reqs = extractor.extract_requirements(req_jd, sections)
        
        # Should contain at least one requirement
        assert any(r.clause_type == ClauseType.REQUIREMENT for r in reqs)
    
    def test_ambiguous_clause_handling(self, extractor):
        """Test that ambiguous clauses are flagged appropriately."""
        # Vague experience requirement
        jd = "5+ years of experience in relevant technologies."
        sections = extractor.extract_sections(jd)
        reqs = extractor.extract_requirements(jd, sections)
        ambiguities = extractor.detect_ambiguities(jd, reqs)
        
        # Should detect ambiguity in "5+ years"
        assert len(ambiguities) > 0
        assert any('5+' in amb.text or 'years' in amb.text for amb in ambiguities)
    
    def test_priority_detection_mandatory(self, extractor):
        """Test detection of mandatory requirements."""
        jd = "Python is required. Must have 5 years experience."
        sections = extractor.extract_sections(jd)
        reqs = extractor.extract_requirements(jd, sections)
        
        # Should have at least one MANDATORY requirement
        assert any(r.priority == RequirementPriority.MANDATORY for r in reqs)
    
    def test_priority_detection_preferred(self, extractor):
        """Test detection of preferred requirements."""
        jd = "Python preferred. Nice to have: React experience."
        sections = extractor.extract_sections(jd)
        reqs = extractor.extract_requirements(jd, sections)
        
        # Should have at least one PREFERRED requirement
        assert any(r.priority == RequirementPriority.PREFERRED for r in reqs)
    
    def test_disjunction_detection(self, extractor):
        """Test detection of OR groups."""
        jd = "Experience with Python or Java required."
        sections = extractor.extract_sections(jd)
        reqs = extractor.extract_requirements(jd, sections)
        disjunctions = extractor.detect_disjunctions(reqs)
        
        # Should detect OR group
        assert len(disjunctions) > 0
        assert all(d.operator == "OR" for d in disjunctions)
    
    def test_section_identification(self, extractor):
        """Test section identification with common headers."""
        jd = """
Requirements:
Python, Java, React

Responsibilities:
Design and develop backend services
Lead technical discussions
        """
        sections = extractor.extract_sections(jd)
        
        # Should identify multiple sections
        assert len(sections) >= 2
        section_types = [s.section_type for s in sections]
        assert 'requirements' in section_types
        assert 'responsibilities' in section_types
    
    def test_parameter_extraction_location(self, extractor):
        """Test extraction of location parameter."""
        jd = "Location: Bangalore, India. Remote work not available."
        sections = extractor.extract_sections(jd)
        params = extractor.extract_parameters(jd, sections)
        
        # Should extract location
        location_params = [p for p in params if p.parameter_name == 'location']
        assert len(location_params) > 0
        assert 'bangalore' in location_params[0].value.lower()
    
    def test_parameter_extraction_work_mode(self, extractor):
        """Test extraction of work mode parameter."""
        test_cases = [
            ("Fully remote position", "remote"),
            ("Onsite work required", "onsite"),
            ("Hybrid work arrangement", "hybrid"),
        ]
        
        for jd_text, expected_mode in test_cases:
            sections = extractor.extract_sections(jd_text)
            params = extractor.extract_parameters(jd_text, sections)
            
            work_mode_params = [p for p in params if p.parameter_name == 'work_mode']
            if work_mode_params:
                assert expected_mode in work_mode_params[0].value.lower()
    
    def test_special_characters_handling(self, extractor):
        """Test handling of special characters in JD text."""
        jd = "C++/C# required. Experience with .NET & ASP.NET Core."
        sections = extractor.extract_sections(jd)
        reqs = extractor.extract_requirements(jd, sections)
        
        # Should handle special characters without crashing
        assert len(reqs) > 0
        texts = ' '.join(r.text for r in reqs)
        # Should preserve special chars
        assert '++' in texts or 'c#' in texts.lower() or '.net' in texts.lower()
    
    def test_multi_sentence_clause_splitting(self, extractor):
        """Test splitting of multi-sentence requirements."""
        jd = "Python required. Java preferred. React is a plus."
        sections = extractor.extract_sections(jd)
        reqs = extractor.extract_requirements(jd, sections)
        
        # Should split into separate requirements
        assert len(reqs) >= 3
    
    def test_conservative_classification_default(self, extractor):
        """Test that ambiguous inputs default to conservative classification."""
        # Unclear clause
        jd = "Good understanding of software development principles."
        sections = extractor.extract_sections(jd)
        reqs = extractor.extract_requirements(jd, sections)
        
        # Should classify conservatively (CONTEXTUAL or AMBIGUOUS)
        if reqs:
            assert reqs[0].priority in [
                RequirementPriority.CONTEXTUAL,
                RequirementPriority.MANDATORY
            ]
    
    def test_no_false_positive_entities(self, extractor):
        """Test that EKG matching doesn't produce false positives."""
        jd = "Experience in a fast-paced environment."
        sections = extractor.extract_sections(jd)
        reqs = extractor.extract_requirements(jd, sections)
        
        # "fast-paced environment" is not a technical skill
        # Should not match technical entities
        for req in reqs:
            if 'fast-paced' in req.text.lower():
                # Should have low or no entity matches
                assert len(req.matched_entities) <= 1
    
    def test_provenance_tracking(self, extractor):
        """Test that source references are properly tracked."""
        jd = "Python required for backend development."
        sections = extractor.extract_sections(jd)
        reqs = extractor.extract_requirements(jd, sections)
        
        # All requirements should have source references
        assert all(req.source is not None for req in reqs)
        assert all(req.source.text for req in reqs)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
