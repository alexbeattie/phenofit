"""Core data models.

Design principle: every claim carries the source it came from, and the tool
separates what it can support from what it cannot. A causality score a clinician
can act on has to show its work — which of the patient's features each variant
explains, and which it leaves on the table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


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
    lab_classification: str = ""  # e.g. "Likely pathogenic", "VUS"
    note: str = ""

    @property
    def label(self) -> str:
        return f"{self.gene} {self.hgvs_c}".strip()


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


@dataclass
class CausalityReport:
    """The ranked answer, plus the honest caveats."""

    patient: PatientProfile
    fits: list[VariantFit] = field(default_factory=list)  # ranked, best first
    # Patient features no reported variant explains -> possible second cause /
    # re-analysis territory.
    residual_unexplained: list[Phenotype] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
