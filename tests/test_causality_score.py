"""Offline tests for the provisional causality-probability heuristic.

The score is bounded by the phenotype fit and modulated by corroborating
evidence. We assert the contract: abstain when knowledge is absent; never exceed
the fit; a confident loss-of-function + pathogenic + OMIM case scores higher than
an undetermined + VUS one at the same fit.
"""

from __future__ import annotations

import unittest

from phenofit.engine import causality_probability
from phenofit.models import (
    ExplainedMatch,
    FitTier,
    OmimEvidence,
    OmimPhenotype,
    Phenotype,
    ReportedVariant,
    VariantFit,
)

SEIZURE = Phenotype("HP:0001250", "Seizure")


def _fit(*, gene="SCN1A", hgvs_c="", hgvs_p="", classification="", score=0.8,
         exact=True, knowledge=True, omim=False):
    match = ExplainedMatch(phenotype=SEIZURE, via="Seizure", exact=exact, weight=1.0)
    ev = None
    if omim:
        ev = OmimEvidence(gene=gene, available=True,
                          phenotypes=[OmimPhenotype(name="Dravet", mim="607208",
                                                    inheritance="Autosomal dominant")])
    return VariantFit(
        variant=ReportedVariant(gene=gene, hgvs_c=hgvs_c, hgvs_p=hgvs_p,
                                lab_classification=classification),
        tier=FitTier.POSSIBLE, score=score, explained=[match] if score else [],
        knowledge_found=knowledge, omim=ev,
    )


class CausalityScoreTests(unittest.TestCase):
    def test_abstains_without_knowledge(self):
        self.assertIsNone(causality_probability(_fit(score=0.0, knowledge=False)))

    def test_never_exceeds_the_fit(self):
        p = causality_probability(_fit(score=0.8, hgvs_p="p.Arg1213*",
                                       classification="Pathogenic", omim=True))
        self.assertLessEqual(p, 0.8 + 1e-9)
        self.assertGreater(p, 0.0)

    def test_strong_evidence_beats_weak_at_same_fit(self):
        strong = causality_probability(_fit(score=0.8, hgvs_p="p.Arg1213*",
                                            classification="Pathogenic", omim=True))
        weak = causality_probability(_fit(score=0.8, hgvs_c="c.3637C>T",
                                          classification="VUS", exact=False, omim=False))
        self.assertGreater(strong, weak)

    def test_full_fit_full_evidence_reaches_the_fit_ceiling(self):
        p = causality_probability(_fit(score=1.0, hgvs_p="p.Arg1213*",
                                       classification="Pathogenic", omim=True))
        self.assertEqual(p, 1.0)


if __name__ == "__main__":
    unittest.main()
