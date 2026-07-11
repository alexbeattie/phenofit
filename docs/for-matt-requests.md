# PhenoFit — what I need from you to go further

Matt — thank you for the three dictations and the walkthrough; they're captured
in full and driving the build. Here's where things stand and, more importantly,
the specific inputs from you that unblock the next steps. I've ordered these by
how much they unlock, and said exactly what format is most useful so it's quick
on your end.

## Where PhenoFit is now (so you know what you'd be testing)

Your **Task 2** — the clinician's causality review — is the working core:

- Drag in the **lab-report PDF plus any other clinical notes**; Claude reads the
  reported variants and the phenotype off the page (structured outputs), and
  every phenotype phrase is grounded in a real HPO term deterministically.
- Reverse causality **ranking** of the reported variants by how well each gene's
  known disease explains *this* patient — rarity-weighted, so a rare specific
  finding outweighs a common one.
- **Explained vs. unexplained** features per variant, the **dual-diagnosis** flag
  (~5% second-cause case), and a genome **re-analysis** trigger for leftovers.
- **OMIM** corroboration (inheritance + disease) beside the HPO score.
- **Protein-level** molecular-consequence axis (per your note to work at the
  protein level, not the nucleotide level).
- A per-disorder **Management & what to assess** panel: curated deep links
  (GeneReviews / OMIM / MedGen / GTR) plus an optional, clearly-labeled,
  self-abstaining AI-drafted brief.
- **Decision traces + an eval harness**, so every ranking decision is inspectable
  (the object-tracing/RL groundwork you asked about).

It's HPO-id + public-knowledge only (no PHI), so it runs behind a hospital
firewall unchanged.

## What I need from you — ranked by what it unblocks

### 1. Pseudonymized cases (unblocks the most)
The single highest-value input. **3–5 de-identified real cases**, each with:

- the **lab report** (PDF is ideal — that's the drag-in path), showing the 2–5
  reported variants with **gene, HGVS (c. and p.), and the lab's classification**;
- the **clinical notes / phenotype** as the clinician saw it (free text is fine —
  Claude extracts and grounds it), the more granular the better;
- the **known answer**: which variant was ultimately judged causal (or that it was
  a dual diagnosis / unsolved), and the confirmed disorder.

These become (a) honest test fixtures, (b) the eval set that proves ranking
quality on *real* cases, and (c) the seed for the causality score below. A case
where **ancestry / thin gnomAD representation** made the call hard is especially
valuable — that becomes the ancestry-confidence fixture.

*Question:* do you have a preferred de-identification standard or an existing
pseudonymizer, or should I propose a minimal safe-harbor stripping step we run
behind your firewall before anything touches Claude?

### 2. The updated (quantitative) ACMG draft
You mentioned the College's newer, more quantitative, more legible criteria
(replacing the 2015/2019 letter/number codes). The **draft PDF/doc** unblocks
Task 1 — the concise **director-facing evidence summary** per variant — so its
language and point structure match what your lab will actually adopt.

### 3. AlphaGenome / AlphaMissense access (unblocks Task 3 — the frontier)
For the intronic/regulatory work (de-novo and compound-recessive non-coding
variants), I want to wire in **AlphaGenome** (splicing + regulatory effect) and
**AlphaMissense** (missense pathogenicity) and fold their scores into the same
ranked list.

- Do you have an **AlphaGenome API key / access** we can use, or should I build
  against the public API and you supply a key behind the firewall?
- The **Gladstone/UCSF regulatory-model link** you were going to send (the
  large-scale enhancer-assessment work) — that plus the bioRxiv MPRA paper you
  already sent (2023.02.15.528663) are the regulatory-scoring backbone.

### 4. The causality score (0–1)
You asked for a probability that a variant (or combination) causes a specific
disease. I've shipped a **provisional, clearly-labeled heuristic** now (derived
from the rarity-weighted fit, consequence, and OMIM inheritance match) so the
number exists and is honest about being an estimate, not outcome-trained.

*To make it a real trained score I need:* a labeled set of **confirmed
pathogenic variant(-combination) → disease** pairs (the pseudonymized cases in
#1 are the start; more is better). *Question:* what would you personally need to
see — calibration, per-criterion contribution, a held-out test — to trust a
trained score enough to use it?

## Four short questions that sharpen everything

1. **Which variant type dominates your queue** — missense SNVs, splicing, CNVs,
   non-coding? I'll bias the eval and scoring toward the biggest bucket.
2. **The last VUS you worked up** — what did you open, in what order, and where
   did you lose time? That tells me what to automate vs. skip.
3. **The trust checklist** — what must be on screen for you to *edit* an automated
   causality draft rather than redo it from scratch?
4. **Management depth** — for the "what to assess next" panel, is a concise
   surveillance/management summary + source links enough, or do you want
   specific care-pathway detail per disorder?

No rush on any of it — even one pseudonymized case and the ACMG draft would move
things a long way. Everything else is already building on what you've given me.
