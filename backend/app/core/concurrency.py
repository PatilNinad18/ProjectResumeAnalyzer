"""
Concurrency management and bounded synchronization for Ollama inference.

Empirical measurement showed that running multiple Ollama inferences in parallel on local
hardware causes heavy CPU/RAM/VRAM contention (latency increases 2.2x and overall throughput
decreases by 3.8%). Therefore, inference concurrency must be tightly bounded.

Meanwhile, deterministic extraction, graph traversal, canonical projection, and database I/O
do NOT touch Ollama and run concurrently without blocking.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Generator, Optional

logger = logging.getLogger("app.concurrency")

# Configurable concurrency limit; defaults to 1 for local single-model deployments
# to eliminate memory contention and GPU thrashing. Set OLLAMA_MAX_CONCURRENCY=2+
# on multi-GPU or dedicated inference nodes.
DEFAULT_OLLAMA_MAX_CONCURRENCY = int(os.getenv("OLLAMA_MAX_CONCURRENCY", "1"))
DEFAULT_SLOT_TIMEOUT = float(os.getenv("OLLAMA_SLOT_TIMEOUT_SECONDS", "120.0"))

_ollama_semaphore = threading.BoundedSemaphore(value=max(1, DEFAULT_OLLAMA_MAX_CONCURRENCY))
_metrics_lock = threading.Lock()
_concurrency_metrics = {
    "total_acquisitions": 0,
    "total_lock_wait_ms": 0.0,
    "max_lock_wait_ms": 0.0,
    "total_inference_ms": 0.0,
}


@contextmanager
def acquire_ollama_slot(task_name: str = "ollama_inference", timeout: Optional[float] = None) -> Generator[float, None, None]:
    """
    Acquires a slot from the bounded Ollama semaphore.
    Measures and yields the lock-wait time in milliseconds.
    Guarantees semaphore release in a finally block.
    """
    effective_timeout = timeout if timeout is not None else DEFAULT_SLOT_TIMEOUT
    t_start = time.perf_counter()
    acquired = _ollama_semaphore.acquire(timeout=effective_timeout)
    if not acquired:
        raise TimeoutError(f"Timed out waiting for Ollama concurrency slot ({task_name}) after {effective_timeout:.1f}s")

    t_acquired = time.perf_counter()
    lock_wait_ms = (t_acquired - t_start) * 1000.0

    with _metrics_lock:
        _concurrency_metrics["total_acquisitions"] += 1
        _concurrency_metrics["total_lock_wait_ms"] += lock_wait_ms
        if lock_wait_ms > _concurrency_metrics["max_lock_wait_ms"]:
            _concurrency_metrics["max_lock_wait_ms"] = lock_wait_ms

    logger.info("Acquired Ollama slot for '%s' (lock wait: %.2f ms)", task_name, lock_wait_ms)
    t_infer_start = time.perf_counter()
    try:
        yield lock_wait_ms
    finally:
        infer_duration_ms = (time.perf_counter() - t_infer_start) * 1000.0
        with _metrics_lock:
            _concurrency_metrics["total_inference_ms"] += infer_duration_ms
        _ollama_semaphore.release()
        logger.info(
            "Released Ollama slot for '%s' (wait: %.2f ms, inference: %.2f ms)",
            task_name,
            lock_wait_ms,
            infer_duration_ms,
        )


def get_concurrency_metrics() -> dict:
    """Return a snapshot of concurrency metrics."""
    with _metrics_lock:
        return dict(_concurrency_metrics)


def reset_concurrency_metrics() -> None:
    """Reset concurrency tracking counters."""
    with _metrics_lock:
        _concurrency_metrics["total_acquisitions"] = 0
        _concurrency_metrics["total_lock_wait_ms"] = 0.0
        _concurrency_metrics["max_lock_wait_ms"] = 0.0
        _concurrency_metrics["total_inference_ms"] = 0.0
