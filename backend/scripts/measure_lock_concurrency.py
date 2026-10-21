"""
Measure lock-wait time separately from Ollama inference time under concurrent requests.
Compares Concurrency Limit = 1 (Mutex Lock) vs Concurrency Limit = 2 (Bounded Semaphore) vs 3.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.services.enrichment.ta_enrichment_service import GroundedEnrichmentService

SAMPLE_REQS_1 = [
    {"id": "req_1", "text": "Python FastAPI backend development and async programming"},
    {"id": "req_2", "text": "Docker containerization and Kubernetes cluster management"},
    {"id": "req_3", "text": "PostgreSQL database schema design and query optimization"},
]

SAMPLE_REQS_2 = [
    {"id": "req_4", "text": "AWS cloud architecture (Lambda, S3, ECS, CloudFront)"},
    {"id": "req_5", "text": "CI/CD automation with GitHub Actions and Terraform"},
    {"id": "req_6", "text": "Redis caching and message queuing for low-latency APIs"},
]

SAMPLE_REQS_3 = [
    {"id": "req_7", "text": "React TypeScript frontend development with modern hooks"},
    {"id": "req_8", "text": "TailwindCSS and responsive design principles"},
    {"id": "req_9", "text": "RESTful and GraphQL API consumption and state caching"},
]


def run_concurrent_test(concurrency_limit: int, num_requests: int = 3) -> Dict[str, Any]:
    service = GroundedEnrichmentService()
    if not service.check_ollama_available():
        return {"error": "Ollama is not available"}

    semaphore = threading.BoundedSemaphore(value=concurrency_limit)
    request_payloads = [SAMPLE_REQS_1, SAMPLE_REQS_2, SAMPLE_REQS_3][:num_requests]

    timings = []
    timing_lock = threading.Lock()

    def worker(req_idx: int, reqs: List[Dict[str, Any]]):
        t_req = time.perf_counter()
        with semaphore:
            t_acquired = time.perf_counter()
            lock_wait_ms = (t_acquired - t_req) * 1000.0

            # Execute actual enrichment
            t_infer = time.perf_counter()
            report = service.generate_enrichment_report(
                spec_version_id=f"test_{req_idx}",
                specification_version=1,
                source_checksum="chk",
                requirements=reqs,
            )
            inference_ms = (time.perf_counter() - t_infer) * 1000.0
            total_req_ms = (time.perf_counter() - t_req) * 1000.0

            with timing_lock:
                timings.append({
                    "req_idx": req_idx,
                    "items_count": len(report.items),
                    "lock_wait_ms": round(lock_wait_ms, 2),
                    "inference_ms": round(inference_ms, 2),
                    "total_ms": round(total_req_ms, 2),
                })

    t_wall_start = time.perf_counter()
    threads = [
        threading.Thread(target=worker, args=(i, p))
        for i, p in enumerate(request_payloads, start=1)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall_time_ms = (time.perf_counter() - t_wall_start) * 1000.0

    # Calculate metrics
    timings.sort(key=lambda x: x["req_idx"])
    avg_lock_wait = sum(t["lock_wait_ms"] for t in timings) / len(timings) if timings else 0
    max_lock_wait = max((t["lock_wait_ms"] for t in timings), default=0)
    avg_inference = sum(t["inference_ms"] for t in timings) / len(timings) if timings else 0

    return {
        "concurrency_limit": concurrency_limit,
        "num_requests": num_requests,
        "wall_time_sec": round(wall_time_ms / 1000.0, 2),
        "avg_lock_wait_ms": round(avg_lock_wait, 2),
        "max_lock_wait_ms": round(max_lock_wait, 2),
        "avg_inference_ms": round(avg_inference, 2),
        "per_request_timings": timings,
    }


def main():
    print("=" * 70, flush=True)
    print("  MEASURING LOCK-WAIT VS INFERENCE TIME UNDER CONCURRENT REQUESTS", flush=True)
    print("=" * 70, flush=True)
    print(flush=True)

    # Test 1: Concurrency = 1 (Mutex lock, current baseline)
    print("[1/2] Testing Concurrency Limit = 1 (Current Global Mutex)...", flush=True)
    res_1 = run_concurrent_test(concurrency_limit=1, num_requests=2)
    print(f"  Wall Time:       {res_1['wall_time_sec']}s", flush=True)
    print(f"  Avg Lock Wait:   {res_1['avg_lock_wait_ms']} ms (Max: {res_1['max_lock_wait_ms']} ms)", flush=True)
    print(f"  Avg Inference:   {res_1['avg_inference_ms']} ms", flush=True)
    for r in res_1["per_request_timings"]:
        print(f"    Req {r['req_idx']}: wait={r['lock_wait_ms']}ms, infer={r['inference_ms']}ms, total={r['total_ms']}ms", flush=True)
    print(flush=True)

    # Test 2: Concurrency = 2 (Bounded Semaphore)
    print("[2/2] Testing Concurrency Limit = 2 (Bounded Semaphore = 2)...", flush=True)
    res_2 = run_concurrent_test(concurrency_limit=2, num_requests=2)
    print(f"  Wall Time:       {res_2['wall_time_sec']}s", flush=True)
    print(f"  Avg Lock Wait:   {res_2['avg_lock_wait_ms']} ms (Max: {res_2['max_lock_wait_ms']} ms)", flush=True)
    print(f"  Avg Inference:   {res_2['avg_inference_ms']} ms", flush=True)
    for r in res_2["per_request_timings"]:
        print(f"    Req {r['req_idx']}: wait={r['lock_wait_ms']}ms, infer={r['inference_ms']}ms, total={r['total_ms']}ms", flush=True)
    print(flush=True)

    # Comparison summary
    print("=" * 70, flush=True)
    print("  COMPARISON SUMMARY", flush=True)
    print("=" * 70, flush=True)
    print(f"  Mutex Lock (Limit=1):        Wall Time = {res_1['wall_time_sec']}s | Max Lock Wait = {res_1['max_lock_wait_ms']}ms", flush=True)
    print(f"  Bounded Semaphore (Limit=2): Wall Time = {res_2['wall_time_sec']}s | Max Lock Wait = {res_2['max_lock_wait_ms']}ms", flush=True)
    if res_1['wall_time_sec'] > 0:
        speedup = ((res_1['wall_time_sec'] - res_2['wall_time_sec']) / res_1['wall_time_sec']) * 100.0
        print(f"  Wall-Clock Improvement:      {speedup:.1f}%", flush=True)
    print("=" * 70, flush=True)


if __name__ == "__main__":
    main()
