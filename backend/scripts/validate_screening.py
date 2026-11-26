"""Prepare blinded review packets and compare two independent recruiter reviews."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document_parser import DocumentParseError, parse_document
from app.services.resume.evaluator import (
    EVALUATOR_ENGINE, POTENTIAL_MATCH_THRESHOLD, _extract_requirements_from_spec,
    anonymize_resume, evaluate_candidate, screening_criteria,
)
from app.services.resume.profiler import profile_resume, resume_parse_issue

GRADES = {"MET", "PARTIALLY_MET", "NOT_EVIDENCED"}
MAX_INPUT_BYTES = 10 * 1024 * 1024


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path.name}.")
    return payload


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def digest(data: Any) -> str:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_uploaded_resume(path: Path) -> tuple[str, str]:
    try:
        with path.open("rb") as handle:
            content = handle.read(MAX_INPUT_BYTES + 1)
    except OSError as exc:
        raise ValueError(f"Cannot read input file {path.name}.") from exc
    if len(content) > MAX_INPUT_BYTES:
        raise ValueError(f"Input file {path.name} exceeds the 10 MB upload limit.")
    try:
        return parse_document(path.name, content), "EXTRACTED"
    except DocumentParseError:
        return "", "PARSE_FAILED"


def manifest_cases(manifest: Path):
    payload = read_json(manifest)
    for row in payload.get("cases", []):
        path = manifest.parent / row["resume"]
        spec = read_json(manifest.parent / row["specification"])
        raw_text, status = _load_uploaded_resume(path)
        transcript = row.get("review_transcript")
        review_text = (manifest.parent / transcript).read_text(encoding="utf-8-sig") if transcript else raw_text
        yield {
            "id": row["id"], "format": path.suffix.lower().lstrip("."), "spec": spec, "text": raw_text,
            "review_text": review_text, "parse": status, "group": row.get("validation_group"),
        }


def synthetic_cases():
    from tests.benchmark_dataset import BENCHMARK_CANDIDATES, TARGET_JOB_SPEC

    for row in BENCHMARK_CANDIDATES:
        text = row["text"]
        yield {
            "id": row["id"], "format": "txt", "spec": TARGET_JOB_SPEC, "text": text,
            "review_text": text if row["category"] != "PARSE_FAILED" else "",
            "parse": "EXTRACTED" if text.strip() else "PARSE_FAILED",
        }


def prepare(cases, output: Path, dataset_kind: str) -> dict:
    packets, predictions, jobs, case_ids = [], [], {}, set()
    for row in cases:
        case_id = row["id"]
        if not isinstance(case_id, str) or not case_id.strip() or case_id in case_ids:
            raise ValueError("Case IDs must be nonempty and unique.")
        case_ids.add(case_id)
        spec = row["spec"]
        spec_id = digest(spec)
        if spec_id not in jobs:
            required, preferred, minimum = _extract_requirements_from_spec(spec)
            critical = {item["text"] for item in screening_criteria(spec) if item["critical"]}
            jobs[spec_id] = {
                "title": (spec.get("role") or {}).get("job_title") or spec.get("title") or "Job specification",
                "minimum_years": minimum if minimum is not None and math.isfinite(minimum) and minimum > 0 else None,
                "criteria": [
                    {"id": f"{category}-{i + 1}", "category": category, "text": requirement,
                     "critical": category == "must_have" and requirement in critical}
                    for category, requirements in (("must_have", required), ("preferred", preferred))
                    for i, requirement in enumerate(requirements)
                ],
            }
        job = jobs[spec_id]
        review = row["review_text"]
        profile = profile_resume(review) if review else {}
        redacted, _ = anonymize_resume(
            review, candidate_name=profile.get("candidate_name"), email=profile.get("email"), phone=profile.get("phone"),
        )
        packets.append({"id": case_id, "format": row["format"], "spec_id": spec_id, "resume": redacted})

        result = None
        if row["parse"] == "PARSE_FAILED":
            status = "PARSE_FAILED"
        elif resume_parse_issue(row["text"]):
            status = "NEEDS_REVIEW"
        else:
            result = evaluate_candidate(row["text"], profile_resume(row["text"]), spec)
            status = "COMPLETED" if result["overall_score"] is not None else "NO_CRITERIA"
        criteria = {(item["category"], item["text"]): item["id"] for item in job["criteria"]}
        predictions.append({
            "id": case_id, "spec_id": spec_id, "format": row["format"], "group": row.get("group"),
            "status": status, "score": result["overall_score"] if result else None,
            "tier": result["match_tier"] if result else None,
            "grades": {
                criteria[(item["category"], item["requirement"])]: item["status"]
                for item in result["detailed_evaluations"]
            } if result else {},
        })
    if not packets:
        raise ValueError("The dataset has no cases.")

    dataset = {"kind": dataset_kind, "jobs": jobs, "cases": packets}
    dataset_id = digest(dataset)
    dataset["dataset_id"] = dataset_id
    output.mkdir(parents=True, exist_ok=True)
    template = Path(__file__).with_name("screening_review_form.html").read_text(encoding="utf-8")
    encoded = json.dumps(dataset, ensure_ascii=True).replace("<", r"\u003c")
    (output / "reviewer.html").write_text(template.replace("{{REVIEW_PACKET}}", encoded), encoding="utf-8")
    baseline = {"dataset_id": dataset_id, "kind": dataset_kind, "evaluator": EVALUATOR_ENGINE,
                "jobs": jobs, "cases": predictions}
    write_json(output / "predictions.private.json", baseline)
    return baseline


def _agreement(pairs: list[tuple[Any, Any]]) -> dict:
    count = len(pairs)
    if not count:
        return {"count": 0, "exact_agreement": None, "cohen_kappa": None}
    a = Counter(left for left, _ in pairs)
    b = Counter(right for _, right in pairs)
    observed = sum(left == right for left, right in pairs) / count
    expected = sum(n * b[label] for label, n in a.items()) / count**2
    return {"count": count, "exact_agreement": round(observed, 4),
            "cohen_kappa": round((observed - expected) / (1 - expected), 4) if expected < 1 else None}


def _validate_review(baseline: dict, review: dict) -> dict:
    reviewer = review.get("reviewer")
    if review.get("dataset_id") != baseline["dataset_id"] or not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("Each review must name its reviewer and match this packet's dataset ID.")
    labels = review.get("labels")
    if not isinstance(labels, dict) or set(labels) != {row["id"] for row in baseline["cases"]}:
        raise ValueError("Each reviewer must submit a label for every case in the packet.")
    for case in baseline["cases"]:
        label = labels[case["id"]]
        grade_ids = {item["id"] for item in baseline["jobs"][case["spec_id"]]["criteria"]}
        if not isinstance(label, dict) or "advance" not in label or "grades" not in label:
            raise ValueError(f"Invalid label for case {case['id']}.")
        advance = label["advance"]
        grades = label["grades"]
        if advance is None and grades == {}:
            continue  # The reviewer could not assess the source document.
        if type(advance) is not bool or not isinstance(grades, dict) or set(grades) != grade_ids or not all(
            isinstance(value, str) and value in GRADES for value in grades.values()
        ):
            raise ValueError(f"Incomplete criterion labels for case {case['id']}.")
    return labels


def report(baseline: dict, first: dict, second: dict, top_k: int | None = None) -> dict:
    a, b = _validate_review(baseline, first), _validate_review(baseline, second)
    if first["reviewer"].strip().casefold() == second["reviewer"].strip().casefold():
        raise ValueError("Use two independent reviews with distinct reviewer identifiers.")
    rows = baseline["cases"]
    format_outcomes: dict = defaultdict(Counter)
    group_counts: dict = defaultdict(Counter)
    criterion_pairs: dict = defaultdict(list)
    evaluator_pairs: dict = defaultdict(list)
    evaluator_vs_first: dict = defaultdict(list)
    evaluator_vs_second: dict = defaultdict(list)
    decision_pairs = []
    under_ranked = []
    disagreements = []
    qualified = 0
    top_choices = set()
    if top_k:
        tier_order = {"STRONG_MATCH": 2, "POTENTIAL_MATCH": 1, "NOT_A_FIT": 0}
        for spec_id in baseline["jobs"]:
            scored = [r for r in rows if r["spec_id"] == spec_id and r["score"] is not None]
            scored.sort(key=lambda r: (tier_order[r["tier"]], r["score"]), reverse=True)
            if scored:
                cutoff = scored[min(top_k, len(scored)) - 1]
                edge = (tier_order[cutoff["tier"]], cutoff["score"])
                top_choices.update(r["id"] for r in scored if (tier_order[r["tier"]], r["score"]) >= edge)
    for row in rows:
        case_id, job_id = row["id"], row["spec_id"]
        format_outcomes[row["format"]][row["status"]] += 1
        group = row.get("group")
        if group:
            group_counts[group]["cases"] += 1
            group_counts[group]["parse_review"] += row["status"] in {"PARSE_FAILED", "NEEDS_REVIEW"}
        left, right = a[case_id], b[case_id]
        if left["advance"] is None or right["advance"] is None:
            continue
        decision_pairs.append((left["advance"], right["advance"]))
        for criterion, grade in left["grades"].items():
            second_grade = right["grades"][criterion]
            key = (job_id, criterion)
            criterion_pairs[key].append((grade, second_grade))
            if criterion in row["grades"]:
                predicted = row["grades"][criterion]
                evaluator_vs_first[key].append((grade, predicted))
                evaluator_vs_second[key].append((second_grade, predicted))
                if grade == second_grade:
                    evaluator_pairs[key].append((grade, predicted))
        if left["advance"] != right["advance"]:
            disagreements.append(case_id)
        if left["advance"] and right["advance"]:
            qualified += 1
            if group:
                group_counts[group]["qualified"] += 1
            missed = row["score"] is None or row["score"] < POTENTIAL_MATCH_THRESHOLD or (top_k is not None and case_id not in top_choices)
            if missed:
                under_ranked.append({"case_id": case_id, "status": row["status"], "score": row["score"]})
                if group:
                    group_counts[group]["under_ranked"] += 1

    groups = {}
    for group, counts in sorted(group_counts.items()):
        if counts["cases"] < 5:
            groups[group] = {"cases": counts["cases"], "outcomes_suppressed": True}
            continue
        qualified_count = counts["qualified"]
        groups[group] = {
            "cases": counts["cases"], "parse_review": counts["parse_review"],
            "parse_review_rate": round(counts["parse_review"] / counts["cases"], 4),
            "qualified": qualified_count, "under_ranked": counts["under_ranked"],
            "qualified_in_shortlist_rate": round((qualified_count - counts["under_ranked"]) / qualified_count, 4)
            if qualified_count else None,
        }
    criterion_text = {
        (spec_id, item["id"]): item["text"]
        for spec_id, job in baseline["jobs"].items() for item in job["criteria"]
    }
    return {
        "dataset_id": baseline["dataset_id"], "kind": baseline["kind"], "evaluator": baseline["evaluator"],
        "case_count": len(rows), "within_planned_30_to_50_cases": 30 <= len(rows) <= 50,
        "reviewer_decision_agreement": _agreement(decision_pairs),
        "unreviewable_by_at_least_one_reviewer": len(rows) - len(decision_pairs),
        "criteria": [
            {"spec_id": key[0], "criterion": key[1], "text": criterion_text[key], "reviewer_agreement": _agreement(pairs),
             "evaluator_vs_first_reviewer": _agreement(evaluator_vs_first[key]),
             "evaluator_vs_second_reviewer": _agreement(evaluator_vs_second[key]),
             "evaluator_vs_reviewer_consensus": _agreement(evaluator_pairs[key])}
            for key, pairs in sorted(criterion_pairs.items())
        ],
        "parse_and_review_outcomes_by_format": {name: dict(counts) for name, counts in sorted(format_outcomes.items())},
        "reviewer_disagreements": disagreements,
        "qualified_by_both_reviewers": qualified, "qualified_ranked_too_low": under_ranked,
        "qualified_in_shortlist_rate": round((qualified - len(under_ranked)) / qualified, 4) if qualified else None,
        "shortlist": {"minimum_score": POTENTIAL_MATCH_THRESHOLD, "top_k_per_job": top_k, "includes_ties_at_cutoff": bool(top_k)},
        "validation_groups": groups,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    source = prep.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest", type=Path)
    source.add_argument("--synthetic", action="store_true")
    prep.add_argument("--output-dir", type=Path, required=True)
    compare = commands.add_parser("report")
    compare.add_argument("predictions", type=Path)
    compare.add_argument("first_review", type=Path)
    compare.add_argument("second_review", type=Path)
    compare.add_argument("--top-k", type=int)
    compare.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            baseline = prepare(
                synthetic_cases() if args.synthetic else manifest_cases(args.manifest),
                args.output_dir, "synthetic" if args.synthetic else "recruiter_validation",
            )
            print(f"Prepared an independent review packet for {len(baseline['cases'])} cases.")
        else:
            if args.top_k is not None and args.top_k < 1:
                parser.error("--top-k must be positive.")
            result = report(read_json(args.predictions), read_json(args.first_review), read_json(args.second_review), args.top_k)
            if args.output:
                write_json(args.output, result)
            print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
