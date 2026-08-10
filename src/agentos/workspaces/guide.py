# $kw: ^workspaces-guide --from Run.Workspace --from Skw.Surface.Token --from Poi.Unlock.Token --note [DC] creating a workspace is gated on a Poi.Unlock.Token receipt for the workspace documentation surface --supp ^c20260809-92u ^<anchor-on-landing>
"""The tokened surface the `workspace init` gate reads.

The guide ships beside the code rather than as a Skillware-managed surface: a
file surface may carry its `Skw.Surface.Token` in its header, and the
token-bearing surface is the authority for its own token. That keeps the gate's
semantics the index's while its plumbing stays local to one consumer.

The token is the guide's last line on purpose. The gate is a speed bump against
creating a workspace blind, not a proof that anything was understood — an agent
that read the output has the receipt, and one that skipped to the end had to
scroll past the whole thing to get there.
"""

from __future__ import annotations

import re
from pathlib import Path


GUIDE_FILENAME = "GUIDE.md"
TOKEN_PREFIX = "aws-unlock:"
_TOKEN_LINE = re.compile(
    r"^surface-token:\s*(" + re.escape(TOKEN_PREFIX) + r"[0-9a-f]{6,})\s*$",
    re.MULTILINE,
)


class GuideError(RuntimeError):
    """The workspaces guide is missing or carries no usable surface token."""


def guide_path() -> Path:
    return Path(__file__).resolve().parent / GUIDE_FILENAME


def guide_text() -> str:
    path = guide_path()
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise GuideError(f"cannot read the workspaces guide at {path}: {error}") from error


def parse_guide_token(text: str) -> str:
    """The surface's own token, or an error.

    Never a default: an unreadable token that returned empty would gate nothing
    while looking exactly like a gate.
    """
    match = _TOKEN_LINE.search(text)
    if match is None:
        raise GuideError(
            "the workspaces guide carries no well-formed surface token "
            f"(expected a line 'surface-token: {TOKEN_PREFIX}<hex>')"
        )
    return match.group(1)


def guide_token() -> str:
    return parse_guide_token(guide_text())
