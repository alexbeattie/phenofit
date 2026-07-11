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

from .hpo import ancestor_ids, fetch_gene_phenotypes, ic_weight
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
from .variant import Mechanism


def _consequence_note(variant: ReportedVariant) -> str:
    """A one-clause annotation of the variant's molecular consequence, or ''.

    Surfaces the *kind* of change (nonsense/missense/frameshift/…) and its broad
    mechanism next to the phenotype fit — the clinician's other axis. It never
    changes the score: mechanism-to-disease compatibility needs per-gene curation
    we don't claim to have, so this annotates, it doesn't weigh.
    """

    cons = variant.consequence
    if cons.mechanism is Mechanism.UNKNOWN:
        return ""
    notation = f" {cons.notation}" if cons.notation else ""
    return f" Variant{notation}: {cons.summary}."

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


def rarity_tag(weight: float) -> str:
    """Human label for an information-content weight (rare features score more).

    Cutoffs are calibrated against the IC weight of real HPO terms (weight =
    0.25 + 0.75 * IC/IC_max, with IC_max the theoretical single-disease maximum):
    a term annotated to under ~1% of diseases lands around 0.6+ ("rare"), the 1-10%
    band around 0.42-0.6 ("uncommon"), and the common tail below that. This keeps a
    genuinely specific finding like Ectopia lentis labelled "rare" rather than the
    compressed value the raw normalization would suggest.
    """
    if weight >= 0.6:
        return "rare"
    if weight >= 0.42:
        return "uncommon"
    return "common"


def _consequence_confidence(fit: VariantFit) -> float:
    """How much the variant's molecular consequence supports a causal role, 0-1."""

    c = fit.variant.consequence
    if c.mechanism is Mechanism.LOSS_OF_FUNCTION:
        return 1.0 if c.confident else 0.8
    if c.mechanism is Mechanism.ALTERED_PROTEIN:
        return 0.75
    if c.mechanism is Mechanism.SILENT:
        return 0.25
    return 0.5  # UNDETERMINED / UNKNOWN — neutral; we don't claim to know


def _classification_prior(lab_classification: str) -> float:
    """Turn the lab's own call into a 0-1 prior (empty/unknown -> neutral 0.5)."""

    s = (lab_classification or "").strip().lower()
    if not s:
        return 0.5
    if "benign" in s:
        return 0.15 if "likely" in s else 0.1
    if "pathogenic" in s:
        return 0.85 if "likely" in s else 1.0
    if "uncertain" in s or "vus" in s:
        return 0.4
    return 0.5


def causality_probability(fit: VariantFit) -> float | None:
    """Provisional 0-1 estimate that this variant causes the patient's picture.

    HEURISTIC, not outcome-trained. Bounded by the rarity-weighted phenotype fit
    (causality requires the phenotype to actually fit), then scaled within
    [0.7, 1.0] by corroborating evidence: how *exact* the phenotype matches are,
    the molecular consequence, the lab's own classification, and whether OMIM
    corroborates the gene-disease link. Returns None when gene knowledge is absent
    (abstain, never guess) — the same contract the score follows. Matt asked for a
    0-1 causality number; this is the honest interim until labeled pathogenic
    variant->disease cases let us train and calibrate a real one.
    """

    if not fit.knowledge_found:
        return None
    signals: list[float] = []
    if fit.explained:  # fraction of matches that are exact (vs broadened ancestors)
        signals.append(sum(1 for m in fit.explained if m.exact) / len(fit.explained))
    signals.append(_consequence_confidence(fit))
    signals.append(_classification_prior(fit.variant.lab_classification))
    if fit.omim is not None and getattr(fit.omim, "available", False):
        signals.append(1.0)  # curated corroboration only adds, never penalizes
    evidence = sum(signals) / len(signals) if signals else 0.5
    return round(fit.score * (0.7 + 0.3 * evidence), 3)


def _match_feature(
    client: httpx.Client, feature: Phenotype, knowledge: GenePhenotypeKnowledge, weight: float
) -> ExplainedMatch | None:
    """Does the gene explain this patient feature, exactly or via a broader term?"""

    if feature.hpo_id in knowledge.phenotype_ids:
        return ExplainedMatch(phenotype=feature, via=feature.label, exact=True, weight=weight)

    # Ontology-aware: a gene annotated to a broader term (e.g. Seizure) explains
    # the patient's more specific feature (e.g. Focal-onset seizure).
    ancestors = ancestor_ids(client, feature.hpo_id)
    broader = ancestors & knowledge.phenotype_ids
    if broader:
        via_label = next(
            (knowledge.phenotype_labels[a] for a in broader if a in knowledge.phenotype_labels),
            "",
        )
        return ExplainedMatch(phenotype=feature, via=via_label or feature.label, exact=False, weight=weight)
    return None


def _score_one(
    client: httpx.Client,
    variant: ReportedVariant,
    patient: PatientProfile,
    knowledge: GenePhenotypeKnowledge,
    weights: dict[str, float],
) -> VariantFit:
    if not knowledge.found:
        return VariantFit(
            variant=variant,
            tier=FitTier.UNLIKELY,
            score=0.0,
            unexplained=list(patient.phenotypes),
            rationale=(
                f"No HPO gene-phenotype knowledge found for {variant.gene}; cannot assess fit."
                + _consequence_note(variant)
            ),
            source=knowledge.source,
            knowledge_found=False,
        )

    explained: list[ExplainedMatch] = []
    unexplained: list[Phenotype] = []
    for feature in patient.phenotypes:
        match = _match_feature(client, feature, knowledge, weights[feature.hpo_id])
        if match is not None:
            explained.append(match)
        else:
            unexplained.append(feature)

    # Score is the fraction of the patient's features the gene explains, but
    # weighted by each feature's information content: a gene that explains one
    # rare, specific finding scores higher than one that explains several common,
    # non-specific ones. Falls back to plain fraction if IC couldn't be fetched
    # (all weights equal).
    total_weight = sum(weights[p.hpo_id] for p in patient.phenotypes) or 1.0
    explained_weight = sum(m.weight for m in explained)
    score = explained_weight / total_weight
    tier = _tier_for(score)

    disease_hint = f" ({knowledge.diseases[0]})" if knowledge.diseases else ""
    rationale = (
        f"{variant.gene}{disease_hint} explains {len(explained)}/{len(patient.phenotypes)} "
        f"of the patient's features (weighted by rarity: {score:.0%})"
    )
    if unexplained:
        rationale += f"; leaves unexplained: {', '.join(p.label for p in unexplained)}."
    else:
        rationale += "; accounts for the full presented picture."
    rationale += _consequence_note(variant)

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
    # Information-content weight for each presented feature, computed once and
    # shared across all variants so a rare finding pulls its weight consistently.
    weights = {p.hpo_id: ic_weight(client, p.hpo_id) for p in patient.phenotypes}

    fits: list[VariantFit] = []
    for v in variants:
        knowledge = fetch_gene_phenotypes(client, v.gene)
        fits.append(_score_one(client, v, patient, knowledge, weights))

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

    report = CausalityReport(
        patient=patient, fits=fits, residual_unexplained=residual, feature_weights=weights
    )
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
