#!/usr/bin/env python3
# $kw: --from Index.Line.Record.Model --note [DC] one sigil across the system; a d-labelled record is remined onto c and every citation follows
"""Relabel the surviving `^d…` records onto the single `c` sigil (impl-req 641).

`d` separated the new index's labels from the anchory anchors while the two label spaces
were distinct. Homogenizing the dossiers removed that distinction, so a second sigil now
names a difference that is gone — but the two spaces allocated the same date-and-sequence
range independently, so **160 of the 163 survivors collide** with a `c` label that already
exists. Each of those is reminted to the next free sequence for its own date.

A label is the public citation, so relabelling a record without rewriting every citation of
it would break exactly the thing the label exists for. Both move in one run, and the run
fails if any citation of an old label survives.
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from tarav.bloberia.core import BloberiaDepot  # noqa: E402
from tarav.index.record.store import LABEL_RE  # noqa: E402

DEPOT = Path.home() / "Documents" / "bloberia" / "tarav-index"
PROJECT = Path(__file__).resolve().parents[3]
ROOTS = ("tarav-md", "tarav-chatlas-md", "_DEPRECATED/tarav2", "tarav-py")
SUFFIXES = {".md", ".py", ".json", ".toml", ".txt"}


def plan(records: list[dict]) -> dict[str, str]:
    """Old label → new label. Sequence allocation is per date, over both spaces at once."""
    taken: dict[str, set[int]] = collections.defaultdict(set)
    for record in records:
        label = (record.get("line") or {}).get("label")
        match = LABEL_RE.match(label) if isinstance(label, str) else None
        if match and match.group("sigil") == "c":
            taken[match.group("date")].add(int(match.group("seq")))

    mapping: dict[str, str] = {}
    for record in sorted(records, key=lambda r: (r.get("line") or {}).get("label") or ""):
        label = (record.get("line") or {}).get("label")
        match = LABEL_RE.match(label) if isinstance(label, str) else None
        if not match or match.group("sigil") != "d":
            continue
        date, seq, tag = match.group("date"), int(match.group("seq")), match.group("tag")
        if seq not in taken[date]:
            chosen = seq
        else:
            chosen = max(taken[date], default=-1) + 1
        taken[date].add(chosen)
        mapping[label] = f"^c{date}-{chosen}{tag}"
    return mapping


def rewrite_citations(mapping: dict[str, str], *, apply: bool) -> collections.Counter:
    """Every citation of an old label, in every repository."""
    pattern = re.compile(
        r"(?<![A-Za-z0-9])\^(" + "|".join(re.escape(k[1:]) for k in mapping) + r")(?![A-Za-z0-9-])"
    )
    stats: collections.Counter = collections.Counter()
    for root in ROOTS:
        for path in (PROJECT / root).rglob("*"):
            if path.is_dir() or ".git/" in str(path) or path.suffix not in SUFFIXES:
                continue
            try:
                text = path.read_text("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            updated, count = pattern.subn(lambda m: mapping["^" + m.group(1)], text)
            if not count:
                continue
            stats["citations"] += count
            stats["files"] += 1
            if apply:
                path.write_text(updated, encoding="utf-8")
    return stats


def main() -> int:
    apply = "--apply" in sys.argv
    depot = BloberiaDepot(DEPOT)
    records = list(depot.iterate())
    mapping = plan(records)
    reminted = sum(1 for old, new in mapping.items() if old[2:] != new[2:])

    print(f"records: {len(records)}   d-labelled: {len(mapping)}   reminted: {reminted}")
    if not mapping:
        print("nothing to do")
        return 0

    if apply:
        for record in records:
            label = (record.get("line") or {}).get("label")
            if label not in mapping:
                continue
            updated = json.loads(json.dumps(record))
            updated["line"]["label"] = mapping[label]
            depot.replace({"id": {"equals": record["id"]}}, updated)

    stats = rewrite_citations(mapping, apply=apply)
    print(f"citations rewritten: {stats['citations']} across {stats['files']} files")

    if not apply:
        print("\ndry run — pass --apply to write")
        return 0

    after = list(depot.iterate())
    survivors = [
        r["line"]["label"] for r in after if (r["line"].get("label") or "").startswith("^d")
    ]
    labels = [r["line"].get("label") for r in after]
    leftover = rewrite_citations(mapping, apply=False)

    print(f"\nrecords: {len(after)}   d-labelled survivors: {len(survivors)}")
    print(f"distinct labels: {len(set(labels))} of {len(labels)}")
    if survivors or leftover["citations"] or len(set(labels)) != len(labels):
        print("FAILED — a d label, a stale citation, or a collision survived")
        return 1
    print("OK — one sigil, every citation follows, no label held twice")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
