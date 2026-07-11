"""Coordinate resolution — gene + coding HGVS -> GRCh38 chrom:pos:ref:alt.

PhenoFit reasons about variants as gene + HGVS, but a genome model like
AlphaGenome needs genomic coordinates. Ensembl's public VEP REST resolves a
`GENE:c.HGVS` string straight to a forward-strand VCF representation (and the
molecular consequence and protein HGVS along the way) with no API key and no
transcript lookup on our side — so this is the bridge from the clinical notation
to the coordinates the science layer needs.

Public endpoint, GRCh38, no key. Degrades to None (with a reason on the returned
object) when VEP can't validate the HGVS — never a fabricated coordinate.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from .http import get_json, now_iso
from .models import Source

VEP_BASE = "https://rest.ensembl.org"

# SO terms VEP returns that are non-coding — the variants AlphaGenome exists to
# interpret (splicing / regulatory), which a coding-consequence view ignores.
_NONCODING_TERMS = {
    "splice_donor_variant", "splice_acceptor_variant", "splice_region_variant",
    "splice_donor_5th_base_variant", "splice_donor_region_variant",
    "splice_polypyrimidine_tract_variant", "intron_variant",
    "5_prime_UTR_variant", "3_prime_UTR_variant", "upstream_gene_variant",
    "downstream_gene_variant", "regulatory_region_variant",
    "TF_binding_site_variant", "intergenic_variant", "non_coding_transcript_exon_variant",
}


@dataclass
class Coordinates:
    """A resolved GRCh38 locus, or an explicit unavailable result with a reason."""

    resolved: bool
    gene: str
    hgvs: str                       # the GENE:c.HGVS we asked about
    chrom: str = ""
    pos: int = 0
    ref: str = ""
    alt: str = ""
    consequence: str = ""           # VEP most_severe_consequence
    protein_hgvs: str = ""
    reason: str = ""
    source: Source | None = None

    @property
    def is_noncoding(self) -> bool:
        return self.consequence in _NONCODING_TERMS

    @property
    def variant_id(self) -> str:
        return f"{self.chrom}:{self.pos}:{self.ref}>{self.alt}" if self.resolved else ""


def resolve(client: httpx.Client, gene: str, hgvs_c: str) -> Coordinates:
    """Resolve `gene:hgvs_c` to GRCh38 coordinates via Ensembl VEP (GRCh38)."""

    hgvs = f"{gene}:{hgvs_c}".strip(": ")
    web = f"https://www.ensembl.org/Homo_sapiens/Tools/VEP?hgvs={hgvs}"
    source = Source(name="Ensembl VEP (GRCh38)", url=web, retrieved_at=now_iso(), detail=hgvs)

    if not gene or not hgvs_c:
        return Coordinates(resolved=False, gene=gene, hgvs=hgvs,
                           reason="Need both a gene and a coding HGVS to resolve coordinates.",
                           source=source)

    url = f"{VEP_BASE}/vep/human/hgvs/{hgvs}"
    params = {"content-type": "application/json", "hgvs": "1", "canonical": "1", "vcf_string": "1"}
    try:
        data = get_json(client, url, params=params)
    except httpx.HTTPStatusError as exc:
        reason = ("VEP could not validate this HGVS."
                  if exc.response.status_code == 400 else f"VEP error {exc.response.status_code}.")
        return Coordinates(resolved=False, gene=gene, hgvs=hgvs, reason=reason, source=source)
    except Exception as exc:  # network / shape — abstain, don't guess
        return Coordinates(resolved=False, gene=gene, hgvs=hgvs, reason=f"VEP query failed: {exc}", source=source)

    if not isinstance(data, list) or not data:
        return Coordinates(resolved=False, gene=gene, hgvs=hgvs,
                           reason="VEP returned no result for this HGVS.", source=source)

    record = data[0]
    vcf = record.get("vcf_string")
    if not vcf:
        return Coordinates(resolved=False, gene=gene, hgvs=hgvs,
                           reason="VEP returned no genomic coordinates.", source=source)
    chrom, pos_s, ref, alt = vcf.split(",")[0].split("-")

    consequence = record.get("most_severe_consequence", "") or ""
    protein = ""
    for tc in record.get("transcript_consequences", []):
        if consequence in tc.get("consequence_terms", []) and tc.get("hgvsp"):
            protein = tc["hgvsp"].split(":", 1)[-1]
            if tc.get("canonical") == 1:
                break

    return Coordinates(
        resolved=True, gene=gene, hgvs=hgvs,
        chrom=chrom, pos=int(pos_s), ref=ref, alt=alt,
        consequence=consequence, protein_hgvs=protein, source=source,
    )
