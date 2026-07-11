"""Offline unit tests for molecular-consequence classification.

No network: `classify` is a pure parse of HGVS notation. These lock the one thing
the classifier is allowed to assert — the *category* of change and its broad
mechanism (loss-of-function vs altered-protein) — and, just as important, that it
ABSTAINS ("undetermined") when the notation cannot support a call, rather than
guessing. Overcalling a variant's effect is exactly the invisible failure this
tool exists to avoid.

    python -m unittest discover -s tests
"""

from __future__ import annotations

import unittest

from phenofit.variant import Mechanism, classify


class ProteinNotationTests(unittest.TestCase):
    def test_nonsense_is_loss_of_function(self):
        for p in ["p.Arg1213*", "p.Arg1213Ter", "p.(Arg1213*)", "p.R1213*"]:
            c = classify("", p)
            self.assertEqual(c.category, "nonsense", p)
            self.assertEqual(c.mechanism, Mechanism.LOSS_OF_FUNCTION, p)
            self.assertTrue(c.confident, p)

    def test_frameshift_is_loss_of_function(self):
        for p in ["p.Gly1213fs", "p.Gly1213GlyfsTer5", "p.Gly1213ValfsTer7"]:
            c = classify("", p)
            self.assertEqual(c.category, "frameshift", p)
            self.assertEqual(c.mechanism, Mechanism.LOSS_OF_FUNCTION, p)

    def test_missense_is_altered_protein(self):
        for p in ["p.Gly1213Asp", "p.G1213D", "p.(Arg502Trp)"]:
            c = classify("", p)
            self.assertEqual(c.category, "missense", p)
            self.assertEqual(c.mechanism, Mechanism.ALTERED_PROTEIN, p)

    def test_inframe_deletion_is_altered_protein(self):
        c = classify("", "p.Phe508del")
        self.assertEqual(c.category, "inframe indel")
        self.assertEqual(c.mechanism, Mechanism.ALTERED_PROTEIN)

    def test_synonymous_is_silent(self):
        c = classify("", "p.Leu100=")
        self.assertEqual(c.category, "synonymous")
        self.assertEqual(c.mechanism, Mechanism.SILENT)

    def test_start_loss_is_loss_of_function(self):
        for p in ["p.Met1?", "p.Met1Val", "p.M1?"]:
            c = classify("", p)
            self.assertEqual(c.category, "start loss", p)
            self.assertEqual(c.mechanism, Mechanism.LOSS_OF_FUNCTION, p)


class CodingNotationTests(unittest.TestCase):
    def test_canonical_splice_is_loss_of_function(self):
        for c_hgvs in ["c.1140+1G>A", "c.1140-2A>G", "c.264+1del"]:
            c = classify(c_hgvs, "")
            self.assertEqual(c.category, "splice", c_hgvs)
            self.assertEqual(c.mechanism, Mechanism.LOSS_OF_FUNCTION, c_hgvs)

    def test_single_base_indel_is_frameshift(self):
        for c_hgvs in ["c.1013del", "c.1013dup", "c.1013_1014insA"]:
            c = classify(c_hgvs, "")
            self.assertEqual(c.category, "frameshift", c_hgvs)
            self.assertEqual(c.mechanism, Mechanism.LOSS_OF_FUNCTION, c_hgvs)

    def test_inframe_deletion_from_coding_span(self):
        # A 3-nucleotide deletion keeps frame: in-frame, not frameshift.
        c = classify("c.1013_1015del", "")
        self.assertEqual(c.category, "inframe indel")
        self.assertEqual(c.mechanism, Mechanism.ALTERED_PROTEIN)

    def test_substitution_alone_is_undetermined(self):
        # A coding substitution could be missense, nonsense, or synonymous; the
        # coding notation alone cannot say which, so we must NOT guess.
        c = classify("c.3637C>T", "")
        self.assertEqual(c.category, "substitution")
        self.assertEqual(c.mechanism, Mechanism.UNDETERMINED)
        self.assertFalse(c.confident)


class PrecedenceAndFallbackTests(unittest.TestCase):
    def test_protein_notation_wins_over_coding(self):
        # Given both, the protein-level call is the precise one.
        c = classify("c.3637C>T", "p.Arg1213*")
        self.assertEqual(c.category, "nonsense")
        self.assertEqual(c.mechanism, Mechanism.LOSS_OF_FUNCTION)

    def test_empty_input_is_unknown(self):
        c = classify("", "")
        self.assertEqual(c.mechanism, Mechanism.UNKNOWN)
        self.assertFalse(c.confident)

    def test_summary_is_human_readable(self):
        c = classify("", "p.Arg1213*")
        self.assertIn("nonsense", c.summary.lower())
        self.assertIn("loss-of-function", c.summary.lower())


if __name__ == "__main__":
    unittest.main()
