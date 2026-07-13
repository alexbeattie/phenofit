"""Static contracts for truthful and accessible long-operation feedback."""

from __future__ import annotations

import unittest
from pathlib import Path


HTML = (Path(__file__).parents[1] / "phenofit" / "static" / "index.html").read_text()


class LoadingUiTests(unittest.TestCase):
    def test_spinner_is_accessible_and_respects_reduced_motion(self):
        self.assertIn(".spinner", HTML)
        self.assertIn("@keyframes spin", HTML)
        self.assertIn("prefers-reduced-motion: reduce", HTML)
        self.assertIn('role="status"', HTML)
        self.assertIn('aria-live="polite"', HTML)
        self.assertIn("aria-busy", HTML)

    def test_every_long_action_has_specific_busy_copy(self):
        expected = (
            "Grounding patient features in HPO and scoring phenotype fit…",
            "Claude is extracting phenotype phrases; then PhenoFit grounds them in HPO…",
            "Reading documents with Claude and grounding findings in HPO…",
            "Claude is drafting a management summary…",
        )
        for message in expected:
            with self.subTest(message=message):
                self.assertIn(message, HTML)

    def test_alphagenome_uses_polled_job_and_can_cancel(self):
        self.assertIn('fetch("/api/alphagenome/jobs"', HTML)
        self.assertIn('fetch("/api/jobs/" + jobId', HTML)
        self.assertIn('method: "DELETE"', HTML)
        self.assertIn("Cancel AlphaGenome", HTML)

    def test_native_crash_copy_reassures_without_hiding_failure(self):
        self.assertIn("AlphaGenome worker crashed", HTML)
        self.assertIn("PhenoFit is still running", HTML)


if __name__ == "__main__":
    unittest.main()
