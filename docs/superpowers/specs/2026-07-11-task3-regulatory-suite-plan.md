# Task 3 — regulatory / intronic science suite: implementation plan

**Status:** planned, not built. Hard-blocked on external access (see "Blockers").
**Goal (Matt's Message 3):** identify and score intronic / intergenic / regulatory
variants the exome missed (de-novo or compound-recessive), and **integrate them
into the same ranked causality list** as coding variants.

This is an executable plan: it names the files to port from the sibling `biohack`
prototypes, the new seams in phenofit, the dependency/gating story, and the
verification. It is ready to run the moment the blockers clear.

## Blockers (why this isn't built yet)

1. **AlphaGenome API key.** The client needs `ALPHAGENOME_API_KEY` (research use).
   Requested from Matt in `docs/for-matt-requests.md` §3.
2. **Coordinate resolution.** AlphaGenome (and trio logic) need GRCh38
   `chrom:pos:ref:alt`. PhenoFit works from gene+HGVS and has no resolver. Solved
   by porting a VEP REST client (free, no key) — this is the first build step and
   unblocks AlphaMissense too.
3. **AlphaMissense data.** Best obtained *free via Ensembl VEP REST*
   (`transcript_consequences[].am_pathogenicity` / `am_class`) once VEP is wired;
   avoids shipping the multi-GB precomputed table.

Building any external-API client blind (no live verification) risks shipping
broken/fabricated output, which violates PhenoFit's abstain-don't-guess contract.
Each phase below ends in a live verification gate.

## Prototypes to port (from the biohack repo worktrees)

- `biohack-alphagenome/variant_curator/clients/alphagenome.py` — the real
  AlphaGenome client (`fetch_alphagenome(chrom,pos,ref,alt,gene) -> evidence`),
  splicing + regulatory scorers, per-gene tissue hints, graceful degradation.
  **Port near-verbatim** (adapt `Source`/models to phenofit).
- `biohack-alphagenome/variant_curator/clients/vep.py` — VEP REST client
  (HGVS → GRCh38 coords + consequence). **Port and extend** to also read
  AlphaMissense fields.
- `biohack-trio/trio_prioritizer/` (`scoring.py`, `models.py`) — de-novo /
  compound-het inheritance logic + integrated ranking. **Port** as phenofit's
  trio mode.
- `biohack-mpra/regmodel/` — offline MPRA CNN + ISM cross-check. **Optional**,
  gated on `torch`; a "small model vs foundation model" novelty, not a clinical
  scorer.

## Build phases

### Phase 0 — coordinate resolution (unblocks everything)
- New `phenofit/coords.py`: port VEP REST client. `resolve(gene, hgvs_c) ->
  {chrom, pos, ref, alt, consequence_terms, transcript}`; graceful degradation +
  `Source`. Cache per run.
- **Verify:** live VEP call resolves `FBN1:c.4082G>A` to GRCh38 coords + SO terms.

### Phase 1 — AlphaMissense (free, no key)
- Extend `coords.py`/new `alphamissense.py` to read `am_pathogenicity` + `am_class`
  from VEP `transcript_consequences` for **missense** variants.
- Attach to `VariantFit` as a molecular-evidence signal; feed into
  `causality_probability` (replace/augment the consequence term) and show in the
  card + management panel, labeled + sourced.
- **Verify:** a known pathogenic missense returns `am_class=likely_pathogenic`.

### Phase 2 — AlphaGenome (key-gated) for non-coding
- New `phenofit/noncoding.py`: port `fetch_alphagenome`; adapt models
  (`SplicingSignal`, `RegulatorySignal`, `AlphaGenomeEvidence`) into
  `phenofit/models.py`.
- Route variants whose VEP consequence is intronic/UTR/regulatory/splice to
  AlphaGenome; attach splicing + regulatory signals; **inert without the key**
  (OMIM-style `available=False` + reason).
- Fold a calibrated splicing/regulatory magnitude into `causality_probability`
  for non-coding variants (provisional thresholds, clearly labeled).
- **Verify:** with a key, a deep-intronic splice variant returns a splicing
  signal; without a key, a clean "unavailable" note.

### Phase 3 — trio mode (de-novo / compound-het)
- New input mode: child + parents (variants per member, or a trio VCF paste).
- Port `trio_prioritizer` logic: flag **de novo** (in child, neither parent) and
  **compound-het** (one allele from each parent in the same gene), score each
  non-coding candidate via Phase 2, and **merge into the single ranked list** with
  the reported coding variants — the integration Matt explicitly asked for.
- **Verify:** the prototype's synthetic trio scenario ranks the planted de-novo
  splice variant into the candidate list, offline.

### Phase 4 — regmodel cross-check (optional, offline)
- Port `regmodel/` behind a `torch` extra. When a local sequence window is
  available, run ISM and show a "small MPRA model vs AlphaGenome" agreement note.
- **Verify:** offline synthetic MPRA trains and ISM runs on CPU.

## Contract (unchanged from the rest of PhenoFit)
- **Abstain, don't fabricate:** every scorer degrades to unavailable+reason
  without keys/data; never a made-up number.
- **Provenance on every claim:** carry each model's `Source` (URL + timestamp).
- **Research-use-only** caveat wherever model scores appear.
- **No PHI;** runs behind a firewall unchanged.
- AI stays fenced to the ingestion edge; these are deterministic model calls, and
  they annotate or feed the score transparently, never a black-box verdict.

## Dependencies
`httpx` (have). Phase 2 adds `alphagenome` + `pandas` (SDK deps). Phase 4 adds an
optional `torch` extra. VEP/AlphaMissense (Phases 0–1) need no new package.

## Definition of done
`import phenofit` works with no keys/packages; full suite passes offline (all
external scorers mocked); with `ALPHAGENOME_API_KEY` set, a non-coding demo
variant shows real splicing/regulatory signals folded into the ranked list; trio
mode surfaces a de-novo/compound-het candidate integrated with the reported
variants.
