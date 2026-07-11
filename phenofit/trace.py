"""Decision trace — the tool's machine-readable "show your work".

A CausalityReport is the human answer; a trace is the same answer decomposed into
every decision the deterministic engine made, in a stable JSON schema. For each
variant it records, per patient feature, whether the gene matched it, whether the
match was exact or via a broader HPO ancestor, the information-content weight the
feature carried, and the contribution that weight made to the score — so the final
number is fully reconstructable from the rows above it.

Why it exists (Matt's "object tracing / evals for RL" thread): a reward model or
an eval harness needs to see the reasoning, not just the verdict. Because scoring
is deterministic and AI-free, this trace is an exact, replayable account — not a
post-hoc rationalization. It is a pure projection of the report: no network, no
model call, no mutation.
"""

from __future__ import annotations

from .engine import rarity_tag
from .models import CausalityReport, VariantFit

SCHEMA = "phenofit.trace/v1"


def _consequence_json(fit: VariantFit) -> dict:
    c = fit.variant.consequence
    return {
        "category": c.category,
        "mechanism": c.mechanism.value,
        "confident": c.confident,
        "notation": c.notation,
        "summary": c.summary,
    }


def _omim_json(fit: VariantFit) -> dict | None:
    ev = fit.omim
    if ev is None:
        return None
    if not ev.available:
        return {"available": False, "reason": ev.reason}
    return {
        "available": True,
        "diseases": [{"name": p.name, "mim": p.mim, "inheritance": p.inheritance}
                     for p in ev.phenotypes],
        "inheritance": ev.inheritance_patterns,
        "source": ev.source.url if ev.source else "",
    }


def _decisions(fit: VariantFit, report: CausalityReport) -> list[dict]:
    """One row per patient feature: matched?/how/weight/contribution."""

    matched = {m.phenotype.hpo_id: m for m in fit.explained}
    rows = []
    for feature in report.patient.phenotypes:
        weight = report.feature_weights.get(feature.hpo_id, 0.0)
        m = matched.get(feature.hpo_id)
        rows.append({
            "hpo_id": feature.hpo_id,
            "label": feature.label,
            "matched": m is not None,
            "exact": bool(m and m.exact),
            "via": m.via if m else "",
            "weight": round(weight, 4),
            # A matched feature contributes its weight; an unmatched one contributes 0.
            "contribution": round(m.weight, 4) if m else 0.0,
        })
    return rows


def build_trace(report: CausalityReport) -> dict:
    """Project a CausalityReport into a JSON-serializable decision trace."""

    features = [
        {
            "hpo_id": p.hpo_id,
            "label": p.label,
            "ic_weight": round(report.feature_weights.get(p.hpo_id, 0.0), 4),
            "rarity": rarity_tag(report.feature_weights.get(p.hpo_id, 0.0)),
        }
        for p in report.patient.phenotypes
    ]

    variants = []
    for fit in report.fits:
        decisions = _decisions(fit, report)
        explained_weight = sum(d["contribution"] for d in decisions)
        total_weight = sum(f["ic_weight"] for f in features) or 1.0
        variants.append({
            "gene": fit.variant.gene,
            "hgvs_c": fit.variant.hgvs_c,
            "hgvs_p": fit.variant.hgvs_p,
            "label": fit.variant.label,
            "lab_classification": fit.variant.lab_classification,
            "knowledge_found": fit.knowledge_found,
            "consequence": _consequence_json(fit),
            "omim": _omim_json(fit),
            "decisions": decisions,
            "score": {
                "explained_weight": round(explained_weight, 4),
                "total_weight": round(total_weight, 4),
                "value": round(fit.score, 4),
                "tier": fit.tier.display,
            },
            "diseases": fit.diseases,
            "source": fit.source.url if fit.source else "",
            "rationale": fit.rationale,
        })

    return {
        "schema": SCHEMA,
        "patient": {"features": features},
        "variants": variants,
        "ranking": [
            {"rank": i, "gene": f.variant.gene, "score": round(f.score, 4), "tier": f.tier.display}
            for i, f in enumerate(report.fits, 1)
        ],
        "residual_unexplained": [p.label for p in report.residual_unexplained],
        "flags": report.flags,
    }
