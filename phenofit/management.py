"""Clinical-management surfacing — curated deep links, deterministic and sourced.

Matt's Task-2 ask: alongside the causality ranking, show what is known about the
clinical management of each disorder and what the team should assess next. This
module supplies the *deterministic* half of that — openable deep links into the
curated resources a clinical geneticist already trusts (GeneReviews, OMIM,
MedGen, GTR), built from the gene symbol (and OMIM MIM when we have it).

No AI here: these links never depend on a model and never change the ranking.
The optional AI-drafted management *brief* lives at the ingestion edge
(`llm.draft_management_brief`) and is always labeled and verifiable against these
same links — the model summarizes, the curated sources remain the source of truth.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from .http import now_iso
from .models import Source


def curated_links(gene: str, omim_mim: str | None = None) -> list[Source]:
    """Openable curated deep links for a gene / disorder, most authoritative first.

    GeneReviews is the canonical expert-authored management resource; OMIM is the
    curated gene/disease catalogue (its exact entry when we have the MIM, else a
    search); MedGen and GTR round out clinical concepts and available testing.
    """

    gene = (gene or "").strip()
    if not gene:
        return []
    g = quote_plus(gene)
    ts = now_iso()

    omim_url = (
        f"https://www.omim.org/entry/{omim_mim}"
        if omim_mim
        else f"https://www.omim.org/search?index=entry&search={g}"
    )

    return [
        Source(
            name="GeneReviews",
            url=f"https://www.ncbi.nlm.nih.gov/books/?term={g}%5Btitle%5D+AND+genereviews%5Bfilter%5D",
            retrieved_at=ts,
            detail="expert-authored management & surveillance",
        ),
        Source(
            name="OMIM",
            url=omim_url,
            retrieved_at=ts,
            detail=f"MIM {omim_mim}" if omim_mim else f"{gene} entry search",
        ),
        Source(
            name="MedGen",
            url=f"https://www.ncbi.nlm.nih.gov/medgen/?term={g}",
            retrieved_at=ts,
            detail="clinical concepts & related conditions",
        ),
        Source(
            name="GTR",
            url=f"https://www.ncbi.nlm.nih.gov/gtr/all/tests/?term={g}%5Bgene%5D",
            retrieved_at=ts,
            detail="genetic testing registry",
        ),
    ]
