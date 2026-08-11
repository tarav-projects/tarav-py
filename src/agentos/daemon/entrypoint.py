# $kw: --from Agentos.Daemon
from __future__ import annotations

import sys

from agentos.runtime import AgentosRuntime, create_runtime

from .runtime import DaemonRuntime, DaemonRuntimeError


def run_daemon(runtime: AgentosRuntime | None = None) -> int:
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
    return run_daemon()


if __name__ == "__main__":
    raise SystemExit(main())
