#!/usr/bin/env python3
# $kw: --from Migration.Current.Only --note [DC] the disconnection is only safe if the record corpus is a superset of the live surfaces, so the delta is computed before the cut and never after --note [CT] content identity is (block address, line text) because a surface line number moves whenever anyone edits the file above it, which would make an ordinal-keyed delta report churn as drift
"""Capture into `index-2208` every live Index line the frozen migration did not see.

`754-extract-index-corpus.py` read the archive, deliberately, so it could not drift. That
also means it froze at one moment while other agents kept landing lines. Before the Markdown
surface is disconnected we owe the corpus one catch-up pass, or the disconnection silently
drops whatever landed after the freeze.

**Conservation still governs.** This only ever appends. A live line already present as a
record is skipped; a line absent from the records is captured with the same mapping the
migration used. Nothing is rewritten, and no record is deleted for having no live twin —
the Markdown surface is not the authority any more, so its silence proves nothing.
"""

from __future__ import annotations

import importlib.util
import json
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
from tarav.indexlab.projection import project_records  # noqa: E402

LIBRARY = PROJECT / "index-library-2208"
WORKSPACE = "index-2208"

MD_REPOS = extract.__dict__.get("MD_REPOS") or (
    "tarav-md",
    "tarav-py",
    "tarav-chatlas-md",
    "tarav-canvas-md",
    "tarav-iterante-md",
    "tarav-projects-center-md",
)
CODE_ROOTS = ("tarav-py/src", "tarav-py/tests", "tarav-py/dev")
NOISE = (".git", "node_modules", ".venv", "__pycache__", "_DEPRECATED")


def live_entries() -> list[dict]:
    """Every Index line on the live tree, addressed exactly as the archive addressed it."""
    entries: list[dict] = []
    for repo in MD_REPOS:
        root = PROJECT / repo
        if root.is_dir():
            entries.extend(_rooted(extract.read_markdown(root), repo))
    for code in CODE_ROOTS:
        root = PROJECT / code
        if root.is_dir():
            entries.extend(_rooted(extract.read_code(root), code))
    return entries


def _rooted(staged: list[dict], prefix: str) -> list[dict]:
    """Re-address reader output from root-relative to project-relative, dropping noise."""
    out = []
    for entry in staged:
        surface = f"{prefix}/{entry['surface']}"
        if any(part in NOISE for part in surface.split("/")):
            continue
        entry = dict(entry)
        entry["surface"] = surface
        out.append(entry)
    return out


def captured_keys() -> set[tuple[str, str]]:
    """(block address, line text) for every line already folded out of the records."""
    library = IndexLibrary.open(LIBRARY)
    workspace = library.resolve(WORKSPACE)
    projection = project_records(RecordStore(workspace).list())
    blocks = {block.id: block.name for block in projection.blocks}
    return {(blocks[line.block_id], line.text) for line in projection.lines}


# $kw: --note [DC] the 754 builder assumes a fresh corpus, so a delta must hand it what the workspace already holds; without that it re-creates open blocks and re-allocates labels that are already taken, and both defects only surface later as a corpus that will not fold --note [CT] the label collision is the dangerous one: a duplicate block.create is refused on insert, but a duplicate label inserts cleanly and breaks the projection afterwards
def _workspace_state() -> tuple[set[str], dict[str, str]]:
    """Labels and blocks the live workspace already holds."""
    workspace = IndexLibrary.open(LIBRARY).resolve(WORKSPACE)
    projection = project_records(RecordStore(workspace).list())
    labels = {line.label for line in projection.lines if line.label}
    blocks = {block.name: block.id for block in projection.blocks}
    return labels, blocks


def main() -> int:
    entries = live_entries()
    entries.sort(key=lambda item: (item["surface"], item["line_number"]))
    known = captured_keys()

    fresh: list[dict] = []
    stats: Counter = Counter()
    for entry in entries:
        address = extract.scope_for(Path(entry["surface"]), entry["concept"])
        stats["live"] += 1
        if (address, entry["text"]) in known:
            stats["already captured"] += 1
            continue
        stats[f"new ({entry['origin']})"] += 1
        fresh.append(entry)

    support_table = extract.load_anchor_support()
    taken_labels, taken_blocks = _workspace_state()
    records, build_stats = (
        extract.build(
            fresh,
            support_table,
            labels_taken=taken_labels,
            blocks_taken=taken_blocks,
        )
        if fresh
        else ([], Counter())
    )

    manifest = {
        "schema": "tarav.indexlab-capture-manifest.v1",
        "records": [record.to_dict() for record in records],
    }
    out = HERE.parent / "758-index-2208-delta-manifest.json"
    out.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", "utf-8")

    print(f"records already in workspace {len(known):>7}")
    for key in sorted(stats):
        print(f"  {key:<26} {stats[key]:>7}")
    print(f"delta records built          {len(records):>7}")
    for key in sorted(build_stats):
        print(f"  {key:<26} {build_stats[key]:>7}")
    print(f"manifest -> {out.relative_to(PROJECT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
