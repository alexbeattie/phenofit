"""Offline tests for coordinate resolution + AlphaGenome scoring (no key, no net).

VEP is mocked at the get_json seam; AlphaGenome is injected via the `_scorer`
hook so the summarizer runs on a small pandas fixture. Asserts the contracts:
resolve parses the VCF string and flags non-coding; scoring abstains without a
key or coordinates; the summarizer keeps the strongest signal per output type.
"""

from __future__ import annotations

import unittest
from unittest import mock

import pandas as pd

from phenofit import coords, noncoding
from phenofit.coords import Coordinates

_VEP_OK = [{
    "most_severe_consequence": "intron_variant",
    "vcf_string": "15-48474533-C-T",
    "transcript_consequences": [
        {"consequence_terms": ["intron_variant"], "canonical": 1,
         "hgvsp": "ENSP00000325527.5:p.Cys1361Tyr", "gene_symbol": "FBN1"},
    ],
}]


class CoordsTests(unittest.TestCase):
    def test_resolves_from_vcf_string(self):
        with mock.patch.object(coords, "get_json", lambda *a, **k: _VEP_OK):
            co = coords.resolve(None, "FBN1", "c.4082G>A")
        self.assertTrue(co.resolved)
        self.assertEqual((co.chrom, co.pos, co.ref, co.alt), ("15", 48474533, "C", "T"))
        self.assertEqual(co.variant_id, "15:48474533:C>T")
        self.assertTrue(co.is_noncoding)  # intron_variant

    def test_http_400_is_unresolved_with_reason(self):
        import httpx
        resp = mock.Mock(status_code=400)

        def boom(*a, **k):
            raise httpx.HTTPStatusError("bad", request=mock.Mock(), response=resp)

        with mock.patch.object(coords, "get_json", boom):
            co = coords.resolve(None, "FBN1", "c.bogus")
        self.assertFalse(co.resolved)
        self.assertIn("validate", co.reason.lower())


class NoncodingTests(unittest.TestCase):
    def _coords(self):
        return Coordinates(resolved=True, gene="FBN1", hgvs="FBN1:c.4082G>A",
                           chrom="15", pos=48474533, ref="C", alt="T",
                           consequence="intron_variant")

    def test_abstains_without_key(self):
        res = noncoding.score(self._coords(), api_key="")
        self.assertFalse(res.available)
        self.assertIn("ALPHAGENOME_API_KEY", res.reason)

    def test_abstains_when_unresolved(self):
        res = noncoding.score(
            Coordinates(resolved=False, gene="X", hgvs="X:c.1", reason="VEP said no"),
            api_key="k")
        self.assertFalse(res.available)
        self.assertIn("No coordinates", res.reason)

    def test_summarizes_injected_scores(self):
        def fake_scorer(chrom, pos, ref, alt, keys, *, api_key):
            if "SPLICE_SITES" in keys:
                return pd.DataFrame({
                    "output_type": ["SPLICE_SITES", "SPLICE_SITES"],
                    "gene_name": ["FBN1", "FBN1"],
                    "quantile_score": [0.78, 0.99], "raw_score": [0.01, 0.02],
                })
            return pd.DataFrame({
                "output_type": ["RNA_SEQ"], "gene_name": ["FBN1"],
                "gtex_tissue": ["K562"], "quantile_score": [0.96], "raw_score": [0.9],
            })

        res = noncoding.score(self._coords(), api_key="k", _scorer=fake_scorer)
        self.assertTrue(res.available)
        self.assertTrue(res.research_use_only)
        self.assertEqual(len(res.splicing), 1)             # one SPLICE_SITES signal
        self.assertAlmostEqual(res.splicing[0].quantile, 0.99)  # strongest kept
        self.assertEqual(res.regulatory[0].direction, "up")


if __name__ == "__main__":
    unittest.main()
