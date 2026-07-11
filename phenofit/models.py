"""Core data models.

Design principle: every claim carries the source it came from, and the tool
separates what it can support from what it cannot. A causality score a clinician
can act on has to show its work — which of the patient's features each variant
explains, and which it leaves on the table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

from .variant import VariantConsequence, classify


@dataclass
class Source:
    """Provenance for an evidence item. `url` should be directly openable."""

    name: str
    url: str
    retrieved_at: str
    detail: str = ""


@dataclass(frozen=True)
class Phenotype:
    """One clinical feature, as an HPO term."""

    hpo_id: str  # e.g. "HP:0001250"
    label: str   # e.g. "Seizure"


@dataclass
class ReportedVariant:
    """A variant the lab already reported, with its lab-side classification.

    This is an INPUT: we take the lab's call as given and ask a different
    question — does it fit THIS patient?
    """

    gene: str
    hgvs_c: str = ""
    hgvs_p: str = ""              # protein-level HGVS, e.g. p.Arg1213* (when reported)
    lab_classification: str = ""  # e.g. "Likely pathogenic", "VUS"
    note: str = ""

    @property
    def label(self) -> str:
        return f"{self.gene} {self.hgvs_c}".strip()

    @property
    def consequence(self) -> VariantConsequence:
        """The variant's molecular consequence, classified from its HGVS notation.

        Protein-level (a nonsense/missense/frameshift call) when the notation
        supports it; honestly "undetermined" when it doesn't. Never a substitute
        for the lab's pathogenicity classification — an annotation beside it.
        """
        return classify(self.hgvs_c, self.hgvs_p)


def parse_variant_spec(spec: str) -> "ReportedVariant | None":
    """Parse a `GENE[:HGVS[:HGVS]]` spec into a ReportedVariant.

    Fields may be separated by colons or whitespace, so `SCN1A:c.3637C>T:p.Arg1213*`
    and `SCN1A c.3637C>T p.Arg1213*` are equivalent — neither a gene symbol nor an
    HGVS token contains an inner space, so this is unambiguous, and it keeps a
    naturally typed `FBN1 c.4082G>A` from reaching the gene-search API as one
    malformed query. The HGVS parts may be given in either order; each is routed
    to the coding or protein field by its `c.`/`p.` prefix, so `SCN1A:p.Arg1213*`
    and `SCN1A:c.3637C>T` also work. Returns None for a blank spec.
    """

    parts = [p for p in re.split(r"[:\s]+", spec.strip()) if p]
    if not parts:
        return None
    gene, *hgvs_parts = parts
    hgvs_c = hgvs_p = ""
    for part in hgvs_parts:
        if part.lower().startswith("p."):
            hgvs_p = part
        else:
            hgvs_c = part
    return ReportedVariant(gene=gene, hgvs_c=hgvs_c, hgvs_p=hgvs_p)


@dataclass
class PatientProfile:
    """The patient's clinical picture, as a set of HPO terms.

    No PHI: features are ontology ids, not identifiers. In production these are
    extracted from EMR notes and normalized to HPO behind the site's firewall.
    """

    phenotypes: list[Phenotype] = field(default_factory=list)
    description: str = ""


class FitTier(IntEnum):
    """How well a variant's gene explains the patient, worst to best."""

    UNLIKELY = 0
    WEAK = 1
    PARTIAL = 2
    POSSIBLE = 3
    BEST_FIT = 4

    @property
    def stars(self) -> str:
        return "*" * int(self) + "." * (4 - int(self))

    @property
    def display(self) -> str:
        return {
            FitTier.BEST_FIT: "Best fit",
            FitTier.POSSIBLE: "Possible",
            FitTier.PARTIAL: "Partial",
            FitTier.WEAK: "Weak",
            FitTier.UNLIKELY: "Unlikely",
        }[self]


@dataclass
class GenePhenotypeKnowledge:
    """Known disease phenotype for a gene, pulled from HPO/Jax."""

    gene: str
    found: bool
    diseases: list[str] = field(default_factory=list)
    phenotype_ids: set[str] = field(default_factory=set)
    phenotype_labels: dict[str, str] = field(default_factory=dict)  # hpo_id -> label
    source: Optional[Source] = None


@dataclass
class ExplainedMatch:
    """A patient feature the gene explains, and how it matched."""

    phenotype: Phenotype  # the patient's feature
    via: str              # the gene-annotated term that explained it (label)
    exact: bool           # True = same HPO term; False = matched a broader ancestor
    weight: float = 1.0   # information-content weight of the feature (rare -> higher)

    @property
    def display(self) -> str:
        if self.exact:
            return self.phenotype.label
        return f"{self.phenotype.label} (via broader: {self.via})"


@dataclass
class OmimPhenotype:
    """One OMIM disease linked to a gene, with its inheritance pattern."""

    name: str
    mim: str = ""            # OMIM phenotype MIM number, e.g. "607208"
    inheritance: str = ""    # e.g. "Autosomal dominant", "Autosomal recessive"


@dataclass
class OmimEvidence:
    """OMIM corroboration for a gene — a second, curated source of truth.

    `available` is True only when OMIM was actually queried and returned data;
    otherwise `reason` says why (no key configured, gene not found, error), so the
    absence is explicit rather than silently blank.
    """

    gene: str
    available: bool
    phenotypes: list[OmimPhenotype] = field(default_factory=list)
    reason: str = ""
    source: Optional[Source] = None

    @property
    def inheritance_patterns(self) -> list[str]:
        seen: list[str] = []
        for p in self.phenotypes:
            if p.inheritance and p.inheritance not in seen:
                seen.append(p.inheritance)
        return seen


@dataclass
class VariantFit:
    """How well one reported variant explains the patient."""

    variant: ReportedVariant
    tier: FitTier
    score: float  # fraction of patient phenotypes this gene explains, 0..1
    explained: list[ExplainedMatch] = field(default_factory=list)
    unexplained: list[Phenotype] = field(default_factory=list)
    diseases: list[str] = field(default_factory=list)
    rationale: str = ""
    source: Optional[Source] = None
    knowledge_found: bool = True
    omim: Optional[OmimEvidence] = None  # OMIM corroboration, attached post-ranking


@dataclass
class CausalityReport:
    """The ranked answer, plus the honest caveats."""

    patient: PatientProfile
    fits: list[VariantFit] = field(default_factory=list)  # ranked, best first
    # Patient features no reported variant explains -> possible second cause /
    # re-analysis territory.
    residual_unexplained: list[Phenotype] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    # Information-content weight used for each feature (hpo_id -> weight), kept so
    # the decision trace can show every feature's weight — including the ones no
    # variant matched, which ExplainedMatch never records.
    feature_weights: dict[str, float] = field(default_factory=dict)
