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
from app.services.extraction_pipeline import ExtractionPipeline
from app.services.projection.canonical_projector import project_to_canonical


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
    """An empty rubric has neither a match score nor a tier."""
    score, tier, breakdown = _compute_score([], [], 0.0, 0.0)
    assert score is None
    assert tier is None
    assert breakdown.get("warning") == "NO_EVALUATION_CRITERIA_DEFINED"
    invalid = evaluate_candidate(
        "Built an accounting tool and improved team reporting.", {},
        {"must_have_requirements": ["Requirements", "All listed elements required: Candidate must demonstrate proficiency."]},
    )
    assert invalid["overall_score"] is None
    assert invalid["detailed_evaluations"] == []


@pytest.mark.parametrize(
    ("requirement", "resume", "status"),
    [
        ("Java", "Built a checkout application with JavaScript.", "NOT_EVIDENCED"),
        ("Must be proficient in Python", "Built a reporting service in Python.", "MET"),
        ("Python proficiency required", "Developed a system and demonstrated proficiency in all listed items.", "NOT_EVIDENCED"),
        ("Python", "Skills: Python, PostgreSQL, and Git", "PARTIALLY_MET"),
        ("Python", "Worked with Python.", "PARTIALLY_MET"),
        ("Python", "Developed a data validation pipeline in Python for a class project.", "MET"),
        ("Python", "Projects\n- Developed a validation pipeline with\n  python for inventory reporting.", "MET"),
        ("Python", "I have no experience with Python.", "NOT_EVIDENCED"),
        ("AWS deployment", "Configured AWS Identity and Access Management for the team.", "PARTIALLY_MET"),
        ("AWS deployment", "Deployed an inventory service to AWS.", "MET"),
        ("Python for financial modeling", "Built an inventory application in Python.", "PARTIALLY_MET"),
        ("Python for financial modeling", "Built a Python tool for financial modeling.", "MET"),
        ("C++", "Implemented a renderer in C++ for a game prototype.", "MET"),
        ("C#", "Built a C++ physics engine for a prototype.", "NOT_EVIDENCED"),
        ("Bachelor's degree in Computer Science", "Education: B.S. in Computer Science, 2022", "MET"),
        ("Bachelor's degree in Computer Science", "Education: B.S. in Mathematics, 2022", "PARTIALLY_MET"),
        ("AWS Certified Solutions Architect", "Deployed a web application to AWS.", "PARTIALLY_MET"),
        ("AWS Certified Solutions Architect", "Certifications: AWS Certified Cloud Practitioner, 2024", "PARTIALLY_MET"),
        ("AWS Certified Solutions Architect", "Certifications: AWS Certified Solutions Architect, 2024", "MET"),
    ],
)
def test_evidence_grades_match_the_claim(requirement, resume, status):
    result = evaluate_candidate(resume, {}, {"must_have_requirements": [requirement]})
    evidence, = result["detailed_evaluations"]
    assert evidence["status"] == status
    for quote in evidence["evidence_quotes"]:
        assert " ".join(quote.split()) in " ".join(resume.split())
    assert bool(evidence["evidence_quotes"]) == (status != "NOT_EVIDENCED")


def test_scoped_years_use_multiple_grounded_roles_and_merge_overlap():
    resume = (
        "Experience\n"
        "Engineer at Example A\nJan 2020 - Dec 2022\n"
        "Developed a Python scheduling service used by the operations team.\n\n"
        "Engineer at Example B\nJan 2022 - Jun 2025\n"
        "Built a Python validation pipeline for inventory data.\n\n"
        "Analyst at Example C\nJan 2010 - Dec 2019\n"
        "Reconciled customer accounts and prepared monthly reports.\n"
    )
    result = evaluate_candidate(
        resume, profile_resume(resume),
        {"must_have_requirements": ["5+ years of Python development", "6+ years of Python development"]},
    )
    met, partial = result["detailed_evaluations"]
    assert met["status"] == "MET"
    assert partial["status"] == "PARTIALLY_MET"
    assert len(met["evidence_quotes"]) == 4
    assert "Jan 2020 - Dec 2022" in met["evidence_quotes"]
    assert "Jan 2022 - Jun 2025" in met["evidence_quotes"]
    assert all(quote in resume and "2010" not in quote for quote in met["evidence_quotes"])
    overall = evaluate_candidate(resume, profile_resume(resume), {"minimum_years": 2})
    assert "Jan 2020 - Dec 2022" in overall["score_breakdown"]["tenure_evidence"]


def test_confirmed_grouping_controls_the_grade():
    requirement = "Python or Java"
    spec = {
        "must_have_requirements": [requirement],
        "requirement_interpretations": [{
            "requirement_id": "req_languages",
            "explicit_requirement": requirement,
            "derived_interpretation": ["All listed elements required: Show application of both languages."],
        }],
    }
    resume = "Projects\nBuilt an inventory application using Python."
    assert evaluate_candidate(resume, {}, {"must_have_requirements": [requirement]})["overall_score"] == 100
    assert evaluate_candidate(resume, {}, spec)["overall_score"] == 50
    resume += "\nImplemented an auditing service in Java."
    result = evaluate_candidate(resume, {}, spec)
    assert result["overall_score"] == 100
    assert len(result["detailed_evaluations"][0]["evidence_quotes"]) == 2


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


def test_evaluator_reads_projected_preferred_and_overall_tenure():
    raw_jd = (
        "Requirements:\n"
        "- 4 years of professional experience.\n"
        "- 8+ years of experience in distributed systems.\n\n"
        "Preferred Qualifications:\n"
        "- 12+ years of experience is preferred.\n"
        "- Terraform infrastructure automation.\n"
    )
    master = ExtractionPipeline().process_jd(raw_jd).to_master_context(raw_jd_text=raw_jd)
    spec = project_to_canonical(master).model_dump(mode="json")

    result = evaluate_candidate("Used Terraform for infrastructure automation.", {"total_experience_years": 2}, spec)

    assert result["score_breakdown"]["tenure_base_weight"] == 0.10
    assert result["score_breakdown"]["tenure_subscore"] == 0.5
    assert result["score_breakdown"]["preferred_base_weight"] == 0.20
    assert result["must_haves_summary"]["total"] == 1
    assert result["detailed_evaluations"][0]["requirement"] == "8+ years of experience in distributed systems."
    assert next(item for item in result["detailed_evaluations"] if "Terraform" in item["requirement"])["status"] == "MET"


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


def test_screening_review_rows_are_unranked_and_coverage_matches_detail(test_setup):
    from pypdf import PdfWriter
    from app.workers.screening_worker import process_candidate_evaluation

    client = TestClient(app)
    jd_id, spec_id = test_setup["jd_id"], test_setup["spec_id"]
    base = f"/api/jds/{jd_id}/resumes"
    pdf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(pdf)
    upload = client.post(base, files=[
        ("files", ("scan.pdf", pdf.getvalue(), "application/pdf")),
        ("files", ("sparse.txt", b"Jordan Doe\njordan@example.com\n1", "text/plain")),
        ("files", ("readable.txt", b"Jordan Doe\nSkills: Python, FastAPI, SQL, Git, Docker, Linux\n", "text/plain")),
    ])
    assert upload.status_code == 202
    response = client.post(f"{base}/screen", json={"spec_version_id": spec_id})
    assert response.status_code == 202
    evaluation_ids = response.json()["candidate_resume_ids"]
    with SessionLocal() as db:
        for evaluation_id in evaluation_ids:
            process_candidate_evaluation(db, evaluation_id)

    leaderboard = {row["filename"]: row for row in client.get(base).json()["candidates"]}
    for filename, status in (("scan.pdf", "PARSE_FAILED"), ("sparse.txt", "NEEDS_REVIEW")):
        row = leaderboard[filename]
        assert row["status"] == status
        assert row["rank"] is row["overall_score"] is row["match_tier"] is None
        detail = client.get(f"{base}/{row['candidate_resume_id']}").json()
        assert detail["review_reason"] == row["review_reason"]
        assert detail["overall_score"] is None
        assert detail["detailed_evaluations"] == []

    readable = leaderboard["readable.txt"]
    detail_path = f"{base}/{readable['candidate_resume_id']}"
    summary = client.get(detail_path).json()["must_haves_summary"]
    assert readable["rank"] == 1
    assert readable["must_haves_met"] == summary["met"] == 0
    assert readable["must_haves_partially_met"] == summary["partially_met"] == 2
    assert readable["not_evidenced_count"] == summary["not_evidenced"] == 0
    assert readable["validation_checkpoints_count"] == 2

    with SessionLocal() as db:
        db.get(JobSpecificationVersion, spec_id).canonical_json = {"must_have_requirements": []}
        db.commit()
    rerun = client.post(f"{base}/screen", json={
        "candidate_resume_ids": [readable["candidate_resume_id"]], "spec_version_id": spec_id,
    })
    assert rerun.status_code == 202
    assert client.get(detail_path).json()["overall_score"] is None
    with SessionLocal() as db:
        process_candidate_evaluation(db, rerun.json()["candidate_resume_ids"][0])
    detail = client.get(detail_path).json()
    assert detail["status"] == "NEEDS_REVIEW"
    assert "no usable screening criteria" in detail["review_reason"]
    assert detail["overall_score"] is None
    assert all(row["rank"] is None for row in client.get(base).json()["candidates"])
