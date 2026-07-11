# Contributing to PhenoFit

A short, repeatable loop so changes land evenly — small, tested, and green.

## One-time setup

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
git config core.hooksPath .githooks   # enable the pre-commit test gate
```

The Anthropic and OMIM keys are optional (see `.env.example`); the tool and the
full test suite run without them.

## The per-change loop

Work in small, self-contained increments. Each change follows the same steps:

1. **Branch** off `main` for anything non-trivial:
   `git switch -c feat/<short-name>` (or `fix/<short-name>`).
2. **Write the test first.** Add or adjust a test under `tests/` that fails for
   the reason you're about to fix. Tests are offline — network calls are mocked
   (`unittest.mock.patch.object(hpo, "get_json", ...)`), so the suite never hits
   the Jax API.
3. **Implement** the smallest change that makes it pass.
4. **Run the suite:** `./.venv/bin/python -m unittest discover -s tests`.
5. **Verify in the app** when the change has a runtime surface — start it with
   `./run_ui.sh --no-open` and exercise the affected path (e.g. POST to
   `/api/review`). A test passing is not the same as the app working.
6. **Commit.** The pre-commit hook re-runs the suite and blocks a red commit.
   Keep the subject imperative and under ~72 chars; explain the *why* in the body.
7. **Open a PR** to `main`. CI (`.github/workflows/ci.yml`) runs the suite on
   every push and PR; nothing merges red.

## Conventions

- **Provenance is a feature.** Every claim carries its source; never surface a
  term or gene link the ontology didn't validate. The LLM proposes phrases only —
  it must never emit an HPO id.
- **Degrade, don't crash.** A single bad input (a malformed variant, a query the
  Jax API 400s on) must reduce to "unresolved / no knowledge", never abort a
  whole review. Match the `try/except httpx.HTTPStatusError` pattern already in
  `hpo.py`.
- **Abstain over guess.** When the data can't support a call, say so
  ("undetermined", "ungrounded") rather than inventing one.

## Running the tests

```bash
./.venv/bin/python -m unittest discover -s tests        # all
./.venv/bin/python -m unittest tests.test_models -v     # one module
```
