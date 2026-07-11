"""Offline unit tests for variant-spec parsing.

No network: `parse_variant_spec` is a pure parse. These lock in that a variant
may be typed with either colons or plain spaces between its fields — because the
space form (`FBN1 c.4082G>A`) is what a user naturally types, and if it isn't
split it reaches the gene-search API as one malformed query and 400s the whole
review.

    python -m unittest discover -s tests
"""

from __future__ import annotations

import unittest

from phenofit.models import parse_variant_spec


class ParseVariantSpecTests(unittest.TestCase):
    def test_colon_delimited(self):
        v = parse_variant_spec("SCN1A:c.3637C>T:p.Arg1213*")
        self.assertEqual(v.gene, "SCN1A")
        self.assertEqual(v.hgvs_c, "c.3637C>T")
        self.assertEqual(v.hgvs_p, "p.Arg1213*")

    def test_space_delimited(self):
        v = parse_variant_spec("SCN1A c.3637C>T p.Arg1213*")
        self.assertEqual(v.gene, "SCN1A")
        self.assertEqual(v.hgvs_c, "c.3637C>T")
        self.assertEqual(v.hgvs_p, "p.Arg1213*")

    def test_gene_and_coding_by_space(self):
        # The exact form that previously 400'd the gene-search endpoint.
        v = parse_variant_spec("FBN1 c.4082G>A")
        self.assertEqual(v.gene, "FBN1")
        self.assertEqual(v.hgvs_c, "c.4082G>A")
        self.assertEqual(v.hgvs_p, "")

    def test_hgvs_order_independent(self):
        v = parse_variant_spec("SCN1A p.Arg1213* c.3637C>T")
        self.assertEqual(v.hgvs_c, "c.3637C>T")
        self.assertEqual(v.hgvs_p, "p.Arg1213*")

    def test_gene_only(self):
        v = parse_variant_spec("FBN1")
        self.assertEqual(v.gene, "FBN1")
        self.assertEqual(v.hgvs_c, "")
        self.assertEqual(v.hgvs_p, "")

    def test_extra_whitespace_collapses(self):
        v = parse_variant_spec("  FBN1   c.4082G>A  ")
        self.assertEqual(v.gene, "FBN1")
        self.assertEqual(v.hgvs_c, "c.4082G>A")

    def test_blank_is_none(self):
        self.assertIsNone(parse_variant_spec("   "))
        self.assertIsNone(parse_variant_spec(""))


if __name__ == "__main__":
    unittest.main()
