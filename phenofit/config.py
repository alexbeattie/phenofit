"""Tiny, dependency-free .env loader.

So a secret like ANTHROPIC_API_KEY can live in a gitignored `.env` at the
project root instead of a shell profile. We only set vars that aren't already in
the environment, so an explicit `export` still wins.
"""

from __future__ import annotations

import os
from pathlib import Path


def _candidate_paths() -> list[Path]:
    here = Path(__file__).resolve()
    return [
        Path.cwd() / ".env",
        here.parent.parent / ".env",  # repo root (parent of the package)
    ]


def load_dotenv() -> None:
    """Load KEY=VALUE lines from the first `.env` found; never override real env vars."""

    for path in _candidate_paths():
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
        return  # first file wins
