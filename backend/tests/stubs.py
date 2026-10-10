"""
tests/stubs.py — Stub factory for Intern 2 Track tests.

These factories produce JDMasterContext instances with pre-populated
StructuredRequirements, ResponsibilityContexts, etc., so that Intern 2's
clarification, projection, and query engine tests can run fully independently
of Intern 1's extraction code.

Usage:
    from tests.stubs import make_master_context, make_hardware_jd_context

    master = make_master_context()
    # or
    master = make_hardware_jd_context()
"""
from __future__ import annotations

from app.schemas.master_context import (
    ConfidenceBand,
    ConfidenceBreakdown,
    DisjunctionGroup,
    GraphActivity,
    JDMasterContext,
    JobContextInfo,
    LogicOperator,
    MatchedEntity,
    OriginType,
    ProvenanceRecord,
    RequirementPriority,
    ResponsibilityContext,
    RoleOverview,
    SourceSpan,
    StructuredRequirement,
)


# ---------------------------------------------------------------------------
# Provenance helpers
# ---------------------------------------------------------------------------

def explicit_prov(raw_text: str = "", section: str = "Requirements") -> ProvenanceRecord:
    """Create an EXPLICIT_JD provenance record."""
    return ProvenanceRecord(
        origin_type=OriginType.EXPLICIT_JD,
        source_span=SourceSpan(raw_text=raw_text, section=section),
        author="test_extractor",
    )


def ekg_prov(rule_id: str = "ekg_traversal") -> ProvenanceRecord:
    """Create an EKG_DERIVED provenance record (never is_mandatory)."""
    return ProvenanceRecord(
        origin_type=OriginType.EKG_DERIVED,
        author="ekg_engine",
        rule_id=rule_id,
    )


def ta_prov(user_id: str = "ta_user_001") -> ProvenanceRecord:
    """Create a TA_CONFIRMED provenance record."""
    return ProvenanceRecord(
        origin_type=OriginType.TA_CONFIRMED,
        author=user_id,
        rule_id="clarification:stub",
    )


# ---------------------------------------------------------------------------
# Requirement stubs
# ---------------------------------------------------------------------------

def make_must_have(text: str, min_years: float = None, section: str = "Requirements") -> StructuredRequirement:
    """A MUST_HAVE requirement from explicit JD text (Traceable Origin compliant)."""
    return StructuredRequirement(
        text=text,
        priority=RequirementPriority.MUST_HAVE,
        provenance=explicit_prov(raw_text=text, section=section),
        is_mandatory=True,
        min_years=min_years,
        confidence=ConfidenceBreakdown(
            entity_match_confidence=ConfidenceBand.HIGH,
            interpretation_confidence=ConfidenceBand.HIGH,
        ),
    )


def make_preferred(text: str) -> StructuredRequirement:
    """A PREFERRED requirement from explicit JD text."""
    return StructuredRequirement(
        text=text,
        priority=RequirementPriority.PREFERRED,
        provenance=explicit_prov(raw_text=text),
        is_mandatory=False,
        confidence=ConfidenceBreakdown(
            entity_match_confidence=ConfidenceBand.HIGH,
            interpretation_confidence=ConfidenceBand.MEDIUM,
        ),
    )


def make_unresolved(text: str) -> StructuredRequirement:
    """An UNRESOLVED requirement (ambiguous phrasing — needs TA clarification)."""
    return StructuredRequirement(
        text=text,
        priority=RequirementPriority.UNRESOLVED,
        provenance=explicit_prov(raw_text=text),
        is_mandatory=False,
        confidence=ConfidenceBreakdown(
            entity_match_confidence=ConfidenceBand.MEDIUM,
            interpretation_confidence=ConfidenceBand.UNKNOWN,
        ),
    )


def make_ekg_derived(text: str) -> StructuredRequirement:
    """
    An EKG_DERIVED informational requirement.
    is_mandatory=False is enforced by the Traceable Origin Invariant.
    """
    return StructuredRequirement(
        text=text,
        priority=RequirementPriority.INFORMATIONAL,
        provenance=ekg_prov(),
        is_mandatory=False,   # MUST be False for EKG_DERIVED
        ekg_node_ids=["ekg_stub_node_001"],
        confidence=ConfidenceBreakdown(
            entity_match_confidence=ConfidenceBand.HIGH,
            interpretation_confidence=ConfidenceBand.MEDIUM,
        ),
    )


def make_or_group(text_a: str, text_b: str) -> DisjunctionGroup:
    """An OR disjunction group: (text_a OR text_b)."""
    return DisjunctionGroup(
        operator=LogicOperator.OR,
        requirements=[make_must_have(text_a), make_must_have(text_b)],
        provenance=explicit_prov(raw_text=f"({text_a} OR {text_b})"),
    )


def make_responsibility(statement: str, section: str = "Responsibilities") -> ResponsibilityContext:
    """A responsibility context with stub EKG entity matches."""
    return ResponsibilityContext(
        raw_statement=statement,
        source_span=SourceSpan(raw_text=statement, section=section),
        matched_entities=[
            MatchedEntity(
                node_id="ekg_node_embedded_c",
                node_type="Language",
                canonical_name="C",
                match_confidence=ConfidenceBand.HIGH,
                aliases_matched=["C language", "C programming"],
            )
        ],
        graph_derived_activities=[
            GraphActivity(
                activity_description="Bare-metal firmware development using register-level C",
                derived_from_node_id="ekg_node_embedded_c",
                relation_type="used_for",
                confidence=ConfidenceBand.HIGH,
            )
        ],
    )


# ---------------------------------------------------------------------------
# Full JDMasterContext factories
# ---------------------------------------------------------------------------

def make_master_context(
    raw_jd_text: str = "Stub JD: We need an embedded engineer with C, RTOS, Python skills.",
    with_unresolved: bool = False,
    with_ekg_derived: bool = False,
) -> JDMasterContext:
    """
    Factory: minimal JDMasterContext for generic testing.
    Suitable for clarification engine and updater tests.
    """
    requirements = [
        make_must_have("Proficiency in C programming", min_years=5.0),
        make_must_have("Experience with RTOS (FreeRTOS or Zephyr)"),
        make_preferred("Python scripting for test automation"),
    ]
    if with_unresolved:
        requirements.append(make_unresolved("Knowledge of PCB design processes"))
    if with_ekg_derived:
        requirements.append(make_ekg_derived("Bare-metal firmware debugging (EKG derived)"))

    return JDMasterContext(
        raw_jd_text=raw_jd_text,
        role_overview=RoleOverview(
            job_title="Embedded Systems Engineer",
            seniority="Senior",
            department="Hardware Engineering",
            work_mode="ONSITE",
        ),
        job_context=JobContextInfo(
            company_context="SmartLeaven Technologies",
            business_context="Embedded product development for IoT",
        ),
        requirements=requirements,
        responsibilities=[
            make_responsibility("Design and implement firmware for ARM Cortex-M4 MCUs"),
            make_responsibility("Conduct board bring-up and hardware validation"),
        ],
    )


def make_hardware_jd_context() -> JDMasterContext:
    """
    Factory: full hardware/embedded JD context matching the sample JDs in tests/sample_jds/.
    Suitable for full integration and zero-LLM proof tests.
    """
    return JDMasterContext(
        raw_jd_text=(
            "Senior Embedded Systems Engineer\n\n"
            "We are looking for a senior embedded engineer with:\n"
            "- 5+ years of embedded C/C++ development (MANDATORY)\n"
            "- Experience with FreeRTOS or Zephyr RTOS (MANDATORY)\n"
            "- Proficiency with JTAG debugging and oscilloscopes (MUST HAVE)\n"
            "- Python scripting for test automation (PREFERRED)\n"
            "- Verilog OR VHDL experience (PREFERRED)\n"
            "- Knowledge of Altium Designer (nice to have)\n\n"
            "Responsibilities:\n"
            "- Design firmware for ARM Cortex-M series MCUs\n"
            "- Conduct board bring-up and pre-silicon validation\n"
            "- Collaborate with hardware team on PCB schematic review\n"
        ),
        role_overview=RoleOverview(
            job_title="Senior Embedded Systems Engineer",
            seniority="Senior",
            department="Hardware Engineering",
            location_city="Pune",
            location_country="India",
            work_mode="ONSITE",
        ),
        job_context=JobContextInfo(
            company_context="SmartLeaven Technologies — IoT & Embedded Products",
            business_context="Industrial IoT hardware products for manufacturing",
        ),
        requirements=[
            make_must_have("5+ years embedded C/C++ development", min_years=5.0),
            make_must_have("Experience with FreeRTOS or Zephyr RTOS"),
            make_must_have("Proficiency with JTAG debugging and oscilloscopes"),
            make_preferred("Python scripting for test automation"),
            make_or_group("Verilog", "VHDL"),
            make_preferred("Altium Designer PCB layout"),
            make_ekg_derived("Board bring-up workflow (EKG derived from ARM Cortex-M knowledge)"),
        ],
        responsibilities=[
            make_responsibility("Design firmware for ARM Cortex-M series MCUs"),
            make_responsibility("Conduct board bring-up and pre-silicon validation"),
            make_responsibility("Collaborate with hardware team on PCB schematic review"),
        ],
    )
