"""Batch clarification isolation and answer-driven artifact regeneration."""
from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile
from io import BytesIO

from fastapi.testclient import TestClient

from app.main import app


def test_batch_jds_keep_questions_isolated_and_screen_after_finalization():
    from app.schemas.master_context import JDMasterContext
    from tests.stubs import make_unresolved

    class FakeExtractionResult:
        def __init__(self, source: str) -> None:
            self.source = source

        def to_master_context(self, jd_id: str, raw_jd_text: str):
            requirements = (
                [make_unresolved(self.source)]
                if "needs-clarification" in self.source
                else []
            )
            return JDMasterContext(
                jd_id=jd_id,
                raw_jd_text=raw_jd_text,
                requirements=requirements,
            )

    class FakeExtractionPipeline:
        def __init__(self, llm_enabled: bool = False) -> None:
            self.llm_enabled = llm_enabled

        def process_jd(self, raw_text: str):
            return FakeExtractionResult(raw_text)

    offline_enrichment = SimpleNamespace(check_ollama_available=lambda: False)

    def verify_candidate(_master, candidate, context):
        source = " / ".join(context.statements)
        return {
            "is_genuine_ambiguity": True,
            "ambiguity_type": "requirement_priority",
            "interpretation_a": "PCB design scope is mandatory.",
            "interpretation_b": "PCB design scope is preferred.",
            "material_impact": "This changes which applicants pass screening.",
            "source_evidence": source,
            "clarification_question": "Is the PCB design scope mandatory or preferred?",
            "answer_options": [
                {"label": "Mandatory", "description": "Candidates must satisfy this criterion."},
                {"label": "Preferred", "description": "The criterion is not disqualifying."},
            ],
            "reasoning": f"Candidate {candidate.key} has distinct screening outcomes.",
        }

    with (
        patch("app.workers.worker.ExtractionPipeline", FakeExtractionPipeline),
        patch(
            "app.services.clarification.engine._verify_ambiguity_candidate",
            verify_candidate,
        ),
        patch(
            "app.services.enrichment.ta_enrichment_service.get_enrichment_service",
            return_value=offline_enrichment,
        ),
        TestClient(app) as client,
    ):
        files = [
            (
                "files",
                (
                    f"role-{index}.txt",
                    (
                        f"Role {index} needs-clarification: PCB design scope is unresolved. "
                        if index < 4
                        else "Role 4 has no ambiguity and no clarification needed."
                    ).encode(),
                    "text/plain",
                ),
            )
            for index in range(5)
        ]
        created = client.post(
            "/api/batches",
            data={"project_id": "batch-clarification-isolation"},
            files=files,
        )
        assert created.status_code == 202, created.text
        batch_id = created.json()["batch_id"]

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            batch = client.get(f"/api/batches/{batch_id}").json()
            if all(task["status"] in {"COMPLETED", "FAILED", "CANCELLED"} for task in batch["tasks"]):
                break
            time.sleep(0.05)

        assert len(batch["tasks"]) == 5
        assert all(task["status"] == "COMPLETED" for task in batch["tasks"])
        questions_by_jd = {}
        for task in batch["tasks"]:
            clarification_response = client.get(
                f"/api/jds/{task['jd_id']}/clarifications"
            )
            assert clarification_response.status_code == 200
            questions_by_jd[task["jd_id"]] = clarification_response.json()["questions"]

        tasks_by_filename = {task["filename"]: task for task in batch["tasks"]}
        jd_ids_by_index = [
            tasks_by_filename[f"role-{index}.txt"]["jd_id"] for index in range(5)
        ]
        assert all(questions_by_jd[jd_id] for jd_id in jd_ids_by_index[:4])
        assert questions_by_jd[jd_ids_by_index[4]] == []
        assert (
            client.get(f"/api/jds/{jd_ids_by_index[4]}/clarifications").json()["lifecycle_status"]
            == "FINALIZED"
        )
        for index, jd_id in enumerate(jd_ids_by_index[:4]):
            question = questions_by_jd[jd_id][0]
            assert f"Role {index}" in question["rationale"]
            assert question["category"] == "TECHNICAL_SCOPE"
            assert question["structured_options"]
            assert all(
                other["question_key"] != question["question_key"]
                for other_jd_id, other_questions in questions_by_jd.items()
                if other_jd_id != jd_id
                for other in other_questions
            )

        target_task = tasks_by_filename["role-0.txt"]
        jd_id = target_task["jd_id"]
        question = questions_by_jd[jd_id][0]
        before_json = client.get(f"/api/jds/{jd_id}/json").json()["json"]
        resolve = client.post(
            f"/api/jds/{jd_id}/clarifications/resolve",
            json={"answers": {question["question_key"]: "Preferred"}},
        )
        assert resolve.status_code == 202, resolve.text
        assert client.get(f"/api/jds/{jd_id}/tasks/resolve").json()["status"] == "done"

        refresh = client.post(
            f"/api/batches/{batch_id}/tasks/{target_task['task_id']}/refresh"
        )
        assert refresh.status_code == 200, refresh.text
        after_json = client.get(f"/api/jds/{jd_id}/json").json()["json"]
        assert after_json != before_json
        batch_json = client.get(
            f"/api/batches/{batch_id}/jds/{jd_id}/downloads/json"
        )
        assert batch_json.status_code == 200
        assert json.loads(batch_json.text) == after_json

        unchanged_json = client.get(
            f"/api/batches/{batch_id}/jds/{jd_ids_by_index[1]}/downloads/json"
        )
        assert unchanged_json.status_code == 200
        assert json.loads(unchanged_json.text) == client.get(
            f"/api/jds/{jd_ids_by_index[1]}/json"
        ).json()["json"]

        archive = client.get(f"/api/batches/{batch_id}/downloads.zip")
        assert archive.status_code == 200
        with ZipFile(BytesIO(archive.content)) as zipped:
            names = zipped.namelist()
        assert len(names) == 10
        assert len(set(names)) == len(names)

        # Resolve two more roles while leaving role 3 unfinished. The saved job
        # list and the batch must agree on which specifications can be screened.
        for index in (1, 2):
            task = tasks_by_filename[f"role-{index}.txt"]
            role_id = task["jd_id"]
            question_key = questions_by_jd[role_id][0]["question_key"]
            resolved = client.post(
                f"/api/jds/{role_id}/clarifications/resolve",
                json={"answers": {question_key: "Mandatory"}},
            )
            assert resolved.status_code == 202, resolved.text
            assert client.get(f"/api/jds/{role_id}/tasks/resolve").json()["status"] == "done"
            assert client.post(f"/api/batches/{batch_id}/tasks/{task['task_id']}/refresh").status_code == 200

        batch_tasks = {task["jd_id"]: task for task in client.get(f"/api/batches/{batch_id}").json()["tasks"]}
        saved = client.get("/api/jds", params={"project_id": "batch-clarification-isolation"})
        assert saved.status_code == 200, saved.text
        saved_jobs = {job["jd_id"]: job for job in saved.json()}
        screening_ids = jd_ids_by_index[:3]
        for role_id in screening_ids:
            assert batch_tasks[role_id]["lifecycle_status"] == "FINALIZED"
            assert saved_jobs[role_id]["lifecycle_status"] == "FINALIZED"
        assert saved_jobs[jd_ids_by_index[3]]["lifecycle_status"] == "AWAITING_CLARIFICATION"

        resume = b"Alex Example designed printed circuit boards, verified schematics and documented the validation results."
        files = [("files", ("alex.txt", resume, "text/plain"))]
        candidate_ids = set()
        run_ids = set()
        for role_id in screening_ids:
            base = f"/api/jds/{role_id}/resumes"
            spec_id = saved_jobs[role_id]["spec_version_id"]
            assert spec_id
            assert client.post(f"{base}/screen", json={"spec_version_id": spec_id}).status_code == 404
            uploaded = client.post(base, files=files)
            assert uploaded.status_code == 202, uploaded.text
            candidate_id = uploaded.json()["uploaded"][0]["candidate_resume_id"]
            assert candidate_id not in candidate_ids
            candidate_ids.add(candidate_id)
            queued = client.post(
                f"{base}/screen",
                json={"spec_version_id": spec_id, "candidate_resume_ids": [candidate_id]},
            )
            assert queued.status_code == 202, queued.text
            assert queued.json()["queued_count"] == 1
            run_id = queued.json()["candidate_resume_ids"][0]
            assert run_id not in run_ids
            run_ids.add(run_id)
            leaderboard = client.get(base).json()
            assert leaderboard["spec_version_id"] == spec_id
            assert leaderboard["total_candidates"] == 1
            assert leaderboard["candidates"][0]["candidate_resume_id"] == candidate_id
            assert leaderboard["candidates"][0]["evaluation_id"] == run_id

        unfinalized_base = f"/api/jds/{jd_ids_by_index[3]}/resumes"
        assert client.post(unfinalized_base, files=files).status_code == 202
        assert client.post(f"{unfinalized_base}/screen").status_code == 409


def test_batch_failure_isolation_retry_and_safe_cancellation():
    from app.schemas.master_context import JDMasterContext

    cancel_worker_entered = threading.Event()
    release_cancel_worker = threading.Event()
    fail_once = {"enabled": True}

    class FakeExtractionResult:
        def __init__(self, source: str) -> None:
            self.source = source

        def to_master_context(self, jd_id: str, raw_jd_text: str):
            return JDMasterContext(jd_id=jd_id, raw_jd_text=raw_jd_text)

    class ControlledExtractionPipeline:
        def __init__(self, llm_enabled: bool = False) -> None:
            self.llm_enabled = llm_enabled

        def process_jd(self, raw_text: str):
            if "FAIL_ONCE" in raw_text and fail_once["enabled"]:
                raise RuntimeError("controlled one-time failure")
            if "CANCEL_ME" in raw_text:
                cancel_worker_entered.set()
                if not release_cancel_worker.wait(timeout=10):
                    raise TimeoutError("test did not release cancellation worker")
            return FakeExtractionResult(raw_text)

    offline_enrichment = SimpleNamespace(check_ollama_available=lambda: False)

    with (
        patch("app.workers.worker.ExtractionPipeline", ControlledExtractionPipeline),
        patch(
            "app.services.enrichment.ta_enrichment_service.get_enrichment_service",
            return_value=offline_enrichment,
        ),
        TestClient(app) as client,
    ):
        created = client.post(
            "/api/batches",
            data={"project_id": "batch-isolation-retry-cancel"},
            files=[
                ("files", ("fail-once.txt", b"FAIL_ONCE role", "text/plain")),
                ("files", ("cancel-me.txt", b"CANCEL_ME role", "text/plain")),
                ("files", ("succeeds.txt", b"independent successful role", "text/plain")),
            ],
        )
        assert created.status_code == 202, created.text
        batch_id = created.json()["batch_id"]
        tasks_by_filename = {
            task["filename"]: task for task in created.json()["tasks"]
        }

        assert cancel_worker_entered.wait(timeout=10)
        cancelled_task = tasks_by_filename["cancel-me.txt"]
        cancel_response = client.post(
            f"/api/batches/{batch_id}/tasks/{cancelled_task['task_id']}/cancel"
        )
        assert cancel_response.status_code == 200
        release_cancel_worker.set()

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            latest = client.get(f"/api/batches/{batch_id}").json()
            states = {task["filename"]: task["status"] for task in latest["tasks"]}
            if all(state in {"COMPLETED", "FAILED", "CANCELLED"} for state in states.values()):
                break
            time.sleep(0.05)

        assert states == {
            "fail-once.txt": "FAILED",
            "cancel-me.txt": "CANCELLED",
            "succeeds.txt": "COMPLETED",
        }
        fail_once["enabled"] = False
        failed_task = tasks_by_filename["fail-once.txt"]
        retry_response = client.post(
            f"/api/batches/{batch_id}/tasks/{failed_task['task_id']}/retry"
        )
        assert retry_response.status_code == 202, retry_response.text

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            latest = client.get(f"/api/batches/{batch_id}").json()
            retried = next(
                task for task in latest["tasks"]
                if task["filename"] == "fail-once.txt"
            )
            if retried["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
                break
            time.sleep(0.05)
        assert retried["status"] == "COMPLETED"
        assert latest["completed"] == 2
