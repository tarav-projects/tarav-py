# $kw: --from Agentos.Daemon
from __future__ import annotations

import sys

from tarav._core.operational_logging import configure_operational_logging
from tarav.runtime import TaravRuntime, create_runtime

from .runtime import DaemonRuntime, DaemonRuntimeError


def run_daemon(runtime: TaravRuntime | None = None) -> int:
    composed = runtime or create_runtime()
    try:
        DaemonRuntime(composed.hooks).serve_forever()
    except DaemonRuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


def main() -> int:
    configure_operational_logging()
    return run_daemon()


if __name__ == "__main__":
    raise SystemExit(main())
