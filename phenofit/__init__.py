"""PhenoFit — does a reported variant actually explain THIS patient?

Genetic diagnosis has two people doing two different jobs. The lab classifies
candidate variants off relatively thin clinical detail and reports back 2-5 that
look suspicious. The clinician then holds what the lab never had: the patient's
fully worked-up phenotype. PhenoFit is the clinician's tool for the second job —
it runs the match in *reverse*.

For each reported variant, it asks how well that gene's known disease phenotype
explains THIS patient's HPO features, ranks the variants by fit, and — the part
a clinician's intuition tends to skip — it is honest about what's left over:

  * features a variant leaves *unexplained* are shown, not glossed;
  * a partial match reads as "explains 3 of 5", never "close enough";
  * features that NO reported variant explains raise a second-cause / genome
    re-analysis flag; and
  * when two variants are each partly responsible, it flags the ~5% "two
    independent diagnoses" case.

Two hard rules:
  * No PHI. Phenotypes are HPO term ids and gene knowledge is public (HPO/Jax),
    so the same engine can run against real EMR-derived HPO profiles behind a
    site's firewall without code changes.
  * Cite everything, abstain otherwise. Every gene-phenotype link carries an
    openable source URL, and a gene with no retrievable knowledge is marked
    unscored rather than guessed.
"""

__version__ = "0.1.0"
