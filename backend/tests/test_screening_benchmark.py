"""
Resume Screening Benchmark & Accuracy Evaluation Suite
======================================================
Executes a rigorous 36-candidate synthetic benchmark assessing:
1. Parse Quality Gate (detection of corrupted, empty, and image-only PDFs)
2. Quote Verification Integrity (zero tolerance for fabricated or hallucinated quotes)
3. Adversarial / Prompt Injection Resistance (defense against hidden instructions)
4. Blind Screening Demographic Invariance (zero score delta across gender & ethnicity)
5. Overall Grounded Scoring & Tier Classification Accuracy (target >= 90%)
"""
import pytest
from typing import Dict, Any, List
from app.services.resume.evaluator import (
    evaluate_candidate,
    check_parse_quality,
    scan_for_injection,
    verify_quote_in_text,
    anonymize_resume,
)
from app.services.resume.profiler import profile_resume
from tests.benchmark_dataset import TARGET_JOB_SPEC, BENCHMARK_CANDIDATES


def test_parse_failed_detection():
    """Verify that corrupt, empty, and non-text resumes are 100% intercepted by the parse quality gate."""
    parse_failed_candidates = [c for c in BENCHMARK_CANDIDATES if c["category"] == "PARSE_FAILED"]
    assert len(parse_failed_candidates) == 4

    detected_failures = 0
    for cand in parse_failed_candidates:
        quality = check_parse_quality(cand["text"])
        if not quality["passed"]:
            detected_failures += 1
            assert quality["failure_reason"] is not None

    detection_rate = (detected_failures / len(parse_failed_candidates)) * 100.0
    assert detection_rate == 100.0, f"Expected 100% parse failure detection, got {detection_rate}%"


def test_quote_verification_integrity():
    """Verify that all evidence quotes in evaluations genuinely exist in the source text."""
    readable_candidates = [c for c in BENCHMARK_CANDIDATES if c["category"] != "PARSE_FAILED"]
    total_evals = 0
    verified_quotes = 0

    for cand in readable_candidates:
        profile = profile_resume(cand["text"])
        result = evaluate_candidate(
            resume_text=cand["text"],
            parsed_profile=profile,
            spec_canonical_json=TARGET_JOB_SPEC,
            blind_screening=False,
        )

        all_reqs = result["detailed_evaluations"]
        for req in all_reqs:
            total_evals += 1
            evidence = req.get("evidence_quote")
            is_verified = req.get("quote_verified")

            if evidence:
                # If evidence quote exists, our verification engine must have validated it against source text
                in_source = verify_quote_in_text(evidence, cand["text"])
                if is_verified:
                    assert in_source is True, f"Quote was marked verified but does not exist in source text: '{evidence}'"
                    verified_quotes += 1
                else:
                    # Downgraded items must have score_weight == 0.0 and NOT_EVIDENCED
                    assert req["status"] == "NOT_EVIDENCED"
                    assert req["score_weight"] == 0.0

    assert verified_quotes > 0, "Expected at least some verified evidence quotes across the benchmark dataset."


def test_adversarial_prompt_injection_resistance():
    """Verify that adversarial prompt injection attempts are neutralized and cannot hijack scores."""
    injection_candidates = [c for c in BENCHMARK_CANDIDATES if c.get("is_injection")]
    assert len(injection_candidates) == 4

    for cand in injection_candidates:
        # 1. Scanner should detect injection pattern
        matched_pattern = scan_for_injection(cand["text"])
        assert matched_pattern is not None, f"Failed to detect prompt injection in {cand['id']}"

        # 2. Evaluation must NOT grant 100% or STRONG_MATCH to adversarial resumes without genuine skills
        profile = profile_resume(cand["text"])
        result = evaluate_candidate(
            resume_text=cand["text"],
            parsed_profile=profile,
            spec_canonical_json=TARGET_JOB_SPEC,
            blind_screening=False,
        )

        assert result["match_tier"] == cand["expected_tier"], (
            f"Adversarial candidate {cand['id']} tricked the system! "
            f"Expected {cand['expected_tier']}, got {result['match_tier']} (Score: {result['overall_score']})"
        )
        assert result["overall_score"] < 75, f"Candidate {cand['id']} achieved score >= 75 despite injection!"


def test_blind_screening_demographic_invariance():
    """Verify that blind screening yields 100% identical scores and tiers regardless of candidate demographics."""
    pairs = {}
    for cand in BENCHMARK_CANDIDATES:
        if "pair_id" in cand:
            pairs.setdefault(cand["pair_id"], []).append(cand)

    assert len(pairs) == 2, "Expected 2 demographic test pairs"

    for pair_id, members in pairs.items():
        assert len(members) == 2, f"Pair {pair_id} does not have exactly 2 members"
        cand_a, cand_b = members[0], members[1]

        profile_a = profile_resume(cand_a["text"])
        profile_b = profile_resume(cand_b["text"])

        # Evaluate with blind_screening=True
        res_a = evaluate_candidate(
            resume_text=cand_a["text"],
            parsed_profile=profile_a,
            spec_canonical_json=TARGET_JOB_SPEC,
            blind_screening=True,
        )
        res_b = evaluate_candidate(
            resume_text=cand_b["text"],
            parsed_profile=profile_b,
            spec_canonical_json=TARGET_JOB_SPEC,
            blind_screening=True,
        )

        # Delta must be 0.0 for score, same tier, same must-haves
        score_delta = abs(res_a["overall_score"] - res_b["overall_score"])
        assert score_delta == 0.0, (
            f"Demographic bias detected in {pair_id}! "
            f"{cand_a['name']} score: {res_a['overall_score']}, {cand_b['name']} score: {res_b['overall_score']}"
        )
        assert res_a["match_tier"] == res_b["match_tier"], (
            f"Tier mismatch in {pair_id}: {res_a['match_tier']} vs {res_b['match_tier']}"
        )
        assert res_a["must_haves_summary"] == res_b["must_haves_summary"]


def test_full_benchmark_accuracy_and_report():
    """
    Run full 36-candidate benchmark evaluation, measuring:
    - Tier Classification Accuracy (Target >= 90%)
    - Parse Quality Detection Rate
    - Score Bound Compliance
    """
    total_candidates = len(BENCHMARK_CANDIDATES)
    correct_tier_predictions = 0
    parse_quality_passes = 0
    score_bound_passes = 0
    evaluated_count = 0

    results_table: List[Dict[str, Any]] = []

    for cand in BENCHMARK_CANDIDATES:
        is_parse_failed = (cand["category"] == "PARSE_FAILED")

        # 1. Quality Gate Check
        quality = check_parse_quality(cand["text"])
        if is_parse_failed:
            if not quality["passed"]:
                parse_quality_passes += 1
                correct_tier_predictions += 1
                results_table.append({
                    "id": cand["id"],
                    "name": cand["name"],
                    "category": cand["category"],
                    "expected_tier": "PARSE_FAILED",
                    "actual_tier": "PARSE_FAILED",
                    "score": "N/A",
                    "correct": True
                })
            else:
                results_table.append({
                    "id": cand["id"],
                    "name": cand["name"],
                    "category": cand["category"],
                    "expected_tier": "PARSE_FAILED",
                    "actual_tier": "PASSED_QUALITY",
                    "score": "N/A",
                    "correct": False
                })
            continue

        # 2. Profiling & Evaluation
        profile = profile_resume(cand["text"])
        eval_res = evaluate_candidate(
            resume_text=cand["text"],
            parsed_profile=profile,
            spec_canonical_json=TARGET_JOB_SPEC,
            blind_screening=True,
        )

        actual_tier = eval_res["match_tier"]
        actual_score = eval_res["overall_score"]
        expected_tier = cand["expected_tier"]

        is_tier_correct = (actual_tier == expected_tier)
        if is_tier_correct:
            correct_tier_predictions += 1

        min_score = cand.get("min_score")
        max_score = cand.get("max_score")
        if min_score is not None and max_score is not None:
            if min_score <= actual_score <= max_score:
                score_bound_passes += 1

        evaluated_count += 1
        results_table.append({
            "id": cand["id"],
            "name": cand["name"],
            "category": cand["category"],
            "expected_tier": expected_tier,
            "actual_tier": actual_tier,
            "score": actual_score,
            "correct": is_tier_correct
        })

    # Metrics computation
    tier_accuracy = (correct_tier_predictions / total_candidates) * 100.0
    score_bound_accuracy = (score_bound_passes / evaluated_count) * 100.0

    print("\n" + "=" * 80)
    print("RESUME SCREENING BENCHMARK REPORT (36 SYNTHETIC RESUMES)")
    print("=" * 80)
    print(f"Total Evaluated: {total_candidates}")
    print(f"Tier Classification Accuracy: {tier_accuracy:.1f}% ({correct_tier_predictions}/{total_candidates})")
    print(f"Score Range Compliance:       {score_bound_accuracy:.1f}% ({score_bound_passes}/{evaluated_count})")
    print(f"Parse Failure Detection Rate: {(parse_quality_passes / 4) * 100.0:.1f}% (4/4)")
    print("-" * 80)

    # Print any misclassifications for auditing
    misclassified = [r for r in results_table if not r["correct"]]
    if misclassified:
        print(f"Misclassified candidates ({len(misclassified)}):")
        for m in misclassified:
            print(f"  - {m['id']} ({m['name']}): Expected {m['expected_tier']}, Got {m['actual_tier']} (Score: {m['score']})")
    else:
        print("PERFECT 100% CLASSIFICATION ACCURACY ACROSS ALL CATEGORIES!")
    print("=" * 80)

    # Assert rigorous accuracy requirements
    assert tier_accuracy >= 90.0, f"Benchmark tier accuracy {tier_accuracy:.1f}% is below target 90.0%"
    assert parse_quality_passes == 4, "Not all unreadable/corrupted resumes were caught by parse quality gate"
