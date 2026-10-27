"""
tests/test_context_comparison.py — Tests for Feature 1: JD Context Comparison.

Verifies:
1. Comparison between Baseline, Enriched, and Ambiguity-Resolved contexts.
2. Accurate classification of requirements into Added, Removed, Modified, and Unchanged.
3. Strict distinction between Source Evidence (verbatim quotes) and TA-Confirmed Facts.
4. Resolved vs Unresolved ambiguities breakdown.
5. Robust fallback handling when historical versions are missing.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from app.services.comparison_service import (
    _extract_provenance_info,
    compute_context_diff,
    build_comparison_payload,
)


def test_provenance_info_distinguishes_source_evidence_and_ta_facts():
    # 1. Source Evidence requirement (from raw JD)
    explicit_req = {
        "text": "5+ years C programming experience",
        "provenance": {
            "origin_type": "EXPLICIT_JD",
            "source_span": {
                "raw_text": "5+ years C programming experience",
                "section": "Requirements",
            },
        },
    }
    explicit_info = _extract_provenance_info(explicit_req)
    assert explicit_info["provenance_type"] == "source_evidence"
    assert "Source Evidence" in explicit_info["provenance_badge"]
    assert explicit_info["source_section"] == "Requirements"
    assert explicit_info["source_text"] == "5+ years C programming experience"

    # 2. TA-Confirmed Fact requirement (clarified by TA)
    ta_req = {
        "text": "PCB design knowledge is confirmed MUST HAVE",
        "provenance": {
            "origin_type": "TA_CONFIRMED",
            "author": "recruiter_jane",
            "timestamp": "2026-10-27T10:00:00Z",
        },
    }
    ta_info = _extract_provenance_info(ta_req)
    assert ta_info["provenance_type"] == "ta_confirmed"
    assert "TA-Confirmed Fact" in ta_info["provenance_badge"]
    assert ta_info["author"] == "recruiter_jane"

    # 3. LLM Hypothesis requirement (enrichment guidance)
    llm_req = {
        "text": "Embedded RTOS kernel internals",
        "provenance": {
            "origin_type": "LLM_HYPOTHESIS",
        },
    }
    llm_info = _extract_provenance_info(llm_req)
    assert llm_info["provenance_type"] == "llm_hypothesis"
    assert "AI Guidance" in llm_info["provenance_badge"]


def test_compute_context_diff_detects_added_removed_modified_unchanged():
    base_reqs = [
        {
            "id": "req_1",
            "text": "5+ years embedded C",
            "priority": "MUST_HAVE",
            "provenance_type": "source_evidence",
            "provenance_badge": "Source Evidence (Verbatim JD)",
        },
        {
            "id": "req_2",
            "text": "Experience with FreeRTOS",
            "priority": "MUST_HAVE",
            "provenance_type": "source_evidence",
            "provenance_badge": "Source Evidence (Verbatim JD)",
        },
        {
            "id": "req_3",
            "text": "PCB layout design",
            "priority": "UNRESOLVED",
            "provenance_type": "source_evidence",
            "provenance_badge": "Source Evidence (Verbatim JD)",
        },
        {
            "id": "req_4",
            "text": "Assembly language debugging",
            "priority": "PREFERRED",
            "provenance_type": "source_evidence",
            "provenance_badge": "Source Evidence (Verbatim JD)",
        },
    ]

    # Target (Resolved):
    # - req_1: unchanged
    # - req_2: unchanged
    # - req_3: modified (priority upgraded to MUST_HAVE, provenance upgraded to TA_CONFIRMED)
    # - req_4: removed (not in target)
    # - req_5: added (new TA confirmed requirement)
    target_reqs = [
        {
            "id": "req_1",
            "text": "5+ years embedded C",
            "priority": "MUST_HAVE",
            "provenance_type": "source_evidence",
            "provenance_badge": "Source Evidence (Verbatim JD)",
        },
        {
            "id": "req_2",
            "text": "Experience with FreeRTOS",
            "priority": "MUST_HAVE",
            "provenance_type": "source_evidence",
            "provenance_badge": "Source Evidence (Verbatim JD)",
        },
        {
            "id": "req_3",
            "text": "PCB layout design",
            "priority": "MUST_HAVE",
            "provenance_type": "ta_confirmed",
            "provenance_badge": "TA-Confirmed Fact",
            "author": "lead_ta",
        },
        {
            "id": "req_5",
            "text": "Hardware lab test equipment (Oscilloscopes)",
            "priority": "MUST_HAVE",
            "provenance_type": "ta_confirmed",
            "provenance_badge": "TA-Confirmed Fact",
            "author": "lead_ta",
        },
    ]

    diff = compute_context_diff(base_reqs, target_reqs, "baseline", "resolved")

    # 1. Unchanged
    assert len(diff["unchanged"]) == 2
    unchanged_ids = [r["id"] for r in diff["unchanged"]]
    assert "req_1" in unchanged_ids
    assert "req_2" in unchanged_ids

    # 2. Modified
    assert len(diff["modified"]) == 1
    mod = diff["modified"][0]
    assert mod["id"] == "req_3"
    assert mod["base_priority"] == "UNRESOLVED"
    assert mod["target_priority"] == "MUST_HAVE"
    assert any("Priority changed" in c for c in mod["changes"])
    assert any("Status changed" in c for c in mod["changes"])

    # 3. Added
    assert len(diff["added"]) == 1
    added = diff["added"][0]
    assert added["id"] == "req_5"
    assert added["diff_status"] == "added"
    assert added["diff_badge"] == "+ Added"

    # 4. Removed
    assert len(diff["removed"]) == 1
    removed = diff["removed"][0]
    assert removed["id"] == "req_4"
    assert removed["diff_status"] == "removed"
    assert removed["diff_badge"] == "- Removed"

    # 5. Counts
    counts = diff["counts"]
    assert counts["total_base"] == 4
    assert counts["total_target"] == 4
    assert counts["added"] == 1
    assert counts["removed"] == 1
    assert counts["modified"] == 1
    assert counts["unchanged"] == 2


def test_build_comparison_payload_handles_missing_versions_gracefully():
    # Mock DB session where no specifications exist
    db_mock = MagicMock()
    db_mock.query.return_value.join.return_value.filter.return_value.order_by.return_value.all.return_value = []

    res = build_comparison_payload("non_existent_jd", db_mock)
    assert res["jd_id"] == "non_existent_jd"
    assert res["has_baseline"] is False
    assert res["has_enriched"] is False
    assert res["has_resolved"] is False
    assert "No specifications" in res["message"]


def test_build_comparison_payload_with_single_baseline_version():
    spec_v1 = MagicMock()
    spec_v1.specification_version = 1
    spec_v1.created_at = None
    spec_v1.s3_markdown_key = "key_v1_md"
    spec_v1.s3_enriched_markdown_key = None
    spec_v1.enrichment_report_json = None
    spec_v1.lifecycle_status = "ANALYZED"
    spec_v1.master_context_json = {
        "requirements": [
            {
                "id": "r1",
                "text": "3+ years Python",
                "priority": "MUST_HAVE",
                "provenance": {"origin_type": "EXPLICIT_JD"},
            }
        ],
        "clarification_history": [
            {
                "question_key": "salary_q",
                "question_text": "Is salary range available?",
                "status": "UNANSWERED",
                "priority": "OPTIONAL",
                "is_blocking": False,
            }
        ],
    }
    spec_v1.canonical_json = {
        "must_have_requirements": ["3+ years Python"],
        "preferred_requirements": [],
    }

    db_mock = MagicMock()
    db_mock.query.return_value.join.return_value.filter.return_value.order_by.return_value.all.return_value = [spec_v1]

    payload = build_comparison_payload("test_jd_single", db_mock, base_context="baseline")

    assert payload["jd_id"] == "test_jd_single"
    assert payload["has_baseline"] is True
    assert payload["has_enriched"] is False
    assert payload["has_resolved"] is False
    assert payload["contexts"]["baseline"]["requirements_count"] == 1
    assert len(payload["diff"]["unchanged"]) == 1
    assert payload["ambiguities"]["counts"]["unresolved"] == 1
    assert payload["ambiguities"]["counts"]["resolved"] == 0
