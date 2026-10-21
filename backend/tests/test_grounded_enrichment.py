"""
test_grounded_enrichment.py — Full Test Suite for Grounded TA Evidence Enrichment.

Validates all 5 approved architectural principles:
  1. Unconditional Deterministic Baseline (0 tokens, no LLM, requirement_ids present, master_context_json persisted).
  2. Strict ID Anchoring & Validation (hallucinated IDs dropped, OriginType.LLM_HYPOTHESIS).
  3. Section 4 Confinement & Labeling ([AI Guidance — Evaluator Aid], sections 2 & 3 untouched).
  4. Markdown-to-JSON round-trip safety.
  5. Immutable baseline artifacts and Safe Offline 503 handling.
"""
import json
import uuid
import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app
from app.models.db_models import (
    JobDescription,
    JobDescriptionVersion,
    JobSpecificationVersion,
    ProcessingJob,
    ProcessingStatusEnum,
    Project,
    RoleEnum,
    User,
)
from app.schemas.canonical import EvidenceSpec, JobEvaluationSpecification
from app.schemas.enrichment import RequirementEnrichmentItem, TAEnrichmentReport
from app.schemas.master_context import OriginType
from app.services.agent import JDUnderstandingAgent
from app.services.enrichment.ta_enrichment_service import (
    GroundedEnrichmentService,
    OllamaUnavailableError,
)
from app.services.markdown_renderer import render_markdown
from app.services.markdown_to_json import markdown_to_spec
from app.services.storage import build_key, get_storage
from app.workers.worker import process_job_description_version

client = TestClient(app)


@pytest.fixture(scope="module")
def setup_db():
    init_db()
    db = SessionLocal()
    user = db.query(User).filter_by(email="test_enrichment@example.com").first()
    if not user:
        user = User(email="test_enrichment@example.com", role=RoleEnum.ADMIN)
        db.add(user)
        db.commit()

    project = db.query(Project).filter_by(name="Enrichment Test Project").first()
    if not project:
        project = Project(name="Enrichment Test Project", owner_id=user.id)
        db.add(project)
        db.commit()
    user_id = str(user.id)
    project_id = str(project.id)
    db.close()
    return {"user_id": user_id, "project_id": project_id}


def test_baseline_worker_runs_deterministically_without_llm(setup_db):
    """Step 1: Baseline worker produces canonical spec, 0 tokens, and stable requirement_ids."""
    db = SessionLocal()
    project_id = setup_db["project_id"]

    jd = JobDescription(project_id=project_id, title="Firmware Platform Engineer")
    db.add(jd)
    db.commit()

    raw_text = (
        "Job Title: Firmware Platform Engineer\n"
        "Location: Bangalore, India\n\n"
        "Requirements:\n"
        "- 4+ years of Embedded C and RTOS development\n"
        "- Proficiency with ARM Cortex microcontrollers and I2C/SPI protocols\n\n"
        "Responsibilities:\n"
        "- Design and implement low-level board support packages\n"
        "- Debug hardware-software integration issues using oscilloscopes\n"
    )

    storage = get_storage()
    raw_key = build_key(project_id, jd.id, 1, "raw")
    storage.put_text(raw_key, raw_text, "text/plain")

    jd_ver = JobDescriptionVersion(
        job_description_id=jd.id,
        version=1,
        s3_raw_key=raw_key,
        raw_text_checksum="checksum_fw_01",
    )
    db.add(jd_ver)
    db.commit()

    # Execute baseline processing
    process_job_description_version(db, jd_ver.id)

    # 1. Processing job status check
    job = db.query(ProcessingJob).filter_by(job_description_version_id=jd_ver.id).first()
    assert job is not None
    assert job.status == ProcessingStatusEnum.READY
    assert job.error_message is None

    # 2. Spec version check
    spec_ver = (
        db.query(JobSpecificationVersion)
        .filter_by(job_description_version_id=jd_ver.id)
        .first()
    )
    assert spec_ver is not None
    assert spec_ver.model_version == "deterministic_ekg"
    assert spec_ver.input_tokens == 0
    assert spec_ver.output_tokens == 0
    assert spec_ver.estimated_cost_usd == 0
    assert spec_ver.master_context_json is not None

    # 3. Canonical JSON checks
    canonical = spec_ver.canonical_json
    assert len(canonical.get("must_have_requirements", [])) > 0

    evidence_reqs = canonical.get("evidence_requirements", [])
    assert len(evidence_reqs) > 0
    for ev in evidence_reqs:
        assert ev.get("requirement_id") is not None
        assert ev.get("requirement_id").startswith("req_")

    db.close()


def test_legacy_jd_understanding_agent_preserved():
    """Verify JDUnderstandingAgent.understand() remains available for legacy callers."""
    agent = JDUnderstandingAgent()
    assert hasattr(agent, "understand")
    assert callable(agent.understand)


def test_grounded_enrichment_service_id_validation_and_origin():
    """Step 2: ID validation drops unknown requirement IDs and assigns OriginType.LLM_HYPOTHESIS."""
    known_requirements = [
        {"id": "req_001", "text": "5+ years of Python microservices", "priority": "MUST_HAVE"},
        {"id": "req_002", "text": "PostgreSQL indexing and schema design", "priority": "MUST_HAVE"},
    ]

    # Mock LLM output that includes one valid ID, and one fabricated/hallucinated ID
    mock_llm_json = json.dumps({
        "items": [
            {
                "requirement_id": "req_001",
                "technical_concept_summary": "Python async microservices using FastAPI or asyncio for high concurrency.",
                "strong_evidence_signals": [
                    "Experience profiling and tuning event loop throughput",
                    "Production deployments on Kubernetes with gRPC or REST",
                ],
                "weak_or_ambiguous_signals": [
                    "Only basic scripting or Flask tutorial repos",
                ],
                "screening_question": "How did you manage connection pooling and async timeouts in high-traffic endpoints?",
            },
            {
                "requirement_id": "req_hallucinated_999",
                "technical_concept_summary": "Invented requirement that was never in the JD.",
                "strong_evidence_signals": ["Invented signal"],
                "weak_or_ambiguous_signals": ["Invented signal"],
                "screening_question": "Invented question",
            },
        ]
    })

    service = GroundedEnrichmentService(llm_caller=lambda sys, usr: mock_llm_json)
    report = service.generate_enrichment_report(
        spec_version_id="test_spec_ver_1",
        specification_version=1,
        source_checksum="sha256_mock",
        requirements=known_requirements,
    )

    # Validated: only req_001 kept, hallucinated ID rejected
    assert len(report.items) == 1
    item = report.items[0]
    assert item.requirement_id == "req_001"
    assert item.requirement_text == "5+ years of Python microservices"
    assert item.origin_type == OriginType.LLM_HYPOTHESIS
    assert "FastAPI" in item.technical_concept_summary
    assert len(item.strong_evidence_signals) == 2
    assert "connection pooling" in item.screening_question


def test_offline_failure_probes_ollama_and_fails_safely():
    """Step 2/4: Probing Ollama when offline raises OllamaUnavailableError safely."""
    service = GroundedEnrichmentService(base_url="http://127.0.0.1:9999")
    assert service.check_ollama_available(timeout=0.2) is False

    with pytest.raises(OllamaUnavailableError):
        service.generate_enrichment_report(
            spec_version_id="test_spec_id",
            specification_version=1,
            source_checksum="test_chk",
            requirements=[{"id": "req_1", "text": "Python"}],
        )


def test_markdown_rendering_with_enrichment_and_roundtrip():
    """Step 3: Enrichment rendered strictly in Section 4 with [AI Guidance — Evaluator Aid], roundtrips safely."""
    spec = JobEvaluationSpecification.model_validate({
        "role": {
            "job_title": "Senior Backend Engineer",
            "role": "Backend Engineer",
            "seniority": "Senior",
            "department": "Engineering",
            "employment_type": "Full-time",
            "reporting_structure": "VP Engineering",
            "team_context": "Core Platform",
        },
        "conventional_requirements": {
            "experience": [
                {
                    "description": "Backend software development",
                    "min_years": 5,
                    "max_years": None,
                    "priority": "MUST_HAVE",
                }
            ],
            "location": {
                "country": "India",
                "city": "Bangalore",
                "work_mode": "hybrid",
                "office_attendance": "3 days/week",
                "relocation_required": False,
            },
        },
        "job_context": {
            "environment": "Fast-paced cloud infrastructure",
            "business_context": "Payment processing",
            "team_size": "8",
        },
        "must_have_requirements": ["5+ years of Backend software development", "Distributed systems in Go"],
        "preferred_requirements": ["Kubernetes operator development"],
        "responsibilities": [
            {"kind": "primary", "description": "Architect high-throughput event processing pipelines"}
        ],
        "evidence_requirements": [
            {
                "requirement_id": "req_backend_01",
                "requirement": "Distributed systems in Go",
                "priority": "MUST_HAVE",
                "explicit_or_derived": "explicit",
                "evidence_to_look_for": ["Go channels", "Raft or Paxos implementations"],
                "strong_evidence": "Production Raft implementation with benchmarked metrics",
                "insufficient_evidence": "Basic CLI scripts in Go",
            }
        ],
    })

    # 1. Baseline rendering without enrichment
    baseline_md = render_markdown(spec)
    assert "[AI Guidance — Evaluator Aid]" not in baseline_md
    assert "## 2. Requirements" in baseline_md
    assert "Distributed systems in Go" in baseline_md

    # 2. Enriched rendering with report
    enrichment_report = TAEnrichmentReport(
        source_specification_version_id="spec_123",
        source_specification_version=1,
        source_checksum="chk_123",
        items=[
            RequirementEnrichmentItem(
                requirement_id="req_backend_01",
                requirement_text="Distributed systems in Go",
                technical_concept_summary="Go provides goroutines and channels tailored for concurrent distributed systems.",
                strong_evidence_signals=["Built custom Raft consensus engine", "Tuned Go GC for <10ms tail latency"],
                weak_or_ambiguous_signals=["Only wrote CRUD microservices with Gin"],
                screening_question="How did you diagnose race conditions or goroutine leaks in production?",
                origin_type=OriginType.LLM_HYPOTHESIS,
            )
        ],
    )

    enriched_md = render_markdown(spec, enrichment_report=enrichment_report)
    assert "[AI Guidance — Evaluator Aid]" in enriched_md
    assert "Go provides goroutines and channels" in enriched_md
    assert "How did you diagnose race conditions" in enriched_md

    # Check confinement: Section 2 and Section 3 must NOT have the tag
    sec2_and_3 = enriched_md.split("## 4. Evidence & Evaluation Rules")[0]
    assert "[AI Guidance — Evaluator Aid]" not in sec2_and_3

    # 3. Round-trip safety: parsing enriched markdown produces valid canonical spec
    parse_result = markdown_to_spec(enriched_md)
    assert parse_result.spec.role.job_title == "Senior Backend Engineer"
    assert "Distributed systems in Go" in parse_result.spec.must_have_requirements
    assert len(parse_result.spec.evidence_requirements) >= 1


def test_enrichment_api_flow(setup_db, monkeypatch):
    """Step 4: POST /enrich offline returns 503; with mock returns 200; markdown param preserves immutability."""
    db = SessionLocal()
    project_id = setup_db["project_id"]

    jd = JobDescription(project_id=project_id, title="MLOps Infrastructure Engineer")
    db.add(jd)
    db.commit()

    raw_text = (
        "Job Title: MLOps Infrastructure Engineer\n"
        "Requirements:\n"
        "- 3+ years managing Kubeflow or MLflow pipelines\n"
        "Responsibilities:\n"
        "- Maintain GPU inference clusters\n"
    )

    storage = get_storage()
    raw_key = build_key(project_id, jd.id, 1, "raw")
    storage.put_text(raw_key, raw_text, "text/plain")

    jd_ver = JobDescriptionVersion(
        job_description_id=jd.id,
        version=1,
        s3_raw_key=raw_key,
        raw_text_checksum="checksum_mlops_01",
    )
    db.add(jd_ver)
    db.commit()

    process_job_description_version(db, jd_ver.id)

    spec_ver = (
        db.query(JobSpecificationVersion)
        .filter_by(job_description_version_id=jd_ver.id)
        .first()
    )
    assert spec_ver is not None
    jd_id = str(jd.id)
    spec_ver_id = str(spec_ver.id)
    evidence_req_id = spec_ver.canonical_json["evidence_requirements"][0]["requirement_id"]
    original_canonical_json = json.dumps(spec_ver.canonical_json, sort_keys=True)
    db.close()

    # 1. Baseline GET /markdown?enriched=false returns deterministic baseline
    r_base = client.get(f"/api/jds/{jd_id}/markdown?enriched=false")
    assert r_base.status_code == 200
    baseline_md = r_base.json()["markdown"]
    assert "[AI Guidance — Evaluator Aid]" not in baseline_md

    # 2. POST /enrich when Ollama is offline returns 503
    # Ensure offline check by patching check_ollama_available to return False
    from app.services.enrichment.ta_enrichment_service import GroundedEnrichmentService

    monkeypatch.setattr(GroundedEnrichmentService, "check_ollama_available", lambda self, timeout=3.0: False)
    r_offline = client.post(f"/api/jds/{jd_id}/enrich")
    assert r_offline.status_code in (202, 503)
    if r_offline.status_code == 202:
        task = client.get(f"/api/jds/{jd_id}/tasks/enrich").json()
        assert task["status"] == "failed"
        assert "unavailable" in task["error"].lower()
    else:
        assert "unavailable" in r_offline.json()["detail"].lower()

    # 3. POST /enrich with active Ollama (mocked) succeeds
    mock_resp = json.dumps({
        "items": [
            {
                "requirement_id": evidence_req_id,
                "technical_concept_summary": "Kubeflow orchestrates machine learning workflows on Kubernetes.",
                "strong_evidence_signals": ["Automated training and validation pipelines"],
                "weak_or_ambiguous_signals": ["Local Jupyter notebooks only"],
                "screening_question": "How did you manage model artifact lineage?",
            }
        ]
    })
    monkeypatch.setattr(GroundedEnrichmentService, "check_ollama_available", lambda self, timeout=3.0: True)
    monkeypatch.setattr(GroundedEnrichmentService, "_call_ollama", lambda self, s, u: mock_resp)

    r_online = client.post(f"/api/jds/{jd_id}/enrich")
    assert r_online.status_code in (200, 202)
    if r_online.status_code == 200:
        enrich_data = r_online.json()
        assert enrich_data["status"] == "enriched"
        assert len(enrich_data["enrichment_report"]["items"]) == 1
    else:
        task = client.get(f"/api/jds/{jd_id}/tasks/enrich").json()
        assert task["status"] == "done"

    # 4. GET /enrich returns the report
    r_get_enrich = client.get(f"/api/jds/{jd_id}/enrich")
    assert r_get_enrich.status_code == 200
    assert r_get_enrich.json()["source_specification_version_id"] == spec_ver_id

    # 5. GET /markdown?enriched=true returns enriched markdown
    r_md_enriched = client.get(f"/api/jds/{jd_id}/markdown?enriched=true")
    assert r_md_enriched.status_code == 200
    assert r_md_enriched.json()["is_enriched"] is True
    assert "[AI Guidance — Evaluator Aid]" in r_md_enriched.json()["markdown"]

    # 6. GET /markdown?enriched=false STILL returns pristine baseline markdown
    r_md_base = client.get(f"/api/jds/{jd_id}/markdown?enriched=false")
    assert r_md_base.status_code == 200
    assert r_md_base.json()["is_enriched"] is False
    assert "[AI Guidance — Evaluator Aid]" not in r_md_base.json()["markdown"]

    # 7. Baseline canonical_json in database was NOT altered (immutability)
    db2 = SessionLocal()
    spec_ver_after = db2.get(JobSpecificationVersion, spec_ver_id)
    assert json.dumps(spec_ver_after.canonical_json, sort_keys=True) == original_canonical_json
    db2.close()


def test_clarification_resolution_and_finalization(setup_db, monkeypatch):
    """Test full cycle: baseline with questions -> TA resolves ambiguities -> final v2 spec."""
    from app.services.enrichment.ta_enrichment_service import GroundedEnrichmentService

    # Mock Ollama offline to test safe fallback during analysis and resolution
    monkeypatch.setattr(GroundedEnrichmentService, "check_ollama_available", lambda self, timeout=3.0: False)

    db = SessionLocal()
    project_id = setup_db["project_id"]

    jd = JobDescription(project_id=project_id, title="Lead Verification Engineer")
    db.add(jd)
    db.commit()

    raw_text = (
        "Job Title: Lead Verification Engineer\n\n"
        "Requirements:\n"
        "- 5+ years of SystemVerilog UVM experience\n"
        "- Strong C++ scripting\n\n"
        "Responsibilities:\n"
        "- Build testbench architecture for ASIC verification\n"
    )

    storage = get_storage()
    raw_key = build_key(project_id, jd.id, 1, "raw")
    storage.put_text(raw_key, raw_text, "text/plain")

    jd_ver = JobDescriptionVersion(
        job_description_id=jd.id,
        version=1,
        s3_raw_key=raw_key,
        raw_text_checksum="checksum_verif_01",
    )
    db.add(jd_ver)
    db.commit()

    jd_ver_id = str(jd_ver.id)
    process_job_description_version(db, jd_ver.id)
    jd_id = str(jd.id)
    db.close()

    # 1. Directly fetch markdown without separate enrich button: should give markdown (deterministic fallback)
    r_md = client.get(f"/api/jds/{jd_id}/markdown")
    assert r_md.status_code == 200
    assert r_md.json()["specification_version"] == 1
    assert r_md.json()["is_enriched"] is False  # Ollama offline -> deterministic rule engine JD

    # 2. Check ambiguities & clarification questions
    r_clar = client.get(f"/api/jds/{jd_id}/clarifications")
    assert r_clar.status_code == 200
    clar_data = r_clar.json()
    assert clar_data["jd_id"] == jd_id
    assert "questions" in clar_data
    assert "blocking_unresolved" in clar_data

    # 3. TA answers questions
    answers = {}
    for q in clar_data["questions"]:
        answers[q["question_key"]] = "Confirmed by TA: verified and finalized."

    r_resolve = client.post(
        f"/api/jds/{jd_id}/clarifications/resolve",
        json={"answers": answers, "answered_by": "Senior TA Lead"},
    )
    assert r_resolve.status_code in (200, 202)
    if r_resolve.status_code == 200:
        res_data = r_resolve.json()
        assert res_data["specification_version"] == 2
        assert "markdown" in res_data
        assert "json" in res_data
        assert res_data["status"] in {"finalized", "updated"}
    else:
        task = client.get(f"/api/jds/{jd_id}/tasks/resolve").json()
        assert task["status"] == "done"

    # 4. Verify version 2 is now latest in database
    db3 = SessionLocal()
    spec_v2 = (
        db3.query(JobSpecificationVersion)
        .filter_by(job_description_version_id=jd_ver_id, specification_version=2)
        .first()
    )
    assert spec_v2 is not None
    assert spec_v2.specification_version == 2
    db3.close()


def test_worker_ollama_timeout_fallback(setup_db, monkeypatch):
    """Verify worker falls back cleanly to deterministic baseline when Ollama times out."""
    from app.services.enrichment.ta_enrichment_service import GroundedEnrichmentService

    monkeypatch.setattr(GroundedEnrichmentService, "check_ollama_available", lambda self, timeout=3.0: True)

    def mock_timeout(self, s, u):
        raise RuntimeError("Ollama inference timed out after 300s")

    monkeypatch.setattr(GroundedEnrichmentService, "_call_ollama", mock_timeout)

    db = SessionLocal()
    project_id = setup_db["project_id"]
    jd = JobDescription(project_id=project_id, title="Timeout Test Engineer")
    db.add(jd)
    db.commit()

    raw_text = "Job Title: Timeout Test Engineer\nRequirements:\n- 3+ years Python\nResponsibilities:\n- Build APIs\n"
    storage = get_storage()
    raw_key = build_key(project_id, jd.id, 1, "raw")
    storage.put_text(raw_key, raw_text, "text/plain")

    jd_ver = JobDescriptionVersion(
        job_description_id=jd.id,
        version=1,
        s3_raw_key=raw_key,
        raw_text_checksum="checksum_timeout_01",
    )
    db.add(jd_ver)
    db.commit()

    process_job_description_version(db, jd_ver.id)

    spec = db.query(JobSpecificationVersion).filter_by(job_description_version_id=jd_ver.id).first()
    assert spec is not None
    assert spec.s3_enriched_markdown_key is None
    assert spec.enrichment_report_json is None

    # Endpoint returns deterministic baseline
    r = client.get(f"/api/jds/{jd.id}/markdown")
    assert r.status_code == 200
    assert r.json()["is_enriched"] is False
    assert "[AI Guidance — Evaluator Aid]" not in r.json()["markdown"]
    db.close()


def test_worker_ollama_crash_fallback(setup_db, monkeypatch):
    """Verify worker falls back cleanly to deterministic baseline on unexpected Ollama crash."""
    from app.services.enrichment.ta_enrichment_service import GroundedEnrichmentService

    monkeypatch.setattr(GroundedEnrichmentService, "check_ollama_available", lambda self, timeout=3.0: True)

    def mock_crash(self, s, u):
        raise RuntimeError("Ollama 500 internal server error")

    monkeypatch.setattr(GroundedEnrichmentService, "_call_ollama", mock_crash)

    db = SessionLocal()
    project_id = setup_db["project_id"]
    jd = JobDescription(project_id=project_id, title="Crash Test Engineer")
    db.add(jd)
    db.commit()

    raw_text = "Job Title: Crash Test Engineer\nRequirements:\n- 3+ years C++\nResponsibilities:\n- Build systems\n"
    storage = get_storage()
    raw_key = build_key(project_id, jd.id, 1, "raw")
    storage.put_text(raw_key, raw_text, "text/plain")

    jd_ver = JobDescriptionVersion(
        job_description_id=jd.id,
        version=1,
        s3_raw_key=raw_key,
        raw_text_checksum="checksum_crash_01",
    )
    db.add(jd_ver)
    db.commit()

    process_job_description_version(db, jd_ver.id)

    spec = db.query(JobSpecificationVersion).filter_by(job_description_version_id=jd_ver.id).first()
    assert spec is not None
    assert spec.s3_enriched_markdown_key is None

    r = client.get(f"/api/jds/{jd.id}/markdown")
    assert r.status_code == 200
    assert r.json()["is_enriched"] is False
    db.close()


def test_worker_ollama_success_output_priority(setup_db, monkeypatch):
    """Verify worker produces enriched markdown as primary output when Ollama succeeds, preserving baseline."""
    from app.services.enrichment.ta_enrichment_service import GroundedEnrichmentService

    monkeypatch.setattr(GroundedEnrichmentService, "check_ollama_available", lambda self, timeout=3.0: True)

    db = SessionLocal()
    project_id = setup_db["project_id"]
    jd = JobDescription(project_id=project_id, title="Priority Test Engineer")
    db.add(jd)
    db.commit()

    raw_text = "Job Title: Priority Test Engineer\nRequirements:\n- 4+ years of Kubernetes operator development in Go\nResponsibilities:\n- Scale clusters\n"
    storage = get_storage()
    raw_key = build_key(project_id, jd.id, 1, "raw")
    storage.put_text(raw_key, raw_text, "text/plain")

    jd_ver = JobDescriptionVersion(
        job_description_id=jd.id,
        version=1,
        s3_raw_key=raw_key,
        raw_text_checksum="checksum_priority_01",
    )
    db.add(jd_ver)
    db.commit()

    def mock_success(self, s, u):
        import re
        req_ids = re.findall(r"ID:\s*([a-zA-Z0-9_\-]+)", u)
        items = []
        for rid in req_ids:
            items.append({
                "requirement_id": rid,
                "technical_concept_summary": "Kubernetes Custom Resource Definitions and controller loops.",
                "strong_evidence_signals": ["Writing reconciliation loops with client-go"],
                "weak_or_ambiguous_signals": ["Using kubectl commands only"],
                "screening_question": "How do you handle controller requeue backoff?",
            })
        return json.dumps({"items": items})

    monkeypatch.setattr(GroundedEnrichmentService, "_call_ollama", mock_success)

    process_job_description_version(db, jd_ver.id)

    spec = db.query(JobSpecificationVersion).filter_by(job_description_version_id=jd_ver.id).first()
    assert spec is not None
    assert spec.s3_enriched_markdown_key is not None
    assert spec.enrichment_report_json is not None

    # Default GET /markdown MUST be enriched (Priority 1)
    r_default = client.get(f"/api/jds/{jd.id}/markdown")
    assert r_default.status_code == 200
    assert r_default.json()["is_enriched"] is True
    assert "[AI Guidance — Evaluator Aid]" in r_default.json()["markdown"]

    # Explicit ?enriched=false MUST be baseline
    r_base = client.get(f"/api/jds/{jd.id}/markdown?enriched=false")
    assert r_base.status_code == 200
    assert r_base.json()["is_enriched"] is False
    assert "[AI Guidance — Evaluator Aid]" not in r_base.json()["markdown"]

    db.close()


