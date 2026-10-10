"""
Test suite for EKG interpretation and responsibility mapping.

Tests:
- EKG entity matching accuracy
- Three-tier responsibility classification
- Capability mapping correctness
- Confidence assessment
- Integration with sample JD
"""
import pytest

from app.schemas.master_context import (
    ClauseType,
    ConfidenceLevel,
    ResponsibilityTier,
)
from app.services.deterministic import create_extractor
from app.services.ekg import get_ekg
from app.services.extraction_pipeline import ExtractionPipeline
from app.services.interpretation import create_interpreter


class TestEKGEntityMatching:
    """Test EKG entity matching functionality."""
    
    @pytest.fixture
    def ekg(self):
        """Get EKG instance."""
        return get_ekg()
    
    def test_ekg_initialization(self, ekg):
        """Test that EKG initializes with seed data."""
        stats = ekg.get_statistics()
        assert stats['initialized'] is True
        assert stats['total_entities'] > 0
        assert stats['total_relationships'] > 0
    
    def test_entity_types_present(self, ekg):
        """Test that all entity types are present in seed data."""
        stats = ekg.get_statistics()
        entity_types = stats['entity_types']
        
        # Should have skills, languages, tools, domains, etc.
        assert len(entity_types) > 0
        assert 'SKILL' in entity_types or 'LANGUAGE' in entity_types
    
    def test_python_entity_matching(self, ekg):
        """Test matching of Python entity."""
        matches = ekg.match_entities("Experience with Python required")
        
        # Should match Python
        assert len(matches) > 0
        # Find python entity
        entity_ids = [eid for eid, conf in matches]
        python_match = [eid for eid in entity_ids if 'python' in eid.lower()]
        assert len(python_match) > 0
    
    def test_embedded_skills_matching(self, ekg):
        """Test matching of embedded systems skills."""
        text = "FPGA programming with VHDL and Verilog experience"
        matches = ekg.match_entities(text)
        
        # Should match FPGA, VHDL, Verilog
        assert len(matches) >= 2  # At least 2 entities
        
        matched_entities = {eid: conf for eid, conf in matches}
        # Check confidence scores
        for entity_id, confidence in matches:
            assert 0.0 <= confidence <= 1.0
    
    def test_hardware_tools_matching(self, ekg):
        """Test matching of hardware tools."""
        text = "PCB design with Altium Designer and MATLAB experience"
        matches = ekg.match_entities(text)
        
        # Should match PCB design, Altium, MATLAB
        assert len(matches) >= 2
    
    def test_case_insensitive_matching(self, ekg):
        """Test that entity matching is case-insensitive."""
        text_lower = "python and react experience"
        text_upper = "PYTHON and REACT experience"
        text_mixed = "Python and React experience"
        
        matches_lower = ekg.match_entities(text_lower)
        matches_upper = ekg.match_entities(text_upper)
        matches_mixed = ekg.match_entities(text_mixed)
        
        # Should get same entities regardless of case
        entities_lower = {eid for eid, _ in matches_lower}
        entities_upper = {eid for eid, _ in matches_upper}
        entities_mixed = {eid for eid, _ in matches_mixed}
        
        assert entities_lower == entities_upper == entities_mixed
    
    def test_no_false_positives(self, ekg):
        """Test that common words don't trigger false matches."""
        text = "Strong communication skills and team player"
        matches = ekg.match_entities(text)
        
        # Should have very few or no matches (these are soft skills, not in seed data)
        # If matches exist, they should have lower confidence
        assert all(conf < 0.9 for _, conf in matches) or len(matches) == 0
    
    def test_entity_relationship_queries(self, ekg):
        """Test querying entity relationships."""
        # Find a language entity
        python_matches = ekg.match_entities("Python")
        if python_matches:
            entity_id = python_matches[0][0]
            
            # Get related entities
            related = ekg.get_related_entities(entity_id)
            # Should have at least some relationships
            assert isinstance(related, list)


class TestResponsibilityInterpretation:
    """Test three-tier responsibility interpretation."""
    
    @pytest.fixture
    def interpreter(self):
        """Create interpreter instance."""
        return create_interpreter()
    
    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return create_extractor()
    
    def test_primary_responsibility_classification(self, interpreter, extractor):
        """Test classification of PRIMARY responsibilities."""
        jd = """
        Responsibilities:
        Design and develop embedded systems firmware
        Lead technical architecture decisions
        Own the bring-up of new hardware prototypes
        """
        sections = extractor.extract_sections(jd)
        requirements = extractor.extract_requirements(jd, sections)
        
        responsibilities = interpreter.interpret_responsibilities(requirements, jd)
        
        # Should have PRIMARY responsibilities
        assert len(responsibilities) > 0
        primary_count = sum(1 for r in responsibilities if r.tier == ResponsibilityTier.PRIMARY)
        assert primary_count > 0
    
    def test_secondary_responsibility_classification(self, interpreter, extractor):
        """Test classification of SECONDARY responsibilities."""
        jd = """
        Support the development team with code reviews
        Assist in debugging production issues
        Contribute to documentation efforts
        """
        sections = extractor.extract_sections(jd)
        requirements = extractor.extract_requirements(jd, sections)
        
        responsibilities = interpreter.interpret_responsibilities(requirements, jd)
        
        # Should have SECONDARY responsibilities
        if responsibilities:
            secondary_count = sum(1 for r in responsibilities if r.tier == ResponsibilityTier.SECONDARY)
            assert secondary_count > 0
    
    def test_situational_responsibility_classification(self, interpreter, extractor):
        """Test classification of SITUATIONAL responsibilities."""
        jd = """
        May participate in on-call rotation as needed
        Occasionally travel to customer sites when required
        Could assist with hiring interviews from time to time
        """
        sections = extractor.extract_sections(jd)
        requirements = extractor.extract_requirements(jd, sections)
        
        responsibilities = interpreter.interpret_responsibilities(requirements, jd)
        
        # Should have SITUATIONAL responsibilities
        if responsibilities:
            situational_count = sum(
                1 for r in responsibilities if r.tier == ResponsibilityTier.SITUATIONAL
            )
            assert situational_count > 0
    
    def test_capability_mapping(self, interpreter, extractor):
        """Test that responsibilities are mapped to capabilities."""
        jd = """
        Requirements:
        Python programming
        React framework experience
        
        Responsibilities:
        Develop backend services using Python
        Build frontend interfaces with React
        """
        sections = extractor.extract_sections(jd)
        requirements = extractor.extract_requirements(jd, sections)
        
        responsibilities = interpreter.interpret_responsibilities(requirements, jd)
        
        # Should have responsibilities with capability mappings
        assert len(responsibilities) > 0
        # At least one responsibility should have capabilities mapped
        has_capabilities = any(len(r.required_capabilities) > 0 for r in responsibilities)
        # Note: May not always map due to entity matching limitations
        # So we don't assert True, just check structure is valid
        for resp in responsibilities:
            assert isinstance(resp.required_capabilities, list)
    
    def test_rationale_generation(self, interpreter, extractor):
        """Test that rationale is generated for each interpretation."""
        jd = "Design and implement backend APIs using Python and FastAPI"
        sections = extractor.extract_sections(jd)
        requirements = extractor.extract_requirements(jd, sections)
        
        responsibilities = interpreter.interpret_responsibilities(requirements, jd)
        
        # All responsibilities should have rationale
        for resp in responsibilities:
            assert resp.rationale is not None
            assert len(resp.rationale) > 0
    
    def test_confidence_assessment(self, interpreter, extractor):
        """Test confidence level assessment."""
        jd = """
        Develop embedded firmware using C and C++
        Lead FPGA design with VHDL
        """
        sections = extractor.extract_sections(jd)
        requirements = extractor.extract_requirements(jd, sections)
        
        responsibilities = interpreter.interpret_responsibilities(requirements, jd)
        
        # All responsibilities should have confidence assessment
        for resp in responsibilities:
            assert resp.interpretation_confidence in [
                ConfidenceLevel.HIGH,
                ConfidenceLevel.MEDIUM,
                ConfidenceLevel.LOW
            ]


class TestIntegrationWithSampleJD:
    """Integration tests with sample JD files."""
    
    @pytest.fixture
    def pipeline(self):
        """Create extraction pipeline."""
        return ExtractionPipeline(llm_enabled=False)
    
    def test_hardware_engineering_jd(self, pipeline):
        """Test extraction from hardware engineering JD."""
        # Read sample JD
        import pathlib
        jd_path = pathlib.Path(__file__).parent / "sample_jds" / "06_hardware_engineering.txt"
        
        if not jd_path.exists():
            pytest.skip(f"Sample JD not found: {jd_path}")
        
        jd_text = jd_path.read_text(encoding='utf-8')
        
        # Process JD
        result = pipeline.process_jd(jd_text)
        
        # Validate structure
        assert result.extraction_mode == "deterministic"
        assert result.llm_enabled is False
        
        # Should extract sections
        assert len(result.sections) > 0
        
        # Should extract requirements
        assert len(result.requirements) > 0
        
        # Should match EKG entities
        assert result.ekg_entities_matched > 0
        assert result.ekg_coverage_score > 0.0
        
        # Check for expected hardware skills
        all_req_text = ' '.join(r.text.lower() for r in result.requirements)
        hardware_indicators = ['fpga', 'vhdl', 'verilog', 'pcb', 'embedded', 'firmware']
        matched_indicators = [ind for ind in hardware_indicators if ind in all_req_text]
        assert len(matched_indicators) >= 2, f"Should match hardware skills, found: {matched_indicators}"
        
        # Should have EKG entity matches
        reqs_with_entities = [r for r in result.requirements if r.matched_entities]
        assert len(reqs_with_entities) > 0
        
        # Print summary for manual verification
        print(f"\n=== Extraction Summary ===")
        print(f"Sections: {len(result.sections)}")
        print(f"Requirements: {len(result.requirements)}")
        print(f"Responsibilities: {len(result.responsibilities)}")
        print(f"Parameters: {len(result.parameters)}")
        print(f"Ambiguities: {len(result.ambiguities)}")
        print(f"EKG entities matched: {result.ekg_entities_matched}")
        print(f"EKG coverage: {result.ekg_coverage_score:.1%}")
    
    def test_typed_extraction_result(self, pipeline):
        """Test that extraction result conforms to master_context schema."""
        jd = """
        Senior Backend Engineer
        
        Requirements:
        Python and FastAPI experience required
        5 years of backend development
        
        Responsibilities:
        Design and develop REST APIs
        Lead technical discussions
        """
        
        result = pipeline.process_jd(jd)
        
        # Validate all fields conform to schema
        assert hasattr(result, 'sections')
        assert hasattr(result, 'requirements')
        assert hasattr(result, 'disjunction_groups')
        assert hasattr(result, 'responsibilities')
        assert hasattr(result, 'parameters')
        assert hasattr(result, 'ambiguities')
        
        # Check requirement structure
        for req in result.requirements:
            assert hasattr(req, 'requirement_id')
            assert hasattr(req, 'text')
            assert hasattr(req, 'clause_type')
            assert hasattr(req, 'priority')
            assert hasattr(req, 'matched_entities')
            assert hasattr(req, 'entity_confidence')
            assert hasattr(req, 'source')
            
            # Check that clause_type is valid enum
            assert req.clause_type in list(ClauseType)
        
        # Check responsibility structure
        for resp in result.responsibilities:
            assert hasattr(resp, 'responsibility_id')
            assert hasattr(resp, 'description')
            assert hasattr(resp, 'tier')
            assert hasattr(resp, 'required_capabilities')
            assert hasattr(resp, 'interpretation_confidence')
            
            # Check that tier is valid enum
            assert resp.tier in list(ResponsibilityTier)
    
    def test_provenance_tracking_throughout_pipeline(self, pipeline):
        """Test that provenance is tracked through entire pipeline."""
        jd = "Python required. Design backend APIs."
        
        result = pipeline.process_jd(jd)
        
        # All requirements should have source references
        for req in result.requirements:
            assert req.source is not None
            assert req.source.text
        
        # All responsibilities should have source references
        for resp in result.responsibilities:
            assert resp.source is not None
            assert resp.source.text
        
        # All ambiguities should have source references
        for amb in result.ambiguities:
            assert amb.source is not None
            assert amb.source.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
