#!/usr/bin/env bash
#
# demo.sh — a guided tour of PhenoFit.
#
# Runs a few causality reviews end to end against the live HPO ontology, each
# chosen to make one point. Before every run it prints WHY the case matters, so
# the demo tells a story instead of just dumping output.
#
#   ./demo.sh            # run the whole reel, pausing between cases
#   ./demo.sh --no-pause # run straight through (good for recording)

set -u

if [[ -x ".venv/bin/python" ]]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

PAUSE=1
[[ "${1:-}" == "--no-pause" ]] && PAUSE=0

if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; CYAN=$'\033[36m'; GREEN=$'\033[32m'; RESET=$'\033[0m'
else
  BOLD=""; DIM=""; CYAN=""; GREEN=""; RESET=""
fi

step=0
case_run() {
  local title="$1"; shift
  local point="$1"; shift
  step=$((step + 1))
  echo
  echo "${CYAN}########################################################################${RESET}"
  echo "${CYAN}#${RESET} ${BOLD}DEMO ${step}: ${title}${RESET}"
  echo "${CYAN}#${RESET} ${DIM}Why it matters:${RESET} ${point}"
  echo "${CYAN}########################################################################${RESET}"
  "$PY" -m phenofit.cli "$@"
  if [[ "$PAUSE" -eq 1 ]]; then
    echo; read -r -p "${DIM}[enter] for the next case...${RESET}" _
  fi
}

echo "${GREEN}${BOLD}"
echo "  PhenoFit — does a reported variant explain THIS patient?"
echo "${RESET}${DIM}  The lab reports variants; you hold the patient. Each case below runs"
echo "  the reverse match against the live HPO ontology.${RESET}"

# 1. The flagship: a dual diagnosis the lab's per-variant view can miss.
case_run \
  "Dual diagnosis — two independent causes" \
  "No single reported variant explains the whole picture: SCN1A covers the seizures/DD/ataxia, FBN1 covers the ectopia lentis/aortic root/tall stature. PhenoFit ranks both and FLAGS that together they explain it — the ~5% two-diagnoses case a per-variant view can miss." \
  --variant "SCN1A:c.3637C>T:p.Arg1213*" --variant "FBN1:c.4082G>A:p.Cys1361Tyr" --variant "MYH7:c.1063G>A:p.Ala355Thr" \
  --hpo "Seizure" --hpo "Global developmental delay" --hpo "Gait ataxia" \
  --hpo "Ectopia lentis" --hpo "Aortic root dilatation" --hpo "Tall stature" --hpo "Arachnodactyly"

# 2. A clean single best-fit.
case_run \
  "Clean single fit — the easy, reassuring case" \
  "When one variant really does explain everything, PhenoFit says so plainly (Best fit, full picture) instead of hedging — the mirror image of the hard case." \
  --variant "SCN1A:c.3637C>T:p.Arg1213*" --variant "MYH7:c.1063G>A:p.Ala355Thr" \
  --hpo "Seizure" --hpo "Febrile seizure" --hpo "Global developmental delay" --hpo "Ataxia"

# 3. A residual feature nothing explains -> re-analysis trigger.
case_run \
  "An orphan feature — the re-analysis trigger" \
  "A feature no reported variant explains isn't a rounding error; it's the signal to consider an unreported extension, a second cause, or a genome re-analysis. PhenoFit surfaces it instead of quietly dropping it." \
  --variant "SCN1A:c.3637C>T:p.Arg1213*" \
  --hpo "Seizure" --hpo "Global developmental delay" --hpo "Ectopia lentis"

echo
echo "${GREEN}${BOLD}  Demo complete.${RESET}"
echo "${DIM}  Every gene-phenotype link above is cited to HPO; a gene with no"
echo "  retrievable knowledge is marked unscored, never guessed.${RESET}"
echo
