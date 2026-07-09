"""HPO (Human Phenotype Ontology) client, via the public Jax ontology API.

Three jobs:
  1. free text -> HPO term, so a clinician can type "seizures" instead of
     looking up HP:0001250;
  2. gene symbol -> the set of HPO phenotype ids known for that gene's diseases
     (the knowledge we match the patient against);
  3. term -> its is_a ancestors, so a gene annotated to a broad term (Seizure)
     still explains a patient's more specific feature (Focal-onset seizure).

Public API (ontology.jax.org), no key required. Every gene result carries an
openable source URL so a clinician can verify the gene-disease link.
"""

from __future__ import annotations

import math
import re

import httpx

from .http import get_json, now_iso
from .models import GenePhenotypeKnowledge, Phenotype, Source

JAX_API = "https://ontology.jax.org/api"

# Size of the HPO disease-annotation corpus (diseases annotated under the root
# "Phenotypic abnormality", HP:0000118). Used as the denominator for a term's
# information content. Held as a constant so scoring is fast and deterministic
# rather than paying a multi-thousand-row fetch of the root on every run; it
# drifts slowly and only the *ratio* between terms drives the weighting.
_TOTAL_DISEASES = 12888

# Ontology roots carry no clinical meaning.
_ROOT_NAMES = {"All", "Phenotypic abnormality"}

# Grouping / "container" category nodes, e.g. "Abnormality of the cardiovascular
# system", "Abnormal nervous system physiology", "Neurodevelopmental
# abnormality". Matching a patient feature to a gene THROUGH one of these is
# spurious — it only means the gene has *some* annotation somewhere under that
# whole category (which is how a connective-tissue gene like FBN1 would appear to
# "explain" developmental delay, via the shared parent "Neurodevelopmental
# abnormality"). We exclude these from ancestor matching, while keeping real (if
# broad) clinical phenotypes like "Seizure" or "Cardiomyopathy". Erring toward
# leaving a feature unexplained is the safe direction for a tool whose whole
# thesis is not overfitting a partial match.
_SYSTEM_CONTAINER_RE = re.compile(
    r"^(abnormality of (the )?.+ system"
    r"|abnormal .+ system (morphology|physiology)"
    r"|.+ abnormality)$",  # grouping categories like "Neurodevelopmental abnormality"
    re.IGNORECASE,
)


# --- free text -> HPO term -------------------------------------------------

def _norm(text: str) -> str:
    """Lowercase and collapse whitespace for name/synonym comparison."""

    return re.sub(r"\s+", " ", text.strip().lower())


def _singular(text: str) -> str:
    """Crude singularization so 'seizures' matches the term named 'Seizure'."""

    return text[:-1] if len(text) > 3 and text.endswith("s") else text


# Filler words dropped before comparing a query to a term by tokens, so word
# order and connective words don't matter ("dilatation of the aortic root"
# matches the synonym "aortic root dilatation").
_STOPWORDS = {"of", "the", "a", "an", "and", "with", "to", "in", "on", "or"}

# Leading/trailing clinical qualifiers that a report may attach but that are not
# part of the canonical HPO term name ("recurrent seizures" -> "seizures").
# Dropped only as a *last resort* when nothing else grounds, and only if the
# stripped query then yields a confident (name/synonym) hit — so we ground to the
# correct general term rather than an unrelated top search hit.
_QUALIFIERS = {
    "recurrent", "chronic", "acute", "bilateral", "unilateral", "mild",
    "moderate", "severe", "progressive", "congenital", "intermittent",
    "episodic", "persistent", "diffuse", "multiple", "frequent", "occasional",
    "generalized", "generalised",
}


def _tokens(text: str) -> frozenset[str]:
    """Order- and stopword-insensitive singularized word set for matching."""

    words = re.findall(r"[a-z0-9]+", _norm(text))
    return frozenset(_singular(w) for w in words if w not in _STOPWORDS)


# Match strength buckets, best first. A term matched at any of these is a
# "strong" (confident) grounding; anything else is a weak fall-back.
def _match_bucket(term: dict, qn: str, qs: str, qtok: frozenset[str]) -> int | None:
    name = _norm(term.get("name", ""))
    if name == qn:
        return 0                                   # exact name
    if _singular(name) == qs:
        return 1                                   # name up to singular/plural
    syns = [_norm(s) for s in (term.get("synonyms") or [])]
    if qn in syns:
        return 2                                   # exact synonym
    if qtok and _tokens(name) == qtok:
        return 3                                   # name, ignoring order/fillers
    if qtok and any(_tokens(s) == qtok for s in syns):
        return 4                                   # synonym, ignoring order/fillers
    return None


def _rank_terms(terms: list[dict], query: str) -> tuple[dict | None, bool]:
    """Pick the best HPO term for a free-text query.

    The Jax search endpoint ranks by its own relevance, which for common terms
    surfaces an over-specific child ("Seizure cluster") above the canonical term
    ("Seizure"), or an adjacent term whose name happens to rank higher than the
    right one ("Aortic arch aneurysm" over "Aortic root aneurysm"). Grounding a
    patient's feature to the wrong term is the quiet-mangle failure this tool
    exists to avoid, so we prefer a match on the term's own name/synonym — by
    exact string, then order-insensitive tokens — over raw search rank.

    Returns (term, strong): `strong` is True when the query confidently matched a
    term's name or a synonym, rather than falling back to the API's top hit.
    """

    if not terms:
        return None, False

    qn = _norm(query)
    qs = _singular(qn)
    qtok = _tokens(query)

    best_term: dict | None = None
    best_bucket = 99
    for t in terms:
        if not t.get("id"):
            continue
        bucket = _match_bucket(t, qn, qs, qtok)
        if bucket is None:
            continue
        name_len = len(t.get("name", ""))
        # Prefer the better bucket; within a bucket the shortest name is the most
        # canonical/general term.
        if bucket < best_bucket or (bucket == best_bucket and best_term is not None
                                    and name_len < len(best_term.get("name", ""))):
            best_term, best_bucket = t, bucket

    if best_term is not None:
        return best_term, True
    return terms[0], False  # fall back to the API's top-ranked result


def _search_terms(client: httpx.Client, query: str) -> list[dict]:
    # `limit` is honored by the API; `max` is silently capped at 10.
    data = get_json(client, f"{JAX_API}/hp/search", params={"q": query, "limit": "40"})
    if isinstance(data, dict):
        return data.get("terms") or data.get("results") or []
    return []


def _strip_qualifiers(query: str) -> str:
    """Drop leading/trailing clinical qualifier words ('recurrent seizures')."""

    words = _norm(query).split()
    core = [w for w in words if _singular(w) not in {_singular(q) for q in _QUALIFIERS}]
    return " ".join(core)


def resolve_term(client: httpx.Client, query: str) -> Phenotype | None:
    """Resolve free text (or an HP:xxxxxxx id) to a single HPO term."""

    q = query.strip()
    if q.upper().startswith("HP:"):
        data = get_json(client, f"{JAX_API}/hp/terms/{q.upper()}")
        if isinstance(data, dict) and data.get("id"):
            return Phenotype(hpo_id=data["id"], label=data.get("name", q))
        return None

    best, strong = _rank_terms(_search_terms(client, q), q)

    # If no confident hit, retry with query variants and take a strong match if
    # one appears. (1) singular/plural: the canonical entry can be missing from
    # the first page (e.g. "Seizure" doesn't surface for "Seizure" but does for
    # "Seizures"). (2) qualifier-stripped: a report qualifier like "recurrent"
    # pulls the whole result set toward other "Recurrent …" terms, so drop it and
    # search the core phrase.
    if not strong:
        ql = q.lower()
        retries = []
        alt = _singular(ql) if ql.endswith("s") else q + "s"
        if _norm(alt) != _norm(q):
            retries.append(alt)
        core = _strip_qualifiers(q)
        if core and _norm(core) != _norm(q):
            retries.append(core)
            retries.append(core + "s")

        for alt_q in retries:
            alt_best, alt_strong = _rank_terms(_search_terms(client, alt_q), alt_q)
            if alt_strong:
                best, strong = alt_best, True
                break

    if best is None or not best.get("id"):
        return None
    return Phenotype(hpo_id=best["id"], label=best.get("name", q))


# --- term -> is_a ancestors ------------------------------------------------

# Ancestors are shared across genes/patients within a run, so cache them to keep
# the is_a graph walk to one API call per distinct term.
_ANCESTOR_CACHE: dict[str, set[str]] = {}


def ancestor_ids(client: httpx.Client, hpo_id: str) -> set[str]:
    """The term itself plus all its HPO is_a ancestors (minus roots/containers)."""

    if hpo_id in _ANCESTOR_CACHE:
        return _ANCESTOR_CACHE[hpo_id]

    ids = {hpo_id}
    try:
        data = get_json(client, f"{JAX_API}/hp/terms/{hpo_id}/ancestors")
        if isinstance(data, list):
            for t in data:
                name = t.get("name", "")
                if not t.get("id") or name in _ROOT_NAMES or _SYSTEM_CONTAINER_RE.match(name):
                    continue
                ids.add(t["id"])
    except Exception:
        pass  # fall back to exact-only matching for this term
    _ANCESTOR_CACHE[hpo_id] = ids
    return ids


# --- term -> information content (rarity) -----------------------------------

# IC is stable within (and across) runs, so cache it per term.
_IC_CACHE: dict[str, float] = {}


def information_content(client: httpx.Client, hpo_id: str) -> float:
    """Information content of a term: -log(diseases with it / all diseases).

    A rare, specific feature (Ectopia lentis, ~73 diseases) carries far more IC
    than a common, non-specific one (Global developmental delay, ~2900), which is
    exactly the clinical intuition that a rare finding is worth more diagnostic
    weight than a common one. Returns 0.0 (the least-informative floor) if the
    count can't be retrieved, so scoring degrades to near-equal weighting rather
    than failing.
    """

    if hpo_id in _IC_CACHE:
        return _IC_CACHE[hpo_id]

    ic = 0.0
    try:
        data = get_json(client, f"{JAX_API}/network/annotation/{hpo_id}")
        if isinstance(data, dict):
            n_diseases = len(data.get("diseases", []))
            freq = max(n_diseases, 1) / _TOTAL_DISEASES
            ic = -math.log(freq)
    except Exception:
        pass  # unknown -> 0.0, i.e. treated as maximally common
    _IC_CACHE[hpo_id] = ic
    return ic


# The IC of a maximally rare term (annotated to a single disease). Used to
# normalize IC into a bounded per-feature weight so no feature is ever weighted
# to zero (a common feature still counts, just less).
_MAX_IC = math.log(_TOTAL_DISEASES)


def ic_weight(client: httpx.Client, hpo_id: str, *, floor: float = 0.25) -> float:
    """Map a term's IC to a weight in [floor, 1.0]. Common -> floor, rare -> 1.0."""

    ic = information_content(client, hpo_id)
    return floor + (1.0 - floor) * (ic / _MAX_IC)


# --- gene -> known disease phenotypes --------------------------------------

# Gene knowledge is stable within a run and often queried repeatedly (a gene
# reported twice, or the same panel across many eval cases), so cache it.
_GENE_CACHE: dict[str, GenePhenotypeKnowledge] = {}


def _gene_id(client: httpx.Client, gene: str) -> str | None:
    """Map a gene symbol to its NCBIGene id via the network search endpoint."""

    data = get_json(client, f"{JAX_API}/network/search/GENE", params={"q": gene, "limit": "10"})
    results = data.get("results", []) if isinstance(data, dict) else []
    for r in results:
        if r.get("name", "").upper() == gene.upper():
            return r.get("id")
    return None


def fetch_gene_phenotypes(client: httpx.Client, gene: str) -> GenePhenotypeKnowledge:
    """All HPO phenotypes and diseases associated with a gene."""

    key = gene.upper()
    if key in _GENE_CACHE:
        return _GENE_CACHE[key]

    web_url = f"https://hpo.jax.org/browse/gene/{gene}"
    source = Source(name="HPO (Jax)", url=web_url, retrieved_at=now_iso(), detail=gene)

    gene_id = _gene_id(client, gene)
    if not gene_id:
        result = GenePhenotypeKnowledge(gene=gene, found=False, source=source)
        _GENE_CACHE[key] = result
        return result

    source.detail = f"{gene} ({gene_id})"
    source.url = f"https://ontology.jax.org/api/network/annotation/{gene_id}"

    data = get_json(client, f"{JAX_API}/network/annotation/{gene_id}")
    if not isinstance(data, dict) or "phenotypes" not in data:
        result = GenePhenotypeKnowledge(gene=gene, found=False, source=source)
        _GENE_CACHE[key] = result
        return result

    phenotype_labels = {p["id"]: p.get("name", p["id"]) for p in data.get("phenotypes", []) if p.get("id")}
    phenotype_ids = set(phenotype_labels)
    diseases = [d.get("name", "") for d in data.get("diseases", []) if d.get("name")]

    result = GenePhenotypeKnowledge(
        gene=gene,
        found=bool(phenotype_ids),
        diseases=diseases,
        phenotype_ids=phenotype_ids,
        phenotype_labels=phenotype_labels,
        source=source,
    )
    _GENE_CACHE[key] = result
    return result
