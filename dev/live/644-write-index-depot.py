#!/usr/bin/env python3
# $kw: --from Index.Store --note [DC] one depot, user-side, holding every index line record; a label collision merges rather than duplicates
"""Write the whole index into one user-side Bloberia depot (impl-req 641, slices 7b/8).

Two inputs meet here: the 3,956 records converted from anchory by `643`, and the records
the index already holds. **33 of them share a label**, which means they are the same line
seen from two sides — the existing record carries the body, scope and trace, the converted
one carries the grounding that anchory held. A label collision therefore *merges*: it would
be a duplicate line otherwise, and a duplicate line is a worse outcome than either input.

The depot is `shards` keyed by `line.label`, which is the index's own identity and the
lookup that dominates. Placement is user-side because a record's support points at chat
evidence in `~/Documents/chatlas` that never ships: a project-tier record would reach a
clone as a dangling reference.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from tarav.bloberia.core import TYPE_SHARDS, BloberiaDepot  # noqa: E402
from tarav.index.record.model import LineRecord  # noqa: E402

DEPOT = Path.home() / "Documents" / "bloberia" / "tarav-index"
EXISTING = Path(__file__).resolve().parents[3] / "tarav-md" / ".tarav" / "index"


def merge(existing: LineRecord, converted: LineRecord) -> LineRecord:
    """One line seen twice. Identity and wording come from the index, evidence from both.

    The index record wins on `id`, `trace`, `scope` and `line` because those are what it
    knows and the dossier never held — a dossier stores a hash of the triplet, not its
    text. Support and gates union, because each side observed evidence the other did not.
    """
    support = list(existing.support)
    support += [s for s in converted.support if s not in support]
    review = list(existing.review)
    review += [g for g in converted.review if g not in review]
    return existing.__class__(
        id=existing.id,
        trace=existing.trace,
        scope=existing.scope,
        line=existing.line,
        support=tuple(support),
        placement=existing.placement,
        review=tuple(review),
        landing=existing.landing,
        equivalence=existing.equivalence,
    )


def main() -> int:
    converted = [
        LineRecord.from_json(p) for p in json.loads(Path(sys.argv[1]).read_text("utf-8"))
    ]
    existing = [
        LineRecord.from_json(json.loads(p.read_text("utf-8")))
        for p in sorted(EXISTING.glob("*.json"))
    ]
    stats = Counter()

    by_label: dict[str, LineRecord] = {}
    for record in existing:
        by_label[record.line.label or record.id] = record
        stats["existing"] += 1
    for record in converted:
        label = record.line.label or record.id
        if label in by_label:
            by_label[label] = merge(by_label[label], record)
            stats["merged"] += 1
        else:
            by_label[label] = record
            stats["converted_only"] += 1

    records = [by_label[k] for k in sorted(by_label)]
    stats["total"] = len(records)
    stats["support_total"] = sum(len(r.support) for r in records)
    stats["gate_total"] = sum(len(r.review) for r in records)

    if "--apply" not in sys.argv:
        for key in sorted(stats):
            print(f"{key}: {stats[key]}")
        print("\ndry run — pass --apply to write")
        return 0

    depot = BloberiaDepot(DEPOT, depot_type=TYPE_SHARDS, key="line.label", git=".")
    if depot.count({}):
        print(f"refusing to write into a depot that already holds records: {DEPOT}")
        return 1
    for record in records:
        depot.insert(record.to_json())

    written = depot.count({})
    for key in sorted(stats):
        print(f"{key}: {stats[key]}")
    print(f"\nwritten: {written} into {DEPOT}")
    if written != len(records):
        print("FAILED — the depot does not hold every record")
        return 1
    sample = depot.first({"line.label": {"equals": records[0].line.label}})
    if sample != records[0].to_json():
        print("FAILED — a record did not round-trip verbatim")
        return 1
    print("OK — every record is in the depot and round-trips verbatim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
