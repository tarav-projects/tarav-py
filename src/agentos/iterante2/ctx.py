"""Ctx — the data-only I/O object between Harness and mission hooks.

It carries data, nothing callable: a mission reaches every capability via
`import iterante2` (e.g. `ctx.call = iterante2.calls.task(...)`), never through ctx.
"""

from __future__ import annotations

import copy
from types import SimpleNamespace


class Ctx:
    """Single mutable object handed to mission hooks each turn.

    Four data zones:
      env   — read-only ephemeral context
      state — persistable mutable state (dict)
      input — read-only turn input
      call  — mutable output slot (set by hook)
    """

    def __init__(
        self,
        *,
        env: dict,
        state: dict | None = None,
        input: dict | None = None,
    ) -> None:
        self.env = SimpleNamespace(**env)
        self.state = copy.deepcopy(state) if state else {}
        self.input = SimpleNamespace(**(input or {}))
        self.call: dict | None = None
