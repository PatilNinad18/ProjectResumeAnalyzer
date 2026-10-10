"""
tests/test_clarification_lifecycle.py — Clarification Engine & Lifecycle Tests.

Validates:
  1. 3-Tier Clarification Question Generation (Problem 2 B):
     - Contradictions & unresolved items produce Tier 1 BLOCKING questions.
     - Missing metadata (salary, team size) produces Tier 3 OPTIONAL questions.
     - Optional questions NEVER have is_blocking=True.
     - Idempotency: re-running question generation never duplicates questions.
  2. Clarification Answer Submission & Atomic Updates:
     - Answering questions updates status, sets TA provenance, updates master context.
     - Skipping a non-blocking question succeeds without override.
     - Skipping a BLOCKING question without authorized override raises ClarificationUpdateError.
     - Skipping a BLOCKING question with authorized override succeeds.
     - Setting status=EXPLICITLY_UNSPECIFIED records explicit absence.
  3. Finalization Gatekeeper (Problem 3 C):
     - Finalization is rejected (raises ClarificationUpdateError) if any BLOCKING question is unresolved.
     - Finalization succeeds once all blocking questions are answered/overridden.
     - Lifecycle status transitions to FINALIZED, finalized_at is set, audit trail is sealed.
  4. Canonical Forward Projection & Traceable Origin Invariant (Problem 4 D & Invariant 1):
     - JDMasterContext deterministically projects to JobEvaluationSpecification.
     - Only EXPLICIT_JD and TA_CONFIRMED requirements enter must_have_requirements.
     - Zero EKG-derived activities enter must_have_requirements.
     - Atomic patching via apply_patch_to_master() rolls back 100% on invalid schema.
  5. Grounded Query Engine (Problem 6 F):
     - Deterministic Q&A against JDMasterContext without LLM or fabrication.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from app.schemas.master_context import (
    ConfidenceBand,
    ConfidenceBreakdown,
    DisjunctionGroup,
    JDLifecycleStatus,
    JDMasterContext,
    OriginType,
    QuestionCategory,
    QuestionPriority,
    QuestionStatus,
    RequirementPriority,
    RoleOverview,
    JobContextInfo,
    StructuredRequirement,
)
from app.services.clarification.engine import (
    generate_clarification_questions,
    recompute_all_blocking_flags,
)
from app.services.clarification.updater import (
    ClarificationUpdateError,
    attempt_finalization,
    submit_answer,
)
from app.services.projection.canonical_projector import (
    apply_patch_to_master,
    project_to_canonical,
)
from app.services.query_engine import answer_query

from tests.stubs import (
    make_ekg_derived,
    make_hardware_jd_context,
    make_master_context,
    make_must_have,
    make_preferred,
    make_unresolved,
)


# ===========================================================================
# 1. Question Generation & 3-Tier Classification Tests
# ===========================================================================

def test_generate_questions_with_unresolved_creates_blocking_question():
    """UNRESOLVED requirement creates a Tier 1 BLOCKING clarification question."""
    master = make_master_context(with_unresolved=True)
    master = generate_clarification_questions(master, actor="test_runner")

    assert master.lifecycle_status == JDLifecycleStatus.AWAITING_CLARIFICATION
    assert len(master.clarification_history) > 0

    unresolved_q = next(
        (q for q in master.clarification_history if "unresolved" in q.question_key),
        None,
    )
    assert unresolved_q is not None
    assert unresolved_q.priority == QuestionPriority.BLOCKING
    assert unresolved_q.is_blocking is True
    assert unresolved_q.status == QuestionStatus.UNANSWERED


def test_generate_questions_missing_metadata_is_optional_not_blocking():
    """Missing team size or salary range creates Tier 3 OPTIONAL, non-blocking questions."""
    master = make_master_context(with_unresolved=False)
    master = generate_clarification_questions(master, actor="test_runner")

    metadata_questions = [
        q for q in master.clarification_history
        if q.category in (QuestionCategory.ORG_METADATA, QuestionCategory.COMPENSATION_LOGISTICS)
    ]
    assert len(metadata_questions) > 0
    for q in metadata_questions:
        assert q.priority == QuestionPriority.OPTIONAL
        assert q.is_blocking is False, f"Optional question {q.question_key} must never be blocking"


def test_generate_questions_idempotent():
    """Running generate_clarification_questions twice produces identical question count without duplicates."""
    master = make_master_context(with_unresolved=True)
    master = generate_clarification_questions(master)
    count_1 = len(master.clarification_history)

    # Run a second time
    master = generate_clarification_questions(master)
    count_2 = len(master.clarification_history)

    assert count_1 == count_2
    keys = [q.question_key for q in master.clarification_history]
    assert len(keys) == len(set(keys)), "Question keys must remain unique"


# ===========================================================================
# 2. Clarification Answer Submission & Atomic Updates
# ===========================================================================

def test_submit_valid_answer_updates_master_and_provenance():
    """Answering a question updates its status, sets TA provenance, and logs audit trail."""
    master = make_master_context(with_unresolved=True)
    master = generate_clarification_questions(master)

    unresolved_q = next(q for q in master.clarification_history if "unresolved" in q.question_key)
    q_key = unresolved_q.question_key

    master = submit_answer(
        master,
        question_key=q_key,
        answer_text="PCB design knowledge is confirmed MUST HAVE for this role.",
        answered_by="recruiter_jane",
        status=QuestionStatus.ANSWERED,
    )

    q_updated = next(q for q in master.clarification_history if q.question_key == q_key)
    assert q_updated.status == QuestionStatus.ANSWERED
    assert q_updated.answer_text == "PCB design knowledge is confirmed MUST HAVE for this role."
    assert q_updated.answered_by == "recruiter_jane"
    assert q_updated.is_blocking is False

    # Check that audit trail recorded the event
    audit_events = [e.event_type for e in master.audit_trail]
    assert "clarification_answered" in audit_events


def test_skip_optional_question_succeeds_without_override():
    """Skipping a Tier 3 OPTIONAL question succeeds without requiring an override record."""
    master = make_master_context()
    master = generate_clarification_questions(master)

    opt_q = next(q for q in master.clarification_history if q.priority == QuestionPriority.OPTIONAL)
    master = submit_answer(
        master,
        question_key=opt_q.question_key,
        answer_text="",
        answered_by="recruiter_jane",
        status=QuestionStatus.SKIPPED,
    )

    q_updated = next(q for q in master.clarification_history if q.question_key == opt_q.question_key)
    assert q_updated.status == QuestionStatus.SKIPPED
    assert q_updated.is_blocking is False


def test_skip_blocking_question_without_override_raises_error():
    """Skipping a Tier 1 BLOCKING question without an authorized override raises ClarificationUpdateError."""
    master = make_master_context(with_unresolved=True)
    master = generate_clarification_questions(master)

    blocking_q = next(q for q in master.clarification_history if q.priority == QuestionPriority.BLOCKING)

    with pytest.raises(ClarificationUpdateError) as exc_info:
        submit_answer(
            master,
            question_key=blocking_q.question_key,
            answer_text="",
            answered_by="recruiter_jane",
            status=QuestionStatus.SKIPPED,
            override_record=None,
        )
    assert "cannot be SKIPPED without an authorized override_record" in str(exc_info.value)


def test_skip_blocking_question_with_override_succeeds():
    """Skipping a Tier 1 BLOCKING question with an authorized override succeeds and clears blocking."""
    master = make_master_context(with_unresolved=True)
    master = generate_clarification_questions(master)

    blocking_q = next(q for q in master.clarification_history if q.priority == QuestionPriority.BLOCKING)
    override = {
        "authorized_by": "vp_engineering",
        "override_reason": "Role will be mentored; PCB ambiguity accepted for now.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    master = submit_answer(
        master,
        question_key=blocking_q.question_key,
        answer_text="Skipped with executive approval",
        answered_by="vp_engineering",
        status=QuestionStatus.SKIPPED,
        override_record=override,
    )

    q_updated = next(q for q in master.clarification_history if q.question_key == blocking_q.question_key)
    assert q_updated.status == QuestionStatus.SKIPPED
    assert q_updated.override_record == override
    assert q_updated.is_blocking is False


def test_submit_explicitly_unspecified_marks_field():
    """Submitting EXPLICITLY_UNSPECIFIED marks the question and sets explicit absence on the domain model."""
    master = make_master_context()
    master = generate_clarification_questions(master)

    team_q = next(
        (q for q in master.clarification_history if "team_size" in q.question_key),
        None,
    )
    if team_q:
        master = submit_answer(
            master,
            question_key=team_q.question_key,
            answer_text="Not specified at this time",
            answered_by="recruiter_jane",
            status=QuestionStatus.EXPLICITLY_UNSPECIFIED,
        )
        assert master.job_context.team_size_explicitly_unspecified is True


# ===========================================================================
# 3. Finalization Gatekeeper Tests
# ===========================================================================

def test_finalization_gate_blocks_when_blocking_questions_remain():
    """attempt_finalization() raises ClarificationUpdateError if any BLOCKING question is unresolved."""
    master = make_master_context(with_unresolved=True)
    master = generate_clarification_questions(master)

    # Master has an unresolved blocking question
    with pytest.raises(ClarificationUpdateError) as exc_info:
        attempt_finalization(master, actor="test_runner")

    assert "unresolved BLOCKING question(s) remain" in str(exc_info.value)
    assert master.lifecycle_status != JDLifecycleStatus.FINALIZED


def test_finalization_gate_succeeds_when_all_blocking_resolved():
    """attempt_finalization() succeeds once all blocking questions are answered, locking the JD."""
    master = make_master_context(with_unresolved=True)
    master = generate_clarification_questions(master)

    # Answer all blocking questions
    for q in master.clarification_history:
        if q.priority == QuestionPriority.BLOCKING:
            master = submit_answer(
                master,
                question_key=q.question_key,
                answer_text="Resolved: must have requirement.",
                answered_by="recruiter_jane",
                status=QuestionStatus.ANSWERED,
            )

    # Now finalization should succeed (even if Tier 3 optional questions are unanswered)
    master = attempt_finalization(master, actor="recruiter_jane")

    assert master.lifecycle_status == JDLifecycleStatus.FINALIZED
    assert master.finalized_at is not None
    assert any(e.event_type == "finalized" for e in master.audit_trail)


# ===========================================================================
# 4. Canonical Forward Projection & Traceable Origin Invariant Tests
# ===========================================================================

def test_canonical_projection_produces_valid_specification():
    """project_to_canonical() deterministically projects JDMasterContext to JobEvaluationSpecification."""
    master = make_hardware_jd_context()
    spec = project_to_canonical(master)

    assert spec.metadata.jd_id == master.jd_id
    assert spec.role.job_title == "Senior Embedded Systems Engineer"
    assert spec.conventional_requirements.location.city == "Pune"
    assert spec.conventional_requirements.location.country == "India"
    assert len(spec.conventional_requirements.technical_skills) > 0
    assert len(spec.responsibilities) == 3


def test_traceable_origin_invariant_enforced_in_projection():
    """
    CRITICAL INVARIANT TEST:
    Only EXPLICIT_JD and TA_CONFIRMED requirements enter must_have_requirements.
    Zero EKG_DERIVED requirements can ever become mandatory in the projected specification.
    """
    master = make_master_context(with_ekg_derived=True)
    spec = project_to_canonical(master)

    # Verify must_have items in projected spec (top-level must_have_requirements list)
    must_have_texts = spec.must_have_requirements

    # Explicit C and RTOS must be present
    assert any("C programming" in t for t in must_have_texts)
    assert any("RTOS" in t for t in must_have_texts)

    # The EKG_DERIVED requirement must NOT be in must_have_requirements
    assert not any("EKG derived" in t for t in must_have_texts), (
        "Traceable Origin Invariant violated: EKG-derived requirement was projected into must_have_requirements!"
    )


def test_apply_patch_to_master_atomic_rollback():
    """apply_patch_to_master() updates master context on valid patch and rolls back 100% on invalid schema."""
    master = make_master_context()
    original_title = master.role_overview.job_title

    # Valid patch
    valid_patch = {
        "role_overview": {
            "job_title": "Lead Embedded Systems Architect",
            "seniority": "Lead",
        }
    }
    master = apply_patch_to_master(master, valid_patch, actor="architect_bob")
    assert master.role_overview.job_title == "Lead Embedded Systems Architect"
    assert master.role_overview.seniority == "Lead"

    # Invalid patch (invalid lifecycle_status value)
    invalid_patch = {
        "lifecycle_status": "BOGUS_INVALID_STATUS",
    }
    with pytest.raises(Exception):
        apply_patch_to_master(master, invalid_patch, actor="architect_bob")

    # Verify rollback: job_title is unchanged from before the failed patch
    assert master.role_overview.job_title == "Lead Embedded Systems Architect"


# ===========================================================================
# 5. Grounded Query Engine Tests
# ===========================================================================

def test_query_engine_mandatory_requirements():
    """Grounded query for mandatory requirements returns explicit items with provenance."""
    master = make_hardware_jd_context()
    result = answer_query(master, "What are the mandatory requirements?")

    assert result.fabricated is False
    assert result.query_type == "mandatory_requirements"
    assert len(result.answers) >= 3
    for ans in result.answers:
        assert ans.provenance_label in ("Explicit JD text", "TA Confirmed")


def test_query_engine_clarification_history():
    """Grounded query for clarification history returns answered questions without fabrication."""
    master = make_master_context(with_unresolved=True)
    master = generate_clarification_questions(master)

    q = next(q for q in master.clarification_history if "unresolved" in q.question_key)
    master = submit_answer(
        master,
        question_key=q.question_key,
        answer_text="PCB design is strictly required for this project.",
        answered_by="recruiter_jane",
    )

    result = answer_query(master, "What did the TA clarify?")
    assert result.fabricated is False
    assert result.query_type == "clarification_answers"
    assert len(result.answers) >= 1
    assert any("PCB design" in a.text for a in result.answers)


def test_query_engine_unspecified_fields():
    """Grounded query for unspecified fields reports missing items honestly."""
    master = make_master_context()
    result = answer_query(master, "What is not specified in this JD?")

    assert result.fabricated is False
    assert result.query_type == "unspecified_fields"
    assert len(result.answers) > 0
    # Team size and salary range are unspecified in this minimal stub
    answers_text = " ".join(a.text for a in result.answers).lower()
    assert "team size" in answers_text or "salary" in answers_text


# ===========================================================================
# 6. REST API Endpoint Integration Tests (FastAPI TestClient)
# ===========================================================================

def test_api_endpoints_full_workflow(monkeypatch):
    """Integration test verifying all 5 new Intern 2 HTTP REST endpoints."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    # 1. Upload JD
    upload_res = client.post(
        "/api/jds",
        data={
            "project_id": "proj-lifecycle-test",
            "title": "Senior Embedded Firmware Lead",
            "text": (
                "Job Title: Senior Embedded Firmware Lead\n\n"
                "Requirements:\n"
                "- 5+ years embedded C programming (MUST HAVE)\n"
                "- Experience with FreeRTOS (MUST HAVE)\n"
                "- Python scripting (PREFERRED)\n\n"
                "Responsibilities:\n"
                "- Design firmware for microcontrollers\n"
            ),
        },
    )
    assert upload_res.status_code == 200, upload_res.text
    jd_id = upload_res.json()["jd_id"]

    # Trigger analysis
    analyze_res = client.post(f"/api/jds/{jd_id}/analyze")
    assert analyze_res.status_code == 202

    # 2. GET /api/jds/{jd_id}/master-context
    mc_res = client.get(f"/api/jds/{jd_id}/master-context")
    assert mc_res.status_code == 200, mc_res.text
    mc_data = mc_res.json()
    assert mc_data["jd_id"] == jd_id
    assert "requirements" in mc_data
    assert "role_overview" in mc_data

    # 3. GET /api/jds/{jd_id}/clarifications
    clarif_res = client.get(f"/api/jds/{jd_id}/clarifications")
    assert clarif_res.status_code == 200, clarif_res.text
    clarif_data = clarif_res.json()
    assert clarif_data["jd_id"] == jd_id
    assert "questions" in clarif_data
    assert "blocking_unresolved" in clarif_data

    # 4. POST /api/jds/{jd_id}/clarifications (answer any open questions)
    for q in clarif_data["questions"]:
        ans_res = client.post(
            f"/api/jds/{jd_id}/clarifications",
            json={
                "question_key": q["question_key"],
                "answer_text": "Clarified by TA: confirmed requirement",
                "status": "ANSWERED",
                "answered_by": "ta_lead",
            },
        )
        assert ans_res.status_code == 200, ans_res.text
        assert ans_res.json()["new_status"] == "ANSWERED"

    # 5. POST /api/jds/{jd_id}/finalize
    final_res = client.post(
        f"/api/jds/{jd_id}/finalize",
        json={"actor": "ta_lead"},
    )
    assert final_res.status_code == 200, final_res.text
    final_data = final_res.json()
    assert final_data["lifecycle_status"] == "FINALIZED"
    assert final_data["finalized_at"] is not None

    # 6. POST /api/jds/{jd_id}/grounded-chat
    chat_res = client.post(
        f"/api/jds/{jd_id}/grounded-chat",
        json={"question": "What are the mandatory requirements?"},
    )
    assert chat_res.status_code == 200, chat_res.text
    chat_data = chat_res.json()
    assert chat_data["fabricated"] is False
    assert chat_data["query_type"] == "mandatory_requirements"
    assert len(chat_data["answers"]) > 0
    assert any("c" in a["text"].lower() or "freertos" in a["text"].lower() for a in chat_data["answers"])
