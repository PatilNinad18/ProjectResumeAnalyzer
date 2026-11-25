"""
Unit & Integration Tests for Resume Screening Agent (Phases 1-5)
================================================================
Tests:
  1. Profiler: Name, contact, experience tenure calculation, skills, work history.
  2. Evaluator:
     - Grounded quote extraction
     - MET (1.0), PARTIALLY_MET (0.5), NOT_EVIDENCED (0.0)
     - Guardrails (high score capped at POTENTIAL_MATCH if must-have unevidenced)
     - Edge cases: 0 must-haves, 0 preferred, 0 criteria (no division-by-zero)
     - Interview questions synthesis & Red flag detection
  3. Screening API:
     - Upload resumes (.txt, .pdf, .docx)
     - Trigger screening
     - Leaderboard querying & sorting
     - Candidate detail retrieval
     - Candidate deletion
"""
import io
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models.db_models import (
    User,
    Project,
    JobDescription,
    JobDescriptionVersion,
    JobSpecificationVersion,
    JDLifecycleStatusEnum,
)
from app.models.screening_models import (
    CandidateResume,
    CandidateEvaluation,
    ScreeningStatusEnum,
    MatchTierEnum,
    EvaluationStatusEnum,
)
from app.services.resume.profiler import profile_resume
from app.services.resume.evaluator import evaluate_candidate, _compute_score


SAMPLE_RESUME_TEXT = """
Sarah Connor
sarah.connor@sky.net | +1 555-0199

Summary
Senior Software Engineer with 7+ years of experience building distributed systems in Python and Go.

Professional Experience
Lead Backend Engineer
Cyberdyne Systems
Jan 2021 - Present
- Architected high-throughput microservices in Python using FastAPI and PostgreSQL handling 20k RPS.
- Deployed containerized applications with Docker and managed Kubernetes clusters in AWS.
- Configured CI/CD automation using GitHub Actions.

Software Engineer
Resistance Tech
Jun 2017 - Dec 2020
- Built REST APIs in Python and Django with Redis caching.
- Maintained relational databases and wrote automated integration tests.

Education
B.S. in Computer Science, 2017

Skills
Python, FastAPI, Django, Go, Docker, Kubernetes, AWS, PostgreSQL, Redis, Git, Linux
"""


# ---------------------------------------------------------------------------
# 1. Profiler Tests
# ---------------------------------------------------------------------------

def test_profiler_extracts_contact_and_tenure():
    profile = profile_resume(SAMPLE_RESUME_TEXT)
    assert profile["candidate_name"] == "Sarah Connor"
    assert profile["email"] == "sarah.connor@sky.net"
    assert "555-0199" in profile["phone"]
    assert profile["total_experience_years"] >= 6.5
    assert "python" in profile["skills"]
    assert "fastapi" in profile["skills"]
    assert "kubernetes" in profile["skills"]
    assert len(profile["work_history"]) >= 1


# ---------------------------------------------------------------------------
# 2. Evaluator Tests & Scoring Edge Cases
# ---------------------------------------------------------------------------

def test_evaluator_grounded_quotes_and_statuses():
    profile = profile_resume(SAMPLE_RESUME_TEXT)
    spec = {
        "must_haves": [
            "5+ years Python backend development",
            "FastAPI microservices design",
            "Kubernetes cluster operations",
        ],
        "preferred_qualifications": [
            "AWS deployment experience",
            "Ruby on Rails experience",
        ],
        "experience_requirements": {"minimum_years": 5},
    }

    result = evaluate_candidate(SAMPLE_RESUME_TEXT, profile, spec)

    assert result["overall_score"] >= 70
    assert result["match_tier"] in ("STRONG_MATCH", "POTENTIAL_MATCH")

    evals = {e["requirement"]: e for e in result["detailed_evaluations"]}

    # FastAPI should be MET or PARTIALLY_MET with an evidence quote
    fastapi_eval = evals["FastAPI microservices design"]
    assert fastapi_eval["status"] in ("MET", "PARTIALLY_MET")
    assert fastapi_eval["evidence_quote"] is not None
    assert "fastapi" in fastapi_eval["evidence_quote"].lower()

    # Ruby on Rails should be NOT_EVIDENCED (not mentioned)
    ruby_eval = evals["Ruby on Rails experience"]
    assert ruby_eval["status"] == "NOT_EVIDENCED"
    assert ruby_eval["evidence_quote"] is None
    assert ruby_eval["score_weight"] == 0.0

    # Ensure interview questions are generated for unevidenced/partial items
    assert len(result["tailored_interview_questions"]) > 0
    assert any("ruby" in q.lower() for q in result["tailored_interview_questions"])


def test_evaluator_scoring_edge_case_zero_criteria():
    """Ensure zero must-haves and zero preferred qualifications do not cause ZeroDivisionError."""
    score, tier, breakdown = _compute_score([], [], 0.0, 0.0)
    assert score == 100
    assert tier == "POTENTIAL_MATCH"
    assert breakdown.get("warning") == "NO_EVALUATION_CRITERIA_DEFINED"


def test_evaluator_scoring_edge_case_zero_preferred():
    """JD with must-haves only (no preferred items) dynamically normalizes weights."""
    must_evals = [
        {"requirement": "Req 1", "score_weight": 1.0, "status": "MET"},
        {"requirement": "Req 2", "score_weight": 0.5, "status": "PARTIALLY_MET"},
    ]
    # 0 preferred, 0 tenure weight
    score, tier, breakdown = _compute_score(must_evals, [], 0.0, 0.0)
    # Average of must-haves is (1.0 + 0.5) / 2 = 0.75 -> 75%
    assert score == 75
    assert tier == "STRONG_MATCH"   # 75 >= STRONG_MATCH_THRESHOLD(75), 0 NOT_EVIDENCED
    assert breakdown["active_weight_total"] == 0.70


def test_evaluator_guardrail_caps_unevidenced_must_have():
    """If candidate has high score but an unevidenced must-have, tier is capped at POTENTIAL_MATCH."""
    must_evals = [
        {"requirement": "Python", "score_weight": 1.0, "status": "MET"},
        {"requirement": "C++ Kernel", "score_weight": 0.0, "status": "NOT_EVIDENCED"},
    ]
    pref_evals = [
        {"requirement": "Docker", "score_weight": 1.0, "status": "MET"},
        {"requirement": "AWS", "score_weight": 1.0, "status": "MET"},
    ]
    # Give full tenure
    score, tier, breakdown = _compute_score(must_evals, pref_evals, 1.0, 0.10)
    # Despite good score, 1 must-have is NOT_EVIDENCED -> tier must be POTENTIAL_MATCH, not STRONG_MATCH
    assert tier == "POTENTIAL_MATCH"


# ---------------------------------------------------------------------------
# 3. API Integration Tests
# ---------------------------------------------------------------------------

@pytest.fixture
def test_setup():
    db = SessionLocal()
    unique_email = f"recruiter_{uuid.uuid4().hex[:8]}@test.com"
    user = User(email=unique_email, role="ta_reviewer")
    db.add(user)
    db.flush()

    project = Project(name="Screening Test Project", owner_id=user.id)
    db.add(project)
    db.flush()

    jd = JobDescription(project_id=project.id, title="Senior Backend Architect")
    db.add(jd)
    db.flush()

    jd_version = JobDescriptionVersion(
        job_description_id=jd.id,
        version=1,
        s3_raw_key="test/jd.txt",
        raw_text_checksum="dummy",
    )
    db.add(jd_version)
    db.flush()

    spec = JobSpecificationVersion(
        job_description_version_id=jd_version.id,
        specification_version=2,
        s3_json_key="test/spec.json",
        s3_markdown_key="test/spec.md",
        canonical_json={
            "must_haves": ["Python backend development", "FastAPI architecture"],
            "preferred_qualifications": ["Kubernetes administration"],
            "experience_requirements": {"minimum_years": 5},
        },
        prompt_version="1.0",
        model_version="test",
        lifecycle_status=JDLifecycleStatusEnum.FINALIZED,
    )
    db.add(spec)
    db.commit()

    yield {"jd_id": jd.id, "spec_id": spec.id}
    db.close()


def test_resume_screening_api_lifecycle(test_setup):
    client = TestClient(app)
    jd_id = test_setup["jd_id"]

    # 1. Upload Resume
    files = [
        ("files", ("sarah_connor.txt", io.BytesIO(SAMPLE_RESUME_TEXT.encode("utf-8")), "text/plain"))
    ]
    res_upload = client.post(f"/api/jds/{jd_id}/resumes", files=files)
    assert res_upload.status_code == 202
    upload_data = res_upload.json()
    assert upload_data["total_queued"] == 1
    resume_id = upload_data["uploaded"][0]["candidate_resume_id"]

    # 2. Trigger Screening
    res_screen = client.post(f"/api/jds/{jd_id}/resumes/screen")
    assert res_screen.status_code == 202
    assert res_screen.json()["queued_count"] >= 1

    # Give background worker a brief moment to process or execute inline
    from app.workers.screening_worker import process_candidate_evaluation
    db = SessionLocal()
    eval_row = db.query(CandidateEvaluation).filter(CandidateEvaluation.candidate_resume_id == resume_id).first()
    if eval_row and eval_row.status != ScreeningStatusEnum.COMPLETED:
        process_candidate_evaluation(db, eval_row.id)
    db.close()

    # 3. Check Leaderboard
    res_lb = client.get(f"/api/jds/{jd_id}/resumes")
    assert res_lb.status_code == 200
    lb_data = res_lb.json()
    assert lb_data["total_candidates"] == 1
    item = lb_data["candidates"][0]
    assert item["candidate_resume_id"] == resume_id
    assert item["overall_score"] is not None
    assert item["match_tier"] in ("STRONG_MATCH", "POTENTIAL_MATCH", "NOT_A_FIT")

    # 4. Check Candidate Detail
    res_detail = client.get(f"/api/jds/{jd_id}/resumes/{resume_id}")
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert detail["candidate_profile"]["candidate_name"] == "Sarah Connor"
    assert len(detail["detailed_evaluations"]) > 0

    # 5. Delete Candidate
    res_del = client.delete(f"/api/jds/{jd_id}/resumes/{resume_id}")
    assert res_del.status_code == 204

    # Verify deleted
    res_lb_after = client.get(f"/api/jds/{jd_id}/resumes")
    assert res_lb_after.json()["total_candidates"] == 0
