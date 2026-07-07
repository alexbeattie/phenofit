"""Claude at the ingestion edge — structured, honest, and skippable.

Used only to turn messy free text (a lab-report PDF, pasted clinical notes) into
STRUCTURED input: the reported variants and candidate phenotype phrases. The
model only ever *proposes* text; every phenotype phrase is then grounded in a
real HPO term by the deterministic search in `hpo.py`, so the model never emits
an HPO id and the scoring core stays AI-free and sourced.

Two design choices that matter for a clinical tool:

  * We use the Anthropic SDK's `messages.parse(output_format=...)` with Pydantic
    schemas, so the model's proposal is guaranteed to be *shaped* correctly or
    raises a clean error. We never regex-scrape a JSON array out of prose — a
    malformed reply that got silently mangled into a plausible-but-wrong list is
    exactly the dangerous, invisible failure mode this tool must not have.
  * The SDK client is built with automatic retries, so transient 429/5xx blips
    are handled, and its typed exceptions are mapped to one `LLMError` with a
    message that names what broke.

The key is read from ANTHROPIC_API_KEY (never hard-coded, never logged); the
model is overridable via ANTHROPIC_MODEL. With no key set, `is_configured()`
returns False and callers degrade gracefully to manual entry.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

DEFAULT_MODEL = "claude-sonnet-5"  # supports structured outputs; override with ANTHROPIC_MODEL
_MAX_TOKENS = 4096  # room for a multi-variant report


class LLMError(RuntimeError):
    """Raised when the LLM call can't be made or its output can't be validated."""


# --- structured-output schemas ---------------------------------------------

class ReportedVariantOut(BaseModel):
    gene: str = Field(description="HGNC gene symbol, e.g. SCN1A")
    hgvs: str = Field(default="", description="coding HGVS such as c.3637C>T, empty if absent")
    classification: str = Field(default="", description="lab's call, e.g. Pathogenic / VUS, empty if absent")


class VariantExtraction(BaseModel):
    variants: list[ReportedVariantOut] = Field(default_factory=list)


class PhenotypeExtraction(BaseModel):
    phrases: list[str] = Field(
        default_factory=list,
        description="short canonical clinical phrases suitable for HPO lookup",
    )


_PHENOTYPE_SYSTEM = (
    "You are a clinical phenotyping assistant. Given free-text clinical content, "
    "extract the patient's OBSERVED phenotypic abnormalities as short, canonical "
    "clinical terms suitable for looking up in the Human Phenotype Ontology (HPO). "
    "Include only positive findings actually present in THIS patient; exclude "
    "explicitly negated findings, normal findings, family history, and "
    "procedures/medications. Prefer standard terminology (e.g. 'seizure', "
    "'hypertrophic cardiomyopathy', 'global developmental delay')."
)

_VARIANT_SYSTEM = (
    "You extract the reported genetic variants from a diagnostic lab report. "
    "Include only variants the lab actually reports for THIS patient; ignore "
    "methodology, references, and genes listed only as panel coverage. For each "
    "variant give the HGNC gene symbol, the coding-level HGVS (e.g. c.3637C>T, "
    "empty string if absent), and the lab's classification (e.g. Pathogenic, "
    "Likely pathogenic, VUS; empty string if absent)."
)


# --- SDK client (built once, injectable for tests) -------------------------

_client = None


def is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)


def get_sdk_client():
    """Lazily build a single Anthropic client with automatic retries."""

    global _client
    if _client is not None:
        return _client
    if not is_configured():
        raise LLMError(
            "ANTHROPIC_API_KEY is not set. Add it to a .env file or export it to "
            "enable the AI ingestion edge, or enter the variants and features manually."
        )
    try:
        import anthropic  # noqa: PLC0415  (optional dep, imported lazily)
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise LLMError("The `anthropic` package is not installed (`pip install anthropic`).") from exc
    _client = anthropic.Anthropic(max_retries=4)
    return _client


def _parse(system: str, user: str, schema, sdk_client=None):
    """One structured-output call; returns a validated schema instance."""

    client = sdk_client or get_sdk_client()
    try:
        import anthropic  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise LLMError("The `anthropic` package is not installed.") from exc

    try:
        resp = client.messages.parse(
            model=_model(),
            max_tokens=_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
    except anthropic.AuthenticationError as exc:
        raise LLMError("Anthropic API key invalid or missing.") from exc
    except anthropic.RateLimitError as exc:
        raise LLMError("Anthropic rate limited; retry shortly.") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMError("Could not reach the Anthropic API.") from exc
    except anthropic.APIStatusError as exc:
        raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
    except Exception as exc:  # validation / unexpected shape -> loud, not silent
        raise LLMError(f"Model returned an unexpected shape: {exc}") from exc

    parsed = resp.parsed_output
    if parsed is None:
        raise LLMError("Model returned no parseable structured output.")
    return parsed


def extract_phenotype_phrases(notes: str, *, sdk_client=None) -> list[str]:
    """Ask Claude for candidate phenotype phrases from clinical text."""

    result = _parse(_PHENOTYPE_SYSTEM, notes, PhenotypeExtraction, sdk_client=sdk_client)
    return [p.strip() for p in result.phrases if p and p.strip()]


def extract_variants_raw(report_text: str, *, sdk_client=None) -> list[dict]:
    """Ask Claude for the reported variants from lab-report text."""

    result = _parse(_VARIANT_SYSTEM, report_text, VariantExtraction, sdk_client=sdk_client)
    out: list[dict] = []
    for v in result.variants:
        if v.gene and v.gene.strip():
            out.append({
                "gene": v.gene.strip(),
                "hgvs": (v.hgvs or "").strip(),
                "classification": (v.classification or "").strip(),
            })
    return out
