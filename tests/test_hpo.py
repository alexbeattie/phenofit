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
from unittest import mock

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

    def test_order_and_filler_insensitive_synonym_match(self):
        # Real failure: Claude emits "Dilatation of the aortic root"; the correct
        # term's synonym is "Aortic root dilatation" (reordered, extra fillers),
        # and a differently-named "Aortic arch aneurysm" ranks higher.
        results = [
            _term("HP:0005113", "Aortic arch aneurysm", synonyms=["Aortic arch dilatation"]),
            _term("HP:0002616", "Aortic root aneurysm", synonyms=["Aortic root dilatation"]),
        ]
        best, strong = hpo._rank_terms(results, "Dilatation of the aortic root")
        self.assertEqual(best["id"], "HP:0002616")
        self.assertTrue(strong)

    def test_exact_name_beats_token_synonym_match(self):
        # Bucket order: an exact name hit must win over a looser token hit.
        results = [
            _term("HP:0002616", "Aortic root aneurysm", synonyms=["Aortic root dilatation"]),
            _term("HP:0001234", "Aortic root dilatation"),  # exact name for the query
        ]
        best, strong = hpo._rank_terms(results, "Aortic root dilatation")
        self.assertEqual(best["id"], "HP:0001234")
        self.assertTrue(strong)

    def test_qualifier_strip_helper(self):
        self.assertEqual(hpo._strip_qualifiers("Recurrent seizures"), "seizures")
        self.assertEqual(hpo._strip_qualifiers("Bilateral ectopia lentis"), "ectopia lentis")
        self.assertEqual(hpo._strip_qualifiers("Ectopia lentis"), "ectopia lentis")

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


class SearchQuerySanitizeTests(unittest.TestCase):
    def test_clean_query_strips_parentheticals(self):
        # HPO names carry "(...)" disambiguators; the Jax search endpoint 400s on
        # them. A resolved label round-trips through the UI and gets re-searched.
        self.assertEqual(
            hpo._clean_query("Febrile seizure (within the age range of 3 months to 6 years)"),
            "Febrile seizure",
        )
        self.assertEqual(hpo._clean_query("Seizure"), "Seizure")

    def test_search_survives_400(self):
        def _boom(_client, _url, **_kw):
            import httpx
            raise httpx.HTTPStatusError("400", request=None, response=None)
        with mock.patch.object(hpo, "get_json", _boom):
            self.assertEqual(hpo._search_terms(None, "anything"), [])

    def test_parenthetical_label_round_trips_to_its_term(self):
        # The demo failure end to end: a resolved HPO label carrying a "(...)"
        # disambiguator gets re-searched when it round-trips through the UI. The
        # cleaned query ("Febrile seizure") is what hits the API, but matching runs
        # against the ORIGINAL parenthetical string, so the term's own full name is
        # an exact hit and grounds strongly (not the API's first over-specific hit).
        full = "Febrile seizure (within the age range of 3 months to 6 years)"
        api_terms = [
            _term("HP:0011145", "Generalized-onset motor seizure"),
            _term("HP:0002373", full),
        ]

        def fake_get_json(_client, url, **kw):
            # The real `_search_terms` runs, so this proves the parens were stripped
            # from the query actually sent to the Jax endpoint (which 400s on them).
            self.assertNotIn("(", kw.get("params", {}).get("q", ""))
            return {"terms": api_terms}

        with mock.patch.object(hpo, "get_json", fake_get_json):
            term = hpo.resolve_term(None, full)
        self.assertIsNotNone(term)
        self.assertEqual(term.hpo_id, "HP:0002373")


class ResolveTermRetryTests(unittest.TestCase):
    def test_qualifier_strip_retry_grounds_correctly(self):
        # "Recurrent seizures" -> API top hit is the unrelated "Recurrent boils";
        # stripping "recurrent" and searching "seizures" must recover "Seizure".
        boils = [_term("HP:5210230", "Recurrent boils"),
                 _term("HP:0004419", "Recurrent thrombophlebitis")]
        seizure = [_term("HP:0033349", "Seizure cluster"),
                   _term("HP:0001250", "Seizure", synonyms=["Seizures"])]

        def fake_search(_client, query):
            return seizure if "seizure" in query.lower() and "recurrent" not in query.lower() else boils

        with mock.patch.object(hpo, "_search_terms", fake_search):
            term = hpo.resolve_term(None, "Recurrent seizures")
        self.assertIsNotNone(term)
        self.assertEqual(term.hpo_id, "HP:0001250")


class InformationContentTests(unittest.TestCase):
    def _fake_get_json(self, counts_by_term):
        def _fn(_client, url, **_kw):
            tid = url.rstrip("/").split("/")[-1]
            return {"diseases": [{"id": f"D{i}"} for i in range(counts_by_term.get(tid, 0))]}
        return _fn

    def test_rare_term_has_higher_weight_than_common(self):
        counts = {"HP:RARE": 5, "HP:COMMON": 6000}
        with mock.patch.object(hpo, "get_json", self._fake_get_json(counts)):
            hpo._IC_CACHE.clear()
            w_rare = hpo.ic_weight(None, "HP:RARE")
            w_common = hpo.ic_weight(None, "HP:COMMON")
        self.assertGreater(w_rare, w_common)
        # weights stay within [floor, 1.0]
        self.assertLessEqual(w_rare, 1.0)
        self.assertGreaterEqual(w_common, 0.25)

    def test_unknown_term_degrades_to_floor(self):
        def _boom(_client, _url, **_kw):
            raise RuntimeError("network down")
        with mock.patch.object(hpo, "get_json", _boom):
            hpo._IC_CACHE.clear()
            self.assertEqual(hpo.ic_weight(None, "HP:9999999"), 0.25)  # IC 0 -> floor


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
