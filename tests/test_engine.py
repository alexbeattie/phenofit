"""Offline unit tests for the scoring engine.

No network: the HPO client calls (`fetch_gene_phenotypes`, `ancestor_ids`) are
patched with a small fake ontology, so these test the ranking, tiering,
explained/unexplained split, and flag logic deterministically.

    python -m unittest discover -s tests
"""

from __future__ import annotations

import unittest
from unittest import mock

from phenofit import engine
from phenofit.models import (
    FitTier,
    GenePhenotypeKnowledge,
    PatientProfile,
    Phenotype,
    ReportedVariant,
)

# --- a tiny fake ontology --------------------------------------------------
# is_a edges (child -> parent) for ancestor expansion.
_PARENTS = {
    "HP:FOCAL_SEIZURE": ["HP:SEIZURE"],
    "HP:SEIZURE": [],
    "HP:DD": [],
    "HP:CLEFT": [],
    "HP:AORTA": [],
}

# Gene -> exact annotated phenotype ids.
_GENE_PH = {
    "SCN1A": {"HP:SEIZURE", "HP:DD"},
    "FBN1": {"HP:AORTA", "HP:DD"},
    "EMPTY": set(),
}


def _fake_ancestors(_client, hpo_id: str) -> set[str]:
    ids = {hpo_id}
    stack = list(_PARENTS.get(hpo_id, []))
    while stack:
        p = stack.pop()
        ids.add(p)
        stack.extend(_PARENTS.get(p, []))
    return ids


def _fake_gene(_client, gene: str) -> GenePhenotypeKnowledge:
    ids = _GENE_PH.get(gene.upper())
    if ids is None:
        return GenePhenotypeKnowledge(gene=gene, found=False)
    return GenePhenotypeKnowledge(
        gene=gene,
        found=bool(ids),
        diseases=[f"{gene}-disease"] if ids else [],
        phenotype_ids=set(ids),
        phenotype_labels={i: i for i in ids},
    )


def _equal_weight(_client, _hpo_id, **_kw):
    return 1.0


def _weights_of(patient, w=1.0):
    return {p.hpo_id: w for p in patient.phenotypes}


SEIZURE = Phenotype("HP:SEIZURE", "Seizure")
FOCAL = Phenotype("HP:FOCAL_SEIZURE", "Focal seizure")
DD = Phenotype("HP:DD", "Developmental delay")
CLEFT = Phenotype("HP:CLEFT", "Cleft palate")
AORTA = Phenotype("HP:AORTA", "Aortic aneurysm")


class TierTests(unittest.TestCase):
    def test_stars_and_thresholds(self):
        self.assertEqual(FitTier.BEST_FIT.stars, "****")
        self.assertEqual(FitTier.UNLIKELY.stars, "....")
        self.assertEqual(engine._tier_for(1.0), FitTier.BEST_FIT)
        self.assertEqual(engine._tier_for(0.6), FitTier.POSSIBLE)
        self.assertEqual(engine._tier_for(0.3), FitTier.PARTIAL)
        self.assertEqual(engine._tier_for(0.1), FitTier.WEAK)
        self.assertEqual(engine._tier_for(0.0), FitTier.UNLIKELY)


class MatchTests(unittest.TestCase):
    @mock.patch.object(engine, "ancestor_ids", _fake_ancestors)
    def test_exact_match(self):
        k = _fake_gene(None, "SCN1A")
        m = engine._match_feature(None, SEIZURE, k, 1.0)
        self.assertIsNotNone(m)
        self.assertTrue(m.exact)

    @mock.patch.object(engine, "ancestor_ids", _fake_ancestors)
    def test_ancestor_match_is_not_exact(self):
        # Patient has focal seizure; gene annotated only to the broader Seizure.
        k = _fake_gene(None, "SCN1A")
        m = engine._match_feature(None, FOCAL, k, 1.0)
        self.assertIsNotNone(m)
        self.assertFalse(m.exact)
        self.assertIn("via broader", m.display)

    @mock.patch.object(engine, "ancestor_ids", _fake_ancestors)
    def test_no_match(self):
        k = _fake_gene(None, "SCN1A")
        self.assertIsNone(engine._match_feature(None, AORTA, k, 1.0))


class ScoreTests(unittest.TestCase):
    @mock.patch.object(engine, "ancestor_ids", _fake_ancestors)
    def test_partial_score_and_unexplained(self):
        patient = PatientProfile(phenotypes=[SEIZURE, DD, CLEFT])
        k = _fake_gene(None, "SCN1A")  # explains seizure + dd, not cleft
        fit = engine._score_one(None, ReportedVariant("SCN1A"), patient, k, _weights_of(patient))
        self.assertEqual(len(fit.explained), 2)
        self.assertEqual([p.label for p in fit.unexplained], ["Cleft palate"])
        self.assertAlmostEqual(fit.score, 2 / 3)  # equal weights -> plain fraction
        self.assertEqual(fit.tier, FitTier.POSSIBLE)

    @mock.patch.object(engine, "ancestor_ids", _fake_ancestors)
    def test_rare_feature_outweighs_common_ones(self):
        # CLEFT is rare (weight 3), SEIZURE + DD common (weight 1 each). A gene
        # explaining only the rare feature should outscore one explaining the two
        # common ones — the whole point of information-content weighting.
        patient = PatientProfile(phenotypes=[SEIZURE, DD, CLEFT])
        weights = {"HP:SEIZURE": 1.0, "HP:DD": 1.0, "HP:CLEFT": 3.0}

        # A fake gene annotated only to the rare CLEFT.
        rare_gene = GenePhenotypeKnowledge(
            gene="RARE", found=True, diseases=["rare-disease"],
            phenotype_ids={"HP:CLEFT"}, phenotype_labels={"HP:CLEFT": "Cleft palate"},
        )
        common_fit = engine._score_one(None, ReportedVariant("SCN1A"), patient, _fake_gene(None, "SCN1A"), weights)
        rare_fit = engine._score_one(None, ReportedVariant("RARE"), patient, rare_gene, weights)
        # common explains 2/5 weight, rare explains 3/5 weight.
        self.assertAlmostEqual(common_fit.score, 2 / 5)
        self.assertAlmostEqual(rare_fit.score, 3 / 5)
        self.assertGreater(rare_fit.score, common_fit.score)

    @mock.patch.object(engine, "ancestor_ids", _fake_ancestors)
    def test_missing_knowledge_abstains(self):
        patient = PatientProfile(phenotypes=[SEIZURE])
        fit = engine._score_one(None, ReportedVariant("EMPTY"), patient, _fake_gene(None, "EMPTY"), _weights_of(patient))
        self.assertFalse(fit.knowledge_found)
        self.assertEqual(fit.tier, FitTier.UNLIKELY)


class ReviewTests(unittest.TestCase):
    @mock.patch.object(engine, "ic_weight", _equal_weight)
    @mock.patch.object(engine, "ancestor_ids", _fake_ancestors)
    @mock.patch.object(engine, "fetch_gene_phenotypes", _fake_gene)
    def test_ranking_and_residual(self):
        patient = PatientProfile(phenotypes=[SEIZURE, DD, CLEFT])
        report = engine.review_causality(None, patient, [ReportedVariant("FBN1"), ReportedVariant("SCN1A")])
        # SCN1A explains 2/3, FBN1 explains 1/3 -> SCN1A ranks first.
        self.assertEqual(report.fits[0].variant.gene, "SCN1A")
        # Cleft palate explained by neither gene -> residual.
        self.assertEqual([p.label for p in report.residual_unexplained], ["Cleft palate"])

    @mock.patch.object(engine, "ic_weight", _equal_weight)
    @mock.patch.object(engine, "ancestor_ids", _fake_ancestors)
    @mock.patch.object(engine, "fetch_gene_phenotypes", _fake_gene)
    def test_dual_diagnosis_flag(self):
        # SCN1A explains seizure; FBN1 explains aorta; together they cover all.
        patient = PatientProfile(phenotypes=[SEIZURE, AORTA])
        report = engine.review_causality(None, patient, [ReportedVariant("SCN1A"), ReportedVariant("FBN1")])
        self.assertTrue(any("dual diagnosis" in f.lower() for f in report.flags))

    @mock.patch.object(engine, "ic_weight", _equal_weight)
    @mock.patch.object(engine, "ancestor_ids", _fake_ancestors)
    @mock.patch.object(engine, "fetch_gene_phenotypes", _fake_gene)
    def test_ancestor_match_ranks_and_is_broad(self):
        patient = PatientProfile(phenotypes=[FOCAL])
        report = engine.review_causality(None, patient, [ReportedVariant("SCN1A")])
        self.assertEqual(report.fits[0].variant.gene, "SCN1A")
        self.assertFalse(report.fits[0].explained[0].exact)


if __name__ == "__main__":
    unittest.main()
