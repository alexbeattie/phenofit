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
    source_doc: str = ""   # label of the document this phrase came from


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


def extract_from_notes(
    client: httpx.Client, notes: str, *, source_doc: str = "", sdk_client=None
) -> ExtractionResult:
    """Free-text clinical notes -> validated HPO phenotypes (Claude proposes, HPO validates)."""

    phrases = extract_phenotype_phrases(notes, sdk_client=sdk_client)
    result = ExtractionResult()
    for phrase in phrases:
        term = resolve_term(client, phrase)
        if term is None:
            result.ungrounded.append(phrase)
        else:
            result.phenotypes.append(
                ExtractedPhenotype(phrase=phrase, phenotype=term, source_doc=source_doc)
            )
    return result


def merge_extractions(results: list[ExtractionResult]) -> ExtractionResult:
    """Union several extractions, deduped by HPO id, keeping first-seen provenance.

    Granular phenotyping across a lab report plus other clinical notes means the
    same feature can appear in more than one document; the patient still has it
    once. We keep the first document that grounded each term (so provenance points
    somewhere real) and de-duplicate ungrounded phrases across documents.
    """

    merged = ExtractionResult()
    seen: set[str] = set()
    seen_ungrounded: set[str] = set()
    for r in results:
        for e in r.phenotypes:
            if e.phenotype.hpo_id not in seen:
                seen.add(e.phenotype.hpo_id)
                merged.phenotypes.append(e)
        for phrase in r.ungrounded:
            if phrase not in seen_ungrounded:
                seen_ungrounded.add(phrase)
                merged.ungrounded.append(phrase)
    return merged


@dataclass
class DocumentsIngest:
    """Everything pulled from a set of dropped/pasted clinical documents."""

    variants: list[dict] = field(default_factory=list)   # from the lab report(s)
    phenotypes: ExtractionResult = field(default_factory=ExtractionResult)
    docs: list[dict] = field(default_factory=list)        # per-doc summary for the UI


def ingest_documents(
    client: httpx.Client, docs: list[dict], *, sdk_client=None
) -> DocumentsIngest:
    """Ingest several clinical documents into one merged, deduped set of inputs.

    Each doc is ``{"role": "lab_report"|"clinical_note", "text": str, "name": str}``.
    A lab report yields reported variants *and* phenotypes; any other clinical
    document yields phenotypes only. Phenotypes are merged (union, deduped by HPO
    id, provenance kept); variants are collected from the lab report(s).
    """

    variants: list[dict] = []
    extractions: list[ExtractionResult] = []
    summary: list[dict] = []
    for i, doc in enumerate(docs):
        text = (doc.get("text") or "").strip()
        name = doc.get("name") or f"document {i + 1}"
        role = doc.get("role") or "clinical_note"
        if not text:
            continue
        if role == "lab_report":
            ingest = ingest_report(client, text, source_doc=name, sdk_client=sdk_client)
            variants.extend(ingest.variants)
            extractions.append(ingest.phenotypes)
            n = len(ingest.phenotypes.phenotypes)
        else:
            extraction = extract_from_notes(client, text, source_doc=name, sdk_client=sdk_client)
            extractions.append(extraction)
            n = len(extraction.phenotypes)
        summary.append({"name": name, "role": role, "n_phenotypes": n})

    return DocumentsIngest(
        variants=_dedupe_variants(variants),
        phenotypes=merge_extractions(extractions),
        docs=summary,
    )


def _dedupe_variants(variants: list[dict]) -> list[dict]:
    """Drop duplicate reported variants (same gene + coding HGVS) across documents."""

    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for v in variants:
        key = (v.get("gene", "").upper(), v.get("hgvs", ""))
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out


@dataclass
class ReportIngest:
    """Everything pulled from a dropped lab-report PDF."""

    variants: list[dict] = field(default_factory=list)  # {gene, hgvs, classification}
    phenotypes: ExtractionResult = field(default_factory=ExtractionResult)


def ingest_report(
    client: httpx.Client, report_text: str, *, source_doc: str = "", sdk_client=None
) -> ReportIngest:
    """Lab-report text -> reported variants + validated HPO phenotypes, in one pass."""

    variants = extract_variants_raw(report_text, sdk_client=sdk_client)
    phenotypes = extract_from_notes(
        client, report_text, source_doc=source_doc, sdk_client=sdk_client
    )
    return ReportIngest(variants=variants, phenotypes=phenotypes)
