# AlphaGenome Isolation and Progress Design

## Goal

Prevent native AlphaGenome dependencies from killing the PhenoFit web server, while giving users immediate, accurate feedback about every long-running action.

## Crash boundary

Coordinate resolution remains in the server because it is an ordinary HTTP call. AlphaGenome SDK loading, model scoring, pandas, PyArrow, and native libraries run in a fresh Python subprocess for every request. The server sends one JSON request over stdin. The worker emits newline-delimited JSON progress events and one final JSON result over stdout.

The parent enforces a 120-second timeout. A malformed response, non-zero exit, signal such as `SIGSEGV`, timeout, or cancellation becomes an explicit unavailable result. It never terminates the server. The API key is inherited through the environment and never appears in command arguments or job responses.

## Job API

AlphaGenome runs as an in-memory background job:

- `POST /api/alphagenome/jobs` returns `202` with a job identifier.
- `GET /api/jobs/{id}` returns `queued`, `running`, `succeeded`, `failed`, or `cancelled`, plus the current truthful stage and message.
- `DELETE /api/jobs/{id}` requests cancellation and terminates only that worker.

Jobs are process-local, bounded, and expired after completion. The existing synchronous `/api/alphagenome` endpoint stays available but uses the same isolated subprocess internally.

## Progress states

AlphaGenome reports only stages it has actually entered:

1. Resolving GRCh38 coordinates with Ensembl VEP.
2. Starting isolated AlphaGenome worker.
3. Scoring splicing signals.
4. Scoring regulatory signals.
5. Preparing research-model evidence.

Other long actions use immediate, action-specific busy states: document reading and Claude/HPO ingestion; Claude phenotype extraction and HPO grounding; HPO phenotype review; and Claude management drafting. Their current synchronous endpoints do not pretend to expose finer backend progress.

Buttons show a compact spinner and active label, disable only duplicate submission, and restore their original text on completion. Status containers use `role="status"`, `aria-live="polite"`, and `aria-busy`. Reduced-motion users receive a non-rotating pulse. Errors remain visible and specific; a native crash says that the AlphaGenome worker crashed and PhenoFit is still running.

## Verification

An offline regression test launches a child that deliberately sends itself `SIGSEGV`, asserts that the parent converts it to a failure result, and then runs another child successfully. Job tests cover real stage updates and cancellation. Static UI tests lock in accessible spinner markup, reduced-motion behavior, polling, and crash-safe copy. The full existing offline suite must remain green.
