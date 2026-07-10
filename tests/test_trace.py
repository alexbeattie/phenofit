"""Offline unit tests for the decision-trace builder.

No network: `build_trace` is a pure projection of a CausalityReport into a
JSON-serializable record. The trace is the tool's "show your work" artifact — a
per-decision log (which feature each variant matched, exactly or via a broader
term, the weight it carried, the contribution it made to the score) that an eval
or an RL reward model can read. These tests lock its shape and, most importantly,
that the numbers reconcile: the per-feature contributions sum to the reported
score's numerator.

    python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import unittest

from phenofit import trace
from phenofit.models import (
    CausalityReport,
    ExplainedMatch,
    FitTier,
    OmimEvidence,
    PatientProfile,
    Phenotype,
    ReportedVariant,
    VariantFit,
)

SEIZURE = Phenotype("HP:0001250", "Seizure")
DD = Phenotype("HP:0001263", "Global developmental delay")
AORTA = Phenotype("HP:0002616", "Aortic root aneurysm")


def _report() -> CausalityReport:
    patient = PatientProfile(phenotypes=[SEIZURE, DD, AORTA])
    weights = {"HP:0001250": 1.0, "HP:0001263": 0.5, "HP:0002616": 0.9}
    fit = VariantFit(
        variant=ReportedVariant("SCN1A", "c.3637C>T", "p.Arg1213*", "Pathogenic"),
        tier=FitTier.PARTIAL,
        score=(1.0 + 0.5) / (1.0 + 0.5 + 0.9),
        explained=[
            ExplainedMatch(phenotype=SEIZURE, via="Seizure", exact=True, weight=1.0),
            ExplainedMatch(phenotype=DD, via="Neurodevelopmental delay", exact=False, weight=0.5),
        ],
        unexplained=[AORTA],
        diseases=["Dravet syndrome"],
        knowledge_found=True,
        omim=OmimEvidence(gene="SCN1A", available=False, reason="OMIM_API_KEY not set"),
    )
    return CausalityReport(
        patient=patient, fits=[fit], residual_unexplained=[AORTA],
        flags=["one flag"], feature_weights=weights,
    )


class TraceShapeTests(unittest.TestCase):
    def setUp(self):
        self.trace = trace.build_trace(_report())

    def test_is_json_serializable_and_versioned(self):
        blob = json.dumps(self.trace)          # must not raise
        self.assertIn("phenofit.trace", self.trace["schema"])
        self.assertGreater(len(blob), 0)

    def test_patient_features_carry_weights(self):
        feats = {f["hpo_id"]: f for f in self.trace["patient"]["features"]}
        self.assertAlmostEqual(feats["HP:0001250"]["ic_weight"], 1.0)
        self.assertIn("rarity", feats["HP:0001263"])

    def test_variant_carries_consequence_and_omim(self):
        v = self.trace["variants"][0]
        self.assertEqual(v["consequence"]["category"], "nonsense")
        self.assertEqual(v["consequence"]["mechanism"], "loss-of-function")
        self.assertFalse(v["omim"]["available"])

    def test_per_feature_decisions_and_contribution(self):
        v = self.trace["variants"][0]
        decisions = {d["hpo_id"]: d for d in v["decisions"]}
        # Every patient feature has an explicit decision row.
        self.assertEqual(set(decisions), {"HP:0001250", "HP:0001263", "HP:0002616"})
        # Matched exactly, matched-via-broader, and unmatched are distinguished.
        self.assertTrue(decisions["HP:0001250"]["matched"] and decisions["HP:0001250"]["exact"])
        self.assertTrue(decisions["HP:0001263"]["matched"] and not decisions["HP:0001263"]["exact"])
        self.assertFalse(decisions["HP:0002616"]["matched"])
        # Unmatched feature contributes nothing.
        self.assertEqual(decisions["HP:0002616"]["contribution"], 0.0)

    def test_contributions_reconcile_with_score(self):
        v = self.trace["variants"][0]
        explained_weight = sum(d["contribution"] for d in v["decisions"])
        total_weight = sum(f["ic_weight"] for f in self.trace["patient"]["features"])
        self.assertAlmostEqual(explained_weight / total_weight, v["score"]["value"])
        self.assertAlmostEqual(v["score"]["value"], self.trace["variants"][0]["score"]["value"])

    def test_ranking_and_residual_present(self):
        self.assertEqual(self.trace["ranking"][0]["gene"], "SCN1A")
        self.assertEqual(self.trace["residual_unexplained"], ["Aortic root aneurysm"])
        self.assertEqual(self.trace["flags"], ["one flag"])


if __name__ == "__main__":
    unittest.main()
