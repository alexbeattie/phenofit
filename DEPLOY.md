# Deploying PhenoFit (for a reviewer like Matt)

Always-on hosting on **Render**, locked to one viewer with HTTP Basic Auth, with
the AI edge enabled. ~10 minutes, most of it one-time dashboard setup.

## What's already in the repo

- `Dockerfile` — builds the app on Python 3.12.
- `render.yaml` — a Render Blueprint that wires up the service and its secrets.
- The server reads `$PORT`/`$HOST` from the environment and enforces Basic Auth
  when `APP_PASSWORD` is set (both handled automatically by `render.yaml`).

## One-time setup

1. Go to <https://dashboard.render.com> → **New** → **Blueprint**.
2. Connect the `alexbeattie/phenofit` GitHub repo and pick the `main` branch.
   Render reads `render.yaml` and creates the `phenofit` web service.
3. When prompted, fill the three secrets (they are **not** in git):
   - `APP_PASSWORD` — a strong password; this is what you share with Matt.
   - `ANTHROPIC_API_KEY` — your Anthropic key (turns on the AI features).
   - `OMIM_API_KEY` — optional; leave blank to skip OMIM corroboration.
   `APP_USER` is preset to `matt` — change it in the dashboard if you like.
4. Click **Apply**. First build takes a few minutes; then you get a URL like
   `https://phenofit.onrender.com`.

## Give Matt access

Send him the URL plus the username (`matt`) and the `APP_PASSWORD`. His browser
will prompt for them once. Nothing else is exposed — every route requires the
password, so the URL can't burn your Anthropic credits.

## Notes

- **Auto-deploy:** every push to `main` redeploys. Combined with the auto-merge
  workflow, a merged PR ships to Matt without another step.
- **Free-plan cold start:** the free service sleeps after ~15 min idle; Matt's
  first hit after a quiet spell takes ~30s to wake, then it's fast. Upgrade the
  plan in the dashboard if you want it always warm.
- **Rotate access:** change `APP_PASSWORD` in the dashboard to cut off access.
- **Local dev is unchanged:** with `APP_PASSWORD` unset, `./run_ui.sh` runs on
  `127.0.0.1:8000` with no auth, exactly as before.
