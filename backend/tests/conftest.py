import os
import sys
import json

import pytest

# Ensure Cython C-extensions in SQLAlchemy are disabled to prevent Windows Application Control DLL blocks
os.environ["DISABLE_SQLALCHEMY_CEXT"] = "1"

# Route all tests to an isolated test database so tests never pollute the dev database (jd_agent.db)
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_isolated.db")
os.environ.setdefault("LLM_PROVIDER", "mock")

from app.db import Base, engine
Base.metadata.create_all(bind=engine)


@pytest.fixture
def fake_resume_model(monkeypatch):
    """Script the local model boundary for API tests without requiring Ollama."""
    from app.services.llm_service import OllamaAdapter
    from app.services.resume.profiler import _extract_date_ranges

    calls = {"profiles": 0, "comparisons": 0}

    def complete(_adapter, *, user_prompt, schema, **_kwargs):
        data = json.loads(user_prompt)
        passages = data["resume_passages"]
        if schema["title"] == "ProfileOutput":
            calls["profiles"] += 1
            facts = []
            for row in passages:
                if _extract_date_ranges(row["text"]):
                    facts.append({"section": "work_history", "summary": "Documented role",
                                  "evidence_ids": [row["id"]], "date_id": row["id"]})
            if not facts:
                facts.append({"section": "skills", "summary": "Documented skill",
                              "evidence_ids": [passages[-1]["id"]]})
            return {"facts": facts}

        calls["comparisons"] += 1
        grades = []
        for criterion in data["job_criteria"]:
            text = criterion["text"].lower()
            term = next((term for term in ("python", "fastapi", "kubernetes", "pcb") if term in text), "")
            match = next((row for row in passages if term and term in row["text"].lower()), None)
            if not match and term == "pcb":
                match = next((row for row in passages if "printed circuit boards" in row["text"].lower()), None)
            grade = "NO_EVIDENCE"
            if match:
                passage = match["text"].lower()
                grade = "PARTIAL" if "lab" in passage else "MENTION" if match["section"] == "skills" else "FULL"
            grades.append({"id": criterion["id"], "grade": grade, "reason": "Scripted model judgment.",
                           "evidence_ids": [match["id"]] if match else []})
        return {"grades": grades}

    monkeypatch.setattr(OllamaAdapter, "complete_private_json", complete)
    return calls

