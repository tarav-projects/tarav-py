#!/usr/bin/env python3
# $kw: --from Migration.Current.Only --note [DC] conservation decides what records, not the reader's convenience: an untyped unanchored line inside an Index chapter is Index data, and the 754 test excluded it only because it asked for a type code or an anchor --note [CT] these capture as incomplete records rather than being typed or labelled on their behalf, because inventing either would put an agent's guess where the linter should be reporting a gap
"""Capture the untyped, unanchored lines written inside Index depot chapters.

`754` classified a bullet as an Index line when it carried a `Line.Type` code or an
anchor. The Index also holds pre-fence legacy lines that carry neither, and they are
not prose: they sit under `##` concept headings inside real depot chapters, and whole
concepts exist only as such lines. `What.Design.Session` had six of them and no record
at all.

They record as they are — no type, no label. The Index is a `WIP.Surface`, so an
incomplete record is legal and its incompleteness is reported by `line-complete`
rather than repaired by a guess here.

**Scope is the depot chapter.** The same bullet shape in a note, README or Impl.Req is
ordinary prose; pulling it in would be the pollution that is worse than drift.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve()
PROJECT = HERE.parents[3]
sys.path.insert(0, str(PROJECT / "tarav-py" / "src"))

_spec = importlib.util.spec_from_file_location(
    "extract754", HERE.parent / "754-extract-index-corpus.py"
)
extract = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(extract)

from tarav.indexlab import IndexLibrary, RecordStore  # noqa: E402
from tarav.indexlab.model import (  # noqa: E402
    IndexRecord,
    Operation,
    RecordContext,
    SupportSet,
    TurnRef,
)
from tarav.indexlab.projection import project_records  # noqa: E402

LIBRARY = PROJECT / "index-library-2208"
WORKSPACE = "index-2208"

MD_REPOS = (
    "tarav-md",
    "tarav-py",
    "tarav-chatlas-md",
    "tarav-canvas-md",
    "tarav-iterante-md",
    "tarav-projects-center-md",
)
NOISE = (".git", "node_modules", ".venv", "__pycache__", "_DEPRECATED")

CHAPTER_RE = re.compile(r"^\d+-(?P<chapter>[a-z-]+)\.md$")
HEADING_RE = re.compile(r"^##\s+(?P<concept>\S+)")
BULLET_RE = re.compile(r"^\s*[-*]\s+(?P<body>\S.*?)\s*$")
TYPED_RE = re.compile(r"^\s*[-*]\s+\[[A-Z]{2,6}\]")
#: Block metadata, not block content. Aliases already captured in 759.
META_RE = re.compile(r"^-\s+(aliases|status|scope|owner):")


def digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:16]


def chapter_lines() -> list[dict]:
    """Every untyped, unanchored bullet under a concept heading in a depot chapter."""
    out: list[dict] = []
    for repo in MD_REPOS:
        root = PROJECT / repo
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            if any(part in NOISE for part in path.parts):
                continue
            chapter = CHAPTER_RE.match(path.name)
            if not chapter or "skills" not in path.parts:
                continue
            parts = path.parts
            depot = parts[parts.index("skills") + 1]
            address_base = f"{depot}/{chapter.group('chapter')}"
            relative = Path(repo) / path.relative_to(root)
            fence = False
            concept: str | None = None
            for number, raw in enumerate(
                path.read_text("utf-8", errors="replace").splitlines(), start=1
            ):
                if raw.strip().startswith("```"):
                    fence = not fence
                    continue
                if fence:
                    continue
                heading = HEADING_RE.match(raw)
                if heading:
                    concept = heading.group("concept").strip("`")
                    continue
                if raw.startswith("#"):
                    continue
                if concept is None or TYPED_RE.match(raw):
                    continue
                if extract.ANCHOR_RE.search(raw) or META_RE.match(raw.strip()):
                    continue
                bullet = BULLET_RE.match(raw)
                if not bullet:
                    continue
                out.append(
                    {
                        "address": f"{address_base}#{concept}",
                        "surface": relative.as_posix(),
                        "surface_line": number,
                        "text": bullet.group("body"),
                    }
                )
    return out


def main() -> int:
    workspace = IndexLibrary.open(LIBRARY).resolve(WORKSPACE)
    store = RecordStore(workspace)
    projection = project_records(store.list())

    blocks = {block.name: block for block in projection.blocks}
    names = {block.id: block.name for block in projection.blocks}
    known = {(names[line.block_id], line.text) for line in projection.lines}

    horizon = TurnRef(
        address=f"{extract.MIGRATION_TAG}:untyped-chapter-lines",
        hash=digest(extract.MIGRATION_TAG, "untyped-chapter-lines"),
    )
    context = RecordContext(session=extract.MIGRATION_SESSION, horizon=horizon)

    records: list[IndexRecord] = []
    created: dict[str, str] = {}
    stats: Counter = Counter()

    def add(operation: str, parameters: dict, assertions=()) -> None:
        records.append(
            IndexRecord(
                id=f"rec_{digest('untyped', str(len(records)), operation, json.dumps(parameters, sort_keys=True))}",
                ordinal=0,
                context=context,
                operation=Operation(type=operation, parameters=parameters),
                support=SupportSet(neighborhoods=()),
                assertions=assertions,
            )
        )

    for entry in chapter_lines():
        stats["read"] += 1
        address = entry["address"]
        if (address, entry["text"]) in known:
            stats["already captured"] += 1
            continue
        block = blocks.get(address)
        if block is not None:
            block_id = block.id
            stats["into an existing block"] += 1
        elif address in created:
            block_id = created[address]
        else:
            block_id = f"blk_{digest('untyped', address)}"
            created[address] = block_id
            stats["blocks created"] += 1
            add(
                "block.create",
                {
                    "block_id": block_id,
                    "isoblock_id": f"iso_{digest('untyped', address)}",
                    "name": address,
                },
            )
        seed = digest("untyped", address, entry["text"], str(entry["surface_line"]))
        stats["lines captured"] += 1
        add(
            "line.capture",
            {
                "line_id": f"lin_{seed}",
                "isoline_id": f"iso_{digest('untyped', address, entry['text'])}",
                "block_id": block_id,
                "text": entry["text"],
            },
            (
                {
                    "line_type": "UNTYPED",
                    "migrated_by": extract.MIGRATION_TAG,
                    "origin": "markdown",
                    "pre_fence_legacy": True,
                    "surface": entry["surface"],
                    "surface_line": entry["surface_line"],
                },
            ),
        )

    manifest = {
        "schema": "tarav.indexlab-capture-manifest.v1",
        "records": [record.to_dict() for record in records],
    }
    out = HERE.parent / "761-index-2208-untyped-manifest.json"
    out.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", "utf-8")

    for key in sorted(stats):
        print(f"  {key:<24} {stats[key]:>6}")
    print(f"records built            {len(records):>6}")
    print(f"manifest -> {out.relative_to(PROJECT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
