"""
tests/test_progress_notifications.py — Tests for Feature 2: Progress Indicators & Notifications.

Verifies:
1. Honest stage-based progress calculations and stage labels for initial JD analysis.
2. 100% is only reported upon confirmed terminal success (READY, NEEDS_REVIEW).
3. In-flight status does not report 100%.
4. Task progress tracking for background ambiguity resolution.
5. Cancellation handlers and error recovery states.
"""
from __future__ import annotations

import pytest
from app.api.routes import (
    _get_analysis_progress,
    _tasks,
    _state_lock,
    _update_task_progress,
    cancel_analysis,
    cancel_task,
    get_task_status,
)


def test_analysis_progress_honest_stages_and_percentages():
    # 1. Non-terminal in-progress stages must never report 100%
    stages_to_test = ["UPLOADED", "PARSING", "UNDERSTANDING", "VALIDATING", "GENERATING"]
    for st in stages_to_test:
        pct, label = _get_analysis_progress(st)
        assert 0 < pct < 100, f"Stage {st} must have an honest intermediate progress percentage, got {pct}"
        assert label, f"Stage {st} must provide a non-empty stage label"

    # Monotonically increasing across stages
    assert _get_analysis_progress("UPLOADED")[0] < _get_analysis_progress("PARSING")[0]
    assert _get_analysis_progress("PARSING")[0] < _get_analysis_progress("UNDERSTANDING")[0]
    assert _get_analysis_progress("UNDERSTANDING")[0] < _get_analysis_progress("VALIDATING")[0]
    assert _get_analysis_progress("VALIDATING")[0] < _get_analysis_progress("GENERATING")[0]

    # 2. Confirmed terminal success states MUST report exactly 100%
    pct_ready, label_ready = _get_analysis_progress("READY")
    assert pct_ready == 100
    assert "complete" in label_ready.lower()

    pct_review, label_review = _get_analysis_progress("NEEDS_REVIEW")
    assert pct_review == 100
    assert "complete" in label_review.lower()

    # 3. Failed terminal state MUST report 0%
    pct_failed, label_failed = _get_analysis_progress("FAILED")
    assert pct_failed == 0
    assert "failed" in label_failed.lower()


def test_task_progress_tracking_and_stages():
    test_key = "resolve:test_jd_prog_123"
    with _state_lock:
        _tasks[test_key] = {
            "status": "running",
            "error": None,
            "started_at": 100.0,
            "finished_at": None,
            "stage": "QUEUED",
            "stage_label": "Queued for execution",
            "progress_percent": 10,
        }

    # Verify initial task status
    status_res = get_task_status("test_jd_prog_123", "resolve")
    assert status_res["status"] == "running"
    assert status_res["stage"] == "QUEUED"
    assert status_res["progress_percent"] == 10

    # Simulate stage updates during ambiguity resolution
    _update_task_progress(test_key, "APPLYING_ANSWERS", "Applying TA answers to requirements", 25)
    s2 = get_task_status("test_jd_prog_123", "resolve")
    assert s2["stage"] == "APPLYING_ANSWERS"
    assert s2["progress_percent"] == 25

    _update_task_progress(test_key, "PROJECTING_SPEC", "Projecting canonical specification v2", 65)
    s3 = get_task_status("test_jd_prog_123", "resolve")
    assert s3["stage"] == "PROJECTING_SPEC"
    assert s3["progress_percent"] == 65

    # Simulate completed resolution
    with _state_lock:
        _tasks[test_key].update(
            status="done",
            stage="DONE",
            stage_label="Ambiguity resolution complete",
            progress_percent=100,
        )

    s_done = get_task_status("test_jd_prog_123", "resolve")
    assert s_done["status"] == "done"
    assert s_done["progress_percent"] == 100
    assert s_done["stage"] == "DONE"


def test_task_cancellation():
    test_key = "resolve:test_cancel_jd"
    with _state_lock:
        _tasks[test_key] = {
            "status": "running",
            "error": None,
            "started_at": 200.0,
            "finished_at": None,
            "stage": "APPLYING_ANSWERS",
            "stage_label": "Applying answers",
            "progress_percent": 30,
        }

    cancel_res = cancel_task("test_cancel_jd", "resolve")
    assert cancel_res["status"] == "cancelled"

    post_cancel = get_task_status("test_cancel_jd", "resolve")
    assert post_cancel["status"] == "failed"
    assert post_cancel["stage"] == "CANCELLED"
    assert post_cancel["progress_percent"] == 0
    assert "cancelled" in post_cancel["error"].lower()
