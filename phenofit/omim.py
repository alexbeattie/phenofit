"""OMIM corroboration — a second, curated source of truth for gene->disease.

The HPO/Jax annotation network is PhenoFit's primary knowledge, and it drives the
score. OMIM (Online Mendelian Inheritance in Man) is the hand-curated catalogue a
clinical geneticist already trusts, and it carries one thing HPO's phenotype set
foregrounds less: the **inheritance pattern** of each gene-disease link (autosomal
dominant/recessive, X-linked), which is central to whether a variant's zygosity
even fits the disease. Matt's ask was to bring that source of truth alongside the
score so a fit can be *confirmed* against it.

This layer is purely corroborative: it never changes the ranking. It attaches, to
each fit, the OMIM diseases + inheritance for that gene and an openable omim.org
link — or, when OMIM can't be reached, an explicit "unavailable, and why".

Access requires a licensed OMIM API key (register at omim.org). Read from
OMIM_API_KEY; with no key the layer is inert (available=False) and the rest of the
tool runs unchanged — the same graceful-degradation contract as the Claude edge.
"""

from __future__ import annotations

import os

import httpx

from .http import get_json, now_iso
from .models import OmimEvidence, OmimPhenotype, Source, VariantFit

OMIM_API = "https://api.omim.org/api"

# Gene corroboration is stable within a run and genes recur across a panel/eval,
# so cache it (keyed by upper-cased symbol).
_CACHE: dict[str, OmimEvidence] = {}


def is_configured() -> bool:
    return bool(os.environ.get("OMIM_API_KEY"))


def _web_url(gene: str, gene_mim: str | None) -> str:
    """A clinician-openable OMIM page: the gene entry if we have its MIM, else search."""

    if gene_mim:
        return f"https://www.omim.org/entry/{gene_mim}"
    return f"https://www.omim.org/search?index=entry&search={gene}"


def _parse(gene: str, data: dict) -> OmimEvidence:
    """Pull the phenotype/inheritance rows for `gene` out of a geneMap search response."""

    gene_maps = (
        data.get("omim", {})
        .get("searchResponse", {})
        .get("geneMapList", [])
    )
    # Prefer the geneMap whose approved symbol matches; fall back to the first.
    chosen = None
    for entry in gene_maps:
        gm = entry.get("geneMap", {})
        symbols = f"{gm.get('approvedGeneSymbols', '')} {gm.get('geneSymbols', '')}".upper()
        if gene.upper() in {s.strip() for s in symbols.replace(",", " ").split()}:
            chosen = gm
            break
    if chosen is None and gene_maps:
        chosen = gene_maps[0].get("geneMap", {})
    if not chosen:
        return OmimEvidence(gene=gene, available=False, reason="No OMIM gene-map entry found.")

    phenotypes: list[OmimPhenotype] = []
    for pm in chosen.get("phenotypeMapList", []):
        p = pm.get("phenotypeMap", {})
        name = (p.get("phenotype") or "").strip()
        if not name:
            continue
        mim = p.get("phenotypeMimNumber")
        phenotypes.append(OmimPhenotype(
            name=name,
            mim=str(mim) if mim else "",
            inheritance=(p.get("phenotypeInheritance") or "").strip(),
        ))

    gene_mim = chosen.get("mimNumber")
    source = Source(
        name="OMIM",
        url=_web_url(gene, str(gene_mim) if gene_mim else None),
        retrieved_at=now_iso(),
        detail=f"{gene} (MIM {gene_mim})" if gene_mim else gene,
    )
    if not phenotypes:
        return OmimEvidence(gene=gene, available=False,
                            reason="OMIM entry has no phenotype mapping.", source=source)
    return OmimEvidence(gene=gene, available=True, phenotypes=phenotypes, source=source)


def fetch_gene_omim(client: httpx.Client, gene: str) -> OmimEvidence:
    """OMIM diseases + inheritance for a gene, or an explicit unavailable result."""

    key = gene.upper()
    if key in _CACHE:
        return _CACHE[key]

    if not is_configured():
        result = OmimEvidence(
            gene=gene, available=False,
            reason="OMIM_API_KEY not set — add a licensed OMIM key to enable corroboration.",
        )
        _CACHE[key] = result
        return result

    try:
        data = get_json(client, f"{OMIM_API}/geneMap/search", params={
            "search": gene,
            "format": "json",
            "apiKey": os.environ.get("OMIM_API_KEY", ""),
        })
        result = _parse(gene, data) if isinstance(data, dict) else OmimEvidence(
            gene=gene, available=False, reason="Unexpected OMIM response shape.")
    except Exception as exc:  # network / auth / shape -> explicit, never crash the review
        result = OmimEvidence(gene=gene, available=False, reason=f"OMIM query failed: {exc}")

    _CACHE[key] = result
    return result


def corroborate(client: httpx.Client, fits: list[VariantFit]) -> None:
    """Attach OMIM evidence to each fit in place (inert but present when no key)."""

    for f in fits:
        f.omim = fetch_gene_omim(client, f.variant.gene)
