"""CLI: rank the reported variants by how well each explains a patient.

    # hardcoded demo case (dual diagnosis: SCN1A + FBN1)
    python -m phenofit.cli

    # your own case: reported variants (gene[:hgvs]) + patient features
    python -m phenofit.cli \
        --variant SCN1A:c.3637C>T --variant FBN1:c.4082G>A \
        --hpo "seizures" --hpo "ectopia lentis" --hpo "aortic root dilatation"

    # let the AI edge read the phenotype out of free-text notes
    python -m phenofit.cli --variant SCN1A --variant FBN1 \
        --notes "4yo with seizures, developmental delay, ectopia lentis, tall stature"
"""

from __future__ import annotations

import argparse

from .config import load_dotenv
from .engine import rarity_tag, review_causality
from .extract import extract_from_notes
from .hpo import resolve_term
from .http import get_client
from .llm import LLMError
from .models import CausalityReport, PatientProfile, Phenotype, ReportedVariant, parse_variant_spec
from .variant import Mechanism

# Hardcoded demo: a 4yo with a mixed neuro + connective-tissue picture. The lab
# reported three candidates. No single one explains everything — SCN1A covers the
# seizures/DD/ataxia, FBN1 covers the ectopia lentis/aortic root/tall stature —
# so the review should flag a possible dual diagnosis.
# hgvs_p is filled so the demo shows the protein-level axis Matt asked for: the
# SCN1A change is a nonsense/loss-of-function (the Dravet mechanism), the others
# missense — a distinction gene-level matching alone is blind to.
DEMO_VARIANTS = [
    ReportedVariant("SCN1A", "c.3637C>T", "p.Arg1213*", "Pathogenic"),
    ReportedVariant("FBN1", "c.4082G>A", "p.Cys1361Tyr", "Likely pathogenic"),
    ReportedVariant("MYH7", "c.1063G>A", "p.Ala355Thr", "VUS"),
]
DEMO_HPO = [
    Phenotype("HP:0001250", "Seizure"),
    Phenotype("HP:0001263", "Global developmental delay"),
    Phenotype("HP:0002066", "Gait ataxia"),
    Phenotype("HP:0001083", "Ectopia lentis"),
    Phenotype("HP:0002616", "Aortic root aneurysm"),
    Phenotype("HP:0000098", "Tall stature"),
    Phenotype("HP:0001166", "Arachnodactyly"),
]


def _print_report(report: CausalityReport) -> None:
    p = report.patient
    print("=" * 74)
    print("  PhenoFit — does a reported variant explain THIS patient?")
    print("=" * 74)

    print("\n[patient] presented features (HPO)")
    for ph in p.phenotypes:
        print(f"  - {ph.hpo_id:12s} {ph.label}")

    print("\n[causality ranking] reported variants, best fit first")
    print("  (score is rarity-weighted: a rare, specific finding counts more than a common one)")
    for rank, f in enumerate(report.fits, 1):
        pct = f" {f.score:.0%}" if f.knowledge_found else ""
        print(
            f"\n  {rank}. [{f.tier.stars}] {f.variant.label:22s} "
            f"{f.tier.display:9s} (explains {len(f.explained)}/{len(p.phenotypes)}{pct})"
        )
        if f.variant.lab_classification:
            print(f"       lab call  : {f.variant.lab_classification}")
        cons = f.variant.consequence
        if cons.mechanism is not Mechanism.UNKNOWN:
            print(f"       variant   : {cons.summary}")
        if f.explained:
            parts = [f"{m.display} [{rarity_tag(m.weight)}]" for m in f.explained]
            print(f"       explains  : {', '.join(parts)}")
        if f.unexplained:
            print(f"       leaves    : {', '.join(ph.label for ph in f.unexplained)}")
        if f.diseases:
            print(f"       disease   : {'; '.join(f.diseases[:3])}")
        if f.source:
            print(f"       source    : {f.source.url}")

    if report.flags:
        print("\n[flags] what the clinician should weigh")
        for fl in report.flags:
            print(f"  - {fl}")
    print()


def _build_patient(client, hpo_args: list[str]) -> list[Phenotype]:
    phenotypes: list[Phenotype] = []
    for raw in hpo_args:
        term = resolve_term(client, raw)
        if term is None:
            print(f"  (could not resolve HPO term for {raw!r}; skipping)")
            continue
        phenotypes.append(term)
    return phenotypes


def _phenotypes_from_notes(client, args) -> list[Phenotype]:
    notes = args.notes
    if args.notes_file:
        with open(args.notes_file, encoding="utf-8") as fh:
            notes = fh.read()
    if not notes:
        return []
    try:
        result = extract_from_notes(client, notes)
    except LLMError as exc:
        print(f"  (AI extraction unavailable: {exc})")
        return []
    for e in result.phenotypes:
        print(f"  [AI] {e.phrase!r} -> {e.phenotype.hpo_id} {e.phenotype.label}")
    for phrase in result.ungrounded:
        print(f"  [AI] {phrase!r} -> (no HPO match; skipped)")
    return result.deduped_phenotypes()


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Rank reported variants by fit to a patient.")
    parser.add_argument(
        "--variant", action="append", default=[],
        help="Reported variant as GENE or GENE:hgvs, e.g. SCN1A:c.3637C>T (repeatable)",
    )
    parser.add_argument(
        "--hpo", action="append", default=[],
        help="Patient feature as free text or HP:xxxxxxx (repeatable)",
    )
    parser.add_argument("--notes", help="Free-text clinical notes; the AI edge extracts the phenotypes")
    parser.add_argument("--notes-file", help="Path to a file of clinical notes (AI extraction)")
    args = parser.parse_args()

    with get_client() as client:
        if args.variant and (args.hpo or args.notes or args.notes_file):
            variants = [v for v in (parse_variant_spec(s) for s in args.variant) if v]
            phenotypes = _build_patient(client, args.hpo) if args.hpo else []
            phenotypes += _phenotypes_from_notes(client, args)
            patient = PatientProfile(phenotypes=phenotypes)
        else:
            print("(no --variant/--hpo given; running the hardcoded demo case)\n")
            variants = DEMO_VARIANTS
            patient = PatientProfile(phenotypes=DEMO_HPO)

        if not patient.phenotypes:
            print("No resolvable patient features; nothing to score.")
            raise SystemExit(2)

        report = review_causality(client, patient, variants)
        _print_report(report)


if __name__ == "__main__":
    main()
