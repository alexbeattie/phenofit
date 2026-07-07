"""Causality-scoring engine.

Given a patient's HPO phenotype set and the variants the lab reported, score how
well each variant's gene explains THIS patient, rank them, and surface the two
traps a clinician's intuition falls into:

  1. Overfitting — we score against an explicit feature set, so a partial match
     reads as "explains 3/5", not "close enough".
  2. Partial explanations — features left unexplained by every reported variant
     are called out, because they may mean an unreported second cause. That is
     the trigger to re-analyze the genome, not a failure of the review.
"""

from __future__ import annotations

import httpx

from .hpo import ancestor_ids, fetch_gene_phenotypes
from .models import (
    CausalityReport,
    ExplainedMatch,
    FitTier,
    GenePhenotypeKnowledge,
    PatientProfile,
    Phenotype,
    ReportedVariant,
    VariantFit,
)

# Fraction of the patient's features a gene must explain to reach each tier.
_TIER_THRESHOLDS = [
    (1.0, FitTier.BEST_FIT),
    (0.6, FitTier.POSSIBLE),
    (0.3, FitTier.PARTIAL),
    (0.0001, FitTier.WEAK),
]


def _tier_for(score: float) -> FitTier:
    for threshold, tier in _TIER_THRESHOLDS:
        if score >= threshold:
            return tier
    return FitTier.UNLIKELY


def _match_feature(
    client: httpx.Client, feature: Phenotype, knowledge: GenePhenotypeKnowledge
) -> ExplainedMatch | None:
    """Does the gene explain this patient feature, exactly or via a broader term?"""

    if feature.hpo_id in knowledge.phenotype_ids:
        return ExplainedMatch(phenotype=feature, via=feature.label, exact=True)

    # Ontology-aware: a gene annotated to a broader term (e.g. Seizure) explains
    # the patient's more specific feature (e.g. Focal-onset seizure).
    ancestors = ancestor_ids(client, feature.hpo_id)
    broader = ancestors & knowledge.phenotype_ids
    if broader:
        via_label = next(
            (knowledge.phenotype_labels[a] for a in broader if a in knowledge.phenotype_labels),
            "",
        )
        return ExplainedMatch(phenotype=feature, via=via_label or feature.label, exact=False)
    return None


def _score_one(
    client: httpx.Client, variant: ReportedVariant, patient: PatientProfile, knowledge: GenePhenotypeKnowledge
) -> VariantFit:
    if not knowledge.found:
        return VariantFit(
            variant=variant,
            tier=FitTier.UNLIKELY,
            score=0.0,
            unexplained=list(patient.phenotypes),
            rationale=f"No HPO gene-phenotype knowledge found for {variant.gene}; cannot assess fit.",
            source=knowledge.source,
            knowledge_found=False,
        )

    explained: list[ExplainedMatch] = []
    unexplained: list[Phenotype] = []
    for feature in patient.phenotypes:
        match = _match_feature(client, feature, knowledge)
        if match is not None:
            explained.append(match)
        else:
            unexplained.append(feature)

    total = len(patient.phenotypes) or 1
    score = len(explained) / total
    tier = _tier_for(score)

    disease_hint = f" ({knowledge.diseases[0]})" if knowledge.diseases else ""
    rationale = (
        f"{variant.gene}{disease_hint} explains {len(explained)}/{total} of the "
        f"patient's features"
    )
    if unexplained:
        rationale += f"; leaves unexplained: {', '.join(p.label for p in unexplained)}."
    else:
        rationale += "; accounts for the full presented picture."

    return VariantFit(
        variant=variant,
        tier=tier,
        score=score,
        explained=explained,
        unexplained=unexplained,
        diseases=knowledge.diseases,
        rationale=rationale,
        source=knowledge.source,
    )


def review_causality(
    client: httpx.Client, patient: PatientProfile, variants: list[ReportedVariant]
) -> CausalityReport:
    fits: list[VariantFit] = []
    for v in variants:
        knowledge = fetch_gene_phenotypes(client, v.gene)
        fits.append(_score_one(client, v, patient, knowledge))

    # Rank purely on fit so the ordering stays objective. Tie-break toward the
    # gene with more EXACT phenotype matches (vs broadened ancestor matches): a
    # gene annotated to the patient's precise feature is a better explanation
    # than one that only matches a more general term.
    fits.sort(
        key=lambda f: (f.score, sum(m.exact for m in f.explained), len(f.explained)),
        reverse=True,
    )

    # Features explained by NO reported variant at all.
    explained_ids = {m.phenotype.hpo_id for f in fits for m in f.explained}
    residual = [p for p in patient.phenotypes if p.hpo_id not in explained_ids]

    report = CausalityReport(patient=patient, fits=fits, residual_unexplained=residual)
    report.flags = _build_flags(fits, residual, len(patient.phenotypes))
    return report


def _build_flags(fits: list[VariantFit], residual: list, n_features: int) -> list[str]:
    flags: list[str] = []
    top = fits[0] if fits else None

    if top and top.tier == FitTier.BEST_FIT:
        flags.append(
            f"Strong single-variant fit: {top.variant.label} explains the full presented picture."
        )
    elif top and top.explained:
        flags.append(
            f"No single variant explains everything; best candidate ({top.variant.label}) "
            f"explains {len(top.explained)}/{n_features}."
        )

    # Dual diagnosis: no single variant covers the picture, but a second reported
    # variant explains features the top one does not, and together they cover
    # (nearly) everything. This is the ~5% "second independent cause" case.
    if top and top.tier != FitTier.BEST_FIT:
        top_ids = {m.phenotype.hpo_id for m in top.explained}
        union_ids = {m.phenotype.hpo_id for f in fits for m in f.explained}
        complementary = [
            f for f in fits[1:]
            if {m.phenotype.hpo_id for m in f.explained} - top_ids
        ]
        if complementary and len(union_ids) > len(top_ids) and len(union_ids) >= n_features - len(residual):
            second = complementary[0]
            extra = ", ".join(
                m.phenotype.label for m in second.explained
                if m.phenotype.hpo_id not in top_ids
            )
            flags.append(
                f"Possible dual diagnosis (two independent causes, ~5% of solved cases): "
                f"{second.variant.label} additionally explains {extra}, which "
                f"{top.variant.label} does not. Consider both variants as contributing."
            )

    if residual:
        labels = ", ".join(p.label for p in residual)
        flags.append(
            f"{len(residual)} feature(s) explained by NO reported variant ({labels}). "
            "Consider an unreported extension of a listed gene's phenotype, a second "
            "independent cause (~5% of solved cases), or genome re-analysis to chase them down."
        )

    for f in fits:
        if not f.knowledge_found:
            flags.append(f"Could not retrieve HPO knowledge for {f.variant.gene}; its fit is unscored.")

    return flags
