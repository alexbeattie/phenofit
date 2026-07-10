"""Offline unit tests for the OMIM corroboration layer.

No network and no key: the API call is mocked. These lock two behaviours that
matter for a clinical tool — (1) when OMIM IS reachable, we parse the curated
gene->phenotype->inheritance mapping and carry an openable omim.org source; and
(2) when it is NOT (no key, gene absent, or a network error), we degrade to an
explicit "unavailable, and here's why" rather than crashing the review or, worse,
silently pretending there was nothing to find.

    python -m unittest discover -s tests
"""

from __future__ import annotations

import unittest
from unittest import mock

from phenofit import omim
from phenofit.models import FitTier, ReportedVariant, VariantFit

# A trimmed but real-shaped OMIM geneMap/search response for FBN1.
_FBN1_RESPONSE = {
    "omim": {"searchResponse": {"geneMapList": [{"geneMap": {
        "mimNumber": 134797,
        "approvedGeneSymbols": "FBN1",
        "phenotypeMapList": [
            {"phenotypeMap": {
                "phenotype": "Marfan syndrome",
                "phenotypeMimNumber": 154700,
                "phenotypeInheritance": "Autosomal dominant",
            }},
            {"phenotypeMap": {
                "phenotype": "Ectopia lentis, familial",
                "phenotypeMimNumber": 129600,
                "phenotypeInheritance": "Autosomal dominant",
            }},
        ],
    }}]}},
}


def _fit(gene: str) -> VariantFit:
    return VariantFit(variant=ReportedVariant(gene), tier=FitTier.POSSIBLE, score=0.5)


class FetchTests(unittest.TestCase):
    def setUp(self):
        omim._CACHE.clear()

    def test_parses_phenotypes_inheritance_and_source(self):
        with mock.patch.object(omim, "is_configured", lambda: True), \
             mock.patch.object(omim, "get_json", lambda *a, **k: _FBN1_RESPONSE):
            ev = omim.fetch_gene_omim(None, "FBN1")
        self.assertTrue(ev.available)
        self.assertEqual([p.name for p in ev.phenotypes],
                         ["Marfan syndrome", "Ectopia lentis, familial"])
        self.assertEqual(ev.phenotypes[0].mim, "154700")
        self.assertEqual(ev.inheritance_patterns, ["Autosomal dominant"])  # deduped
        self.assertIsNotNone(ev.source)
        self.assertIn("omim.org", ev.source.url)
        self.assertIn("134797", ev.source.url)  # links to the gene's OMIM entry

    def test_no_key_is_unavailable_with_reason(self):
        with mock.patch.object(omim, "is_configured", lambda: False):
            ev = omim.fetch_gene_omim(None, "FBN1")
        self.assertFalse(ev.available)
        self.assertIn("OMIM_API_KEY", ev.reason)
        self.assertEqual(ev.phenotypes, [])

    def test_network_error_degrades_not_raises(self):
        def _boom(*a, **k):
            raise RuntimeError("connection reset")
        with mock.patch.object(omim, "is_configured", lambda: True), \
             mock.patch.object(omim, "get_json", _boom):
            ev = omim.fetch_gene_omim(None, "FBN1")
        self.assertFalse(ev.available)
        self.assertTrue(ev.reason)

    def test_gene_absent_from_response_is_unavailable(self):
        empty = {"omim": {"searchResponse": {"geneMapList": []}}}
        with mock.patch.object(omim, "is_configured", lambda: True), \
             mock.patch.object(omim, "get_json", lambda *a, **k: empty):
            ev = omim.fetch_gene_omim(None, "ZZZZ")
        self.assertFalse(ev.available)


class CorroborateTests(unittest.TestCase):
    def setUp(self):
        omim._CACHE.clear()

    def test_attaches_evidence_to_every_fit(self):
        fits = [_fit("FBN1"), _fit("SCN1A")]
        with mock.patch.object(omim, "is_configured", lambda: False):
            omim.corroborate(None, fits)
        self.assertTrue(all(f.omim is not None for f in fits))
        self.assertTrue(all(not f.omim.available for f in fits))  # no key -> inert but present


if __name__ == "__main__":
    unittest.main()
