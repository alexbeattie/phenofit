"""Evaluation harness: does the true causal gene rank first?

Each fixture is a solved case: a set of the patient's classic clinical features
(real HPO terms) and the gene that actually explains it. We hand the reviewer a
candidate panel made of *every* fixture gene (so each case competes against a
dozen real disease genes, not strawmen), hide which one is the answer, and
measure how often the true gene lands at rank 1.

This tests ranking + discrimination against live HPO data. It is a
sanity/regression eval, NOT a held-out clinical validation: the phenotypes are
curated classic features and the tool matches against the same HPO annotations,
so a real deployment must still be measured on real solved cases. It does show
the engine separates the right gene from unrelated disease genes.

Metrics: top-1 accuracy, top-3 accuracy, mean reciprocal rank.

    python -m phenofit.eval
"""

from __future__ import annotations

from dataclasses import dataclass

from .engine import review_causality
from .http import get_client
from .models import PatientProfile, Phenotype, ReportedVariant


@dataclass
class EvalCase:
    name: str
    true_gene: str
    features: list[Phenotype]


# Curated solved cases. Every HPO term below is a real, present feature of its
# gene's disease (matched exactly or via an is_a ancestor).
CASES: list[EvalCase] = [
    EvalCase("Cystic fibrosis", "CFTR", [
        Phenotype("HP:0002205", "Recurrent respiratory infections"),
        Phenotype("HP:0001738", "Exocrine pancreatic insufficiency"),
        Phenotype("HP:0002110", "Bronchiectasis"),
        Phenotype("HP:0004401", "Meconium ileus"),
        Phenotype("HP:0012236", "Elevated sweat chloride"),
    ]),
    EvalCase("Marfan syndrome", "FBN1", [
        Phenotype("HP:0001083", "Ectopia lentis"),
        Phenotype("HP:0002616", "Aortic root aneurysm"),
        Phenotype("HP:0001166", "Arachnodactyly"),
        Phenotype("HP:0000098", "Tall stature"),
        Phenotype("HP:0000767", "Pectus excavatum"),
    ]),
    EvalCase("Dravet syndrome", "SCN1A", [
        Phenotype("HP:0001250", "Seizure"),
        Phenotype("HP:0001263", "Global developmental delay"),
        Phenotype("HP:0002373", "Febrile seizure"),
        Phenotype("HP:0001251", "Ataxia"),
    ]),
    EvalCase("Hypertrophic cardiomyopathy", "MYH7", [
        Phenotype("HP:0001639", "Hypertrophic cardiomyopathy"),
        Phenotype("HP:0001644", "Dilated cardiomyopathy"),
        Phenotype("HP:0011675", "Arrhythmia"),
        Phenotype("HP:0001635", "Congestive heart failure"),
    ]),
    EvalCase("Familial hypercholesterolemia", "LDLR", [
        Phenotype("HP:0003124", "Hypercholesterolemia"),
        Phenotype("HP:0001114", "Xanthelasma"),
        Phenotype("HP:0001677", "Coronary artery atherosclerosis"),
    ]),
    EvalCase("Long QT syndrome", "KCNQ1", [
        Phenotype("HP:0001657", "Prolonged QT interval"),
        Phenotype("HP:0001279", "Syncope"),
        Phenotype("HP:0001645", "Sudden cardiac death"),
        Phenotype("HP:0004308", "Ventricular arrhythmia"),
    ]),
    EvalCase("Rett syndrome", "MECP2", [
        Phenotype("HP:0002376", "Developmental regression"),
        Phenotype("HP:0000252", "Microcephaly"),
        Phenotype("HP:0001249", "Intellectual disability"),
        Phenotype("HP:0001250", "Seizure"),
    ]),
    EvalCase("Malignant hyperthermia", "RYR1", [
        Phenotype("HP:0002071", "Abnormal extrapyramidal motor function"),
        Phenotype("HP:0003236", "Elevated circulating creatine kinase concentration"),
        Phenotype("HP:0001324", "Muscle weakness"),
    ]),
    EvalCase("Pompe disease", "GAA", [
        Phenotype("HP:0001324", "Muscle weakness"),
        Phenotype("HP:0001638", "Cardiomyopathy"),
        Phenotype("HP:0002093", "Respiratory insufficiency"),
        Phenotype("HP:0003547", "Elevated urinary glucose tetrasaccharide"),
    ]),
]


def _candidate_panel() -> list[str]:
    return sorted({c.true_gene for c in CASES})


def _rank_of(fits, gene: str) -> int:
    for i, f in enumerate(fits, 1):
        if f.variant.gene.upper() == gene.upper():
            return i
    return len(fits) + 1  # not found -> worse than last


def run() -> dict:
    panel = _candidate_panel()
    rows = []
    reciprocal_ranks = []
    top1 = top3 = 0

    with get_client() as client:
        for case in CASES:
            variants = [ReportedVariant(gene=g) for g in panel]
            patient = PatientProfile(phenotypes=case.features)
            report = review_causality(client, patient, variants)
            rank = _rank_of(report.fits, case.true_gene)
            reciprocal_ranks.append(1.0 / rank)
            top1 += rank == 1
            top3 += rank <= 3
            winner = report.fits[0].variant.gene if report.fits else "-"
            rows.append((case.name, case.true_gene, rank, winner))

    n = len(CASES)
    summary = {
        "n": n,
        "top1": top1 / n,
        "top3": top3 / n,
        "mrr": sum(reciprocal_ranks) / n,
        "panel_size": len(panel),
    }
    _print(rows, summary)
    return summary


def _print(rows, summary) -> None:
    print("=" * 72)
    print(f"  PhenoFit ranking eval — {summary['n']} solved cases vs a {summary['panel_size']}-gene panel")
    print("=" * 72)
    print(f"\n  {'case':32s} {'true':7s} {'rank':4s} {'top gene':8s}")
    for name, gene, rank, winner in rows:
        mark = "OK " if rank == 1 else "!! "
        print(f"  {mark}{name:30s} {gene:7s} {rank:>3d}  {winner}")
    print("\n" + "-" * 72)
    print(f"  Top-1 accuracy : {summary['top1']:.0%}  (true gene ranked #1)")
    print(f"  Top-3 accuracy : {summary['top3']:.0%}")
    print(f"  Mean recip.rank: {summary['mrr']:.3f}")
    print()


if __name__ == "__main__":
    run()
