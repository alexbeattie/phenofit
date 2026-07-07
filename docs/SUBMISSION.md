# Submission materials

## Written summary (for the CV platform, ~160 words)

**PhenoFit — does a reported variant actually explain THIS patient?**

Genetic diagnosis splits into two jobs. The lab classifies candidate variants off
thin clinical detail and reports 2–5 suspicious ones. The clinician then holds the
patient's fully worked-up phenotype and must decide, per variant, whether it truly
explains *this* patient. PhenoFit is the clinician's tool for that second job: it
runs the match in reverse, scoring how well each reported gene's known disease
explains the patient's HPO features, ranking the variants, and — the part
intuition skips — being honest about what's left unexplained. It flags the ~5%
"two independent diagnoses" case and the residual features that trigger a genome
re-analysis.

Claude is used only at the ingestion edge: it reads a lab-report PDF or clinical
notes into structured variants and phenotype phrases via SDK structured outputs,
then every phrase is grounded in a real HPO term deterministically — the model
never invents an ontology id. Scoring stays AI-free, sourced, and abstains when it
lacks knowledge. Built from scratch; MIT; top-1 89% on a 9-case benchmark.

---

## 3-minute demo video script

**[0:00–0:25] The problem — a named user.**
"This is for Matt, a clinical geneticist. When a lab finishes, it sends him a
report with a handful of suspicious variants. Matt has something the lab didn't:
the patient's full clinical picture. His job is to ask, for each variant — does
this actually explain *this* patient? That's the question tools skip, and it's
where a second diagnosis hides."

**[0:25–0:55] The reverse match + the two traps.**
Show the landing page. "PhenoFit runs the match in reverse. And it's built around
two traps: the mind overfits a partial match, and a partial explanation can hide a
second cause. So it scores against an explicit feature set and it's honest about
what's left over."

**[0:55–1:35] Claude at the edge — drop the PDF.**
Drop `sample_lab_report.pdf`. "I drop the lab report. Claude reads the variants and
the phenotype off the page — using structured outputs, so it can't silently mangle
a report into wrong data. Then every phenotype phrase is grounded in a real HPO
term deterministically; the model never emits an ontology id. Everything it fills
is editable before I run it." Point at the filled variant + feature boxes.

**[1:35–2:30] Run it — the dual diagnosis.**
Click Run. "No single variant explains everything. FBN1 — Marfan — explains the
ectopia lentis, aortic root, tall stature. SCN1A explains the seizures,
developmental delay, ataxia that FBN1 can't. PhenoFit ranks both and flags a
possible dual diagnosis: two independent causes. Each feature is tagged explained
or not; every gene links back to its HPO source; a gene with no knowledge is marked
unscored, never guessed."

**[2:30–3:00] Trust + eval, close.**
"No PHI — it's all ontology ids and public knowledge, so it can run behind a
hospital firewall unchanged. On a 9-case benchmark it ranks the true gene first
89% of the time — and I'm upfront that that's a ranking check, not a clinical
validation yet. It's open source, it runs from a fresh clone in a minute, with or
without an API key. That's PhenoFit."

---

## Screenshots

- `docs/screenshots/01-landing.png` — landing view
- `docs/screenshots/02-ranked-result.png` — the dual-diagnosis ranking + flags
- `docs/screenshots/03-result-closeup.png` — results column close-up

## Judging-criteria map

- **Impact (25%):** a named clinician's real daily task; reverse causality review
  + dual-diagnosis/re-analysis triggers; runnable behind a firewall (no PHI).
- **Claude Use (25%):** structured-output ingestion edge with a hard grounding
  contract (LLM proposes, ontology validates), so AI never touches the scored call.
- **Depth & Execution (20%):** deterministic sourced engine, ontology-aware
  matching with container-node exclusion, abstention, 23 offline tests, a
  measured eval with an honest caveat.
- **Demo (30%):** one-drop PDF → ranked, cited answer with a genuine
  dual-diagnosis story; runs from a clean clone.
