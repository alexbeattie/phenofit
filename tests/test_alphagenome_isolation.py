"""Subprocess containment tests for optional AlphaGenome native dependencies."""

from __future__ import annotations

import os
import signal
import sys
import threading
import unittest
from unittest import mock

from phenofit.alphagenome_isolation import run_isolated


def _python(source: str) -> list[str]:
    return [sys.executable, "-c", source]


_SUCCESS = r"""
import json, sys
json.load(sys.stdin)
print(json.dumps({"type": "progress", "stage": "scoring_splicing", "message": "Scoring splicing signals…"}), flush=True)
print(json.dumps({"type": "result", "result": {"variant_id": "15:1:C>T", "splicing": [], "regulatory": []}}), flush=True)
"""


class IsolationTests(unittest.TestCase):
    def test_real_worker_protocol_abstains_cleanly_without_api_key(self):
        payload = {
            "coordinates": {
                "resolved": True, "gene": "FBN1", "hgvs": "FBN1:c.1A>G",
                "chrom": "15", "pos": 1, "ref": "A", "alt": "G",
                "consequence": "intron_variant", "protein_hgvs": "", "reason": "",
            }
        }

        with mock.patch.dict(os.environ, {"ALPHAGENOME_API_KEY": ""}):
            result = run_isolated(payload)

        self.assertFalse(result["available"])
        self.assertIn("ALPHAGENOME_API_KEY", result["error"])

    def test_forwards_progress_and_returns_final_result(self):
        events = []

        result = run_isolated(
            {"gene": "FBN1"},
            progress=lambda stage, message: events.append((stage, message)),
            command=_python(_SUCCESS),
        )

        self.assertEqual(result["variant_id"], "15:1:C>T")
        self.assertEqual(events, [("scoring_splicing", "Scoring splicing signals…")])

    @unittest.skipUnless(hasattr(signal, "SIGSEGV"), "platform has no SIGSEGV")
    def test_native_crash_is_contained_and_next_worker_still_runs(self):
        crash = "import os, signal; os.kill(os.getpid(), signal.SIGSEGV)"

        failed = run_isolated({}, command=_python(crash))
        recovered = run_isolated({}, command=_python(_SUCCESS))

        self.assertTrue(failed["error"])
        self.assertTrue(failed["worker_crashed"])
        self.assertIn("PhenoFit is still running", failed["error"])
        self.assertEqual(recovered["variant_id"], "15:1:C>T")

    def test_malformed_worker_output_is_an_explicit_failure(self):
        result = run_isolated({}, command=_python("print('not-json', flush=True)"))

        self.assertIn("invalid output", result["error"].lower())
        self.assertFalse(result["worker_crashed"])

    def test_timeout_terminates_only_the_worker(self):
        result = run_isolated(
            {}, timeout=0.05,
            command=_python("import time; time.sleep(10)"),
        )

        self.assertTrue(result["timed_out"])
        self.assertIn("timed out", result["error"].lower())

    def test_cancellation_terminates_only_the_worker(self):
        cancelled = threading.Event()
        cancelled.set()

        result = run_isolated(
            {}, cancel_event=cancelled,
            command=_python("import time; time.sleep(10)"),
        )

        self.assertTrue(result["cancelled"])
        self.assertIn("cancelled", result["error"].lower())


if __name__ == "__main__":
    unittest.main()
