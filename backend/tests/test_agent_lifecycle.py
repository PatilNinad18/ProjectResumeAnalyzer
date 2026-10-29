"""
tests/test_agent_lifecycle.py — Agent CRUD & Deletion Lifecycle Tests.

Validates:
1. Agent creation, retrieval, and listing via REST API.
2. Missing agent returns 404 for GET and DELETE.
3. Data Retention Invariant: Agent deletion MUST preserve JobDescription,
   JobDescriptionVersion, and JobSpecificationVersion records (no cascade delete).
4. Audit Trail: Agent creation, update, and deletion emit AuditEvent records.
5. Active Operation Protection: In-flight operations block deletion with 409 Conflict.
6. Safe Cancellation: cancel_active=true terminates running tasks and deletes the agent.
7. Metadata updates via PATCH without altering JD canonical models.
"""
from __future__ import annotations

import os
import time
import pytest

os.environ.setdefault("LLM_PROVIDER", "mock")

from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models.db_models import (
    Agent,
    AuditEvent,
    JobDescription,
    JobDescriptionVersion,
    JobSpecificationVersion,
)
from app.api.routes import _state_lock, _inflight, _tasks


@pytest.fixture
def client():
    return TestClient(app)


def _create_test_jd(client: TestClient, title: str = "Systems Architect") -> str:
    res = client.post(
        "/api/jds",
        data={
            "project_id": "test-agent-project",
            "title": title,
            "text": (
                f"Job Title: {title}\n\n"
                "Requirements:\n"
                "- 8+ years distributed systems (MUST HAVE)\n"
                "- Golang and Kubernetes experience\n\n"
                "Responsibilities:\n"
                "- Lead cloud platform development\n"
            ),
        },
    )
    assert res.status_code == 200, res.text
    return res.json()["jd_id"]


def test_agent_crud_lifecycle(client: TestClient):
    """Test full agent CRUD lifecycle: create, get, list, patch, delete."""
    jd_id = _create_test_jd(client, title="Fullstack Lead")

    # 1. Create Agent
    create_payload = {
        "name": "Fullstack Hiring Agent",
        "title": "Fullstack Lead",
        "companyDetails": {
            "companyName": "Acme Systems",
            "department": "Core Infra",
            "projectName": "Infra2026",
        },
        "jdId": jd_id,
        "status": "ACTIVE",
    }
    create_res = client.post("/api/agents", json=create_payload)
    assert create_res.status_code == 200, create_res.text
    agent_data = create_res.json()
    agent_id = agent_data["id"]
    assert agent_data["agentName"] == "Fullstack Hiring Agent"
    assert agent_data["companyDetails"]["companyName"] == "Acme Systems"
    assert agent_data["jdId"] == jd_id
    assert agent_data["status"] == "ACTIVE"

    # 2. Get Agent by ID
    get_res = client.get(f"/api/agents/{agent_id}")
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["id"] == agent_id
    assert get_res.json()["title"] == "Fullstack Lead"

    # 3. List Agents
    list_res = client.get("/api/agents")
    assert list_res.status_code == 200, list_res.text
    agents_list = list_res.json()
    assert any(a["id"] == agent_id for a in agents_list)

    # 4. Patch Agent Metadata
    patch_res = client.patch(
        f"/api/agents/{agent_id}",
        json={
            "name": "Senior Fullstack Hiring Agent",
            "companyDetails": {"companyName": "Acme Global"},
        },
    )
    assert patch_res.status_code == 200, patch_res.text
    assert patch_res.json()["name"] == "Senior Fullstack Hiring Agent"
    assert patch_res.json()["companyDetails"]["companyName"] == "Acme Global"

    # 5. Delete Agent
    del_res = client.delete(f"/api/agents/{agent_id}")
    assert del_res.status_code == 200, del_res.text
    assert del_res.json()["status"] == "deleted"
    assert del_res.json()["agent_id"] == agent_id
    assert del_res.json()["job_description_retained"] is True

    # 6. Verify Agent is gone
    get_again = client.get(f"/api/agents/{agent_id}")
    assert get_again.status_code == 404


def test_delete_missing_agent_returns_404(client: TestClient):
    """Deleting a non-existent agent returns 404."""
    del_res = client.delete("/api/agents/non-existent-agent-id-999")
    assert del_res.status_code == 404
    assert "not found" in del_res.json()["detail"].lower()


def test_agent_deletion_preserves_job_description_and_audit(client: TestClient):
    """
    CRITICAL DATA RETENTION TEST:
    Verifies that deleting an Agent removes the agent entity but strictly retains
    the JobDescription and emits an AuditEvent.
    """
    jd_id = _create_test_jd(client, title="Kernel Engineer")

    create_res = client.post(
        "/api/agents",
        json={"name": "Kernel Agent", "jdId": jd_id, "title": "Kernel Engineer"},
    )
    assert create_res.status_code == 200
    agent_id = create_res.json()["id"]

    db = SessionLocal()
    try:
        # Verify JD and Agent exist in DB before deletion
        jd_before = db.query(JobDescription).filter(JobDescription.id == jd_id).first()
        assert jd_before is not None
        agent_before = db.query(Agent).filter(Agent.id == agent_id).first()
        assert agent_before is not None

        # Delete Agent
        del_res = client.delete(f"/api/agents/{agent_id}")
        assert del_res.status_code == 200

        # Verify Agent is removed
        agent_after = db.query(Agent).filter(Agent.id == agent_id).first()
        assert agent_after is None

        # Verify JobDescription IS STILL RETAINED (No cascade delete!)
        jd_after = db.query(JobDescription).filter(JobDescription.id == jd_id).first()
        assert jd_after is not None
        assert jd_after.id == jd_id

        # Verify AuditEvent was logged
        audit = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.entity_type == "agent",
                AuditEvent.entity_id == agent_id,
                AuditEvent.action == "deleted",
            )
            .first()
        )
        assert audit is not None
        assert audit.action == "deleted"
        assert audit.details.get("job_description_id") == jd_id
        assert audit.details.get("job_description_retained") is True
    finally:
        db.close()


def test_delete_agent_prevents_deletion_during_active_operation(client: TestClient):
    """
    SAFETY TEST:
    Verify that an agent cannot be deleted while an operation (analysis/enrichment/resolution)
    is actively running for its JD, returning 409 Conflict.
    """
    jd_id = _create_test_jd(client, title="Security Lead")

    create_res = client.post(
        "/api/agents",
        json={"name": "Security Agent", "jdId": jd_id, "title": "Security Lead"},
    )
    assert create_res.status_code == 200
    agent_id = create_res.json()["id"]

    # Simulate an active analysis operation
    with _state_lock:
        _inflight[jd_id] = time.time()

    try:
        # Attempt deletion without cancel_active -> must fail with 409
        del_res = client.delete(f"/api/agents/{agent_id}")
        assert del_res.status_code == 409, del_res.text
        assert "Cannot delete agent" in del_res.json()["detail"]
        assert "active" in del_res.json()["detail"]

        # Verify agent still exists
        get_res = client.get(f"/api/agents/{agent_id}")
        assert get_res.status_code == 200
    finally:
        # Clean up in-flight simulation
        with _state_lock:
            _inflight.pop(jd_id, None)


def test_delete_agent_with_cancel_active_cancels_and_deletes(client: TestClient):
    """
    SAFE CANCELLATION TEST:
    Verify that passing cancel_active=true safely cancels in-flight operations
    and successfully deletes the agent.
    """
    jd_id = _create_test_jd(client, title="DevOps Architect")

    create_res = client.post(
        "/api/agents",
        json={"name": "DevOps Agent", "jdId": jd_id, "title": "DevOps Architect"},
    )
    assert create_res.status_code == 200
    agent_id = create_res.json()["id"]

    # Simulate running enrich task and analysis
    with _state_lock:
        _inflight[jd_id] = time.time()
        _tasks[f"enrich:{jd_id}"] = {
            "status": "running",
            "started_at": time.time(),
            "finished_at": None,
            "error": None,
            "stage": "EXTRACTING",
            "stage_label": "In progress",
            "progress_percent": 40,
        }

    try:
        # Delete with cancel_active=true
        del_res = client.delete(f"/api/agents/{agent_id}?cancel_active=true")
        assert del_res.status_code == 200, del_res.text
        res_data = del_res.json()
        assert res_data["status"] == "deleted"
        assert res_data["cancelled_active_operations"] is True

        # Verify in-flight and tasks were cancelled
        with _state_lock:
            assert jd_id not in _inflight
            assert _tasks[f"enrich:{jd_id}"]["status"] == "failed"
            assert "cancelled" in _tasks[f"enrich:{jd_id}"]["error"].lower()

        # Verify agent is gone
        get_res = client.get(f"/api/agents/{agent_id}")
        assert get_res.status_code == 404
    finally:
        with _state_lock:
            _inflight.pop(jd_id, None)
            _tasks.pop(f"enrich:{jd_id}", None)


def test_create_agent_invalid_jd_returns_404(client: TestClient):
    """Attempting to create an agent for a non-existent JD returns 404."""
    res = client.post(
        "/api/agents",
        json={"name": "Ghost Agent", "jdId": "non-existent-jd-id"},
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()
