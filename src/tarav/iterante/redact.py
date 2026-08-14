# $kw: --from Iterante.Runtime
"""Output sensors — Mechanism 2 of agent-facing leak hardening.

A reusable runtime primitive that scrubs harness/mission machinery paths from the
*general output stream* (rendered frames, forwarded mission `print()`s). An
ordered registry of sensors, each owning its detector and replacement; new leak
classes are handled by appending a sensor. Errors are NOT handled here — that is
the controlled error surface (`errors.py`, Mechanism 1).

See notes/live/001-iterante-output-redaction-impl-req.md (Index C).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from tarav.iterante.errors import dev_bypass


@dataclass(frozen=True)
class Sensor:
    """One leak class: a name, a detector, and how to fill it."""

    name: str
    pattern: re.Pattern[str]
    replacement: str | Callable[[re.Match[str]], str]

    def apply(self, line: str) -> str:
        return self.pattern.sub(self.replacement, line)




SENSORS: tuple[Sensor, ...] = (
    Sensor(
        name="run-path",
        pattern=re.compile(r"\S*\.tarav/missions/[^/\s]+/runs/\S*"),
        replacement="‹run›",
    ),
    Sensor(
        name="mission-path",
        pattern=re.compile(r"\S*\.tarav/missions/[^/\s]+\S*"),
        replacement="‹mission›",
    ),
    Sensor(
        name="install-path",
        pattern=re.compile(r"\S*/(?:uv/tools|site-packages)/\S*"),
        replacement="‹iterante-internal›",
    ),
    Sensor(


        name="abs-path",
        pattern=re.compile(r"(?<!\S)/[^\s/]+(?:/[^\s]*)+"),
        replacement="‹path›",
    ),
)


def redact(text: str) -> str:
    """Scrub machinery paths from agent-facing text.

    Runs the sensors line by line; fail-open — a sensor that raises on a line is
    skipped for that line, never crashing output. No-op under the dev bypass.
    """
    if dev_bypass():
        return text
    out = []
    for line in text.splitlines(keepends=True):
        for sensor in SENSORS:
            try:
                line = sensor.apply(line)
            except Exception:
                continue
        out.append(line)
    return "".join(out)
