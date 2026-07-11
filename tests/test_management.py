"""Offline tests for the clinical-management layer.

Curated links are pure/deterministic (no network, no key). The AI-drafted brief
is exercised with a fake SDK client, asserting the abstention contract holds:
when the model isn't confident, the brief comes back with confident=False.

    python -m unittest discover -s tests
"""

from __future__ import annotations

import unittest
from unittest import mock
from urllib.parse import urlparse

from phenofit import llm, management
from phenofit.llm import ManagementBrief


class CuratedLinksTests(unittest.TestCase):
    def test_links_are_well_formed_and_named(self):
        links = management.curated_links("SCN1A")
        names = [s.name for s in links]
        self.assertEqual(names, ["GeneReviews", "OMIM", "MedGen", "GTR"])
        for s in links:
            parsed = urlparse(s.url)
            self.assertIn(parsed.scheme, ("http", "https"))
            self.assertTrue(parsed.netloc, f"{s.name} link has no host")
            self.assertIn("SCN1A", s.url)

    def test_omim_mim_deep_links_the_entry(self):
        links = management.curated_links("FBN1", omim_mim="154700")
        omim = next(s for s in links if s.name == "OMIM")
        self.assertIn("/entry/154700", omim.url)

    def test_blank_gene_yields_no_links(self):
        self.assertEqual(management.curated_links("  "), [])


class _FakeMessages:
    def __init__(self, parsed):
        self._parsed = parsed

    def parse(self, **_kwargs):
        return mock.Mock(parsed_output=self._parsed)


class _FakeClient:
    def __init__(self, parsed):
        self.messages = _FakeMessages(parsed)


class ManagementBriefTests(unittest.TestCase):
    def test_returns_points_when_confident(self):
        parsed = ManagementBrief(
            surveillance=["annual echocardiogram"],
            management=["beta-blockade"],
            systems_to_assess=["cardiovascular", "ophthalmology"],
            confident=True,
            caveat="verify against the Marfan GeneReviews chapter",
        )
        brief = llm.draft_management_brief("FBN1", "Marfan syndrome",
                                           sdk_client=_FakeClient(parsed))
        self.assertTrue(brief.confident)
        self.assertIn("beta-blockade", brief.management)

    def test_abstains_when_not_confident(self):
        parsed = ManagementBrief(confident=False, caveat="not well-characterized")
        brief = llm.draft_management_brief("XYZ1", "ultra-rare disorder",
                                           sdk_client=_FakeClient(parsed))
        self.assertFalse(brief.confident)
        self.assertEqual(brief.management, [])
        self.assertEqual(brief.surveillance, [])


if __name__ == "__main__":
    unittest.main()
