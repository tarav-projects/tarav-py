# $kw: ^workspaces-manifest --from Run.Workspace --note [PR] status and extracted are what make sweeping possible: nothing is ever deleted while nobody can tell whether anything left --supp ^c20260809-89u ^<anchor-on-landing>
"""The machine-readable part of a workspace's one required surface.

`status` and `extracted` live in a `### manifest` section of the same
`AGENTS.md` that carries the prose, mirroring the `### meta` convention already
used in index blocks. One surface, so the two cannot drift; a sidecar file would
be a second authority that quietly disagrees with the thing people actually
edit.

Absent keys read as their defaults rather than failing. A workspace someone
wrote by hand is still a workspace, and refusing to read it would make the
disposal listing silently incomplete — the one thing that listing must never be.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

MANIFEST_HEADING = "### manifest"
_ENTRY = re.compile(r"^-\s*([A-Za-z][\w.-]*)\s*:\s*(.*?)\s*$")
_HEADING = re.compile(r"^#{1,6}\s")

DEFAULT_KIND = "unknown"
DEFAULT_EXTRACTED = "none"


class ManifestError(RuntimeError):
    """A workspace's `AGENTS.md` is missing or carries an unreadable manifest."""


class Status(Enum):
    OPEN = "open"
    HARVESTED = "harvested"
    ABANDONED = "abandoned"


@dataclass(frozen=True)
class Manifest:
    path: Path
    kind: str = DEFAULT_KIND
    created: str = ""
    status: Status = Status.OPEN
    extracted: str = DEFAULT_EXTRACTED

    @property
    def slug(self) -> str:
        return self.path.parent.name


def read_manifest(path: Path | str) -> Manifest:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ManifestError(f"cannot read {path}: {error}") from error

    entries = _manifest_entries(text)
    raw_status = entries.get("status", Status.OPEN.value)
    try:
        status = Status(raw_status)
    except ValueError as error:
        allowed = ", ".join(item.value for item in Status)
        raise ManifestError(
            f"{path}: unknown status {raw_status!r}; expected one of {allowed}"
        ) from error

    return Manifest(
        path=path,
        kind=entries.get("kind", DEFAULT_KIND) or DEFAULT_KIND,
        created=entries.get("created", ""),
        status=status,
        extracted=entries.get("extracted", DEFAULT_EXTRACTED) or DEFAULT_EXTRACTED,
    )


def _manifest_entries(text: str) -> dict[str, str]:
    """The `- key: value` lines under the manifest heading, and nothing else."""
    entries: dict[str, str] = {}
    inside = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower() == MANIFEST_HEADING:
            inside = True
            continue
        if inside and _HEADING.match(stripped):
            break
        if not inside:
            continue
        match = _ENTRY.match(stripped)
        if match:
            entries[match.group(1).lower()] = match.group(2)
    return entries


def render_agents_md(
    *,
    slug: str,
    kind: str,
    purpose: str,
    provenance: str,
    created: str,
) -> str:
    """The template a new workspace defines itself with.

    Prose first, because the reader is an agent landing here cold; the manifest
    last, because it is the part a tool reads.
    """
    return f"""# {slug}

A `Run.Workspace`: one run of one agentic workflow, outside every project.

**This is a `Volatile.Surface`.** No stable surface may depend on anything in
here. This workspace may read stable surfaces; nothing stable may reference a
path inside it. Content leaves only by copy — a stable surface takes it and owns
it. Then this directory is deletable, which is the normal end of its life.

## Purpose

{purpose}

## Provenance

{provenance}

## How to run it

Not yet described. Whoever sets this up should say here what to run and in what
order, so a later reader does not have to reconstruct it.

### manifest

- kind: {kind}
- created: {created}
- status: open
- extracted: none
"""
