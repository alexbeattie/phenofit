"""Disposable AlphaGenome process.

This module is the native-library fault boundary. It speaks one JSON-lines
protocol over stdio and is intentionally launched with ``python -m`` by the web
server. A PyArrow or SDK segfault can terminate this process, never the server.
"""

from __future__ import annotations

import json
import sys

from .coords import Coordinates
from .noncoding import AlphaGenomeResult, score


def _emit(message: dict) -> None:
    print(json.dumps(message, separators=(",", ":")), flush=True)


def _signal_json(signal) -> dict:
    return {
        "interpretation": signal.interpretation,
        "quantile": signal.quantile,
        "direction": signal.direction,
    }


def _result_json(result: AlphaGenomeResult, coordinates: Coordinates) -> dict:
    return {
        "available": result.available,
        "error": "" if result.available else result.reason,
        "variant_id": result.variant_id,
        "consequence": coordinates.consequence,
        "is_noncoding": coordinates.is_noncoding,
        "protein_hgvs": coordinates.protein_hgvs,
        "splicing": [_signal_json(item) for item in result.splicing],
        "regulatory": [_signal_json(item) for item in result.regulatory],
        "research_use_only": result.research_use_only,
        "source": result.source.url if result.source else "",
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        coordinates = Coordinates(**payload["coordinates"])
        result = score(
            coordinates,
            _progress=lambda stage, message: _emit(
                {"type": "progress", "stage": stage, "message": message}
            ),
        )
        _emit({"type": "result", "result": _result_json(result, coordinates)})
        return 0
    except Exception as exc:
        _emit({"type": "error", "error": f"{type(exc).__name__}: {exc}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
