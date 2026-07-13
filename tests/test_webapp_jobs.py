"""HTTP and orchestration contracts for isolated AlphaGenome jobs."""

from __future__ import annotations

import http.client
import json
import threading
import unittest
from unittest import mock

from phenofit import webapp
from phenofit.coords import Coordinates
from phenofit.jobs import JobRegistry


class AlphaGenomeOrchestrationTests(unittest.TestCase):
    def test_resolves_before_starting_isolated_worker(self):
        events = []
        coordinates = Coordinates(
            resolved=True, gene="FBN1", hgvs="FBN1:c.1A>G",
            chrom="15", pos=1, ref="A", alt="G", consequence="intron_variant",
        )

        def isolated(payload, *, progress, cancel_event):
            self.assertEqual(payload["coordinates"]["chrom"], "15")
            return {"variant_id": "15:1:A>G", "splicing": [], "regulatory": []}

        with mock.patch.object(webapp, "alphagenome_configured", return_value=True), \
             mock.patch.object(webapp, "resolve_coords", return_value=coordinates):
            result = webapp._run_alphagenome(
                {"gene": "FBN1", "hgvs": "c.1A>G"},
                progress=lambda stage, message: events.append((stage, message)),
                cancel_event=threading.Event(),
                _isolated_runner=isolated,
            )

        self.assertEqual(result["variant_id"], "15:1:A>G")
        self.assertEqual(events[0][0], "resolving_coordinates")
        self.assertEqual(events[1][0], "starting_worker")


class JobHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_jobs = webapp._JOBS
        webapp._JOBS = JobRegistry(
            lambda payload, **kwargs: {"variant_id": payload["gene"], "splicing": [], "regulatory": []}
        )
        cls.server = webapp._Server(("127.0.0.1", 0), webapp.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(1)
        webapp._JOBS = cls.original_jobs

    def request(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        encoded = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if encoded else {}
        conn.request(method, path, encoded, headers)
        response = conn.getresponse()
        data = json.loads(response.read() or b"{}")
        conn.close()
        return response.status, data

    def test_create_poll_and_cancel_contract(self):
        with mock.patch.object(webapp, "alphagenome_configured", return_value=True):
            status, created = self.request("POST", "/api/alphagenome/jobs", {"gene": "FBN1", "hgvs": "c.1A>G"})
        self.assertEqual(status, 202)
        self.assertTrue(created["job_id"])

        status, snapshot = self.request("GET", f"/api/jobs/{created['job_id']}")
        self.assertEqual(status, 200)
        self.assertIn(snapshot["state"], {"queued", "running", "succeeded"})

        status, _ = self.request("DELETE", f"/api/jobs/{created['job_id']}")
        self.assertIn(status, {200, 409})

    def test_unknown_job_returns_404(self):
        status, data = self.request("GET", "/api/jobs/missing")

        self.assertEqual(status, 404)
        self.assertEqual(data["error"], "Job not found.")


if __name__ == "__main__":
    unittest.main()
