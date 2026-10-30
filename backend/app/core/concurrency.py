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
import subprocess
import threading
import time
from contextlib import contextmanager
from typing import Generator, Optional

logger = logging.getLogger("app.concurrency")

# Keep inference bounded independently from the worker queue. Explicit positive
# settings override the GPU-memory-aware default.
from app.config import get_settings

_settings = get_settings()


def _available_gpu_memory_mb() -> Optional[int]:
    """Return free NVIDIA GPU memory in MiB, or None when it cannot be queried."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    free_values = []
    for line in result.stdout.splitlines():
        try:
            free_values.append(int(line.strip()))
        except ValueError:
            continue
    return max(free_values) if free_values else None


def resolve_ollama_concurrency(requested: int, available_gpu_memory_mb: Optional[int]) -> int:
    """Reserve roughly 1 GiB of free VRAM per Ollama request by default."""
    if requested > 0:
        return requested
    if available_gpu_memory_mb is None:
        return 1
    return max(1, min(4, available_gpu_memory_mb // 1024))


_GPU_MEMORY_FREE_MB = _available_gpu_memory_mb()
DEFAULT_OLLAMA_MAX_CONCURRENCY = resolve_ollama_concurrency(
    _settings.ollama_max_concurrency,
    _GPU_MEMORY_FREE_MB,
)
DEFAULT_SLOT_TIMEOUT = max(0.1, _settings.ollama_slot_timeout_seconds)

_ollama_semaphore = threading.BoundedSemaphore(value=max(1, DEFAULT_OLLAMA_MAX_CONCURRENCY))
_metrics_lock = threading.Lock()
_concurrency_metrics = {
    "total_acquisitions": 0,
    "total_lock_wait_ms": 0.0,
    "max_lock_wait_ms": 0.0,
    "total_inference_ms": 0.0,
}
_active_inferences = 0
_max_observed_concurrency = 0
logger.info(
    "Ollama inference concurrency configured: limit=%d source=%s free_gpu_memory_mb=%s",
    DEFAULT_OLLAMA_MAX_CONCURRENCY,
    "environment" if _settings.ollama_max_concurrency > 0 else "GPU-memory-aware default",
    _GPU_MEMORY_FREE_MB,
)


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

    global _active_inferences, _max_observed_concurrency
    with _metrics_lock:
        _concurrency_metrics["total_acquisitions"] += 1
        _concurrency_metrics["total_lock_wait_ms"] += lock_wait_ms
        if lock_wait_ms > _concurrency_metrics["max_lock_wait_ms"]:
            _concurrency_metrics["max_lock_wait_ms"] = lock_wait_ms
        _active_inferences += 1
        _max_observed_concurrency = max(_max_observed_concurrency, _active_inferences)

    logger.info("Acquired Ollama slot for '%s' (lock wait: %.2f ms)", task_name, lock_wait_ms)
    t_infer_start = time.perf_counter()
    try:
        yield lock_wait_ms
    finally:
        infer_duration_ms = (time.perf_counter() - t_infer_start) * 1000.0
        with _metrics_lock:
            _concurrency_metrics["total_inference_ms"] += infer_duration_ms
            _active_inferences -= 1
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
        return {
            **_concurrency_metrics,
            "configured_max_concurrency": DEFAULT_OLLAMA_MAX_CONCURRENCY,
            "available_gpu_memory_mb": _GPU_MEMORY_FREE_MB,
            "max_observed_concurrency": _max_observed_concurrency,
            "active_inferences": _active_inferences,
        }


def reset_concurrency_metrics() -> None:
    """Reset concurrency tracking counters."""
    global _max_observed_concurrency
    with _metrics_lock:
        _concurrency_metrics["total_acquisitions"] = 0
        _concurrency_metrics["total_lock_wait_ms"] = 0.0
        _concurrency_metrics["max_lock_wait_ms"] = 0.0
        _concurrency_metrics["total_inference_ms"] = 0.0
        _max_observed_concurrency = _active_inferences
