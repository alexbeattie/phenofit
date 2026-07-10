"""Molecular-consequence classification from HGVS notation.

Matt's central note on the demo: a review that only looks at the *gene* is
blind to the thing a clinician actually weighs — the *kind* of change and its
mechanism. A nonsense change that abolishes the protein (loss-of-function) is a
different clinical object from a missense change that swaps one residue, even in
the same gene. This module turns the reported HGVS string into that category.

It is deliberately conservative. Protein-level notation (`p.Arg1213*`) is a
precise, translatable statement, so we classify it confidently. Coding notation
(`c.3637C>T`) mostly is NOT: a substitution could be missense, nonsense, or
synonymous depending on the codon, which the coding string alone cannot tell us —
so we ABSTAIN ("undetermined") rather than guess. The only coding forms we call
are the ones the notation itself determines: a canonical splice-site position,
and an insertion/deletion whose length fixes the reading frame.

Nothing here asserts pathogenicity. Mechanism is an annotation a clinician reads
alongside the phenotype fit — never a substitute for the lab's classification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Mechanism(str, Enum):
    """Broad functional bucket a consequence falls into."""

    LOSS_OF_FUNCTION = "loss-of-function"   # nonsense, frameshift, canonical splice, start-loss
    ALTERED_PROTEIN = "altered-protein"     # missense, in-frame indel, stop-loss
    SILENT = "silent"                        # synonymous
    UNDETERMINED = "undetermined"            # a real change of unknown effect (bare substitution)
    UNKNOWN = "unknown"                      # no usable notation at all


@dataclass(frozen=True)
class VariantConsequence:
    """The classified effect of a variant, with the notation it was read from."""

    category: str          # "nonsense", "frameshift", "missense", "splice", ...
    mechanism: Mechanism
    confident: bool        # True only when the notation determines the call
    notation: str          # the HGVS string the call was based on ("" if none)
    summary: str           # one-line human-readable description

    @property
    def is_loss_of_function(self) -> bool:
        return self.mechanism is Mechanism.LOSS_OF_FUNCTION


_SUMMARIES = {
    "nonsense": "nonsense (stop-gain) — predicted loss-of-function",
    "frameshift": "frameshift — predicted loss-of-function",
    "splice": "canonical splice-site change — predicted loss-of-function",
    "start loss": "start-codon loss — predicted loss-of-function",
    "stop loss": "stop-codon loss — altered (extended) protein",
    "missense": "missense — single-residue substitution, altered protein",
    "inframe indel": "in-frame indel — altered protein, reading frame preserved",
    "synonymous": "synonymous — no change to the protein sequence",
    "substitution": "coding substitution — protein effect undetermined from c. notation",
    "indel": "indel — reading-frame effect undetermined from the notation",
    "unknown": "no HGVS notation to classify",
}


def _consequence(category: str, mechanism: Mechanism, confident: bool, notation: str) -> VariantConsequence:
    return VariantConsequence(
        category=category,
        mechanism=mechanism,
        confident=confident,
        notation=notation,
        summary=_SUMMARIES.get(category, category),
    )


# --- protein notation (the precise path) -----------------------------------

# <aa><pos><aa>, 3-letter (Arg) or 1-letter (R), differing residues -> missense.
_MISSENSE_RE = re.compile(r"^([a-z]{3}|[a-z])(\d+)([a-z]{3}|[a-z])$")
# A change AT the initiator methionine (Met1 / M1) -> start loss.
_START_RE = re.compile(r"^(met|m)1(?![0-9])(.+)$")


def _classify_protein(hgvs_p: str) -> tuple[str, Mechanism] | None:
    s = hgvs_p.strip()
    if s.lower().startswith("p."):
        s = s[2:].strip()
    if s.startswith("(") and s.endswith(")"):   # predicted, e.g. p.(Arg1213*)
        s = s[1:-1].strip()
    if not s or s == "?":
        return None                              # p.? — unknown, defer to coding
    low = s.lower()

    if "fs" in low:
        return "frameshift", Mechanism.LOSS_OF_FUNCTION    # check before the Ter it may carry
    if s.endswith("="):
        return "synonymous", Mechanism.SILENT
    start = _START_RE.match(low)
    if start:
        return "start loss", Mechanism.LOSS_OF_FUNCTION    # before nonsense: Met1* etc.
    if s.endswith("*") or low.endswith("ter"):
        return "nonsense", Mechanism.LOSS_OF_FUNCTION
    if any(k in low for k in ("del", "dup", "ins")):
        return "inframe indel", Mechanism.ALTERED_PROTEIN  # frameshift already ruled out above
    if low.startswith("ter") or s.startswith("*"):
        return "stop loss", Mechanism.ALTERED_PROTEIN
    mm = _MISSENSE_RE.match(low)
    if mm and mm.group(1) != mm.group(3):
        return "missense", Mechanism.ALTERED_PROTEIN
    return None


# --- coding notation (determinable cases only) -----------------------------

def _frame_change(hgvs_c: str) -> int | None:
    """Net length change (in bases) of an indel, or None if the notation hides it."""

    low = hgvs_c.lower()
    if "delins" in low:
        span = re.search(r"(\d+)_(\d+)", hgvs_c)
        del_len = (int(span.group(2)) - int(span.group(1)) + 1) if span else 1
        ins_seq = low.rsplit("ins", 1)[1]
        if re.fullmatch(r"[acgt]+", ins_seq):
            ins_len = len(ins_seq)
        elif ins_seq.isdigit():
            ins_len = int(ins_seq)
        else:
            return None
        return abs(del_len - ins_len)
    if "ins" in low:
        ins_seq = low.rsplit("ins", 1)[1]
        if re.fullmatch(r"[acgt]+", ins_seq):
            return len(ins_seq)
        if ins_seq.isdigit():
            return int(ins_seq)
        return None
    # del / dup: a range fixes the span; a single position is one base.
    span = re.search(r"(\d+)_(\d+)", hgvs_c)
    return (int(span.group(2)) - int(span.group(1)) + 1) if span else 1


def _classify_coding(hgvs_c: str) -> tuple[str, Mechanism, bool] | None:
    s = hgvs_c.strip()
    if s.lower().startswith("c."):
        s = s[2:].strip()
    if not s:
        return None
    low = s.lower()

    # Canonical splice site: an intronic offset of ±1 or ±2 from an exon boundary.
    offset = re.search(r"[+-](\d+)", s)
    if offset and int(offset.group(1)) in (1, 2):
        return "splice", Mechanism.LOSS_OF_FUNCTION, True

    if any(k in low for k in ("del", "dup", "ins")):
        change = _frame_change(s)
        if change is None:
            return "indel", Mechanism.UNDETERMINED, False
        if change % 3 == 0:
            return "inframe indel", Mechanism.ALTERED_PROTEIN, True
        return "frameshift", Mechanism.LOSS_OF_FUNCTION, True

    if ">" in s:
        # A bare coding substitution: could be missense/nonsense/synonymous. The
        # coding string alone cannot say which — abstain rather than overcall.
        return "substitution", Mechanism.UNDETERMINED, False

    return None


def classify(hgvs_c: str = "", hgvs_p: str = "") -> VariantConsequence:
    """Classify a variant's molecular consequence from its HGVS notation.

    Protein notation is preferred when present (it is precise); coding notation is
    used only for the cases it determines. Returns an UNKNOWN/undetermined result
    rather than guessing when the notation cannot support a confident call.
    """

    protein = _classify_protein(hgvs_p) if hgvs_p else None
    if protein is not None:
        category, mechanism = protein
        return _consequence(category, mechanism, True, hgvs_p.strip())

    coding = _classify_coding(hgvs_c) if hgvs_c else None
    if coding is not None:
        category, mechanism, confident = coding
        return _consequence(category, mechanism, confident, hgvs_c.strip())

    return _consequence("unknown", Mechanism.UNKNOWN, False, (hgvs_p or hgvs_c).strip())
