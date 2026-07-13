"""AlphaGenome — non-coding / splicing / regulatory scoring (Task 3).

Intronic and regulatory variants are exactly what a coding-consequence view is
blind to: they aren't missense or nonsense, yet they cause disease by creating
cryptic splice sites, disrupting branch points, or altering enhancer/promoter
activity. AlphaGenome (Google DeepMind) scores those effects directly from
genomic coordinates, so this is what lets PhenoFit reason about the non-coding
path Matt asked about.

Contract, matching the rest of the tool:
  - Needs `ALPHAGENOME_API_KEY` (free, research use) and the `alphagenome` package.
    Both are imported lazily; with either missing, or on any API error, we return
    `available=False` + a reason — never a fabricated score.
  - Predictions are a research model, not clinically validated: `research_use_only`
    is always True, surfaced wherever scores are shown.
  - Deterministic model output; the AI ingestion edge is not involved.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .coords import Coordinates
from .http import now_iso
from .models import Source

API_KEY_ENV = "ALPHAGENOME_API_KEY"
ALPHAGENOME_URL = "https://deepmind.google.com/science/alphagenome"

SPLICING_SCORERS = ("SPLICE_SITES", "SPLICE_SITE_USAGE", "SPLICE_JUNCTIONS")
REGULATORY_SCORERS = ("RNA_SEQ", "CAGE", "PROCAP", "DNASE", "ATAC", "CHIP_TF", "CHIP_HISTONE")

_SPLICING_PHRASE = {
    "SPLICE_SITES": "predicted splice-site alteration",
    "SPLICE_SITE_USAGE": "predicted change in splice-site usage",
    "SPLICE_JUNCTIONS": "predicted altered splice junction",
}


@dataclass
class AGSignal:
    """One summarized AlphaGenome signal (a splicing scorer or a regulatory modality)."""

    kind: str            # "splicing" | "regulatory"
    modality: str        # output_type, e.g. SPLICE_SITES / RNA_SEQ / DNASE
    tissue: str          # "" for splicing
    quantile: float | None
    direction: str | None
    interpretation: str


@dataclass
class AlphaGenomeResult:
    available: bool
    variant_id: str
    reason: str = ""
    splicing: list[AGSignal] = field(default_factory=list)
    regulatory: list[AGSignal] = field(default_factory=list)
    research_use_only: bool = True
    source: Source | None = None


def is_configured() -> bool:
    return bool(os.environ.get(API_KEY_ENV))


def _chrom(chrom: str) -> str:
    c = str(chrom)
    return c if c.startswith("chr") else f"chr{c}"


def _score(chrom, pos, ref, alt, scorer_keys, *, api_key):
    """One AlphaGenome scorer set -> tidy long DataFrame. All SDK contact is here
    so tests patch this single function and run with no key and no package."""

    from alphagenome.data import genome
    from alphagenome.models import dna_client, variant_scorers

    model = dna_client.create(api_key)
    variant = genome.Variant(
        chromosome=_chrom(chrom), position=int(pos),
        reference_bases=ref, alternate_bases=alt,
    )
    interval = variant.reference_interval.resize(dna_client.SEQUENCE_LENGTH_1MB)
    selected = [variant_scorers.RECOMMENDED_VARIANT_SCORERS[k] for k in scorer_keys]
    scores = model.score_variant(
        interval=interval, variant=variant, variant_scorers=selected,
        organism=dna_client.Organism.HOMO_SAPIENS,
    )
    return variant_scorers.tidy_scores([scores])


def _num(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    import math
    return None if math.isnan(f) else f


def _tissue_of(row) -> str:
    for key in ("gtex_tissue", "biosample_name", "track_name"):
        val = row.get(key)
        if val is not None and str(val).strip() and str(val) != "nan":
            return str(val).strip()
    return "unspecified tissue"


def _summarize(df, gene: str, kinds: tuple[str, ...], kind: str, top: int = 3) -> list[AGSignal]:
    """Reduce the tidy DataFrame to the strongest signal per output type."""

    if df is None or df.empty or "output_type" not in df.columns:
        return []
    # keep rows for our gene (splicing is gene-scoped); positional tracks carry no gene
    if "gene_name" in df.columns:
        names = df["gene_name"].astype(str)
        df = df[(names == gene) | (names == "nan") | (names.str.strip() == "")]
    out: list[AGSignal] = []
    for output_type, group in df.groupby("output_type"):
        if output_type not in kinds:
            continue
        best_row, best_mag = None, -1.0
        for _, row in group.iterrows():
            q = _num(row.get("quantile_score"))
            mag = abs(q) if q is not None else 0.0
            if mag > best_mag:
                best_mag, best_row = mag, row
        if best_row is None:
            continue
        q = _num(best_row.get("quantile_score"))
        if kind == "splicing":
            phrase = _SPLICING_PHRASE.get(str(output_type), "predicted splicing effect")
            interp = f"{phrase} in {gene} (|quantile|={abs(q):.2f})" if q is not None else f"{phrase} in {gene}"
            out.append(AGSignal("splicing", str(output_type), "", abs(q) if q is not None else None, None, interp))
        else:
            tissue = _tissue_of(best_row)
            direction = None if q in (None, 0) else ("up" if q > 0 else "down")
            interp = f"{output_type} {direction or 'change'} in {tissue} (quantile={q:+.2f})" if q is not None else f"{output_type} change in {tissue}"
            out.append(AGSignal("regulatory", str(output_type), tissue, q, direction, interp))
    out.sort(key=lambda s: abs(s.quantile) if s.quantile is not None else 0.0, reverse=True)
    return out[:top]


def score(
    coords: Coordinates,
    *,
    api_key: str | None = None,
    _scorer=None,
    _progress=None,
) -> AlphaGenomeResult:
    """Score a resolved variant for splicing + regulatory effect on its gene.

    `_scorer` is injectable for tests. Degrades to available=False + reason on a
    missing key/package, an unresolved coordinate, or any API error.
    """

    variant_id = coords.variant_id
    source = Source(name="AlphaGenome (Google DeepMind)", url=ALPHAGENOME_URL,
                    retrieved_at=now_iso(), detail=variant_id or coords.hgvs)

    if not coords.resolved:
        return AlphaGenomeResult(available=False, variant_id="",
                                 reason=f"No coordinates: {coords.reason}", source=source)
    key = api_key if api_key is not None else os.environ.get(API_KEY_ENV)
    if not key:
        return AlphaGenomeResult(available=False, variant_id=variant_id,
                                 reason=f"{API_KEY_ENV} not set.", source=source)

    run = _scorer or _score
    try:
        if _progress:
            _progress("scoring_splicing", "Scoring splicing signals…")
        splice_df = run(coords.chrom, coords.pos, coords.ref, coords.alt, SPLICING_SCORERS, api_key=key)
        if _progress:
            _progress("scoring_regulatory", "Scoring regulatory signals…")
        reg_df = run(coords.chrom, coords.pos, coords.ref, coords.alt, REGULATORY_SCORERS, api_key=key)
    except ImportError:
        return AlphaGenomeResult(available=False, variant_id=variant_id,
                                 reason="alphagenome package not installed (pip install alphagenome).",
                                 source=source)
    except Exception as exc:  # API / network / SDK — abstain, never guess
        return AlphaGenomeResult(available=False, variant_id=variant_id,
                                 reason=f"AlphaGenome API error: {exc}", source=source)

    if _progress:
        _progress("preparing_evidence", "Preparing research-model evidence…")
    return AlphaGenomeResult(
        available=True,
        variant_id=variant_id,
        splicing=_summarize(splice_df, coords.gene, set(SPLICING_SCORERS), "splicing"),
        regulatory=_summarize(reg_df, coords.gene, set(REGULATORY_SCORERS), "regulatory"),
        source=source,
    )
