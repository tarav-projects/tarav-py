#!/usr/bin/env python3
# $kw: --from Migration.Current.Only --note [DC] an alias declaration is an ordinary Index line and captures as one, rather than becoming a second block-level schema field the kernel would have to learn --note [CT] the 754 line regex required a type code or an anchor, which is why untyped unanchored `- aliases:` meta-lines were never seen; they are index data and skw locator resolution reads them
"""Capture `- aliases:` block meta-lines into `index-2208` as `Index.Record`s.

The corpus migration classified a bullet as an Index line when it carried a `Line.Type`
code or an anchor. Alias declarations carry neither, so all 62 of them fell outside that
test and never reached the records — while `Dotted.Name` locator resolution in the skw
builder reads exactly those lines to find a block by an alternate name.

They capture as ordinary lines carrying an `alias` assertion, rather than as a new
block-level field. The kernel keeps assertions opaque and a reader that understands the
`alias` key may read it; adding a schema field would make every writer learn it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
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
ALIAS_RE = re.compile(r"^-\s+aliases:\s*(?P<body>.+?)\s*$")
#: An alias belongs to the enclosing block, and a block heading is `##`. A `###` is a
#: subsection inside one — `### meta` is where alias declarations are conventionally written.
BLOCK_HEADING_RE = re.compile(r"^##\s+(?P<concept>\S+)")
NAME_RE = re.compile(r"`([^`]+)`")


def digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:16]


def alias_lines() -> list[dict]:
    """Every alias meta-line, addressed to the block it is written under."""
    out: list[dict] = []
    for repo in MD_REPOS:
        root = PROJECT / repo
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            if any(part in NOISE for part in path.parts):
                continue
            relative = Path(repo) / path.relative_to(root)
            concept: str | None = None
            in_fence = False
            for number, raw in enumerate(path.read_text("utf-8").splitlines(), start=1):
                if raw.strip().startswith("```"):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                heading = BLOCK_HEADING_RE.match(raw)
                if heading:
                    concept = heading.group("concept").strip("`")
                    continue
                if raw.startswith("#"):
                    continue
                found = ALIAS_RE.match(raw)
                if not found or concept is None:
                    continue
                names = NAME_RE.findall(found.group("body"))
                if not names:
                    continue
                out.append(
                    {
                        "address": extract.scope_for(relative, concept),
                        "surface": relative.as_posix(),
                        "surface_line": number,
                        "text": raw.strip().lstrip("- ").strip(),
                        "aliases": names,
                    }
                )
    return out


def main() -> int:
    library = IndexLibrary.open(LIBRARY)
    workspace = library.resolve(WORKSPACE)
    store = RecordStore(workspace)
    projection = project_records(store.list())

    blocks = {block.name: block for block in projection.blocks}
    names = {block.id: block.name for block in projection.blocks}
    known_text = {(names[ln.block_id], ln.text) for ln in projection.lines}
    used_labels = {line.label for line in projection.lines}

    horizon = TurnRef(
        address=f"{extract.MIGRATION_TAG}:aliases",
        hash=digest(extract.MIGRATION_TAG, "aliases"),
    )
    context = RecordContext(session=extract.MIGRATION_SESSION, horizon=horizon)

    records: list[IndexRecord] = []
    skipped = {"already captured": 0, "no such block": 0}
    for entry in alias_lines():
        block = blocks.get(entry["address"])
        if block is None:
            skipped["no such block"] += 1
            continue
        if (block.name, entry["text"]) in known_text:
            skipped["already captured"] += 1
            continue
        seed = digest(entry["address"], entry["text"])
        label = f"^alias-{seed}"
        suffix = 1
        while label in used_labels:
            suffix += 1
            label = f"^alias-{seed}~{suffix}"
        used_labels.add(label)
        line_id = f"lin_{digest('alias', entry['address'], entry['text'])}"
        records.append(
            IndexRecord(
                id=f"rec_{digest('alias', line_id)}",
                ordinal=0,
                context=context,
                operation=Operation(
                    type="line.capture",
                    parameters={
                        "line_id": line_id,
                        "isoline_id": f"iso_{digest('alias', entry['address'], entry['text'])}",
                        "block_id": block.id,
                        "label": label,
                        "text": entry["text"],
                    },
                ),
                support=SupportSet(neighborhoods=()),
                assertions=(
                    {
                        "kind": "alias",
                        "aliases": entry["aliases"],
                        "line_type": "DF",
                        "migrated_by": extract.MIGRATION_TAG,
                        "origin": "markdown",
                        "surface": entry["surface"],
                        "surface_line": entry["surface_line"],
                    },
                ),
            )
        )

    manifest = {
        "schema": "tarav.indexlab-capture-manifest.v1",
        "records": [record.to_dict() for record in records],
    }
    out = HERE.parent / "759-index-2208-alias-manifest.json"
    out.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", "utf-8")

    print(f"alias meta-lines found  {len(alias_lines()):>5}")
    for key, value in sorted(skipped.items()):
        print(f"  {key:<22} {value:>5}")
    print(f"alias records built     {len(records):>5}")
    print(f"manifest -> {out.relative_to(PROJECT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
