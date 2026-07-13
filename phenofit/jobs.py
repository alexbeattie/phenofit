"""Small thread-safe registry for browser-polled background work."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable


class JobRegistry:
    """Run jobs in daemon threads and expose JSON-safe immutable snapshots."""

    def __init__(self, runner: Callable, *, max_completed: int = 50, max_active: int = 4):
        self._runner = runner
        self._max_completed = max_completed
        self._max_active = max_active
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, payload: dict) -> str | None:
        job_id = uuid.uuid4().hex
        cancel_event = threading.Event()
        with self._lock:
            active = sum(
                job["state"] in {"queued", "running"}
                for job in self._jobs.values()
            )
            if active >= self._max_active:
                return None
            self._jobs[job_id] = {
                "job_id": job_id,
                "state": "queued",
                "stage": "queued",
                "message": "AlphaGenome job queued…",
                "result": None,
                "error": None,
                "created_at": time.time(),
                "updated_at": time.time(),
                "_cancel_event": cancel_event,
            }
        threading.Thread(
            target=self._execute,
            args=(job_id, dict(payload), cancel_event),
            daemon=True,
            name=f"alphagenome-job-{job_id[:8]}",
        ).start()
        return job_id

    def _update(self, job_id: str, **changes) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.update(changes)
            job["updated_at"] = time.time()

    def _execute(self, job_id: str, payload: dict, cancel_event: threading.Event) -> None:
        self._update(
            job_id,
            state="running",
            stage="starting",
            message="Starting AlphaGenome review…",
        )

        def progress(stage: str, message: str) -> None:
            self._update(job_id, stage=stage, message=message)

        try:
            result = self._runner(payload, progress=progress, cancel_event=cancel_event)
        except Exception as exc:
            result = {"error": f"{type(exc).__name__}: {exc}"}

        if result.get("cancelled"):
            state, message = "cancelled", "AlphaGenome scoring cancelled."
        elif result.get("error"):
            state, message = "failed", str(result["error"])
        else:
            state, message = "succeeded", "AlphaGenome evidence ready."
        self._update(
            job_id,
            state=state,
            stage=state,
            message=message,
            result=result,
            error=result.get("error"),
        )
        self._prune_completed()

    def _prune_completed(self) -> None:
        with self._lock:
            completed = sorted(
                (
                    job for job in self._jobs.values()
                    if job["state"] in {"succeeded", "failed", "cancelled"}
                ),
                key=lambda job: job["updated_at"],
                reverse=True,
            )
            for job in completed[self._max_completed:]:
                self._jobs.pop(job["job_id"], None)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return {key: value for key, value in job.items() if not key.startswith("_")}

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job["state"] not in {"queued", "running"}:
                return False
            job["_cancel_event"].set()
            job["message"] = "Cancelling isolated AlphaGenome worker…"
            job["updated_at"] = time.time()
            return True
