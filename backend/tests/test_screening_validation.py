"""Regression tests for independent screening validation packets and metrics."""
from __future__ import annotations

import json

import pytest

from scripts.validate_screening import prepare, report


def test_packet_hides_predictions_and_reports_qualified_cases_lost_to_parsing(tmp_path):
    spec = {"title": "Backend Engineer", "must_have_requirements": ["Python"]}
    resume = "Projects\nBuilt a Python tool for quality checks and documented the reporting process.\n"
    baseline = prepare([
        {"id": "case-1", "spec": spec, "format": "txt", "text": resume, "review_text": resume, "parse": "EXTRACTED"},
        {"id": "case-2", "spec": spec, "format": "pdf", "text": "", "review_text": resume, "parse": "PARSE_FAILED"},
        {"id": "case-3", "spec": spec, "format": "docx", "text": resume, "review_text": resume, "parse": "EXTRACTED",
         "group": "Private subgroup"},
    ], tmp_path, "synthetic")
    html = (tmp_path / "reviewer.html").read_text(encoding="utf-8")
    payload = html.split('id="packet">', 1)[1].split("</script>", 1)[0]
    parsed = json.loads(payload)
    assert "Private subgroup" not in html
    assert all("score" not in case for case in parsed["cases"])

    def review(reviewer, decision):
        return {
            "dataset_id": baseline["dataset_id"], "reviewer": reviewer,
            "labels": {f"case-{i}": {"advance": advance, "grades": {"must_have-1": "MET"}}
                       for i, advance in enumerate(decision, 1)},
        }

    a = review("Test reviewer A", (True, True, True))
    b = review("Test reviewer B", (True, True, False))
    result = report(baseline, a, b)
    assert result["reviewer_decision_agreement"]["exact_agreement"] == 0.6667
    assert result["parse_and_review_outcomes_by_format"]["pdf"] == {"PARSE_FAILED": 1}
    assert result["qualified_ranked_too_low"] == [{"case_id": "case-2", "status": "PARSE_FAILED", "score": None}]
    assert result["qualified_in_shortlist_rate"] == 0.5
    assert result["criteria"][0]["evaluator_vs_reviewer_consensus"]["count"] == 2
    assert result["validation_groups"]["Private subgroup"] == {"cases": 1, "outcomes_suppressed": True}
    with pytest.raises(ValueError, match="distinct reviewer identifiers"):
        report(baseline, a, a)
    with pytest.raises(ValueError, match="match this packet"):
        report(baseline, a, {**b, "dataset_id": "another-packet"})
