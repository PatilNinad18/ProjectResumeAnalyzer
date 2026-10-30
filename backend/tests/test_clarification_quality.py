"""Semantic ambiguity verification and false-positive regression tests."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.schemas.master_context import (
    ConfidenceBand,
    JDMasterContext,
    RequirementPriority,
    RoleOverview,
)
from app.services.clarification import engine
from tests.stubs import make_must_have, make_preferred, make_responsibility


def _master(raw_jd: str, requirements=None, *, title: str = "Engineer", responsibilities=None):
    return JDMasterContext(
        raw_jd_text=raw_jd,
        role_overview=RoleOverview(job_title=title),
        requirements=requirements or [],
        responsibilities=responsibilities or [],
    )


def _verified_payload(evidence: str, question: str) -> dict:
    return {
        "is_genuine_ambiguity": True,
        "ambiguity_type": "priority_or_scope",
        "interpretation_a": "The requirement is mandatory and disqualifying.",
        "interpretation_b": "The requirement is preferred and not disqualifying.",
        "material_impact": "These interpretations change candidate screening eligibility.",
        "source_evidence": evidence,
        "clarification_question": question,
        "answer_options": [
            {"label": "Mandatory", "description": "Candidates must satisfy this criterion."},
            {"label": "Preferred", "description": "The criterion is not disqualifying."},
        ],
        "reasoning": "Both interpretations are supported by the source and affect screening.",
    }


def _install_fake_llm(monkeypatch, response: dict, captured: list | None = None):
    class FakeLLMService:
        def complete_structured(self, **kwargs):
            if captured is not None:
                captured.append(kwargs)
            return SimpleNamespace(parsed_json=response, raw_text=json.dumps(response))

    monkeypatch.setattr(
        engine,
        "_get_clarification_llm_service",
        lambda: FakeLLMService(),
    )


@pytest.mark.parametrize(
    "raw_jd,title,requirements,responsibilities",
    [
        (
            "Requirements:\n- Must have 5 to 15 years of systems engineering.\n"
            "- Python is required for test automation.\n"
            "- Experience with PCIe, CXL, UCIe, AMBA, AXI, and NVLink.\n"
            "- Hybrid work arrangement.",
            "Lead Architect",
            [
                make_must_have("Must have 5 to 15 years of systems engineering."),
                make_must_have("Python is required for test automation."),
                make_must_have("Experience with PCIe, CXL, UCIe, AMBA, AXI, and NVLink."),
                make_must_have("Hybrid work arrangement."),
            ],
            [],
        ),
        (
            "Responsibilities:\n- Lead the design of platform architecture.",
            "Lead Architect",
            [],
            [make_responsibility("Lead the design of platform architecture.")],
        ),
        (
            "Requirements:\n- Python experience is required.",
            "Engineer",
            [
                make_must_have("Python experience is required."),
            ],
            [],
        ),
        (
            "Requirements:\n- We welcome applicants from all backgrounds.\n"
            "- Employment is subject to background checks.\n"
            "- This role uses relevant systems where appropriate.",
            "Principal Engineer",
            [],
            [],
        ),
    ],
)
def test_clear_requirements_and_false_positive_signals_do_not_generate_questions(
    monkeypatch, raw_jd, title, requirements, responsibilities
):
    if requirements and raw_jd.endswith("Python experience is required."):
        requirements[0].confidence.entity_match_confidence = ConfidenceBand.LOW
        requirements[0].ekg_node_ids = []
    master = _master(
        raw_jd,
        requirements,
        title=title,
        responsibilities=responsibilities,
    )

    def unexpected_llm():
        raise AssertionError("The LLM must not be called without a grounded ambiguity candidate.")

    monkeypatch.setattr(engine, "_get_clarification_llm_service", unexpected_llm)
    result = engine.generate_clarification_questions(master)

    assert result.clarification_history == []
    assert result.lifecycle_status.value == "READY_FOR_REVIEW"


def test_missing_salary_and_team_size_are_not_clarification_questions(monkeypatch):
    master = _master("Requirements:\n- Python experience is required.", [make_must_have("Python experience is required.")])
    monkeypatch.setattr(
        engine,
        "_get_clarification_llm_service",
        lambda: (_ for _ in ()).throw(AssertionError("No semantic candidate expected")),
    )

    result = engine.generate_clarification_questions(master)

    assert result.clarification_history == []


@pytest.mark.parametrize(
    "raw_jd,requirement,question,evidence",
    [
        (
            "Requirements:\n- Python experience is mandatory.\n"
            "- Python experience is preferred for automation.",
            None,
            "Should Python experience be mandatory or preferred?",
            "Python experience is mandatory.\n- Python experience is preferred for automation.",
        ),
        (
            "Requirements:\n- Experience with Java and Python or C# is required.",
            "Experience with Java and Python or C# is required.",
            "Does the requirement need Java and Python together, or either option?",
            "Experience with Java and Python or C# is required.",
        ),
        (
            "Requirements:\n- Strong experience with relevant semiconductor simulation tools is required.",
            "Strong experience with relevant semiconductor simulation tools is required.",
            "Which semiconductor simulation tools meet the stated requirement?",
            "Strong experience with relevant semiconductor simulation tools is required.",
        ),
    ],
)
def test_genuine_conflict_logic_and_vague_technical_scope_are_verified(
    monkeypatch, raw_jd, requirement, question, evidence
):
    if requirement is None:
        requirements = [
            make_must_have("Python experience is mandatory."),
            make_preferred("Python experience is preferred for automation."),
        ]
    else:
        requirements = [make_must_have(requirement)]
    captured = []
    _install_fake_llm(monkeypatch, _verified_payload(evidence, question), captured)

    result = engine.generate_clarification_questions(
        _master(raw_jd, requirements, title="Senior Engineer")
    )

    assert len(result.clarification_history) == 1
    generated = result.clarification_history[0]
    assert generated.question_text == question
    assert generated.structured_options
    assert generated.rationale.count("Original JD Statement:") == 1
    assert len(captured) == 1
    prompt = json.loads(captured[0]["user_prompt"])
    assert prompt["complete_original_jd"] == raw_jd
    assert prompt["exact_source_statements"]
    assert prompt["surrounding_paragraph"]
    assert prompt["section_heading"] == "Requirements"
    assert prompt["extracted_requirement_and_priority"]


def test_semantic_verifier_rejects_nonmaterial_or_ungrounded_response(monkeypatch):
    raw_jd = "Requirements:\n- Experience with Java and Python or C# is required."
    requirement = make_must_have("Experience with Java and Python or C# is required.")
    invalid = _verified_payload("Experience with Java and Python or C# is required.", "What about Java?")
    invalid["interpretation_b"] = invalid["interpretation_a"]
    _install_fake_llm(monkeypatch, invalid)

    result = engine.generate_clarification_questions(_master(raw_jd, [requirement]))

    assert result.clarification_history == []
    assert result.lifecycle_status.value == "READY_FOR_REVIEW"


def test_semantic_verifier_fails_closed_when_model_evidence_is_not_from_jd(monkeypatch):
    raw_jd = "Requirements:\n- Experience with Java and Python or C# is required."
    requirement = make_must_have("Experience with Java and Python or C# is required.")
    invalid = _verified_payload(
        "Candidates must have ten years of cloud security experience.",
        "Does the requirement need Java and Python together, or either option?",
    )
    _install_fake_llm(monkeypatch, invalid)

    result = engine.generate_clarification_questions(_master(raw_jd, [requirement]))

    assert result.clarification_history == []


def test_unresolved_extraction_is_rejected_when_jd_context_resolves_priority(monkeypatch):
    raw_jd = "Preferred Qualifications:\n- Python experience is preferred."
    requirement = make_preferred("Python experience is preferred.")
    requirement.priority = RequirementPriority.UNRESOLVED
    response = {
        "is_genuine_ambiguity": False,
        "ambiguity_type": "priority",
        "interpretation_a": "Python is mandatory.",
        "interpretation_b": "Python is preferred.",
        "material_impact": "Would change candidate screening.",
        "source_evidence": "Python experience is preferred.",
        "clarification_question": "Should Python be mandatory?",
        "answer_options": [
            {"label": "Mandatory", "description": "Required for screening."},
            {"label": "Preferred", "description": "Not disqualifying."},
        ],
        "reasoning": "The section heading and source sentence explicitly state preferred.",
    }
    captured = []
    _install_fake_llm(monkeypatch, response, captured)

    result = engine.generate_clarification_questions(_master(raw_jd, [requirement]))

    assert result.clarification_history == []
    assert json.loads(captured[0]["user_prompt"])["section_heading"] == "Preferred Qualifications"
