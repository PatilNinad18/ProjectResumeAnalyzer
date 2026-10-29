"""
Thread-safe, per-JD progress tracking registry.

Maintains isolated, non-simulated real-time progress for:
- Initial JD Analysis (Extraction, EKG, Canonical Projection, Validation, Enrichment)
- Grounded TA Evidence Enrichment (Ollama)
- Ambiguity Resolution & Incremental Re-enrichment

Guarantees:
1. Strict per-JD isolation for concurrent analysis.
2. Monotonic progress based on actual work units; never simulated with arbitrary timers.
3. 100% completion is reached ONLY when the operation succeeds.
4. Supports cooperative cancellation and error capture.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("app.progress")


@dataclass
class JDProgress:
    jd_id: str
    operation: str  # "analysis" | "enrich" | "resolve"
    stage: str      # e.g. "PARSING", "UNDERSTANDING", "PROJECTING", "CLARIFYING", "VALIDATING", "GENERATING", "READY", "FAILED", "CANCELLED"
    message: str    # Descriptive human-readable stage message
    percent: int    # 0 to 100
    current_step: int
    total_steps: int
    started_at: float
    updated_at: float
    finished_at: Optional[float] = None
    error: Optional[str] = None
    cancelled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        now = self.finished_at if self.finished_at is not None else time.time()
        data["elapsed_seconds"] = round(max(0.0, now - self.started_at), 1)
        return data


class ProgressRegistry:
    """Thread-safe registry of in-flight and recently completed operations per JD."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Key: f"{operation}:{jd_id}" or jd_id -> JDProgress
        self._progress: Dict[str, JDProgress] = {}
        self._cancel_flags: Dict[str, bool] = {}

    def _make_key(self, jd_id: str, operation: str = "analysis") -> str:
        return f"{operation}:{jd_id}"

    def start_progress(
        self,
        jd_id: str,
        operation: str,
        total_steps: int,
        initial_stage: str = "STARTED",
        initial_message: str = "Starting operation...",
        initial_percent: int = 5,
    ) -> JDProgress:
        key = self._make_key(jd_id, operation)
        now = time.time()
        with self._lock:
            self._cancel_flags.pop(key, None)
            progress = JDProgress(
                jd_id=jd_id,
                operation=operation,
                stage=initial_stage,
                message=initial_message,
                percent=max(0, min(95, initial_percent)),
                current_step=1,
                total_steps=total_steps,
                started_at=now,
                updated_at=now,
                finished_at=None,
                error=None,
                cancelled=False,
            )
            self._progress[key] = progress
            logger.info("[%s:%s] Progress started: %s (%d%%)", operation, jd_id, initial_message, initial_percent)
            return progress

    def update_progress(
        self,
        jd_id: str,
        operation: str,
        stage: str,
        message: str,
        percent: int,
        current_step: Optional[int] = None,
    ) -> Optional[JDProgress]:
        key = self._make_key(jd_id, operation)
        now = time.time()
        with self._lock:
            p = self._progress.get(key)
            if not p:
                return None
            if p.cancelled:
                return p
            p.stage = stage
            p.message = message
            # Never reach 100% in update_progress; 100% is reserved for complete_progress
            p.percent = max(p.percent, min(95, percent))
            if current_step is not None:
                p.current_step = current_step
            p.updated_at = now
            logger.debug("[%s:%s] Progress updated: %s (%d%%)", operation, jd_id, message, p.percent)
            return p

    def complete_progress(
        self,
        jd_id: str,
        operation: str,
        stage: str = "READY",
        message: str = "Operation completed successfully.",
    ) -> Optional[JDProgress]:
        key = self._make_key(jd_id, operation)
        now = time.time()
        with self._lock:
            p = self._progress.get(key)
            if not p:
                p = JDProgress(
                    jd_id=jd_id,
                    operation=operation,
                    stage=stage,
                    message=message,
                    percent=100,
                    current_step=1,
                    total_steps=1,
                    started_at=now,
                    updated_at=now,
                    finished_at=now,
                    error=None,
                    cancelled=False,
                )
                self._progress[key] = p
            else:
                p.stage = stage
                p.message = message
                p.percent = 100
                p.current_step = p.total_steps
                p.updated_at = now
                p.finished_at = now
            logger.info("[%s:%s] Progress completed: 100%%", operation, jd_id)
            return p

    def fail_progress(
        self,
        jd_id: str,
        operation: str,
        error_message: str,
        stage: str = "FAILED",
    ) -> Optional[JDProgress]:
        key = self._make_key(jd_id, operation)
        now = time.time()
        with self._lock:
            p = self._progress.get(key)
            if not p:
                p = JDProgress(
                    jd_id=jd_id,
                    operation=operation,
                    stage=stage,
                    message=f"Failed: {error_message}",
                    percent=0,
                    current_step=0,
                    total_steps=1,
                    started_at=now,
                    updated_at=now,
                    finished_at=now,
                    error=error_message,
                    cancelled=False,
                )
                self._progress[key] = p
            else:
                p.stage = stage
                p.message = f"Failed: {error_message}"
                p.error = error_message
                p.updated_at = now
                p.finished_at = now
            logger.warning("[%s:%s] Progress failed: %s", operation, jd_id, error_message)
            return p

    def cancel_progress(
        self,
        jd_id: str,
        operation: Optional[str] = None,
        reason: str = "Cancelled by user",
    ) -> bool:
        now = time.time()
        cancelled_any = False
        with self._lock:
            keys = [self._make_key(jd_id, operation)] if operation else [
                k for k in self._progress if k.endswith(f":{jd_id}") or k == jd_id
            ]
            for key in keys:
                self._cancel_flags[key] = True
                p = self._progress.get(key)
                if p and not p.finished_at:
                    p.cancelled = True
                    p.stage = "CANCELLED"
                    p.message = reason
                    p.error = reason
                    p.updated_at = now
                    p.finished_at = now
                    cancelled_any = True
                    logger.info("[%s] Operation cancelled", key)
        return cancelled_any

    def is_cancelled(self, jd_id: str, operation: str = "analysis") -> bool:
        key = self._make_key(jd_id, operation)
        with self._lock:
            if self._cancel_flags.get(key, False):
                return True
            p = self._progress.get(key)
            return bool(p and p.cancelled)

    def get_progress(self, jd_id: str, operation: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            if operation:
                key = self._make_key(jd_id, operation)
                p = self._progress.get(key)
                return p.to_dict() if p else None

            # If no operation specified, return the most recently updated operation for this jd_id
            matching = [p for p in self._progress.values() if p.jd_id == jd_id]
            if not matching:
                return None
            matching.sort(key=lambda x: x.updated_at, reverse=True)
            return matching[0].to_dict()

    def clear(self, jd_id: Optional[str] = None) -> None:
        with self._lock:
            if jd_id:
                keys = [k for k in self._progress if k.endswith(f":{jd_id}") or k == jd_id]
                for k in keys:
                    self._progress.pop(k, None)
                    self._cancel_flags.pop(k, None)
            else:
                self._progress.clear()
                self._cancel_flags.clear()


# Global singleton registry
progress_registry = ProgressRegistry()
