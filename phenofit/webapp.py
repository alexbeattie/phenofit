"""Minimal web UI — zero third-party web framework.

Python's stdlib HTTP server serves one static page and a few JSON endpoints that
run the *real* scoring engine and the *real* AI edge — no mock data. The UI
calls the same `review_causality` the CLI does.

    python -m phenofit.webapp            # then open http://localhost:8000
    python -m phenofit.webapp --port 8080

Input: the variants the lab reported + the patient's features (free text or
HP:xxxxxxx), optionally auto-filled by dropping a lab-report PDF or pasting
clinical notes. Output: the ranked causality list, with explained vs unexplained
features, source links, and the second-cause / dual-diagnosis flags.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hmac
import json
import os
import webbrowser
from dataclasses import fields
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import load_dotenv
from .coords import resolve as resolve_coords
from .engine import causality_probability, rarity_tag as _rarity_tag, review_causality
from .extract import extract_from_notes, ingest_documents, ingest_report
from .alphagenome_isolation import run_isolated
from .jobs import JobRegistry
from .noncoding import is_configured as alphagenome_configured
from .hpo import resolve_term
from .http import get_client
from .llm import LLMError, draft_management_brief, is_configured
from .management import curated_links
from .models import PatientProfile, Phenotype, ReportedVariant, parse_variant_spec
from .omim import corroborate as omim_corroborate, is_configured as omim_configured
from .trace import build_trace
from .pdf import PdfError, extract_text

STATIC_DIR = Path(__file__).parent / "static"

# Optional HTTP Basic Auth. When APP_PASSWORD is set (production), every request
# must carry matching Basic credentials; when it's unset (local dev), auth is off
# and the server behaves exactly as before.
_AUTH_USER = os.environ.get("APP_USER", "matt")
_AUTH_PASSWORD = os.environ.get("APP_PASSWORD", "")


def _credentials_ok(header: str | None, user: str, password: str) -> bool:
    """True if an HTTP Basic `Authorization` header matches `user:password`.

    Constant-time comparison so a wrong guess leaks no timing signal.
    """
    if not header or not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:], validate=True).decode("utf-8", "replace")
    except (binascii.Error, ValueError):
        return False
    got_user, _, got_pass = decoded.partition(":")
    return hmac.compare_digest(got_user, user) and hmac.compare_digest(got_pass, password)


def _parse_variants(raw: list[str]) -> list[ReportedVariant]:
    return [v for v in (parse_variant_spec(line) for line in raw) if v]


def _run_review(payload: dict) -> dict:
    """Resolve features to HPO, run the engine, and serialize the report."""

    variants = _parse_variants(payload.get("variants", []))
    feature_lines = [f.strip() for f in payload.get("features", []) if f.strip()]

    with get_client() as client:
        phenotypes: list[Phenotype] = []
        unresolved: list[str] = []
        for raw in feature_lines:
            term = resolve_term(client, raw)
            if term is None:
                unresolved.append(raw)
            else:
                phenotypes.append(term)

        if not variants:
            return {"error": "No reported variants given."}
        if not phenotypes:
            return {"error": "No patient features could be resolved to HPO terms.", "unresolved": unresolved}

        patient = PatientProfile(phenotypes=phenotypes)
        report = review_causality(client, patient, variants)
        omim_corroborate(client, report.fits)

    return {
        "patient": [{"hpo_id": p.hpo_id, "label": p.label} for p in report.patient.phenotypes],
        "unresolved": unresolved,
        "fits": [
            {
                "rank": i,
                "gene": f.variant.gene,
                "hgvs": f.variant.hgvs_c,
                "hgvs_p": f.variant.hgvs_p,
                "consequence": {
                    "category": f.variant.consequence.category,
                    "mechanism": f.variant.consequence.mechanism.value,
                    "confident": f.variant.consequence.confident,
                    "summary": f.variant.consequence.summary,
                },
                "label": f.variant.label,
                "stars": f.tier.stars,
                "tier": f.tier.display,
                "tier_level": int(f.tier),
                "score": round(f.score, 3),
                "explained_count": len(f.explained),
                "total": len(report.patient.phenotypes),
                "causality_probability": causality_probability(f),
                "explained": [
                    {"label": m.phenotype.label, "exact": m.exact, "via": m.via,
                     "weight": round(m.weight, 3), "rarity": _rarity_tag(m.weight)}
                    for m in f.explained
                ],
                "unexplained": [p.label for p in f.unexplained],
                "diseases": f.diseases[:3],
                "knowledge_found": f.knowledge_found,
                "source": f.source.url if f.source else "",
                "omim": _omim_json(f),
                "management_links": [
                    {"name": s.name, "url": s.url, "detail": s.detail}
                    for s in curated_links(f.variant.gene, _first_omim_mim(f))
                ],
                "top_disease": _top_disease(f),
            }
            for i, f in enumerate(report.fits, 1)
        ],
        "residual": [p.label for p in report.residual_unexplained],
        "flags": report.flags,
        "omim_enabled": omim_configured(),
        "trace": build_trace(report),
    }


def _omim_json(fit) -> dict | None:
    """Serialize a fit's OMIM corroboration, or None when nothing was attached."""

    ev = fit.omim
    if ev is None or not ev.available:
        return None
    return {
        "diseases": [{"name": p.name, "mim": p.mim, "inheritance": p.inheritance}
                     for p in ev.phenotypes[:4]],
        "inheritance": ev.inheritance_patterns,
        "source": ev.source.url if ev.source else "",
    }


def _first_omim_mim(fit) -> str | None:
    """The first OMIM phenotype MIM for a fit's gene, to deep-link its OMIM entry."""

    ev = fit.omim
    if ev is None or not ev.available:
        return None
    for p in ev.phenotypes:
        if p.mim:
            return p.mim
    return None


def _top_disease(fit) -> str:
    """The best single disease label to hand the management brief (OMIM, then HPO)."""

    ev = fit.omim
    if ev is not None and ev.available and ev.phenotypes:
        return ev.phenotypes[0].name
    return fit.diseases[0] if fit.diseases else ""


def _run_extract(payload: dict) -> dict:
    """Free-text clinical notes -> validated HPO phenotypes via the AI edge."""

    notes = (payload.get("notes") or "").strip()
    if not notes:
        return {"error": "No clinical notes provided."}
    with get_client() as client:
        try:
            result = extract_from_notes(client, notes)
        except LLMError as exc:
            return {"error": str(exc)}
    return {
        "phenotypes": [
            {"phrase": e.phrase, "hpo_id": e.phenotype.hpo_id, "label": e.phenotype.label}
            for e in result.phenotypes
        ],
        "ungrounded": result.ungrounded,
    }


def _run_ingest_pdf(payload: dict) -> dict:
    """A dropped lab-report PDF -> reported variants + validated HPO phenotypes."""

    b64 = payload.get("pdf_base64") or ""
    if not b64:
        return {"error": "No PDF data received."}
    try:
        data = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        return {"error": "PDF data was not valid base64."}

    try:
        text = extract_text(data)
    except PdfError as exc:
        return {"error": str(exc)}

    with get_client() as client:
        try:
            ingest = ingest_report(client, text)
        except LLMError as exc:
            return {"error": str(exc)}

    return {
        "variants": ingest.variants,
        "phenotypes": [
            {"phrase": e.phrase, "hpo_id": e.phenotype.hpo_id, "label": e.phenotype.label}
            for e in ingest.phenotypes.phenotypes
        ],
        "ungrounded": ingest.phenotypes.ungrounded,
        "chars": len(text),
    }


def _run_ingest_docs(payload: dict) -> dict:
    """Several dropped/pasted clinical documents -> merged variants + phenotypes.

    `documents` is a list of {role, kind, content, name}: kind "pdf" carries
    base64, kind "text" carries raw text. Lab reports yield variants; every
    document yields phenotypes, merged and deduped across the set.
    """

    raw_docs = payload.get("documents") or []
    if not raw_docs:
        return {"error": "No documents provided."}

    prepared: list[dict] = []
    for i, d in enumerate(raw_docs):
        name = d.get("name") or f"document {i + 1}"
        role = d.get("role") or "clinical_note"
        kind = d.get("kind") or "text"
        if kind == "pdf":
            try:
                data = base64.b64decode(d.get("content") or "", validate=True)
            except (binascii.Error, ValueError):
                return {"error": f"{name}: PDF data was not valid base64."}
            try:
                text = extract_text(data)
            except PdfError as exc:
                return {"error": f"{name}: {exc}"}
        else:
            text = d.get("content") or ""
        prepared.append({"role": role, "name": name, "text": text})

    with get_client() as client:
        try:
            ingest = ingest_documents(client, prepared)
        except LLMError as exc:
            return {"error": str(exc)}

    return {
        "variants": ingest.variants,
        "phenotypes": [
            {"phrase": e.phrase, "hpo_id": e.phenotype.hpo_id,
             "label": e.phenotype.label, "source_doc": e.source_doc}
            for e in ingest.phenotypes.phenotypes
        ],
        "ungrounded": ingest.phenotypes.ungrounded,
        "docs": ingest.docs,
    }


def _run_management(payload: dict) -> dict:
    """AI-drafted, verify-against-source management brief for a gene/disorder.

    Gated by the API key (curated links carry the load without it); the model is
    instructed to abstain when unsure, surfaced here as confident=False.
    """

    gene = (payload.get("gene") or "").strip()
    disease = (payload.get("disease") or "").strip()
    if not gene:
        return {"error": "No gene provided."}
    if not is_configured():
        return {"error": "AI brief unavailable (ANTHROPIC_API_KEY not set). Use the curated links."}
    try:
        brief = draft_management_brief(gene, disease)
    except LLMError as exc:
        return {"error": str(exc)}
    return {
        "gene": gene,
        "disease": disease,
        "confident": brief.confident,
        "surveillance": brief.surveillance,
        "management": brief.management,
        "systems_to_assess": brief.systems_to_assess,
        "caveat": brief.caveat,
    }


def _run_alphagenome(
    payload: dict,
    *,
    progress=None,
    cancel_event=None,
    _isolated_runner=run_isolated,
) -> dict:
    """Resolve a variant's coordinates and score its non-coding/splicing effect.

    Gene + coding HGVS -> GRCh38 coordinates (Ensembl VEP, free) -> AlphaGenome
    splicing + regulatory signals. Gated by ALPHAGENOME_API_KEY; abstains with a
    reason on any failure. Research-model output, surfaced as such.
    """

    gene = (payload.get("gene") or "").strip()
    hgvs = (payload.get("hgvs") or "").strip()
    if not gene:
        return {"error": "No gene provided."}
    if not alphagenome_configured():
        return {"error": "AlphaGenome unavailable (ALPHAGENOME_API_KEY not set)."}

    if progress:
        progress("resolving_coordinates", "Resolving GRCh38 coordinates with Ensembl VEP…")
    with get_client() as client:
        co = resolve_coords(client, gene, hgvs)
    if not co.resolved:
        return {"error": f"Could not resolve coordinates via VEP: {co.reason}"}

    if progress:
        progress("starting_worker", "Starting isolated AlphaGenome worker…")
    coordinate_payload = {
        field.name: getattr(co, field.name)
        for field in fields(co)
        if field.name != "source"
    }
    return _isolated_runner(
        {"coordinates": coordinate_payload},
        progress=progress,
        cancel_event=cancel_event,
    )


_JOBS = JobRegistry(_run_alphagenome)


class _Server(ThreadingHTTPServer):
    allow_reuse_address = True  # rebind immediately after a restart


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the console clean
        pass

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, value: dict) -> None:
        self._send(code, json.dumps(value).encode(), "application/json")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def _authorized(self) -> bool:
        """Enforce Basic Auth when APP_PASSWORD is set; send 401 and return False if not."""
        if not _AUTH_PASSWORD:
            return True
        if _credentials_ok(self.headers.get("Authorization"), _AUTH_USER, _AUTH_PASSWORD):
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="PhenoFit"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def do_GET(self) -> None:
        if not self._authorized():
            return
        if self.path in ("/", "/index.html"):
            html = (STATIC_DIR / "index.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
        elif self.path == "/api/config":
            cfg = {"ai_enabled": is_configured(), "alphagenome_enabled": alphagenome_configured()}
            self._send_json(200, cfg)
        elif self.path.startswith("/api/jobs/"):
            snapshot = _JOBS.get(self.path.removeprefix("/api/jobs/").split("?", 1)[0])
            if snapshot is None:
                self._send_json(404, {"error": "Job not found."})
            else:
                self._send_json(200, snapshot)
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        if not self._authorized():
            return
        if self.path == "/api/alphagenome/jobs":
            try:
                payload = self._read_json()
            except (ValueError, json.JSONDecodeError) as exc:
                self._send_json(400, {"error": f"Invalid JSON: {exc}"})
                return
            if not (payload.get("gene") or "").strip():
                self._send_json(400, {"error": "No gene provided."})
                return
            if not alphagenome_configured():
                self._send_json(503, {"error": "AlphaGenome unavailable (ALPHAGENOME_API_KEY not set)."})
                return
            job_id = _JOBS.start(payload)
            if job_id is None:
                self._send_json(429, {"error": "AlphaGenome is busy; try again after a running job finishes."})
                return
            self._send_json(202, {"job_id": job_id})
            return
        routes = {
            "/api/review": _run_review,
            "/api/extract": _run_extract,
            "/api/ingest-pdf": _run_ingest_pdf,
            "/api/ingest-docs": _run_ingest_docs,
            "/api/management": _run_management,
            "/api/alphagenome": _run_alphagenome,
        }
        handler = routes.get(self.path)
        if handler is None:
            self._send(404, b"not found", "text/plain")
            return
        try:
            payload = self._read_json()
            result = handler(payload)
        except Exception as exc:  # surface to UI, don't 500 silently
            result = {"error": f"{type(exc).__name__}: {exc}"}
        self._send_json(200, result)

    def do_DELETE(self) -> None:
        if not self._authorized():
            return
        if not self.path.startswith("/api/jobs/"):
            self._send(404, b"not found", "text/plain")
            return
        job_id = self.path.removeprefix("/api/jobs/").split("?", 1)[0]
        if _JOBS.get(job_id) is None:
            self._send_json(404, {"error": "Job not found."})
        elif _JOBS.cancel(job_id):
            self._send_json(200, {"job_id": job_id, "message": "Cancellation requested."})
        else:
            self._send_json(409, {"error": "Job is already complete."})


def _bind(host: str, port: int, tries: int = 20) -> _Server:
    """Bind to `host:port`, or the next free port if it's already in use."""

    last: OSError | None = None
    for candidate in range(port, port + tries):
        try:
            return _Server((host, candidate), Handler)
        except OSError as exc:
            last = exc
            if candidate == port:
                print(f"Port {port} is busy; trying {port + 1}…")
    raise SystemExit(f"No free port in {port}-{port + tries - 1}: {last}")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="PhenoFit web UI.")
    # A hosting platform injects $PORT (and we bind $HOST=0.0.0.0); locally these
    # are unset and the old 127.0.0.1:8000 behavior is preserved.
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--no-open", action="store_true", help="don't auto-open a browser")
    args = parser.parse_args()

    # When the platform assigns an exact port, bind it strictly (no fallback
    # scan) and never try to open a browser.
    hosted = "PORT" in os.environ
    server = _bind(args.host, args.port, tries=1 if hosted else 20)
    actual_port = server.server_address[1]
    url = f"http://localhost:{actual_port}"
    print(f"PhenoFit UI running at {url}  (Ctrl-C to stop)")
    if not args.no_open and not hosted:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
