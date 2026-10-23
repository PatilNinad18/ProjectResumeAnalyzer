"""
test_inference_optimization.py — Regression tests for JD Agent inference optimization.

Verifies:
1. Compressed prompt integrity (preserves all rules, enums, limits, and schema keys).
2. Dynamic predict token tuning (scales predictably with JD word count, prevents runaway generation).
3. Measured adaptive context strategy (selects 2048 when safe, retains 4096 for long/complex JDs).
4. Anti-truncation safeguard (automatically retries with 4096 if length ceiling is reached under 2048).
5. Structured specification completeness on complex and long JDs.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.canonical import JobEvaluationSpecification, Priority
from app.services.agent import JDUnderstandingAgent, JDUnderstandingError
from app.services.llm_service import LLMResult, LLMService, LLMUsage
from app.services.prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt


# ---------------------------------------------------------------------------
# Test Job Descriptions
# ---------------------------------------------------------------------------

JD_SHORT = """Job Title: Junior Python Developer
Location: Remote
Requirements:
- 1+ years of Python experience
- FastAPI knowledge
"""

JD_LONG_COMPLEX = """Job Title: Lead Autonomous Robotics & Embedded Platform Architect
Location: Seattle, WA (Hybrid - 3 days onsite)
Salary: $180,000 - $220,000
Clearance: US Citizenship required for aerospace compliance

About the Role:
We are seeking a Lead Robotics & Systems Architect with 8+ years of experience
architecting high-reliability embedded platforms, real-time control loops, and edge perception pipelines.

Requirements:
- 8+ years of modern C++ (C++17/20) and Python for robotics platforms.
- Deep expertise in ROS2 (Robot Operating System), DDS middleware, and real-time Linux (PREEMPT_RT).
- Hands-on experience with sensor fusion (LiDAR, Radar, IMU, Stereo Cameras) and Kalman filtering.
- Experience with embedded Linux board bring-up on ARM Cortex-A and NVIDIA Jetson (Orin/Xavier).
- Proven track record with FPGA hardware acceleration using VHDL/Verilog is preferred.
- Familiarity with functional safety standards (ISO 26262, IEC 61508).
- Master's or PhD degree in Robotics, Electrical Engineering, or Computer Science.
- Excellent cross-functional technical leadership and mentoring experience.

Responsibilities:
- Architect end-to-end edge compute architecture for autonomous inspection rovers.
- Design real-time telemetry streaming over gRPC and ZeroMQ.
- Oversee hardware-in-the-loop (HIL) testing and thermal qualification.
- Collaborate with AI researchers to deploy TensorRT quantized models on Jetson nodes.
- Lead code reviews, architecture decision records (ADRs), and safety compliance audits.
"""


# ---------------------------------------------------------------------------
# 1. Prompt Integrity & Constraint Verification
# ---------------------------------------------------------------------------

def test_compressed_prompt_preserves_all_canonical_schema_keys():
    """Verify that the compressed SYSTEM_PROMPT retains every canonical top-level key."""
    expected_keys = [
        "role",
        "job_context",
        "responsibilities",
        "conventional_requirements",
        "must_have_requirements",
        "preferred_requirements",
        "responsibility_requirement_mapping",
        "requirement_interpretations",
        "evidence_requirements",
        "non_conventional_parameters",
        "evaluation_rules",
        "unscored_rules",
        "prohibited_inferences",
        "compliance_flags",
        "ambiguities",
        "missing_information",
        "ta_confirmation_required",
        "candidate_analysis_instructions",
    ]
    for key in expected_keys:
        assert f'"{key}"' in SYSTEM_PROMPT, f"Missing required canonical key: {key}"


def test_compressed_prompt_preserves_core_business_rules():
    """Verify that extraction directives, grounding rules, and enum definitions are intact."""
    assert "<jd_content>" in SYSTEM_PROMPT
    assert "Never invent salary" in SYSTEM_PROMPT
    assert "MUST_HAVE" in SYSTEM_PROMPT and "PREFERRED" in SYSTEM_PROMPT
    assert "technical_skills" in SYSTEM_PROMPT
    assert "must_have_requirements" in SYSTEM_PROMPT
    assert "Do not infer" in SYSTEM_PROMPT
    assert "missing_information" in SYSTEM_PROMPT
    # Verify version bump
    assert PROMPT_VERSION == "jd-understanding-agent-v11"


# ---------------------------------------------------------------------------
# 2. Adaptive Context & Predict Token Sizing
# ---------------------------------------------------------------------------

def test_adaptive_context_selects_2048_for_short_jd():
    """Short JDs whose prompt + predict budget <= 1650 must select num_ctx=2048."""
    mock_llm = MagicMock(spec=LLMService)
    mock_llm.complete_structured.return_value = LLMResult(
        raw_text="{}",
        parsed_json={"role": {"job_title": "Junior Python Developer"}},
        usage=LLMUsage(input_tokens=1100, output_tokens=300),
        prompt_version=PROMPT_VERSION,
        finish_reason="stop",
    )

    agent = JDUnderstandingAgent(llm_service=mock_llm, enable_rag=False)
    spec, res = agent.understand(JD_SHORT, jd_id="short-test", jd_version=1)

    assert mock_llm.complete_structured.called
    call_kwargs = mock_llm.complete_structured.call_args[1]
    
    # Context should adaptively choose 2048
    assert call_kwargs["num_ctx"] == 2048
    # Max tokens should be tuned to safe baseline for short JD
    assert call_kwargs["max_tokens"] == 640


def test_adaptive_context_retains_4096_for_long_complex_jd():
    """Complex/long JDs exceeding 1950 token budget must safely retain num_ctx=4096."""
    mock_llm = MagicMock(spec=LLMService)
    mock_llm.complete_structured.return_value = LLMResult(
        raw_text="{}",
        parsed_json={"role": {"job_title": "Lead Autonomous Robotics Architect"}},
        usage=LLMUsage(input_tokens=1400, output_tokens=850),
        prompt_version=PROMPT_VERSION,
        finish_reason="stop",
    )

    agent = JDUnderstandingAgent(llm_service=mock_llm, enable_rag=False)
    spec, res = agent.understand(JD_LONG_COMPLEX, jd_id="complex-test", jd_version=1)

    assert mock_llm.complete_structured.called
    call_kwargs = mock_llm.complete_structured.call_args[1]

    # Long JD exceeds 1950 budget -> must safely retain 4096
    assert call_kwargs["num_ctx"] == 4096
    # Predict budget should scale up with word count (>900)
    assert call_kwargs["max_tokens"] >= 900


def test_adaptive_context_disabled_flag_respects_global_4096(monkeypatch):
    """When ENABLE_ADAPTIVE_CTX is False, num_ctx must default to global OLLAMA_NUM_CTX (4096)."""
    monkeypatch.setenv("ENABLE_ADAPTIVE_CTX", "false")
    monkeypatch.setenv("OLLAMA_NUM_CTX", "4096")

    mock_llm = MagicMock(spec=LLMService)
    mock_llm.complete_structured.return_value = LLMResult(
        raw_text="{}",
        parsed_json={"role": {"job_title": "Junior Python Developer"}},
        usage=LLMUsage(input_tokens=1100, output_tokens=300),
        prompt_version=PROMPT_VERSION,
        finish_reason="stop",
    )

    agent = JDUnderstandingAgent(llm_service=mock_llm, enable_rag=False)
    agent.understand(JD_SHORT)

    call_kwargs = mock_llm.complete_structured.call_args[1]
    assert call_kwargs["num_ctx"] == 4096


# ---------------------------------------------------------------------------
# 3. Anti-Truncation Fallback Safeguard
# ---------------------------------------------------------------------------

def test_anti_truncation_guard_automatically_retries_with_4096():
    """If generation truncates (finish_reason=length) under 2048, agent must retry with 4096."""
    mock_llm = MagicMock(spec=LLMService)

    # First call truncates mid-JSON under 2048
    truncated_result = LLMResult(
        raw_text='{"role": {"job_title": "Junior Python',
        parsed_json=None,
        usage=LLMUsage(input_tokens=1100, output_tokens=948),
        prompt_version=PROMPT_VERSION,
        finish_reason="length",
    )

    # Retry call completes cleanly under 4096
    recovered_result = LLMResult(
        raw_text='{"role": {"job_title": "Junior Python Developer"}}',
        parsed_json={"role": {"job_title": "Junior Python Developer"}},
        usage=LLMUsage(input_tokens=1100, output_tokens=1050),
        prompt_version=PROMPT_VERSION,
        finish_reason="stop",
    )

    mock_llm.complete_structured.side_effect = [truncated_result, recovered_result]

    agent = JDUnderstandingAgent(llm_service=mock_llm, enable_rag=False)
    spec, result = agent.understand(JD_SHORT)

    # Must have invoked complete_structured twice
    assert mock_llm.complete_structured.call_count == 2
    
    # First call: attempted 2048
    first_call_ctx = mock_llm.complete_structured.call_args_list[0][1]["num_ctx"]
    assert first_call_ctx == 2048

    # Second call: recovered with safe 4096
    second_call_ctx = mock_llm.complete_structured.call_args_list[1][1]["num_ctx"]
    assert second_call_ctx == 4096
    assert result.finish_reason == "stop"
    assert spec.role.job_title == "Junior Python Developer"


# ---------------------------------------------------------------------------
# 4. Structured Output Completeness
# ---------------------------------------------------------------------------

def test_structured_specification_validation_on_complex_mock():
    """Verify end-to-end Pydantic validation and postprocessing on full structured output."""
    full_canonical_dict = {
        "role": {
            "job_title": "Lead Autonomous Robotics Architect",
            "role": "Robotics Platform Lead",
            "department": "Autonomous Systems",
            "seniority": "Lead",
        },
        "job_context": {
            "company_context": "Aerospace & Robotics Inc.",
            "team_size": "15 engineers",
        },
        "responsibilities": [
            {
                "description": "Architect edge compute architecture for autonomous inspection rovers.",
                "kind": "primary",
                "source": {"text": "Architect edge compute", "section": "Responsibilities"},
            }
        ],
        "conventional_requirements": {
            "experience": [
                {
                    "description": "8+ years in robotics and embedded platforms",
                    "min_years": 8.0,
                    "priority": "MUST_HAVE",
                    "explicit_or_derived": "explicit",
                }
            ],
            "technical_skills": [
                {"name": "C++", "category": "language", "priority": "MUST_HAVE", "explicit_or_derived": "explicit"},
                {"name": "Python", "category": "language", "priority": "MUST_HAVE", "explicit_or_derived": "explicit"},
                {"name": "ROS2", "category": "framework", "priority": "MUST_HAVE", "explicit_or_derived": "explicit"},
                {"name": "FPGA", "category": "hardware", "priority": "PREFERRED", "explicit_or_derived": "explicit"},
            ],
            "education": [{"description": "Master's or PhD degree in Robotics", "priority": "MUST_HAVE"}],
            "domain": ["Robotics", "Aerospace"],
            "location": {"city": "Seattle", "work_mode": "hybrid"},
            "work_mode": "hybrid",
        },
        "must_have_requirements": [
            "8+ years of modern C++ and Python",
            "Deep expertise in ROS2 and real-time Linux",
        ],
        "preferred_requirements": [
            "FPGA hardware acceleration using VHDL/Verilog",
        ],
        "evidence_requirements": [
            {
                "requirement": "8+ years of modern C++ and Python",
                "priority": "MUST_HAVE",
                "explicit_or_derived": "explicit",
                "evidence_to_look_for": ["Production C++ codebases", "Git commits"],
                "strong_evidence": "Production deployment of C++17/20 robotics software",
                "prohibited_inference": "Do not infer embedded systems depth from general Python scripting.",
            }
        ],
        "missing_information": [],
        "ambiguities": [],
    }

    mock_llm = MagicMock(spec=LLMService)
    mock_llm.complete_structured.return_value = LLMResult(
        raw_text=json.dumps(full_canonical_dict),
        parsed_json=full_canonical_dict,
        usage=LLMUsage(input_tokens=1400, output_tokens=900),
        prompt_version=PROMPT_VERSION,
        finish_reason="stop",
    )

    agent = JDUnderstandingAgent(llm_service=mock_llm, enable_rag=False)
    spec, res = agent.understand(JD_LONG_COMPLEX)

    assert isinstance(spec, JobEvaluationSpecification)
    assert spec.role.job_title == "Lead Autonomous Robotics & Embedded Platform Architect"
    assert len(spec.conventional_requirements.technical_skills) >= 4
    assert spec.conventional_requirements.experience[0].min_years == 8.0
    assert len(spec.must_have_requirements) > 0
    assert len(spec.preferred_requirements) > 0
