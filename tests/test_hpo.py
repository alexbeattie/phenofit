"""Offline unit tests for HPO free-text term ranking and container filtering.

No network: `_rank_terms` and `_SYSTEM_CONTAINER_RE` are pure. These lock in two
fixes that both defend against the same failure — quietly grounding a feature to
the wrong term:

  1. the Jax search endpoint ranks an over-specific child ("Seizure cluster")
     above the canonical term ("Seizure"); we prefer a name/synonym match.
  2. matching a feature up to a grouping category ("Neurodevelopmental
     abnormality") lets an unrelated gene appear to explain it; those ancestors
     are excluded.

    python -m unittest discover -s tests
"""

from __future__ import annotations

import unittest

from phenofit import hpo


def _term(hpo_id, name, synonyms=None):
    return {"id": hpo_id, "name": name, "synonyms": synonyms or []}


# The real API ordering for the query "Seizure": the canonical term is NOT first.
_SEIZURE_RESULTS = [
    _term("HP:0033349", "Seizure cluster"),
    _term("HP:0002069", "Bilateral tonic-clonic seizure"),
    _term("HP:0007359", "Focal-onset seizure"),
    _term("HP:0001250", "Seizure", synonyms=["Epileptic seizure", "Seizures"]),
]


class RankTermsTests(unittest.TestCase):
    def test_prefers_exact_name_over_api_rank(self):
        best, strong = hpo._rank_terms(_SEIZURE_RESULTS, "Seizure")
        self.assertEqual(best["id"], "HP:0001250")
        self.assertTrue(strong)

    def test_plural_query_matches_singular_term(self):
        best, strong = hpo._rank_terms(_SEIZURE_RESULTS, "Seizures")
        self.assertEqual(best["id"], "HP:0001250")
        self.assertTrue(strong)

    def test_synonym_match_counts_as_strong(self):
        results = [
            _term("HP:0002616", "Aortic root aneurysm", synonyms=["Aortic root dilatation"]),
            _term("HP:9999999", "Something else"),
        ]
        best, strong = hpo._rank_terms(results, "Aortic root dilatation")
        self.assertEqual(best["id"], "HP:0002616")
        self.assertTrue(strong)

    def test_falls_back_to_top_hit_when_no_name_match(self):
        results = [_term("HP:0033258", "Sudden unexpected death in epilepsy"),
                   _term("HP:0002123", "Generalized myoclonic seizure")]
        best, strong = hpo._rank_terms(results, "Epilepsy")
        self.assertEqual(best["id"], "HP:0033258")
        self.assertFalse(strong)  # weak: only the API's top hit, no confident match

    def test_empty_results(self):
        best, strong = hpo._rank_terms([], "Seizure")
        self.assertIsNone(best)
        self.assertFalse(strong)


class ContainerFilterTests(unittest.TestCase):
    def test_organ_system_containers_excluded(self):
        for name in [
            "Abnormality of the cardiovascular system",
            "Abnormal nervous system physiology",
            "Neurodevelopmental abnormality",
            "Skeletal abnormality",
        ]:
            self.assertIsNotNone(hpo._SYSTEM_CONTAINER_RE.match(name), name)

    def test_real_phenotypes_kept(self):
        for name in ["Seizure", "Hypertrophic cardiomyopathy", "Ataxia", "Ectopia lentis"]:
            self.assertIsNone(hpo._SYSTEM_CONTAINER_RE.match(name), name)


if __name__ == "__main__":
    unittest.main()
