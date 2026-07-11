# Matt Deardorff — full feedback (source of truth)

Primary-source record of Matt's guidance for PhenoFit: three dictated voice
messages, a regulatory-assay reference, two follow-up notes, and the Zoom
meeting summary with action items. Captured 2026-07-11.

Matt is a clinical geneticist and the named user for PhenoFit. The dictations
below are **lightly cleaned from speech-to-text** (fixing obvious transcription
garbles such as "exon", "intronic", "autosomal recessive", "missense", "gene",
"de novo") — meaning is preserved, nothing substantive changed. His explicit
terminology note: use **"variants"**, not "variance".

---

## Part A — Matt's three dictated messages

### Message 1 — the lab-side variant classification process

The current classifications interpret variants for patients to understand the
degree of pathogenicity — the disruption of a gene in a clinical context. The
ACMG guidelines take a number of things into account. For a rare-disease
diagnosis they first **filter out variants too common in the population** to
plausibly cause the disease. Then two broad evidence categories:

1. **Has this variant been seen before** in an individual, and if so, is it a
   convincing cause of that disease? If yes, high evidence for pathogenic.
2. **Is the *kind* of change the same kind seen** in individuals with the same
   clinical features who are known to have the disease — e.g. if the change is a
   loss of function and the disease is caused by loss of function. There are many
   ways to create a loss-of-function mutation; they converge on the same
   downstream effect (you lose the function of at least one copy of the gene).

Inheritance matters: **autosomal dominant** (one change is enough) vs
**autosomal recessive** (both copies affected). Recessive is interesting because
you may see one clear variant and a second of less certainty — then you must
sort out at a functional/biological level whether that change predicts a
deficient or defective protein. Evidence used for that:

- **Known protein function** — where specific mutation types are known to be
  disruptive (reducing function, or increasing/altering normal activity).
- **Predictive mechanisms for missense** — conservation across species, the
  physicochemical effect of the amino-acid change at that position, and — more
  recently — **structural models** of the protein and how the change disrupts
  structure.

The lab does this classification off the previous criteria (ACMG 2015/2019).
Those criteria use hard-to-remember letter/number labels; the College has since
moved toward a **more quantitative and more understandable** criteria set. *(Matt
is sending the draft of the updated ACMG guidelines.)*

The lab analyzes exome or genome data, looking at the molecular change **and**
the patient's clinical features, encoded as **HPO (Human Phenotype Ontology)**
terms with a built-in structure. Many phenotypes are mapped to genes and even
classes of mutations. Current interpretation = efficient, accurate extraction of
clinical info into HPO terms, then tools that prioritize variants from those
terms. *(Aside: there's room to improve the variant-prioritization algorithms
that use clinical features.)*

**What the lab struggles with:** once variants are prioritized (often ≤10
relevant candidates), reviewing the associated data is slow. Curated-data
companies exist and are fairly good, but it's still slow for a human to scan and
get a sense. **The opportunity:** highlight and prioritize highly relevant
literature/data, concisely — the clinical phenotype summarized precisely but also
broadly (patients don't always fully overlap), the inheritance type, the mutation
classes in the gene that produce each clinical phenotype, and any relevant data
for *this* variant in literature or databases — summarized concisely for
**directors** to review, improving the reporting process.

### Message 2 — the clinician's causality review (PhenoFit's core)

The clinician receives the lab report: **2–5 variants** with some suspicion of
causing the phenotype, based on the lab's often limited-granularity clinical
picture. The clinician's task: **is a variant in this report convincingly
causal of the clinical picture?** They re-look-up much of the lab's data but also
bring **much more nuance about the patient's actual features**.

Psychologically this is a **retrospective comparison** — does the patient match
what's expected for this "positive" variant? Two traps:

- **The mind overfits** the similarity to what's expected → need an **objective**
  way to do the comparison.
- **Partial explanation.** A clear variant may explain a large portion of
  features but not all. Are the extra features an **unreported extension** of the
  gene, or a **second underlying cause**? ~**5%** of individuals have a second
  positive reason. Then: account for features caused by the primary result, and
  decide whether to **re-analyze the genome** for the rest. *(Those extra features
  may not have been prioritized by the lab — so there may be no variant in the
  report relevant to them.)*

**The desired tool:** quickly gather info from the report, review the patient's
clinical features in a **highly granular** way (extraction from the electronic
record), and do a secondary interpretation / **prioritization of each variant's
relevance ("causality")** to the clinical picture. Also helpful: **what is known
about clinical management** of each disorder, and what the clinical team should
assess.

### Message 3 — intronic / intergenic / regulatory variants (the frontier)

Previously ignored because **exome-only sequencing** captures only exons (~1–2%
of the genome, the translated parts). Between exons are regions regulating how a
gene is spliced / alternatively spliced, and which transcripts are expressed in
which tissues. A relevant mutation should affect a transcript expressed in the
affected tissue.

The bigger challenge: **intronic and regulatory variants**, now seen far more
often with **whole-genome sequencing**. Short-read WGS (150–250 bp) can't map
highly repetitive regions, but handles the fairly unique regions — "**80–90% of
the genome**" *(Claude's clarification: short-read WGS reliably calls ~90%; the
stubborn ~5–8% — centromeres, segmental duplications, long tandem repeats — was
only resolved in 2022 by the T2T-CHM13 long-read complete genome)*.

Variants here are found mostly via **trio sequencing** (child vs parents):

- **Recessive:** each parent carries one changed copy; both come together in the
  child. Often one variant is found and the **second is missing** — increasingly
  it's non-exonic (UTR, intron, regulatory, or an aberrant splice site).
- **Dominant / severe disease:** the change is **de novo** (new in the child, not
  in either parent).

We still lack a good way to **assess pathogenicity** for these. Mechanisms:

- **Aberrant splice junction** — the gene is mis-spliced, perhaps tissue-specific.
- **Regulatory disruption** — enhancers / promoter regions. Reasonable, improving
  databases of predicted enhancers exist (ENCODE and others); large-scale
  assessment models exist *(Matt mentions Gladstone/UCSF data — link to follow)*.

**The desired tool:** identify intronic/intergenic variants suggestive of
disease (de novo, or compound-recessive across the two parents in/near an
appropriate gene), **prioritize them, and integrate them with the other candidate
variants** from Message 1/2.

---

## Part B — follow-up notes

- **Regulatory-assay reference (MPRA):**
  https://www.biorxiv.org/content/10.1101/2023.02.15.528663v2
  ("I'm sure there are references in that paper to other relevant projects.")
- **Task-2 UI:** drag a **PDF genetic-testing report** into the tool; also
  cut/paste or drag **other clinical reports** in, for more granular data →
  generate a prioritized **"causality"** list.
- **Causality score idea:** train a model on all clearly pathogenic
  variant/variant-combinations for individuals known to have disease, and emit a
  **0–1 probability** that a variant (or combination) causes a specific clinical
  disease.
- **Terminology:** use "variants", not "variance".

---

## Part C — Zoom meeting summary + action items

**Recap:** Discussed PhenoFit — AI tool evaluating whether reported variants
explain a patient's phenotype. Alex demoed a prototype (lab report → clinical
interpretation); hit an HPO/JAX API issue during the demo (full HPO term names
with parentheses). Matt walked through the clinical workflow: pathogenicity
verification, considering both mutation type and clinical presentation. Discussed
validating variant classifications and improving AI training via object tracing /
evals. Covered Mendelian-inheritance complexity and the need for expert clinical
context.

**Notable points from the call:**
- Prefer **protein-level** effects over nucleotide-level in the UI.
- **OMIM** as a structured source of truth (~26,000 entries; ~6,700 with known
  molecular basis; ~1,400 with unknown genetic basis).
- **Object tracing + evals** to show the AI's decision path (for RL / trust).
- **FBN1** can map to multiple disorders depending on the specific mutation —
  genotype→phenotype is many-to-many; presentation to a ~100-member Discord.
- Demo case: **4-year-old boy** — global developmental delay, seizures, lens
  dislocation, aortic root dilation; clinical description AI-generated.
- **SCN1A** nonsense, heterozygous, de novo → Dravet reasoning example.
- **HIPAA / pseudonymization** behind the firewall to safely use Claude.
- **AlphaGenome** case: **WDR26** variant explaining seizures + developmental
  delay; predicted functional impact and even a **treatment** strategy (blocking
  the problematic variant to restore gene function).

**Action items — Alex:**
1. Refine the demo over the weekend for **functionality/usefulness over UI
   aesthetics**.
2. Explore **OMIM** as a source of truth (structured).
3. Investigate **object tracing + evals** to show the AI's decision-making (for
   RL).

**Action items — Matt:**
1. Provide **pseudonymized clinical documents and lab reports** for testing.
2. Send **dictations** on report verification & pathogenicity classification
   *(delivered — Part A)*.
3. Consider a **pseudonymizer behind the firewall** to enable safe external-AI
   use.

---

## Part D — requirement extraction, mapped to status

Status legend: ✅ built · 🟡 partial · ⬜ not started · ⏳ awaiting Matt

### Task 1 — lab-side classification support (mostly new scope)
- ⬜ Concise **director-facing evidence summary** per variant: phenotype (precise
  + broad), inheritance, mutation-class→phenotype, and this-variant literature /
  database evidence.
- ⏳ Adopt the **updated quantitative ACMG** criteria (awaiting Matt's draft).

### Task 2 — clinician causality review (PhenoFit's core)
- ✅ Objective explained-vs-unexplained scoring (counters overfitting).
- ✅ ~5% **dual-diagnosis** flag + genome **re-analysis** trigger.
- ✅ **PDF** lab-report ingestion at the Claude edge.
- ✅ **OMIM** corroboration (structured source of truth).
- ✅ **Decision traces + eval** harness (for trust / RL).
- ✅ **Protein-level** molecular-consequence axis.
- ✅ HPO parenthetical-name sanitization (the demo bug).
- ✅ **Multi-document** ingestion — accept *other* clinical reports/notes, not
  just the lab PDF, for granular phenotyping (2026-07-11).
- ✅ **Clinical management / "what to assess next"** per disorder — curated links
  + labeled AI-drafted brief (2026-07-11).
- 🟡 **0–1 causality score** — provisional heuristic shipped; a trained model
  awaits Matt's pseudonymized pathogenic cases.

### Task 3 — intronic / intergenic / regulatory frontier (the "cloud science")
- 🟡 **AlphaGenome** routing for non-coding/splicing (prototyped on biohack
  `feat/alphagenome-noncoding`).
- 🟡 **MPRA regulatory model** (biohack `feat/mpra-regulatory-model`; matches the
  bioRxiv reference).
- 🟡 **Trio** de-novo / compound-recessive prioritization (biohack
  `feat/trio-noncoding-prioritizer`).
- ⬜ **Integrate** regulatory/intronic candidates into the same ranked causality
  list as coding variants.
- ⏳ **Gladstone/UCSF** enhancer-assessment link (awaiting Matt).

### Cross-cutting
- ⬜ Rename "variance" → "variants" wherever it appears.
- ⬜ **Pseudonymization** path for HIPAA-safe use behind a firewall.
- ⬜ Provider-note **reliability weighting** (e.g. epilepsy, many providers).

---

## Part E — awaiting from Matt
- Draft of the **updated (quantitative) ACMG** guidelines.
- **Pseudonymized** clinical documents + lab reports (test fixtures).
- **Gladstone/UCSF** regulatory-model link.
