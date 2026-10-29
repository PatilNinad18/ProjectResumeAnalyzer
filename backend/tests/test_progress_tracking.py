"""
Tests for JD Analysis Progress Tracking, Cancellation, and Multi-JD Isolation.

Validates:
1. Progress starts, updates through actual stages, and is monotonic.
2. Progress reaches 100% only upon operation success (never during in-flight steps).
3. Cancellation cleanly halts operations and marks CANCELLED.
4. Failures capture error messages without reaching 100%.
5. Multiple concurrent JDs maintain strictly isolated progress states.
6. REST API endpoints (/progress, /cancel, /analysis) return correct progress payloads.
"""
from __future__ import annotations

import time
import pytest
from unittest.mock import MagicMock, patch

from app.core.progress import ProgressRegistry, progress_registry


def test_progress_lifecycle_and_monotonicity():
    """Verify progress starts, advances through stages, and reaches 100% only on complete."""
    reg = ProgressRegistry()
    jd_id = "test-jd-progress-1"

    # 1. Start
    p = reg.start_progress(jd_id, "analysis", total_steps=6, initial_stage="PARSING", initial_percent=10)
    assert p.percent == 10
    assert p.stage == "PARSING"
    assert p.finished_at is None
    assert p.cancelled is False

    # 2. Update stage
    p = reg.update_progress(jd_id, "analysis", stage="UNDERSTANDING", message="Extracting requirements", percent=30, current_step=2)
    assert p is not None
    assert p.percent == 30
    assert p.stage == "UNDERSTANDING"
    assert p.current_step == 2

    # 3. Monotonic check: updating with a lower percent does not decrease percent
    p = reg.update_progress(jd_id, "analysis", stage="UNDERSTANDING", message="Still extracting", percent=25)
    assert p.percent == 30  # Should remain 30

    # 4. In-flight update cannot reach 100%
    p = reg.update_progress(jd_id, "analysis", stage="GENERATING", message="Generating context", percent=100)
    assert p.percent == 95  # Capped at 95 until complete_progress

    # 5. Complete
    p = reg.complete_progress(jd_id, "analysis", stage="READY", message="All done")
    assert p is not None
    assert p.percent == 100
    assert p.stage == "READY"
    assert p.finished_at is not None
    assert p.error is None


def test_progress_failure_handling():
    """Verify failed progress records error message and does not reach 100%."""
    reg = ProgressRegistry()
    jd_id = "test-jd-progress-fail"

    reg.start_progress(jd_id, "analysis", total_steps=6, initial_stage="PARSING", initial_percent=10)
    reg.update_progress(jd_id, "analysis", stage="UNDERSTANDING", message="Parsing failed", percent=30)
    
    p = reg.fail_progress(jd_id, "analysis", error_message="Ollama connection refused")
    assert p is not None
    assert p.stage == "FAILED"
    assert "Ollama connection refused" in p.error
    assert p.percent == 30  # Stays at last progress point, does not reach 100%
    assert p.finished_at is not None


def test_progress_cancellation():
    """Verify cooperative cancellation marks cancelled and stops updates."""
    reg = ProgressRegistry()
    jd_id = "test-jd-cancel"

    reg.start_progress(jd_id, "analysis", total_steps=6, initial_stage="PARSING", initial_percent=10)
    assert reg.is_cancelled(jd_id, "analysis") is False

    # Cancel
    cancelled = reg.cancel_progress(jd_id, "analysis", reason="User clicked cancel")
    assert cancelled is True
    assert reg.is_cancelled(jd_id, "analysis") is True

    p = reg.get_progress(jd_id, "analysis")
    assert p is not None
    assert p["cancelled"] is True
    assert p["stage"] == "CANCELLED"
    assert "User clicked cancel" in p["message"]

    # Updating cancelled progress should be ignored
    p_after = reg.update_progress(jd_id, "analysis", stage="GENERATING", message="Should not happen", percent=90)
    assert p_after.stage == "CANCELLED"
    assert p_after.percent == 10


def test_multi_jd_isolation_progress():
    """Verify simultaneous multiple JDs have isolated progress states."""
    reg = ProgressRegistry()
    jd1 = "jd-alpha"
    jd2 = "jd-beta"

    # Start both
    reg.start_progress(jd1, "analysis", total_steps=6, initial_stage="PARSING", initial_percent=10)
    reg.start_progress(jd2, "analysis", total_steps=6, initial_stage="PARSING", initial_percent=10)

    # Advance jd1 to 65% (CLARIFYING)
    reg.update_progress(jd1, "analysis", stage="CLARIFYING", message="Clarifying jd1", percent=65)

    # Advance jd2 to 30% (UNDERSTANDING)
    reg.update_progress(jd2, "analysis", stage="UNDERSTANDING", message="Understanding jd2", percent=30)

    p1 = reg.get_progress(jd1, "analysis")
    p2 = reg.get_progress(jd2, "analysis")

    assert p1["percent"] == 65
    assert p1["stage"] == "CLARIFYING"
    assert p2["percent"] == 30
    assert p2["stage"] == "UNDERSTANDING"

    # Cancel only jd2
    reg.cancel_progress(jd2, "analysis")
    assert reg.is_cancelled(jd2, "analysis") is True
    assert reg.is_cancelled(jd1, "analysis") is False

    # Complete jd1 successfully
    reg.complete_progress(jd1, "analysis")
    p1_final = reg.get_progress(jd1, "analysis")
    p2_final = reg.get_progress(jd2, "analysis")

    assert p1_final["percent"] == 100
    assert p1_final["stage"] == "READY"
    assert p2_final["stage"] == "CANCELLED"


def test_progress_api_endpoints():
    """Verify FastAPI routes for progress and cancellation."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    jd_id = "test-api-progress-jd"

    # Clean progress
    progress_registry.clear(jd_id)

    # 1. GET /progress when idle
    res = client.get(f"/api/jds/{jd_id}/progress")
    assert res.status_code == 200
    data = res.json()
    assert data["stage"] == "IDLE"
    assert data["percent"] == 0

    # 2. Simulate start in registry
    progress_registry.start_progress(jd_id, "analysis", total_steps=6, initial_stage="UNDERSTANDING", initial_percent=30)
    res = client.get(f"/api/jds/{jd_id}/progress")
    assert res.status_code == 200
    data = res.json()
    assert data["stage"] == "UNDERSTANDING"
    assert data["percent"] == 30

    # 3. POST /cancel
    cancel_res = client.post(f"/api/jds/{jd_id}/cancel", json={"operation": "analysis"})
    assert cancel_res.status_code == 200
    assert cancel_res.json()["cancelled"] is True

    # 4. Verify progress reflects cancellation
    res_after = client.get(f"/api/jds/{jd_id}/progress")
    assert res_after.status_code == 200
    assert res_after.json()["cancelled"] is True
    assert res_after.json()["stage"] == "CANCELLED"
