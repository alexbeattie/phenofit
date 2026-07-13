# AlphaGenome Isolation and Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Isolate AlphaGenome native code in a disposable subprocess and expose truthful, accessible loading feedback in the web UI.

**Architecture:** A JSON-lines worker protocol carries real progress and a final result from a fresh child process. An in-memory job registry runs and cancels AlphaGenome work while preserving the synchronous endpoint for compatibility; the browser polls the job endpoint and reuses one busy-state component for all long actions.

**Tech Stack:** Python 3 stdlib (`subprocess`, `threading`, `queue`, `http.server`), vanilla JavaScript, CSS, `unittest`.

## Global Constraints

- AlphaGenome SDK, pandas, PyArrow, and their native dependencies never load in the web-server process.
- Worker timeout is 120 seconds.
- API keys are inherited through the environment, never passed in arguments or returned to clients.
- Existing synchronous endpoints and CLI behavior remain compatible.
- Progress copy reflects stages actually entered; no fake percentages or timer-driven stage changes.
- AlphaGenome remains labeled as a research model, not clinically validated.

---

### Task 1: Isolated Worker Protocol

**Files:**
- Create: `phenofit/alphagenome_worker.py`
- Create: `phenofit/alphagenome_isolation.py`
- Create: `tests/test_alphagenome_isolation.py`

**Interfaces:**
- Consumes: serialized `Coordinates` fields and inherited `ALPHAGENOME_API_KEY`.
- Produces: `run_isolated(payload, progress, timeout=120, cancel_event=None, command=None) -> dict`.

- [ ] **Step 1: Write failing tests** for successful JSON-lines progress, deliberate `SIGSEGV`, malformed output, timeout, and cancellation. The crash test must run a second successful subprocess afterward to prove the parent survives.
- [ ] **Step 2: Run** `../../.venv/bin/python -m unittest tests.test_alphagenome_isolation -v` and confirm missing-module failures.
- [ ] **Step 3: Implement the worker** so it reads one JSON object, constructs `Coordinates`, calls `noncoding.score`, emits actual scoring stages through a callback, and writes a serializable result.
- [ ] **Step 4: Implement the parent runner** with `Popen`, a stdout reader thread, timeout/cancel termination, exit-signal interpretation, bounded stderr capture, and strict final-result validation.
- [ ] **Step 5: Re-run the focused tests** and expect all isolation tests to pass.

### Task 2: Job Registry and HTTP Contract

**Files:**
- Create: `phenofit/jobs.py`
- Modify: `phenofit/webapp.py`
- Create: `tests/test_jobs.py`
- Create: `tests/test_webapp_jobs.py`

**Interfaces:**
- Consumes: `run_isolated` and `_run_alphagenome(payload, progress=None, cancel_event=None)`.
- Produces: `JobRegistry.start`, `JobRegistry.get`, `JobRegistry.cancel`; POST/GET/DELETE job routes.

- [ ] **Step 1: Write failing tests** for state transitions, real stage messages, cancellation, unknown IDs, and a synchronous AlphaGenome call using an injected isolated runner.
- [ ] **Step 2: Run focused tests** and confirm failures because the registry/routes do not exist.
- [ ] **Step 3: Implement a locked in-memory registry** with daemon worker threads, JSON-safe snapshots, bounded completed-job retention, and per-job cancellation events.
- [ ] **Step 4: Route AlphaGenome through isolation** after coordinate resolution; add `POST /api/alphagenome/jobs`, `GET /api/jobs/{id}`, and `DELETE /api/jobs/{id}` without removing `/api/alphagenome`.
- [ ] **Step 5: Run focused tests** and expect all job and route tests to pass.

### Task 3: Truthful Loading UI

**Files:**
- Modify: `phenofit/static/index.html`
- Create: `tests/test_webapp_ui.py`

**Interfaces:**
- Consumes: job snapshots `{state, stage, message, result, error}`.
- Produces: reusable busy/status markup and AlphaGenome polling/cancellation UI.

- [ ] **Step 1: Write failing static-contract tests** for spinner CSS, reduced-motion fallback, live-region attributes, action-specific text, AlphaGenome polling, cancellation, and survivor copy.
- [ ] **Step 2: Run** `../../.venv/bin/python -m unittest tests.test_webapp_ui -v` and verify expected failures.
- [ ] **Step 3: Add the reusable busy-state helpers and CSS** using transform/opacity only, `aria-live="polite"`, `aria-busy`, a linear spinner, and a reduced-motion pulse.
- [ ] **Step 4: Apply busy states** to review, extraction, document ingestion, and management drafting; restore button labels and enabled state in `finally`.
- [ ] **Step 5: Replace direct AlphaGenome fetch** with create-and-poll, render actual server messages, add cancellation, and show `AlphaGenome worker crashed. PhenoFit is still running.` for signal failures.
- [ ] **Step 6: Run focused UI tests** and expect all to pass.

### Task 4: Regression and Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/SUBMISSION.md`

**Interfaces:**
- Consumes: completed worker/job/UI implementation.
- Produces: accurate operational and hackathon claims.

- [ ] **Step 1: Document** that AlphaGenome is optional, subprocess-isolated, cancellable, research-only, and safely unavailable after native failure.
- [ ] **Step 2: Run** `../../.venv/bin/python -m unittest discover -s tests -v` and require zero failures.
- [ ] **Step 3: Start the app with AlphaGenome disabled**, verify `/`, `/api/config`, and an ordinary validation response, then stop it cleanly.
- [ ] **Step 4: Review the diff** for secrets, accidental generated files, fake progress, and unrelated edits.
