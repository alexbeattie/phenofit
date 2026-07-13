"""In-memory job lifecycle tests."""

from __future__ import annotations

import threading
import time
import unittest

from phenofit.jobs import JobRegistry


def _wait_for(registry: JobRegistry, job_id: str, state: str, timeout: float = 1) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = registry.get(job_id)
        if snapshot and snapshot["state"] == state:
            return snapshot
        time.sleep(0.005)
    raise AssertionError(f"job {job_id} did not reach {state}: {registry.get(job_id)}")


class JobRegistryTests(unittest.TestCase):
    def test_records_real_progress_then_success(self):
        release = threading.Event()

        def runner(payload, *, progress, cancel_event):
            progress("scoring_splicing", "Scoring splicing signals…")
            release.wait(1)
            return {"variant_id": payload["variant_id"]}

        jobs = JobRegistry(runner)
        job_id = jobs.start({"variant_id": "15:1:C>T"})
        running = _wait_for(jobs, job_id, "running")
        self.assertEqual(running["stage"], "scoring_splicing")
        self.assertEqual(running["message"], "Scoring splicing signals…")

        release.set()
        done = _wait_for(jobs, job_id, "succeeded")
        self.assertEqual(done["result"]["variant_id"], "15:1:C>T")
        self.assertIsNone(done["error"])

    def test_cancel_signals_only_that_job(self):
        def runner(payload, *, progress, cancel_event):
            while not cancel_event.wait(0.005):
                pass
            return {"error": "AlphaGenome scoring cancelled.", "cancelled": True}

        jobs = JobRegistry(runner)
        job_id = jobs.start({})
        _wait_for(jobs, job_id, "running")

        self.assertTrue(jobs.cancel(job_id))
        cancelled = _wait_for(jobs, job_id, "cancelled")
        self.assertEqual(cancelled["message"], "AlphaGenome scoring cancelled.")

    def test_unknown_job_is_safe(self):
        jobs = JobRegistry(lambda *a, **k: {})

        self.assertIsNone(jobs.get("missing"))
        self.assertFalse(jobs.cancel("missing"))

    def test_runner_error_becomes_failed_job(self):
        jobs = JobRegistry(lambda *a, **k: {"error": "worker crashed", "worker_crashed": True})

        failed = _wait_for(jobs, jobs.start({}), "failed")

        self.assertEqual(failed["error"], "worker crashed")
        self.assertTrue(failed["result"]["worker_crashed"])

    def test_active_job_limit_rejects_excess_work(self):
        release = threading.Event()

        def runner(*args, **kwargs):
            release.wait(1)
            return {}

        jobs = JobRegistry(runner, max_active=1)
        first = jobs.start({})

        self.assertIsNotNone(first)
        self.assertIsNone(jobs.start({}))
        release.set()


if __name__ == "__main__":
    unittest.main()
