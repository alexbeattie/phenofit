# Slice: multi-document ingestion + clinical-management panel

**Date:** 2026-07-11
**Source:** Matt's Task-2 asks (see [matt-feedback.md](../../matt-feedback.md) Parts A/B).
**Priority:** first "Matt-fidelity" increment.

Two features, both fitting the existing contract: **Claude proposes only at the
ingestion edge; the scored clinical output stays deterministic, sourced, and
abstains.** No change to the scoring engine or the ranking.

## Feature A — multi-document ingestion

**Why:** Matt wants to drag the lab-report PDF *and* paste/drag other clinical
reports for granular phenotyping. Today only one PDF + one notes box.

**Backend**
- `extract.py`: give `ExtractedPhenotype` an optional `source_doc` label
  (which document produced the phrase). Add `merge_extractions(results)` →
  union of phenotypes deduped by HPO id, first-seen provenance kept.
- New `ingest_documents(client, docs)` where `docs = [{role, kind, content}]`:
  - `role="lab_report"` → run `ingest_report` (variants + phenotypes).
  - `role="clinical_note"` → run `extract_from_notes` (phenotypes only).
  - Merge all phenotypes; collect variants from lab reports.
- `webapp.py`: new `POST /api/ingest-docs` accepting a list of documents
  (each pasted text or base64 PDF + role). Returns `{variants, phenotypes (with
  source_doc), ungrounded, docs: [{name, role, n_phenotypes}]}`.

**Frontend** (extend the current two-column layout, do not re-impose the grid)
- Replace the single PDF drop with a **document list**: drop multiple PDFs and/or
  add pasted notes; each row shows name + a role selector (Lab report / Clinical
  note) + remove. One **"Ingest all"** button.
- After ingest: variants box filled from lab report(s); features box filled with
  the **deduped union**; a line shows "N features from M documents".
- Existing single-PDF and single-notes paths keep working (they call the same
  merge under the hood).

## Feature B — clinical-management & "what to assess" panel

**Why:** Matt wants, per ranked disorder, what's known about management and what
the team should assess next.

**Hybrid source (approved):**
1. **Deterministic curated links (always, no key needed):** per gene/disease,
   openable deep links to **GeneReviews, OMIM, MedGen, GTR**. Built in a new
   `management.py`, returned inline on `/api/review` so they show with zero cost.
2. **AI-drafted brief (on demand, gated by `ANTHROPIC_API_KEY`):** a concise
   management/surveillance summary fetched lazily per card via new
   `POST /api/management` `{gene, disease}`. Clearly labeled *"AI-drafted from
   public knowledge — verify against GeneReviews"*; **abstains** (empty, with a
   "consult GeneReviews" note) when the model isn't confident.

**Backend**
- `management.py`: `curated_links(gene, omim_mim=None) -> list[Source]`.
- `llm.py`: `ManagementBrief` schema `{surveillance[], management[],
  systems_to_assess[], confident, caveat}` + `draft_management_brief(gene,
  disease)`. System prompt: summarize only well-established, GeneReviews-level
  management; set `confident=false` and empty lists if unsure; never invent.
- `webapp.py`: attach `management_links` to each fit in `/api/review`; add
  `POST /api/management` returning the AI brief (or `{error}` when no key).

**Frontend**
- Each result card gets a **"Management & what to assess"** section: the curated
  links render immediately; a **"Draft brief (AI)"** button lazily loads the brief
  into the card, with the verify label and abstention handled.

## Tests
- `test_extract`: `merge_extractions` dedups by HPO id and keeps provenance;
  `ingest_documents` routes roles correctly (stub SDK + stubbed HPO).
- `test_management`: `curated_links` returns well-formed openable URLs for a gene
  (and gene+MIM); `draft_management_brief` abstains when the stub returns
  `confident=false`.
- Run the full suite (currently 26 tests) — keep it green.

## Out of scope (this slice)
Task-3 regulatory/AlphaGenome integration, the 0–1 trained causality score, EHR
connectors, pseudonymization. Tracked in matt-feedback.md.
