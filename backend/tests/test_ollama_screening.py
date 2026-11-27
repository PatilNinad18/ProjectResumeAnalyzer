import json

import pytest

from app.services.llm_service import OllamaAdapter
from app.services.resume.ollama_screening import ScreeningModelError, evaluate_with_ollama, resume_markdown, structure_resume, work_date_evidence
from app.services.resume.profiler import profile_resume
from app.services.storage import checksum


RESUME = """Taylor Example
taylor@example.test
Work Experience
Backend Engineer, Example Systems
Jan 2020 - Jan 2024
Built and shipped Python REST APIs with FastAPI, including tests.
Wrote PostgreSQL queries for an internal reporting project.
Skills
Python, FastAPI, Docker, PostgreSQL
"""


def _profile_response(data):
    rows = {row["text"]: row["id"] for row in data["resume_passages"]}
    date_id = rows["Jan 2020 - Jan 2024"]
    api_id = rows["Built and shipped Python REST APIs with FastAPI, including tests."]
    sql_id = rows["Wrote PostgreSQL queries for an internal reporting project."]
    skills_id = rows["Python, FastAPI, Docker, PostgreSQL"]
    return {"facts": [
        {"section": "work_history", "summary": "Worked on Python APIs and PostgreSQL reporting at Example Systems.",
         "evidence_ids": [date_id, api_id, sql_id], "date_id": date_id},
        {"section": "skills", "summary": "Docker", "evidence_ids": [skills_id]},
    ]}


def test_ollama_evidence_yields_the_agreed_weighted_score(monkeypatch):
    def complete(_adapter, *, user_prompt, schema, **other):
        data = json.loads(user_prompt)
        assert "taylor@example.test" not in user_prompt
        assert other["model"] == "test-model"
        if schema["title"] == "ProfileOutput":
            return _profile_response(data)
        items = data["job_criteria"]
        assert len(items) == 3
        assert data["resume_facts"][0]["section"] == "work_history"
        rows = {row["text"]: row["id"] for row in data["resume_passages"]}
        sources = [key for key in rows if key.startswith(("Built and", "Wrote PostgreSQL", "Python, FastAPI"))]
        return {"grades": [
            {"id": item["id"], "grade": grade, "evidence_ids": [rows[quote]], "reason": "Test fixture"}
            for item, grade, quote in zip(items, ("FULL", "PARTIAL", "MENTION"), sources, strict=True)
        ]}

    monkeypatch.setattr(OllamaAdapter, "complete_private_json", complete)
    identity = profile_resume(RESUME)
    profile = structure_resume(RESUME, identity, "test-model", checksum(RESUME))
    assert "## Work history" in resume_markdown(profile)
    spec = {
        "must_have_requirements": ["Building Python REST APIs", "Optimize production PostgreSQL queries", "Team size: 20"],
        "preferred_requirements": ["Hands-on Docker usage", "Salary range: $120,000–150,000"],
        "experience_requirements": {"minimum_years": 4},
        "evidence_requirements": [{"requirement_id": "sql", "requirement": "Optimize production PostgreSQL queries",
                                   "priority": "MUST_HAVE", "critical": True}],
        "salary": "Internal company information",
    }
    result = evaluate_with_ollama(RESUME, identity, profile, spec, "test-model")
    assert result["overall_score"] == 68
    assert result["score_breakdown"]["experience_points"] == 10
    assert result["score_breakdown"]["critical_to_verify"] == ["Optimize production PostgreSQL queries"]
    assert [row["points_earned"] for row in result["detailed_evaluations"]] == [35, 17.5, 5]
    assert all(row["quote_verified"] for row in result["detailed_evaluations"])


def test_ollama_invalid_citation_needs_review_and_dated_claim_cannot_overstate_duration(monkeypatch):
    evidence_id = 900

    def complete(_adapter, *, user_prompt, schema, **_kwargs):
        data = json.loads(user_prompt)
        if schema["title"] == "ProfileOutput":
            return _profile_response(data)
        return {"grades": [{"id": 1, "grade": "FULL", "evidence_ids": [evidence_id], "reason": "Test fixture"}]}

    monkeypatch.setattr(OllamaAdapter, "complete_private_json", complete)
    identity = profile_resume(RESUME)
    profile = structure_resume(RESUME, identity, "test-model", checksum(RESUME))
    spec = {"must_have_requirements": ["5 years building Python APIs"]}
    with pytest.raises(ScreeningModelError, match="valid resume evidence"):
        evaluate_with_ollama(RESUME, identity, profile, spec, "test-model")

    evidence_id = next(row["id"] for row in profile["passages"] if row["text"].startswith("Built and"))
    result = evaluate_with_ollama(RESUME, identity, profile, spec, "test-model")
    assert result["overall_score"] == 50
    assert result["detailed_evaluations"][0]["evidence_grade"] == "PARTIAL"
    assert "4.0 relevant years" in result["detailed_evaluations"][0]["reasoning"]


def test_dated_unrelated_work_and_skill_mentions_cannot_earn_applied_credit(monkeypatch):
    text = """Lee Example
Experience
Office Assistant, Example Systems
Jun 2023 - Dec 2023
Organized purchase orders and prepared spreadsheets using Excel.
Skills
Python, PostgreSQL, Docker, Excel
"""

    def complete(_adapter, *, user_prompt, schema, **_kwargs):
        data = json.loads(user_prompt)
        dates = next(row for row in data["resume_passages"] if row["text"].startswith("Jun 2023"))
        skills = next(row for row in data["resume_passages"] if row["section"] == "skills")
        if schema["title"] == "ProfileOutput":
            return {"facts": [
                {"section": "work_history", "summary": "Office Assistant", "evidence_ids": [dates["id"]], "date_id": dates["id"]},
                {"section": "skills", "summary": "Python, PostgreSQL, Docker", "evidence_ids": [skills["id"]]},
            ]}
        return {"grades": [{"id": item["id"], "grade": "FULL", "evidence_ids": [dates["id"], skills["id"]],
                            "reason": "Incorrectly attributed the listed skills to unrelated work."}
                           for item in data["job_criteria"]]}

    monkeypatch.setattr(OllamaAdapter, "complete_private_json", complete)
    identity = profile_resume(text)
    profile = structure_resume(text, identity, "test-model", checksum(text))
    result = evaluate_with_ollama(text, identity, profile, {
        "must_have_requirements": ["Building Python REST APIs", "Optimizing production PostgreSQL queries"],
        "preferred_requirements": ["Hands-on Docker usage"], "experience_requirements": {"minimum_years": 4},
    }, "test-model")
    assert result["overall_score"] == 24
    assert all(row["evidence_grade"] == "MENTION" for row in result["detailed_evaluations"])
    assert all(row["evidence_quotes"] == ["Python, PostgreSQL, Docker, Excel"] for row in result["detailed_evaluations"])


def test_missing_and_duplicate_grades_are_retried_without_discarding_valid_results(monkeypatch):
    retried = []

    def complete(_adapter, *, user_prompt, schema, **_kwargs):
        data = json.loads(user_prompt)
        if schema["title"] == "ProfileOutput":
            return _profile_response(data)
        api = next(row["id"] for row in data["resume_passages"] if row["text"].startswith("Built and"))
        if schema["title"] == "GradeOutput":
            return {"grades": [
                {"id": 1, "grade": "FULL", "evidence_ids": [api], "reason": "Demonstrated API work."},
                {"id": 2, "grade": "FULL", "evidence_ids": [900], "reason": "Invalid source."},
                {"id": 2, "grade": "NO_EVIDENCE", "evidence_ids": [], "reason": "Duplicate grade."},
            ]}
        criterion, = data["job_criteria"]
        retried.append(criterion["id"])
        return {"grade": "NO_EVIDENCE", "evidence_ids": [], "reason": "No documented experience."}

    monkeypatch.setattr(OllamaAdapter, "complete_private_json", complete)
    identity = profile_resume(RESUME)
    profile = structure_resume(RESUME, identity, "test-model", checksum(RESUME))
    result = evaluate_with_ollama(RESUME, identity, profile, {
        "must_have_requirements": ["Building Python REST APIs", "Java", "Rust"],
    }, "test-model")
    assert retried == [2, 3]
    assert result["overall_score"] == 33


@pytest.mark.parametrize("initial_grade", ["NO_EVIDENCE", "MENTION"])
def test_pdf_internships_count_and_current_degree_cannot_earn_full_credit(monkeypatch, initial_grade):
    text = """Technical Skills
React, PostgreSQL
Experience / Internship
Software Engineer InternJun 2023 � Dec 2023
Built full-stack apps with React and PostgreSQL for internal users.
Education
BT ech Electronics and TelecommunicationAug 2023 � Present
"""

    def complete(_adapter, *, user_prompt, schema, **_kwargs):
        data = json.loads(user_prompt)
        if schema["title"] == "ProfileOutput":
            role = next(row for row in data["resume_passages"] if "Engineer Intern" in row["text"])
            assert role["section"] == "experience"
            return {"facts": [{"section": "work_history", "summary": "Intern", "evidence_ids": [role["id"]]}]}
        degree = next(row["id"] for row in data["resume_passages"] if "Telecommunication" in row["text"])
        return {"grades": [{"id": 1, "grade": "FULL", "evidence_ids": [degree], "reason": "Degree listed."},
                            {"id": 2, "grade": initial_grade, "evidence_ids": [degree] if initial_grade == "MENTION" else [],
                             "reason": "Missed the skill listing."}]}

    monkeypatch.setattr(OllamaAdapter, "complete_private_json", complete)
    identity = profile_resume(text)
    profile = structure_resume(text, identity, "test-model", checksum(text))
    tenure, _ = work_date_evidence(profile, documented_work=identity["work_history"])
    assert round(tenure, 1) == 0.5
    result = evaluate_with_ollama(text, identity, profile, {"must_have_requirements": ["Bachelor's degree in Engineering"],
                                                           "preferred_requirements": ["Experience with React"]}, "test-model")
    assert result["overall_score"] == 44
    assert "in progress" in result["detailed_evaluations"][0]["reasoning"]
    assert result["detailed_evaluations"][1]["evidence_grade"] == "MENTION"
