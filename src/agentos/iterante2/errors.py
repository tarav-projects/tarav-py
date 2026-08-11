"""Controlled error surface — Mechanism 1 of agent-facing leak hardening.

Agents must not know about mission mechanics. Any fatal error is captured here:
the full detail (traceback, paths, internal filenames) goes to a log file in the
mission folder for the developer; the agent receives only a generic, leak-free
message. The full detail is shown inline only under the developer bypass.

See notes/live/001-iterante2-output-redaction-impl-req.md (Index B).
"""

from __future__ import annotations

import datetime as _dt
import os
import traceback
from pathlib import Path

ERROR_LOG_NAME = "errors.log"
FATAL_MESSAGE = "fatal error — the run could not continue"

# Single developer switch governing both mechanisms: disables output sensors and
# makes the error boundary verbose (full traceback inline). Propagates to the
# `_runner` subprocess as an env var.
BYPASS_ENV = "ITERANTE_NO_REDACT"


def dev_bypass() -> bool:
    """True when the developer bypass env var is set to a truthy value."""
    return os.environ.get(BYPASS_ENV) not in (None, "", "0")


def record_fatal(
    exc: BaseException,
    *,
    log_dir: Path | None = None,
    verbose: bool = False,
) -> str:
    """Capture a fatal error and return an agent-safe message.

    Best-effort appends the full traceback to ``<log_dir>/errors.log``; never
    raises (a logging failure must not crash the run). Returns the generic
    `FATAL_MESSAGE` by default, or the full traceback when ``verbose``.
    """
    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    if log_dir is not None:
        try:
            d = Path(log_dir)
            d.mkdir(parents=True, exist_ok=True)
            ts = _dt.datetime.now().isoformat(timespec="seconds")
            with (d / ERROR_LOG_NAME).open("a", encoding="utf-8") as fh:
                fh.write(f"\n===== {ts} =====\n{detail}")
        except Exception:
            pass  # best-effort; the agent-safe message must still return

    return detail if verbose else FATAL_MESSAGE
