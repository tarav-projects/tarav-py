#!/usr/bin/env python3
# $kw: --from Durable.Evidence.Audit --note [DC] a recovered wording is written only where proven or unambiguous; a guess is reported as a POI instead
"""Recover historical line content for the quarantined records (impl-req 641, slice 7c).

`643` assumed an uncited anchor's wording was unrecoverable, because a dossier stores a
triplet *hash* and never the text. That was wrong in one direction and right in another:
the text is gone from the dossier, but repository git history retains the surface editions
that carried it. This reads that history.

**Evidence strength decides what gets written**, not recency:

```text
verified     one candidate whose recomputed triplet hash equals the dossier's   → write
single       one candidate, but the dossier carries no hash to check it against → write
ambiguous    several candidates, nothing that can choose between them           → POI
mismatch     a hash exists and no candidate reproduces it                       → POI
absent       the anchor appears nowhere in any repository's history             → POI
```

Selecting the newest occurrence would be wrong for a reason stronger than staleness:
some anchors were **reused**, carrying unrelated statements at different times, so the
wrong pick is a wrong attribution rather than an old wording.

Only `line.body`, `line.type` and provenance are touched. Support and gate cardinality
must come out identical, and the run fails if they do not. A recovered line is *not*
promoted onto a current surface: these records are quarantined precisely because no
surface cites them, and history is preserved rather than reinstated.
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from tarav.l1.bloberia.core import BloberiaDepot  # noqa: E402
from tarav.index_model.identity import index_line_anchor_triplet_hash  # noqa: E402

DEPOT = Path.home() / "Documents" / "bloberia" / "tarav-index"
ANCHORY = Path.home() / "Documents" / "chatlas" / "anchory"
QUARANTINE = "tarav-pkg/design#Unattached"

_CITE = re.compile(r"\^([cd]\d{8}-\d+[a-z])\s*$")
#: A markdown index line, or an `Skw.Annotation` note carrying the same anchor.
_LINE = re.compile(r"^\+(?P<line>\s*-\s*(?:\[[A-Z]{2}\]\s*)?.*?)\s*\^[cd]\d{8}-\d+[a-z]\s*$")
_TYPE = re.compile(r"^\s*-\s*\[(?P<type>[A-Z]{2})\]\s*(?P<body>.*)$")
#: The same line hosted inside an `Skw.Annotation` rather than on an index surface.
_NOTE = re.compile(
    r"--note\s+\[(?P<type>[A-Z]{2})\]\s*(?P<body>.*?)\s*\^(?P<anchor>[cd]\d{8}-\d+[a-z])"
)


def _editions_in(raw: str) -> list[tuple[str, str]]:
    """Anchored index lines in one added diff line, in either hosting syntax.

    An `Index.Native.Surface` writes `- [DF] body ^anchor`. An ordinary product surface
    hosts the same line inside an `Skw.Annotation`, as `--note [DF] body ^anchor`, and one
    annotation may carry several. Both are index lines; only the host differs.

    Prose that merely *cites* an anchor is not an edition of it, which is why neither
    pattern matches a bare mention.
    """
    line = _LINE.match(raw)
    if line:
        anchor = _CITE.search(raw)
        if anchor:
            return [(anchor.group(1), line.group("line").strip())]
    return [
        (m.group("anchor"), f"- [{m.group('type')}] {m.group('body').strip()}")
        for m in _NOTE.finditer(raw)
    ]


def history(scratch: Path) -> dict[str, list[dict]]:
    """Every historical edition of every anchored line, with commit and path."""
    found: dict[str, list[dict]] = collections.defaultdict(list)
    for source in sorted(scratch.glob("*-prov.txt")):
        repo = source.stem.removesuffix("-prov")
        commit, at, path = None, None, None
        for raw in source.read_text("utf-8", errors="replace").splitlines():
            if raw.startswith("COMMIT "):
                parts = raw.split()
                commit, at = parts[1], parts[2] if len(parts) > 2 else None
                continue
            if raw.startswith("+++ "):
                path = raw[4:].removeprefix("b/").strip()
                continue
            for anchor, text in _editions_in(raw):
                found[anchor].append(
                    {
                        "line": text,
                        "repo": repo,
                        "commit": commit,
                        "at": at,
                        "path": path,
                    }
                )
    return found


def dossiers() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for shard in sorted(ANCHORY.glob("*/[0-9a-f][0-9a-f].json")):
        out.update(json.loads(shard.read_text("utf-8")))
    return out


def classify(anchor: str, editions: list[dict], stored_hash: str | None) -> dict:
    """One quarantined anchor, resolved by evidence rather than by recency."""
    wordings: dict[str, dict] = {}
    for edition in editions:
        wordings.setdefault(edition["line"], edition)

    if not wordings:
        return {"verdict": "absent", "chosen": None, "candidates": []}
    if stored_hash:
        hits = [w for w in wordings if index_line_anchor_triplet_hash(w, anchor) == stored_hash]
        if len(hits) == 1:
            return {"verdict": "verified", "chosen": wordings[hits[0]], "candidates": list(wordings)}
        if len(hits) > 1:
            return {"verdict": "ambiguous", "chosen": None, "candidates": hits}
        return {"verdict": "mismatch", "chosen": None, "candidates": list(wordings)}
    if len(wordings) == 1:
        only = next(iter(wordings))
        return {"verdict": "single", "chosen": wordings[only], "candidates": [only]}
    return {"verdict": "ambiguous", "chosen": None, "candidates": list(wordings)}


def split_line(line: str) -> tuple[str | None, str]:
    typed = _TYPE.match(line)
    if typed:
        return typed.group("type"), typed.group("body").strip()
    return None, line.lstrip("- ").strip()


def main() -> int:
    scratch = Path(sys.argv[1])
    apply = "--apply" in sys.argv
    depot = BloberiaDepot(DEPOT)

    before = {
        "records": depot.count({}),
        "support": sum(len(r["links"]["grounding"]) for r in depot.iterate()),
        "gates": sum(len(r["links"]["review"]) for r in depot.iterate()),
    }

    editions, doss = history(scratch), dossiers()
    quarantined = depot.all({"scope": {"equals": QUARANTINE}})
    stats: collections.Counter = collections.Counter()
    report: list[dict] = []

    for record in quarantined:
        anchor = (record["line"]["label"] or "").lstrip("^")
        stored = (doss.get(anchor, {}).get("attachment") or {}).get("triplet_hash")
        outcome = classify(anchor, editions.get(anchor, []), stored)
        stats[outcome["verdict"]] += 1
        report.append(
            {
                "anchor": anchor,
                "had_hash": bool(stored),
                "verdict": outcome["verdict"],
                "chosen": outcome["chosen"],
                "candidates": outcome["candidates"],
            }
        )

        if not apply or outcome["chosen"] is None:
            continue
        chosen = outcome["chosen"]
        line_type, body = split_line(chosen["line"])
        updated = json.loads(json.dumps(record))
        updated["line"]["type"] = line_type
        updated["line"]["body"] = body
        # Scope stays quarantined on purpose. The wording is recovered; the *placement*
        # is not, because no current surface carries this line — writing the historical
        # path into `scope` would state a grouping that no longer exists. The commit and
        # path live in the report, and the record's own history is in the depot's git.
        depot.replace({"line.label": {"equals": record["line"]["label"]}}, updated)
        stats["written"] += 1

    (scratch / "645-recovery-report.json").write_text(
        json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    for key in sorted(stats):
        print(f"{key}: {stats[key]}")
    print(f"\nquarantined: {len(quarantined)}   classified: {sum(stats[v] for v in ('verified','single','ambiguous','mismatch','absent'))}")

    after = {
        "records": depot.count({}),
        "support": sum(len(r["links"]["grounding"]) for r in depot.iterate()),
        "gates": sum(len(r["links"]["review"]) for r in depot.iterate()),
    }
    print(f"before: {before}\nafter : {after}")
    if before != after:
        print("FAILED — recovery changed record, support or gate cardinality")
        return 1
    print("\ndry run — pass --apply to write" if not apply else "\nOK — bodies restored, cardinalities unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
