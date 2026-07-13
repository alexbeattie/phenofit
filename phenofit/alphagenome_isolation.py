"""Parent-side runner for the disposable AlphaGenome worker."""

from __future__ import annotations

import json
import queue
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable

DEFAULT_TIMEOUT_SECONDS = 120.0


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1)


def _failure(message: str, **flags) -> dict:
    result = {
        "error": message,
        "worker_crashed": False,
        "timed_out": False,
        "cancelled": False,
    }
    result.update(flags)
    return result


def run_isolated(
    payload: dict,
    *,
    progress: Callable[[str, str], None] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    cancel_event: threading.Event | None = None,
    command: list[str] | None = None,
) -> dict:
    """Run one worker, forwarding real progress and containing fatal exits."""

    process = subprocess.Popen(
        command or [sys.executable, "-m", "phenofit.alphagenome_worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    process.stdin.write(json.dumps(payload))
    process.stdin.close()

    messages: queue.Queue[str] = queue.Queue()
    stderr: list[str] = []

    def read_stdout() -> None:
        for line in process.stdout:
            messages.put(line)

    def read_stderr() -> None:
        for line in process.stderr:
            if sum(map(len, stderr)) < 8192:
                stderr.append(line)

    out_thread = threading.Thread(target=read_stdout, daemon=True)
    err_thread = threading.Thread(target=read_stderr, daemon=True)
    out_thread.start()
    err_thread.start()

    def finish(result: dict) -> dict:
        out_thread.join(timeout=0.2)
        err_thread.join(timeout=0.2)
        process.stdout.close()
        process.stderr.close()
        return result

    started = time.monotonic()
    final: dict | None = None
    invalid_output = False
    worker_error = ""

    while process.poll() is None or out_thread.is_alive() or not messages.empty():
        if cancel_event is not None and cancel_event.is_set():
            _stop(process)
            return finish(_failure("AlphaGenome scoring cancelled.", cancelled=True))
        if time.monotonic() - started > timeout:
            _stop(process)
            return finish(_failure(
                f"AlphaGenome worker timed out after {timeout:g} seconds.",
                timed_out=True,
            ))
        try:
            line = messages.get(timeout=0.02)
        except queue.Empty:
            continue
        try:
            message = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            invalid_output = True
            continue
        kind = message.get("type")
        if kind == "progress" and progress:
            progress(str(message.get("stage", "")), str(message.get("message", "")))
        elif kind == "result" and isinstance(message.get("result"), dict):
            final = message["result"]
        elif kind == "error":
            worker_error = str(message.get("error") or "AlphaGenome worker failed.")

    returncode = process.wait()
    if returncode < 0:
        signum = -returncode
        try:
            signal_name = signal.Signals(signum).name
        except ValueError:
            signal_name = f"signal {signum}"
        return finish(_failure(
            f"AlphaGenome worker crashed ({signal_name}). PhenoFit is still running.",
            worker_crashed=True,
        ))
    if invalid_output:
        return finish(_failure("AlphaGenome worker returned invalid output."))
    if returncode != 0:
        detail = worker_error or "".join(stderr).strip() or f"exit code {returncode}"
        return finish(_failure(f"AlphaGenome worker failed: {detail}"))
    if final is None:
        return finish(_failure("AlphaGenome worker returned no result."))
    return finish(final)
