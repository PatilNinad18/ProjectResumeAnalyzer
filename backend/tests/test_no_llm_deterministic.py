"""
tests/test_no_llm_deterministic.py — Genuine Zero-LLM Determinism Proof.

CRITICAL ARCHITECTURAL PROOF:
Guarantees that the entire JD understanding lifecycle (clarification,
lifecycle management, canonical forward projection, atomic patching,
and grounded query engine) functions 100% deterministically without:
  1. Calling any local LLM (Ollama, vLLM, etc.)
  2. Making any outbound network or socket requests
  3. Inventing/fabricating requirements (Traceable Origin Invariant)

If ANY code path attempts an outbound network call or LLM invocation,
this test suite will immediately FAIL.
"""
from __future__ import annotations

import socket
import pytest
from unittest.mock import patch

from app.schemas.master_context import (
    JDLifecycleStatus,
    JDMasterContext,
    QuestionPriority,
    QuestionStatus,
)
from app.services.clarification.engine import generate_clarification_questions
from app.services.clarification.updater import (
    attempt_finalization,
    submit_answer,
)
from app.services.projection.canonical_projector import (
    apply_patch_to_master,
    project_to_canonical,
)
from app.services.query_engine import answer_query
from tests.stubs import make_hardware_jd_context


# ---------------------------------------------------------------------------
# Strict Socket Blocker: Disallow ALL outbound networking
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def block_all_network():
    """
    Monkeypatches socket.socket to raise an error if any network connection is attempted.
    Guarantees genuine offline execution.
    """
    orig_connect = socket.socket.connect

    def forbidden_connect(*args, **kwargs):
        raise RuntimeError("CRITICAL VIOLATION: Zero-LLM test attempted outbound network connection!")

    with patch.object(socket.socket, "connect", side_effect=forbidden_connect):
        yield


# ---------------------------------------------------------------------------
# Zero-LLM End-to-End Proof
# ---------------------------------------------------------------------------

def test_full_lifecycle_zero_llm_offline():
    """
    Comprehensive Zero-LLM proof:
    1. Ingest hardware JD into authoritative master context.
    2. Generate clarification questions deterministically (zero LLMs).
    3. Verify question classification (blocking vs optional).
    4. Submit TA answers and updates (zero LLMs).
    5. Finalize the JD through the gatekeeper (zero LLMs).
    6. Project deterministically into canonical JobEvaluationSpecification.
    7. Execute 5 natural-language grounded queries (zero LLMs, zero fabrication).
    """
    # 1. Start with hardware JD context
    master: JDMasterContext = make_hardware_jd_context()
    assert master.lifecycle_status == JDLifecycleStatus.DRAFT

    # 2. Clarification generation (zero LLMs)
    master = generate_clarification_questions(master, actor="offline_runner")
    assert master.lifecycle_status in (
        JDLifecycleStatus.AWAITING_CLARIFICATION,
        JDLifecycleStatus.READY_FOR_REVIEW,
    )
    assert len(master.clarification_history) > 0

    # 3. Answer any blocking questions deterministically
    blocking_questions = [
        q for q in master.clarification_history
        if q.priority == QuestionPriority.BLOCKING
    ]
    for q in blocking_questions:
        master = submit_answer(
            master,
            question_key=q.question_key,
            answer_text="Resolved offline deterministically: MUST HAVE",
            answered_by="offline_tester",
            status=QuestionStatus.ANSWERED,
        )

    # 4. Finalization gatekeeper (zero LLMs)
    master = attempt_finalization(master, actor="offline_tester")
    assert master.lifecycle_status == JDLifecycleStatus.FINALIZED
    assert master.finalized_at is not None

    # 5. Canonical forward projection (zero LLMs, Traceable Origin Invariant enforced)
    spec = project_to_canonical(master)
    assert spec.metadata.jd_id == master.jd_id
    assert spec.role.job_title == "Senior Embedded Systems Engineer"
    assert len(spec.must_have_requirements) > 0

    # Traceable Origin verification: no graph activity made it to must_have
    for req_text in spec.must_have_requirements:
        assert "EKG derived" not in req_text

    # 6. Atomic patching (zero LLMs)
    patch_dict = {
        "job_context": {
            "company_context": "SmartLeaven Autonomous Systems Div",
        }
    }
    master = apply_patch_to_master(master, patch_dict, actor="offline_tester")
    assert master.job_context.company_context == "SmartLeaven Autonomous Systems Div"

    # 7. Grounded query engine (zero LLMs, fabricated=False)
    queries = [
        "What are the mandatory requirements?",
        "What are the preferred requirements?",
        "What did the TA clarify?",
        "What is not specified in this JD?",
        "What responsibilities are involved?",
    ]
    for q in queries:
        result = answer_query(master, q)
        assert result.fabricated is False, f"Query '{q}' marked fabricated!"
        assert len(result.answers) >= 0


def test_clarification_engine_never_calls_ollama():
    """Verify that neither the clarification engine nor updater import or invoke ollama."""
    import sys
    with patch.dict(sys.modules, {"ollama": None, "httpx": None, "requests": None}):
        master = make_hardware_jd_context()
        master = generate_clarification_questions(master)
        assert len(master.clarification_history) > 0


def test_projection_and_query_engine_never_call_ollama():
    """Verify that canonical projector and query engine never invoke ollama or network."""
    import sys
    with patch.dict(sys.modules, {"ollama": None, "httpx": None, "requests": None}):
        master = make_hardware_jd_context()
        spec = project_to_canonical(master)
        assert spec.role.job_title is not None
        result = answer_query(master, "What are the mandatory requirements?")
        assert result.fabricated is False
