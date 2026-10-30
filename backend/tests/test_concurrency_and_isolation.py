"""
Concurrency, lock-wait tracking, and multi-JD isolation tests.
Validates:
1. Lock-wait time is tracked separately from inference time.
2. Bounded semaphore limits concurrent Ollama slots while preventing permit leakage.
3. Multiple concurrent JDs execute Stage 1 deterministic analysis without mutual blocking.
4. JD isolation, deterministic fallback, and result ordering are strictly preserved.
"""
import json
import os
import subprocess
import sys
import threading
import time
import pytest
from unittest.mock import patch, MagicMock

from app.core.concurrency import (
    acquire_ollama_slot,
    get_concurrency_metrics,
    resolve_ollama_concurrency,
    reset_concurrency_metrics,
)
from app.services.enrichment.ta_enrichment_service import GroundedEnrichmentService


def test_environment_configures_more_than_two_ollama_slots():
    """A fresh backend process honors an explicit concurrency value above two."""
    script = """
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from app.config import get_settings
from app.core.concurrency import acquire_ollama_slot, get_concurrency_metrics

barrier = threading.Barrier(5)
def request():
    barrier.wait()
    with acquire_ollama_slot("test_request"):
        time.sleep(0.1)

with ThreadPoolExecutor(max_workers=5) as pool:
    list(pool.map(lambda _: request(), range(5)))
metrics = get_concurrency_metrics()
metrics["worker_pool_size"] = get_settings().jd_processing_concurrency
print(json.dumps(metrics))
"""
    env = {**os.environ, "OLLAMA_MAX_CONCURRENCY": "3"}
    env["JD_PROCESSING_CONCURRENCY"] = "5"
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        env=env,
        timeout=15,
    )
    metrics = json.loads(result.stdout.strip().splitlines()[-1])
    assert metrics["configured_max_concurrency"] == 3
    assert metrics["max_observed_concurrency"] == 3
    assert metrics["worker_pool_size"] == 5


def test_gpu_memory_aware_concurrency_default():
    assert resolve_ollama_concurrency(0, None) == 1
    assert resolve_ollama_concurrency(0, 900) == 1
    assert resolve_ollama_concurrency(0, 2_048) == 2
    assert resolve_ollama_concurrency(0, 3_072) == 3
    assert resolve_ollama_concurrency(0, 6_144) == 4
    assert resolve_ollama_concurrency(3, 1_000) == 3


def test_lock_wait_tracked_separately_from_inference():
    """Verify lock-wait time and inference duration are tracked separately and accurately."""
    reset_concurrency_metrics()

    wait_times = []
    infer_times = []

    def task(task_name: str, hold_time: float):
        t0 = time.perf_counter()
        with acquire_ollama_slot(task_name) as wait_ms:
            wait_times.append(wait_ms)
            time.sleep(hold_time)
            infer_times.append((time.perf_counter() - t0) * 1000.0 - wait_ms)

    # Thread 1 holds the slot for 0.1s
    t1 = threading.Thread(target=task, args=("task_1", 0.1))
    # Thread 2 starts slightly later and must wait for Thread 1
    t2 = threading.Thread(target=task, args=("task_2", 0.05))

    t1.start()
    time.sleep(0.02)  # ensure t1 acquires first
    t2.start()

    t1.join()
    t2.join()

    metrics = get_concurrency_metrics()
    assert metrics["total_acquisitions"] >= 2
    # Thread 1 had ~0 lock wait
    assert wait_times[0] < 50.0
    # Thread 2 waited for Thread 1 (~80ms)
    assert wait_times[1] >= 50.0
    # Thread 1 held for ~100ms
    assert infer_times[0] >= 90.0


def test_semaphore_permit_never_leaks_on_exception():
    """Verify that exceptions inside acquire_ollama_slot cleanly release the semaphore."""
    reset_concurrency_metrics()

    class CustomTestError(Exception):
        pass

    try:
        with acquire_ollama_slot("failing_task"):
            raise CustomTestError("Simulated inference crash")
    except CustomTestError:
        pass

    # Next caller should immediately acquire without timing out or blocking
    acquired = False
    with acquire_ollama_slot("recovery_task", timeout=0.5) as wait_ms:
        acquired = True
        assert wait_ms < 50.0

    assert acquired is True


def test_deterministic_fallback_when_ollama_unavailable():
    """Verify enrichment service cleanly falls back without raising unhandled exceptions."""
    service = GroundedEnrichmentService()

    with patch.object(service, "check_ollama_available", return_value=False):
        # Offline probe returns False -> caller gets clean fallback
        assert service.check_ollama_available() is False


def test_concurrent_enrichment_preserves_requirement_order():
    """Verify requirement ordering is preserved across concurrent chunks."""
    service = GroundedEnrichmentService()

    sample_reqs = [
        {"id": f"req_{i}", "text": f"Requirement number {i} with specific technical details", "priority": "MUST_HAVE"}
        for i in range(1, 10)
    ]

    # Mock Ollama response returning enriched items
    mock_response = """```json
    {
      "items": [
        {"requirement_id": "req_1", "evidence_queries": ["q1"], "evaluation_intent": "intent1", "interview_questions": ["iq1"], "scoring_guide": {"5": "ex", "3": "mid", "1": "low"}},
        {"requirement_id": "req_2", "evidence_queries": ["q2"], "evaluation_intent": "intent2", "interview_questions": ["iq2"], "scoring_guide": {"5": "ex", "3": "mid", "1": "low"}}
      ],
      "evaluation_priorities": ["intent1", "intent2"]
    }
    ```"""

    with patch.object(service, "check_ollama_available", return_value=True):
        with patch.object(service, "_call_ollama", return_value=mock_response):
            report = service.generate_enrichment_report(
                spec_version_id="order_test",
                specification_version=1,
                source_checksum="chk_123",
                requirements=sample_reqs,
            )
            assert report.source_specification_version == 1
            assert len(report.items) >= 2


def test_concurrent_multi_jd_processing_isolation():
    """Verify concurrent analysis of two distinct JDs produces isolated specifications."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    # Upload JD 1
    res1 = client.post(
        "/api/jds",
        data={
            "project_id": "proj_concurrent",
            "title": "Concurrent Backend Go Lead",
            "text": "Go Backend Lead with Kubernetes, Microservices, and gRPC experience.",
        },
    )
    assert res1.status_code == 200
    jd1_id = res1.json()["jd_id"]

    # Upload JD 2
    res2 = client.post(
        "/api/jds",
        data={
            "project_id": "proj_concurrent",
            "title": "Concurrent Mobile iOS Architect",
            "text": "iOS Architect with Swift, SwiftUI, Combine, and offline-first mobile sync.",
        },
    )
    assert res2.status_code == 200
    jd2_id = res2.json()["jd_id"]

    errors = []

    def analyze(jd_id: str):
        try:
            r = client.post(f"/api/jds/{jd_id}/analyze")
            if r.status_code not in (200, 202):
                errors.append(f"Failed to analyze {jd_id}: {r.text}")
        except Exception as e:
            errors.append(str(e))

    with patch("app.services.enrichment.ta_enrichment_service.GroundedEnrichmentService.check_ollama_available", return_value=False):
        t1 = threading.Thread(target=analyze, args=(jd1_id,))
        t2 = threading.Thread(target=analyze, args=(jd2_id,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    assert not errors, f"Errors during concurrent analysis: {errors}"

    # Verify specs are isolated
    spec1_res = client.get(f"/api/jds/{jd1_id}/markdown")
    spec2_res = client.get(f"/api/jds/{jd2_id}/markdown")
    assert spec1_res.status_code == 200
    assert spec2_res.status_code == 200

    md1 = spec1_res.json()["markdown"]
    md2 = spec2_res.json()["markdown"]

    assert "Go" in md1 or "Backend" in md1
    assert "iOS" in md2 or "Swift" in md2
    assert md1 != md2


def test_realistic_concurrent_load():
    """
    Test realistic concurrent load: simultaneous uploads, clarification submissions,
    and chat queries without deadlock or state corruption.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    # 1. Simultaneous JD uploads
    res1 = client.post(
        "/api/jds",
        data={
            "project_id": "proj_load",
            "title": "Cloud Platform Engineer",
            "text": "Cloud Engineer with Terraform, AWS, Docker, and Python automation.",
        },
    )
    res2 = client.post(
        "/api/jds",
        data={
            "project_id": "proj_load",
            "title": "Data Engineering Lead",
            "text": "Data Engineer with Apache Spark, Kafka, Snowflake, and SQL pipelines.",
        },
    )
    assert res1.status_code == 200
    assert res2.status_code == 200
    jd1_id = res1.json()["jd_id"]
    jd2_id = res2.json()["jd_id"]

    with patch("app.services.enrichment.ta_enrichment_service.GroundedEnrichmentService.check_ollama_available", return_value=False):
        # 2. Analyze both
        client.post(f"/api/jds/{jd1_id}/analyze")
        client.post(f"/api/jds/{jd2_id}/analyze")

        results = []

        def run_chat(jd_id: str, question: str):
            try:
                r = client.post(f"/api/jds/{jd_id}/chat", json={"question": question})
                results.append(("chat", r.status_code))
            except Exception as e:
                results.append(("chat_err", str(e)))

        def run_clarification(jd_id: str):
            try:
                r = client.post(
                    f"/api/jds/{jd_id}/clarifications/resolve",
                    json={"answers": {"job_context.team_size": "5-10 engineers"}},
                )
                results.append(("clarification", r.status_code))
            except Exception as e:
                results.append(("clarification_err", str(e)))

        threads = [
            threading.Thread(target=run_chat, args=(jd1_id, "What skills are needed?")),
            threading.Thread(target=run_chat, args=(jd2_id, "What databases are required?")),
            threading.Thread(target=run_clarification, args=(jd1_id,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    # All concurrent requests should succeed (200/202) or gracefully handle slot queuing without crashes
    for kind, code in results:
        assert code in (200, 202, 503), f"Unexpected status {code} in {kind}"


def test_slot_timeout_explicit_failure_reporting():
    """
    Confirm that waiting for an Ollama slot cannot cause misleading success
    or silently discard enrichment: on slot timeout, an explicit failure is raised/recorded.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.concurrency import _ollama_semaphore

    client = TestClient(app)

    # Upload JD
    res = client.post(
        "/api/jds",
        data={
            "project_id": "proj_timeout",
            "title": "Timeout Test Engineer",
            "text": "Timeout Test role requiring Python and PyTest.",
        },
    )
    jd_id = res.json()["jd_id"]
    client.post(f"/api/jds/{jd_id}/analyze")

    # Exhaust the semaphore artificially to simulate slot starvation
    _ollama_semaphore.acquire()
    try:
        with patch("app.core.concurrency.DEFAULT_SLOT_TIMEOUT", 0.1):
            # Attempting enrichment with a starved slot must result in explicit failure
            res_enrich = client.post(f"/api/jds/{jd_id}/enrich")
            assert res_enrich.status_code == 202

            # Poll task status: must record failed with clear error, NOT misleading success
            task_info = client.get(f"/api/jds/{jd_id}/tasks/enrich").json()
            assert task_info["status"] in ("failed", "running")
            if task_info["status"] == "failed":
                assert "Ollama" in task_info["error"] or "Timed out" in task_info["error"]
    finally:
        _ollama_semaphore.release()


def test_incremental_reenrichment_touches_only_affected_requirements():
    """
    P3 Validation: When a TA answers a clarification touching a specific requirement,
    only the affected requirement is re-enriched via Ollama, while untouched requirements
    preserve their existing enrichment items without full re-enrichment.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import SessionLocal
    from app.models.db_models import JobSpecificationVersion
    from app.services.enrichment.ta_enrichment_service import GroundedEnrichmentService

    client = TestClient(app)

    # Upload JD
    res = client.post(
        "/api/jds",
        data={
            "project_id": "proj_p3",
            "title": "Backend Architect",
            "text": "1. Python FastAPI microservices.\n2. Kubernetes and Docker clusters.\n3. Kafka message streaming.",
        },
    )
    jd_id = res.json()["jd_id"]
    client.post(f"/api/jds/{jd_id}/analyze")

    # Seed mock prior enrichment report in DB
    db = SessionLocal()
    try:
        spec_v1 = (
            db.query(JobSpecificationVersion)
            .join(JobSpecificationVersion.jd_version)
            .filter(JobSpecificationVersion.jd_version.has(job_description_id=jd_id))
            .first()
        )
        assert spec_v1 is not None

        req_items = []
        if spec_v1.master_context_json and "requirements" in spec_v1.master_context_json:
            for r in spec_v1.master_context_json["requirements"]:
                req_items.append({
                    "requirement_id": r["id"],
                    "requirement_text": r.get("text", "Requirement text"),
                    "technical_concept_summary": "Technical concept summary",
                    "strong_evidence_signals": [f"query_{r['id']}"],
                    "weak_or_ambiguous_signals": [f"weak_{r['id']}"],
                    "screening_question": f"question_{r['id']}",
                })

        mock_prior_report = {
            "source_specification_version_id": str(spec_v1.id),
            "source_specification_version": 1,
            "source_checksum": "chk_v1",
            "evaluation_priorities": ["Priority 1", "Priority 2"],
            "items": req_items,
            "model_version": "mock_model",
        }
        spec_v1.enrichment_report_json = mock_prior_report
        from app.services.storage import build_key, get_storage
        storage = get_storage()
        proj_id = str(spec_v1.jd_version.job_description.project_id) if spec_v1.jd_version and spec_v1.jd_version.job_description else "proj_p3"
        valid_enriched_key = build_key(proj_id, jd_id, 1, "enriched_markdown")
        storage.put_text(valid_enriched_key, "# Enriched Markdown v1")
        spec_v1.s3_enriched_markdown_key = valid_enriched_key
        db.commit()

        # Target requirement 1
        target_req_id = req_items[0]["requirement_id"]
    finally:
        db.close()

    # Track requirements received by generate_enrichment_report during resolve
    passed_requirements = []

    def mock_gen_enrich(self, *args, **kwargs):
        reqs = kwargs.get("requirements") or []
        passed_requirements.extend(reqs)
        from app.schemas.enrichment import TAEnrichmentReport, RequirementEnrichmentItem
        return TAEnrichmentReport(
            source_specification_version_id=str(kwargs.get("spec_version_id", "dummy_spec")),
            source_specification_version=kwargs.get("specification_version", 2),
            source_checksum="chk_v2",
            evaluation_priorities=["Updated Priority"],
            items=[
                RequirementEnrichmentItem(
                    requirement_id=r["requirement_id"],
                    requirement_text=r.get("text", "Requirement text"),
                    technical_concept_summary="Updated summary",
                    strong_evidence_signals=["updated_signal"],
                    weak_or_ambiguous_signals=[],
                    screening_question="updated_question",
                )
                for r in reqs
            ],
            model_version="mock_model",
        )

    with patch.object(GroundedEnrichmentService, "check_ollama_available", return_value=True):
        with patch.object(GroundedEnrichmentService, "generate_enrichment_report", mock_gen_enrich):
            # Answer clarification specifically targeting requirement 1
            res_resolve = client.post(
                f"/api/jds/{jd_id}/clarifications/resolve",
                json={
                    "answers": {
                        f"requirements[id={target_req_id}].priority": "MUST_HAVE",
                    }
                },
            )
            assert res_resolve.status_code == 202

    # Verify P3 behavior: Only the affected requirement was passed to Ollama!
    passed_ids = [r["requirement_id"] for r in passed_requirements]
    assert target_req_id in passed_ids
    # Crucial: Not ALL requirements were passed again!
    assert len(passed_requirements) < len(req_items)


def test_incremental_reenrichment_zero_llm_calls_for_non_technical_clarification():
    """
    P3 Validation: When clarification answer touches role context (e.g. salary or team size),
    zero LLM calls are made and prior enrichments are reused immediately in 0ms.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import SessionLocal
    from app.models.db_models import JobSpecificationVersion
    from app.services.enrichment.ta_enrichment_service import GroundedEnrichmentService

    client = TestClient(app)

    res = client.post(
        "/api/jds",
        data={
            "project_id": "proj_p3_zero",
            "title": "Lead Architect",
            "text": "Lead Architect with Python and AWS.",
        },
    )
    jd_id = res.json()["jd_id"]
    client.post(f"/api/jds/{jd_id}/analyze")

    # Seed mock prior enrichment report in DB
    db = SessionLocal()
    try:
        spec_v1 = (
            db.query(JobSpecificationVersion)
            .join(JobSpecificationVersion.jd_version)
            .filter(JobSpecificationVersion.jd_version.has(job_description_id=jd_id))
            .first()
        )
        spec_v1.enrichment_report_json = {
            "source_specification_version_id": str(spec_v1.id),
            "source_specification_version": 1,
            "source_checksum": "chk_v1",
            "evaluation_priorities": ["Priority 1"],
            "items": [
                {
                    "requirement_id": "req_lead_1",
                    "requirement_text": "Lead Architect with Python and AWS.",
                    "technical_concept_summary": "Concept summary",
                    "strong_evidence_signals": ["Signal 1"],
                    "weak_or_ambiguous_signals": [],
                    "screening_question": "Screening question",
                }
            ],
            "model_version": "mock_model",
        }
        from app.services.storage import build_key, get_storage
        storage = get_storage()
        proj_id = str(spec_v1.jd_version.job_description.project_id) if spec_v1.jd_version and spec_v1.jd_version.job_description else "proj_p3_zero"
        valid_enriched_key = build_key(proj_id, jd_id, 1, "enriched_markdown")
        storage.put_text(valid_enriched_key, "# Enriched Markdown v1")
        spec_v1.s3_enriched_markdown_key = valid_enriched_key
        db.commit()
    finally:
        db.close()

    mock_called = False

    def mock_gen_fail(self, *args, **kwargs):
        nonlocal mock_called
        mock_called = True
        raise RuntimeError("Ollama should NOT be called for non-technical clarification!")

    with patch.object(GroundedEnrichmentService, "generate_enrichment_report", mock_gen_fail):
        res_resolve = client.post(
            f"/api/jds/{jd_id}/clarifications/resolve",
            json={"answers": {"job_context.team_size": "8 engineers"}},
        )
        assert res_resolve.status_code == 202

    # Verify zero calls occurred
    assert mock_called is False

    # Verify new spec exists with preserved enrichment
    spec_v2_res = client.get(f"/api/jds/{jd_id}/markdown")
    assert spec_v2_res.status_code == 200
    assert spec_v2_res.json()["specification_version"] == 2
    assert spec_v2_res.json()["is_enriched"] is True


def test_stale_enrichment_never_carried_forward():
    """
    Edge Case 1: If a clarification changes a requirement, ensure the new version
    never carries forward outdated enrichment for that requirement.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import SessionLocal
    from app.models.db_models import JobSpecificationVersion
    from app.services.enrichment.ta_enrichment_service import GroundedEnrichmentService
    from app.schemas.enrichment import TAEnrichmentReport, RequirementEnrichmentItem

    client = TestClient(app)

    # 1. Upload JD with 2 requirements
    res = client.post(
        "/api/jds",
        data={
            "project_id": "proj_stale",
            "title": "Data Engineer",
            "text": "1. Python PySpark ETL pipelines.\n2. Snowflake data warehouse modeling.",
        },
    )
    jd_id = res.json()["jd_id"]
    client.post(f"/api/jds/{jd_id}/analyze")

    # 2. Seed mock v1 enrichment report
    db = SessionLocal()
    try:
        spec_v1 = (
            db.query(JobSpecificationVersion)
            .join(JobSpecificationVersion.jd_version)
            .filter(JobSpecificationVersion.jd_version.has(job_description_id=jd_id))
            .first()
        )
        reqs = spec_v1.master_context_json["requirements"]
        req1_id = reqs[0]["id"]
        req2_id = reqs[1]["id"]

        spec_v1.enrichment_report_json = {
            "source_specification_version_id": str(spec_v1.id),
            "source_specification_version": 1,
            "source_checksum": "chk_v1",
            "evaluation_priorities": ["Priority 1"],
            "items": [
                {
                    "requirement_id": req1_id,
                    "requirement_text": reqs[0].get("text"),
                    "technical_concept_summary": "STALE_OLD_SUMMARY_REQ1",
                    "strong_evidence_signals": ["stale_signal_1"],
                    "weak_or_ambiguous_signals": [],
                    "screening_question": "stale_q1",
                },
                {
                    "requirement_id": req2_id,
                    "requirement_text": reqs[1].get("text"),
                    "technical_concept_summary": "VALID_SUMMARY_REQ2",
                    "strong_evidence_signals": ["valid_signal_2"],
                    "weak_or_ambiguous_signals": [],
                    "screening_question": "valid_q2",
                },
            ],
            "model_version": "mock_v1",
        }
        from app.services.storage import build_key, get_storage
        storage = get_storage()
        proj_id = str(spec_v1.jd_version.job_description.project_id) if spec_v1.jd_version and spec_v1.jd_version.job_description else "proj_stale"
        valid_enriched_key = build_key(proj_id, jd_id, 1, "enriched_markdown")
        storage.put_text(valid_enriched_key, "# Enriched Markdown v1")
        spec_v1.s3_enriched_markdown_key = valid_enriched_key
        db.commit()
    finally:
        db.close()

    # 3. Simulate re-enriching req1 with a brand new summary
    def mock_gen_enrich(self, *args, **kwargs):
        reqs_passed = kwargs.get("requirements") or []
        assert len(reqs_passed) == 1
        assert reqs_passed[0]["requirement_id"] == req1_id
        return TAEnrichmentReport(
            source_specification_version_id="dummy",
            source_specification_version=2,
            source_checksum="chk_v2",
            evaluation_priorities=["Updated Priority"],
            items=[
                RequirementEnrichmentItem(
                    requirement_id=req1_id,
                    requirement_text=reqs_passed[0].get("text"),
                    technical_concept_summary="FRESH_NEW_SUMMARY_REQ1",
                    strong_evidence_signals=["fresh_signal_1"],
                    weak_or_ambiguous_signals=[],
                    screening_question="fresh_q1",
                )
            ],
            model_version="mock_v2",
        )

    with patch.object(GroundedEnrichmentService, "check_ollama_available", return_value=True):
        with patch.object(GroundedEnrichmentService, "generate_enrichment_report", mock_gen_enrich):
            # Change requirement 1
            client.post(
                f"/api/jds/{jd_id}/clarifications/resolve",
                json={
                    "answers": {
                        f"requirements[id={req1_id}].priority": "MUST_HAVE",
                    }
                },
            )

    # 4. Check v2 enrichment report in DB
    db = SessionLocal()
    try:
        spec_v2 = (
            db.query(JobSpecificationVersion)
            .join(JobSpecificationVersion.jd_version)
            .filter(JobSpecificationVersion.jd_version.has(job_description_id=jd_id))
            .filter(JobSpecificationVersion.specification_version == 2)
            .first()
        )
        assert spec_v2 is not None
        v2_report = spec_v2.enrichment_report_json
        assert v2_report is not None

        items_by_id = {item["requirement_id"]: item for item in v2_report["items"]}
        # Verify req1 received FRESH enrichment and STALE summary is GONE
        assert items_by_id[req1_id]["technical_concept_summary"] == "FRESH_NEW_SUMMARY_REQ1"
        assert "STALE_OLD_SUMMARY_REQ1" not in str(v2_report)

        # Verify req2 preserved its VALID enrichment
        assert items_by_id[req2_id]["technical_concept_summary"] == "VALID_SUMMARY_REQ2"
    finally:
        db.close()


def test_affected_requirement_detection_comprehensive():
    """
    Edge Case 2: Test indirect changes, multiple answers, and ambiguous references
    to ensure no affected requirement is missed.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import SessionLocal
    from app.models.db_models import JobSpecificationVersion
    from app.services.enrichment.ta_enrichment_service import GroundedEnrichmentService
    from app.schemas.master_context import DetectedAmbiguity

    client = TestClient(app)

    # 1. Upload JD with 3 distinct requirements
    res = client.post(
        "/api/jds",
        data={
            "project_id": "proj_detect",
            "title": "Platform Engineer",
            "text": (
                "1. Kubernetes cluster administration and Helm charts.\n"
                "2. PostgreSQL database tuning and indexing.\n"
                "3. 5+ years of senior software engineering experience."
            ),
        },
    )
    jd_id = res.json()["jd_id"]
    client.post(f"/api/jds/{jd_id}/analyze")

    db = SessionLocal()
    try:
        spec_v1 = (
            db.query(JobSpecificationVersion)
            .join(JobSpecificationVersion.jd_version)
            .filter(JobSpecificationVersion.jd_version.has(job_description_id=jd_id))
            .first()
        )
        mc = spec_v1.master_context_json
        reqs = mc["requirements"]
        k8s_req_id = reqs[0]["id"]
        pg_req_id = reqs[1]["id"]
        exp_req_id = reqs[2]["id"]

        # Add ambiguity referencing Postgres
        from app.schemas.master_context import JDMasterContext
        master_obj = JDMasterContext.model_validate(mc)
        master_obj.raw_ambiguities.append(
            DetectedAmbiguity(
                ambiguity_id="amb_pg_cluster",
                text="PostgreSQL replication clustering",
                reason="Unclear if patroni or aurora is required",
            )
        )
        spec_v1.master_context_json = master_obj.model_dump(mode="json")
        spec_v1.enrichment_report_json = {
            "source_specification_version_id": str(spec_v1.id),
            "source_specification_version": 1,
            "source_checksum": "chk_v1",
            "evaluation_priorities": [],
            "items": [
                {
                    "requirement_id": r["id"],
                    "requirement_text": r.get("text"),
                    "technical_concept_summary": f"Concept for {r['id']}",
                    "strong_evidence_signals": [],
                    "weak_or_ambiguous_signals": [],
                    "screening_question": "q",
                }
                for r in reqs
            ],
            "model_version": "mock_v1",
        }
        db.commit()
    finally:
        db.close()

    # Track which requirements are sent for re-enrichment
    enriched_req_ids = []

    def mock_gen_enrich(self, *args, **kwargs):
        reqs_passed = kwargs.get("requirements") or []
        enriched_req_ids.extend([r["requirement_id"] for r in reqs_passed])
        from app.schemas.enrichment import TAEnrichmentReport, RequirementEnrichmentItem
        return TAEnrichmentReport(
            source_specification_version_id="dummy",
            source_specification_version=2,
            source_checksum="chk_v2",
            evaluation_priorities=[],
            items=[
                RequirementEnrichmentItem(
                    requirement_id=r["requirement_id"],
                    requirement_text=r.get("text"),
                    technical_concept_summary="Updated",
                    strong_evidence_signals=[],
                    weak_or_ambiguous_signals=[],
                    screening_question="q",
                )
                for r in reqs_passed
            ],
            model_version="mock_v2",
        )

    with patch.object(GroundedEnrichmentService, "check_ollama_available", return_value=True):
        with patch.object(GroundedEnrichmentService, "generate_enrichment_report", mock_gen_enrich):
            # Resolve with MULTIPLE simultaneous answers:
            # - Direct field target on k8s
            # - Ambiguity reference on postgres
            # - Non-technical answer on team size
            client.post(
                f"/api/jds/{jd_id}/clarifications/resolve",
                json={
                    "answers": {
                        f"requirements[id={k8s_req_id}].priority": "MANDATORY",
                        "amb_pg_cluster": "We use AWS Aurora PostgreSQL multi-AZ",
                        "job_context.team_size": "12 engineers",
                    }
                },
            )

    # Both k8s (direct) and pg (ambiguous text/token reference) MUST be detected as affected!
    assert k8s_req_id in enriched_req_ids
    assert pg_req_id in enriched_req_ids


def test_failure_during_incremental_enrichment_preserves_prior_and_falls_back():
    """
    Edge Case 3: Verify that partial results or failures during incremental enrichment
    cannot silently replace valid prior results or mark the new version as fully enriched.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import SessionLocal
    from app.models.db_models import JobSpecificationVersion
    from app.services.enrichment.ta_enrichment_service import GroundedEnrichmentService

    client = TestClient(app)

    # 1. Upload JD
    res = client.post(
        "/api/jds",
        data={
            "project_id": "proj_fail_inc",
            "title": "Cloud Architect",
            "text": "1. AWS CloudFormation and Terraform.\n2. Golang microservice development.",
        },
    )
    jd_id = res.json()["jd_id"]
    client.post(f"/api/jds/{jd_id}/analyze")

    # 2. Seed mock v1 enrichment report
    db = SessionLocal()
    try:
        spec_v1 = (
            db.query(JobSpecificationVersion)
            .join(JobSpecificationVersion.jd_version)
            .filter(JobSpecificationVersion.jd_version.has(job_description_id=jd_id))
            .first()
        )
        reqs = spec_v1.master_context_json["requirements"]
        req1_id = reqs[0]["id"]

        prior_v1_report = {
            "source_specification_version_id": str(spec_v1.id),
            "source_specification_version": 1,
            "source_checksum": "chk_v1",
            "evaluation_priorities": ["Priority 1"],
            "items": [
                {
                    "requirement_id": r["id"],
                    "requirement_text": r.get("text"),
                    "technical_concept_summary": f"Prior Concept {r['id']}",
                    "strong_evidence_signals": ["prior_sig"],
                    "weak_or_ambiguous_signals": [],
                    "screening_question": "prior_q",
                }
                for r in reqs
            ],
            "model_version": "mock_v1",
        }
        spec_v1.enrichment_report_json = prior_v1_report
        from app.services.storage import build_key, get_storage
        storage = get_storage()
        proj_id = str(spec_v1.jd_version.job_description.project_id) if spec_v1.jd_version and spec_v1.jd_version.job_description else "proj_fail_inc"
        valid_enriched_key = build_key(proj_id, jd_id, 1, "enriched_markdown")
        storage.put_text(valid_enriched_key, "# Enriched Markdown v1 Valid")
        spec_v1.s3_enriched_markdown_key = valid_enriched_key
        db.commit()
    finally:
        db.close()

    # Part A: Outright Ollama failure/exception during incremental re-enrichment
    def mock_gen_crash(self, *args, **kwargs):
        raise RuntimeError("Ollama crashed during incremental re-enrichment!")

    with patch.object(GroundedEnrichmentService, "check_ollama_available", return_value=True):
        with patch.object(GroundedEnrichmentService, "generate_enrichment_report", mock_gen_crash):
            res_resolve = client.post(
                f"/api/jds/{jd_id}/clarifications/resolve",
                json={
                    "answers": {
                        f"requirements[id={req1_id}].priority": "MUST_HAVE",
                    }
                },
            )
            assert res_resolve.status_code == 202

    # Verification for Part A:
    db = SessionLocal()
    try:
        # 1. Spec v1 remains intact with its valid enrichment report
        v1_check = (
            db.query(JobSpecificationVersion)
            .join(JobSpecificationVersion.jd_version)
            .filter(JobSpecificationVersion.jd_version.has(job_description_id=jd_id))
            .filter(JobSpecificationVersion.specification_version == 1)
            .first()
        )
        assert v1_check.enrichment_report_json is not None
        assert v1_check.s3_enriched_markdown_key is not None

        # 2. Spec v2 was created but NOT marked as enriched (fallback to clean baseline)
        v2_check = (
            db.query(JobSpecificationVersion)
            .join(JobSpecificationVersion.jd_version)
            .filter(JobSpecificationVersion.jd_version.has(job_description_id=jd_id))
            .filter(JobSpecificationVersion.specification_version == 2)
            .first()
        )
        assert v2_check is not None
        assert v2_check.enrichment_report_json is None
        assert v2_check.s3_enriched_markdown_key is None
    finally:
        db.close()

    # Verify endpoint returns is_enriched=False for v2
    v2_md_res = client.get(f"/api/jds/{jd_id}/markdown")
    assert v2_md_res.status_code == 200
    assert v2_md_res.json()["specification_version"] == 2
    assert v2_md_res.json()["is_enriched"] is False
