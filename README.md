# PhenoFit

**Does a reported variant actually explain THIS patient?**

Built for the *Built with Claude: Life Sciences* hackathon (Builder Track). Named
user: **Matt Deardorff**, a clinical geneticist. Everything here is open source
(MIT) and built from scratch during the event.

---

## The problem

Genetic diagnosis has two people doing two different jobs:

1. **The lab** classifies candidate variants off relatively thin clinical detail
   and reports back 2–5 that look suspicious.
2. **The clinician** then holds what the lab never had — the patient's *fully
   worked-up phenotype* — and has to decide, for each reported variant, *does
   this actually explain THIS patient?*

That second job is the one Matt does, and the one tools skip. The usual variant
tools run the match forwards ("find variants that might fit a phenotype").
PhenoFit runs it **in reverse**: given the variants already on the table plus the
patient's HPO features, it scores how well each gene's known disease explains
this specific patient, and — the part intuition tends to skip — it is honest
about what's left over.

Two clinical traps it exists to counter:

- **The mind overfits.** It's easy to talk yourself into a match when the overlap
  is partial. PhenoFit scores against an explicit feature set, so a partial match
  reads as *"explains 3 of 5"*, never "close enough." And it doesn't count every
  feature the same: the score is **rarity-weighted**, so a gene that explains one
  rare, specific finding (*ectopia lentis*, ~73 diseases) outranks one that
  explains several common, non-specific ones (*developmental delay*, ~2,900) —
  matching the clinical instinct that a rare finding carries more diagnostic weight.
- **Partial explanations hide second diagnoses.** Features no reported variant
  explains are surfaced, not glossed — the trigger to consider an unreported
  extension, a **second independent cause** (~5% of solved cases), or a genome
  re-analysis. When two variants are each partly responsible, PhenoFit flags the
  **dual diagnosis**.

## What it does

Input: the **reported variants** (`GENE`, `GENE:c.HGVS`, or
`GENE:c.HGVS:p.HGVS`) and the patient's **features** (HPO ids or free text like
`"seizures"`). Output: a ranked list, and for each variant — the features it
**explains** (exactly, or "via broader" through the HPO `is_a` graph, each tagged
**rare / uncommon / common**), the features it **leaves unexplained**, the
variant's **molecular consequence** (see below), **OMIM corroboration** when a key
is set, the associated diseases, an **openable HPO source link**, and case-level
**flags** (strong single fit / possible dual diagnosis / residual features nothing
explains).

### The variant's molecular consequence (the protein-level axis)

A gene-level match is blind to the *kind* of change, which is the other axis a
clinician weighs. PhenoFit classifies each reported variant's consequence from its
HGVS — **nonsense / frameshift / canonical-splice / start-loss → loss-of-function**,
**missense / in-frame indel → altered protein**, **synonymous → silent** — and,
crucially, **abstains** ("undetermined") on a bare coding substitution like
`c.3637C>T`, whose protein effect the coding string alone cannot settle. Protein
notation (`p.Arg1213*`) is used when present because it is precise. This is an
**annotation shown beside the fit; it never changes the score** — mapping a
mechanism to a disease's mechanism needs per-gene curation the tool doesn't claim.

### OMIM corroboration (a second source of truth)

With a licensed `OMIM_API_KEY`, each fit is confirmed against OMIM's curated
gene→disease catalogue, surfacing the **inheritance pattern** (AD / AR / X-linked)
that governs whether a variant's zygosity even fits — with an openable omim.org
link. It is **purely corroborative and never reorders the ranking**; with no key
the layer is inert and the tool runs unchanged.

### Decision trace (show-your-work, for evals / RL)

Every review can emit a machine-readable **decision trace** (`phenofit.trace/v1`):
for each variant, a row per patient feature recording matched?/exact-or-via-broader/
weight/**contribution**, whose contributions sum back to the score. Because scoring
is deterministic, the trace is an exact, replayable account of the reasoning — the
artifact an eval or RL reward model reads. CLI `--trace`, `/api/review` `trace`
field (with a UI download link), and `eval --traces` (JSONL) all emit it.

### How the score works

For each variant, the fit score is the fraction of the patient's features the gene
explains, **weighted by each feature's information content** — the rarer the term
across HPO's disease annotations, the more it counts. A term's weight is
`0.25 + 0.75 · IC/IC_max`, where `IC = −log(diseases with the term / all diseases)`
comes straight from the HPO/Jax annotation network. Nothing is ever weighted to
zero (a common feature still counts, just less), and if the rarity signal can't be
fetched the score gracefully degrades to a plain explained-fraction.

## How Claude is used (the ingestion edge)

Turning a messy lab-report PDF or free-text notes into structured input is the one
place an LLM earns its keep, so that's the only place it's used — and it's used
carefully:

1. **Claude proposes.** Drop a lab-report PDF (or paste notes) and Claude reads
   off the **reported variants** and the **phenotype phrases** in one pass, via the
   Anthropic SDK's **structured outputs** (`messages.parse` + Pydantic schemas) —
   so the model's reply is guaranteed to be *shaped* correctly or raises a clean
   error. No regex-scraping a JSON blob out of prose, which could silently mangle a
   report into plausible-but-wrong data — exactly the invisible failure a clinical
   tool must not have.
2. **HPO grounds.** Every proposed phenotype phrase is resolved to a real HPO term
   by a deterministic ontology search. **The model never emits an HPO id**, so it
   can't invent one.
3. **The engine scores AI-free.** Scoring only ever sees validated HPO terms and
   is fully deterministic and sourced.

Everything Claude fills is **editable before you run it** — it drafts, you confirm.
No key? The tool still runs end to end; you just type the inputs yourself.

## Two hard rules

- **No PHI.** Phenotypes are HPO ids and gene knowledge is public (HPO/Jax), so the
  same engine can run against real EMR-derived HPO profiles behind a site's
  firewall without code changes.
- **Cite everything, abstain otherwise.** Every gene–phenotype link carries an
  openable source URL; a gene with no retrievable knowledge is marked *unscored*,
  not guessed.

## Quickstart

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# CLI — hardcoded demo (a dual-diagnosis case)
./.venv/bin/python -m phenofit.cli

# your own case
./.venv/bin/python -m phenofit.cli \
    --variant SCN1A:c.3637C>T --variant FBN1:c.4082G>A \
    --hpo "seizures" --hpo "ectopia lentis" --hpo "aortic root dilatation"

# guided demo reel (three narrated cases)
./demo.sh
```

### Web UI

```bash
./run_ui.sh            # http://localhost:8000 (or the next free port)
```

Then drop [`phenofit/samples/sample_lab_report.pdf`](phenofit/samples/sample_lab_report.pdf)
and click **Run causality review**. The AI ingestion panels (PDF drop + notes)
appear only when an Anthropic key is configured:

```bash
cp .env.example .env    # then put your key in .env (gitignored)
```

## Evaluation

```bash
./.venv/bin/python -m phenofit.eval
```

A ranking sanity/regression harness: 9 solved cases, each scored against a panel
of every fixture gene. Current result: **top-1 89%, top-3 100%, MRR 0.926, mean
margin +0.308** (the true gene's score minus the best distractor's — the
discrimination signal accuracy alone hides). `--traces PATH` also writes each
case's full decision trace as JSONL.

This is a *ranking + discrimination* check against live HPO data, **not** a
held-out clinical validation — the phenotypes are curated classic features matched
against the same HPO annotations, so a real deployment must still be measured on
real solved cases. The single miss (RYR1 malignant hyperthermia, ranked 3rd) is
honest: MH is an anesthesia-triggered reaction whose baseline HPO features overlap
other myopathies.

## Tests

```bash
./.venv/bin/python -m unittest discover -s tests
```

58 offline tests (no network, no key): the scoring engine (matching, tiering,
explained/unexplained split, ranking, residual, dual-diagnosis, rarity weighting,
consequence annotation), the HPO term ranking + container filtering +
information-content weighting + parenthetical round-trip, the molecular-consequence
classifier (including its abstentions), the OMIM corroboration layer (parse /
no-key / network-error / gene-absent), the decision-trace builder (shape + numbers
reconcile), the mocked-SDK ingestion edge, and PDF extraction.

## Architecture

```
phenofit/
  models.py     data models; every evidence item carries a Source(url, retrieved_at)
  http.py       polite HTTP for the HPO API (Retry-After + exponential backoff)
  hpo.py        HPO/Jax client: free-text -> term, gene -> phenotypes, is_a ancestors,
                information-content (rarity) weight per term
  variant.py    HGVS -> molecular consequence (nonsense/missense/frameshift/splice…)
                + loss-of-function vs altered-protein mechanism; abstains when unsure
  engine.py     the reverse match: rarity-weighted score/rank of variants, split
                explained vs unexplained, residual + dual-diagnosis detection
  omim.py       OMIM corroboration: gene -> disease + inheritance (needs OMIM_API_KEY),
                graceful no-key fallback; corroborative only, never reorders
  trace.py      CausalityReport -> machine-readable decision trace (phenofit.trace/v1)
  llm.py        Claude edge via anthropic SDK structured outputs (Pydantic schemas)
  extract.py    ingestion: Claude proposes -> HPO grounds -> validated terms only
  pdf.py        lab-report PDF -> text (pypdf)
  cli.py        run a review from the terminal (+ hardcoded demo, --trace)
  webapp.py     stdlib HTTP server + JSON endpoints calling the same engine
  static/       single-page UI (no web framework)
  eval.py       9-case ranking harness (top-1/top-3/MRR/margin, --traces)
  samples/      fictional lab-report PDF fixture + its generator
tests/          offline unit tests
```

## Scope & honesty

PhenoFit is decision-support, not a diagnosis. Scoring weights features by
information content (rarity); the variant's molecular consequence and OMIM's
inheritance pattern are now **surfaced beside** the score (not folded into it),
because turning mechanism/zygosity into a weight responsibly needs per-gene
curation — the honest next step, not a shortcut to take now. Text extraction
assumes a selectable-text PDF; scanned/image-only reports would need OCR (the tool
says so rather than guessing).
