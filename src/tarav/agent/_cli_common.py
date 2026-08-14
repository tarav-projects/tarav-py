# $kw: --from Agentos.Agent.Adapter
from __future__ import annotations

import json
import re
import time
from typing import Sequence

from tarav._core.errors import CliError


_LOOKBACK_DURATION_RE = re.compile(r"^(?P<value>\d+)(?P<unit>[smhdw]?)$")


def normalize_updated_since(value: str | None) -> float | None:
    if value is None:
        return None

    normalized = value.strip().lower()
    match = _LOOKBACK_DURATION_RE.fullmatch(normalized)
    if match is None:
        raise CliError("updated-since must be an integer with optional unit s|m|h|d|w, e.g. 72h or 3d")

    amount = int(match.group("value"))
    if amount < 1:
        raise CliError("updated-since must be greater than 0")

    unit = match.group("unit") or "s"
    multiplier = {
        "s": 1,
        "m": 60,
        "h": 60 * 60,
        "d": 24 * 60 * 60,
        "w": 7 * 24 * 60 * 60,
    }[unit]
    return time.time() - (amount * multiplier)


def optional_string_tuple(values: Sequence[str] | None) -> tuple[str, ...] | None:
    if not values:
        return None
    return tuple(values)


def format_json_output(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


__all__ = ["format_json_output", "normalize_updated_since", "optional_string_tuple"]
