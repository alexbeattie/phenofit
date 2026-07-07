"""Ingestion edge: messy text -> structured input the engine can score.

Pipeline:
  1. Claude reads free-text clinical content and PROPOSES phenotype phrases (and,
     for a lab report, the reported variants).
  2. Each phenotype phrase is grounded against the HPO ontology by the
     deterministic term search — the model never emits an HPO id, so it cannot
     invent one.

The result keeps provenance: which phrase produced which HPO term, and which
phrases could not be grounded. The scoring engine only ever sees real, validated
HPO terms.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from .hpo import resolve_term
from .llm import extract_phenotype_phrases, extract_variants_raw
from .models import Phenotype


@dataclass
class ExtractedPhenotype:
    phrase: str            # what Claude proposed
    phenotype: Phenotype   # the HPO term it grounded to


@dataclass
class ExtractionResult:
    phenotypes: list[ExtractedPhenotype] = field(default_factory=list)
    ungrounded: list[str] = field(default_factory=list)  # phrases with no HPO match

    def deduped_phenotypes(self) -> list[Phenotype]:
        seen: set[str] = set()
        out: list[Phenotype] = []
        for e in self.phenotypes:
            if e.phenotype.hpo_id not in seen:
                seen.add(e.phenotype.hpo_id)
                out.append(e.phenotype)
        return out


def extract_from_notes(client: httpx.Client, notes: str, *, sdk_client=None) -> ExtractionResult:
    """Free-text clinical notes -> validated HPO phenotypes (Claude proposes, HPO validates)."""

    phrases = extract_phenotype_phrases(notes, sdk_client=sdk_client)
    result = ExtractionResult()
    for phrase in phrases:
        term = resolve_term(client, phrase)
        if term is None:
            result.ungrounded.append(phrase)
        else:
            result.phenotypes.append(ExtractedPhenotype(phrase=phrase, phenotype=term))
    return result


@dataclass
class ReportIngest:
    """Everything pulled from a dropped lab-report PDF."""

    variants: list[dict] = field(default_factory=list)  # {gene, hgvs, classification}
    phenotypes: ExtractionResult = field(default_factory=ExtractionResult)


def ingest_report(client: httpx.Client, report_text: str, *, sdk_client=None) -> ReportIngest:
    """Lab-report text -> reported variants + validated HPO phenotypes, in one pass."""

    variants = extract_variants_raw(report_text, sdk_client=sdk_client)
    phenotypes = extract_from_notes(client, report_text, sdk_client=sdk_client)
    return ReportIngest(variants=variants, phenotypes=phenotypes)
