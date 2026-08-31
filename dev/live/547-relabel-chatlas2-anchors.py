#!/usr/bin/env python3
"""Relabel the `d…` Chatlas2 anchors onto the one `c…` namespace.

Impl.Req 546. The `d` prefix separated the experimental system's anchors from the current
ones while both stood. Once every record carries the Chatlas2 model there is one kind of
record, so the second prefix names a distinction that no longer exists.

The `d` side is the small one — 148 records against 2,364 — so it is the side that moves.
Where `d<date>-<n><tag>` would collide with an existing `c<date>-<n><tag>`, a fresh id is
minted under the same date rather than overwriting anything: an anchor id is a public
handle, and the record's identity does not follow it.

Citations are rewritten in the same run. A relabel that leaves a surface citing the old id
is worse than not relabelling, so the store and the surfaces move together.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from tarav.chatlas.paths import default_chatlas_root

PROJECT_ROOT = Path("/Users/pereiro/projects/taravangian-project")
SKIP_PARTS = ("/.skw/", "_DEPRECATED", "/.git/", "/node_modules/")
ANCHOR_RE = re.compile(r"(?P<prefix>[a-z])(?P<date>\d{8})-(?P<seq>\d+)(?P<tag>[a-z]?)")


def read_namespace(root: Path) -> dict[str, Any]:
    records: dict[str, Any] = {}
    for shard in sorted(root.glob("*.json")):
        if shard.name == "meta.json":
            continue
        payload = json.loads(shard.read_text("utf-8"))
        if isinstance(payload, dict):
            records.update(payload)
    return records


def shard_of(anchor: str) -> str:
    match = re.fullmatch(r"(?P<base>[a-z]\d{8}-\d+)[a-z]?", anchor)
    key = match.group("base") if match else anchor
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:2]


def plan_labels(source: dict[str, Any], target: dict[str, Any]) -> dict[str, str]:
    """`d…` -> `c…`, minting a fresh sequence only where the direct rename collides."""
    taken = set(target)
    highest: dict[str, int] = {}
    for anchor in taken:
        match = ANCHOR_RE.fullmatch(anchor)
        if match:
            date = match.group("date")
            highest[date] = max(highest.get(date, -1), int(match.group("seq")))

    mapping: dict[str, str] = {}
    for anchor in sorted(source):
        match = ANCHOR_RE.fullmatch(anchor)
        if match is None:
            continue
        date, tag = match.group("date"), match.group("tag")
        direct = f"c{date}-{match.group('seq')}{tag}"
        if direct not in taken:
            chosen = direct
        else:
            nxt = highest.get(date, -1) + 1
            chosen = f"c{date}-{nxt}{tag}"
            while chosen in taken:
                nxt += 1
                chosen = f"c{date}-{nxt}{tag}"
            highest[date] = nxt
        taken.add(chosen)
        mapping[anchor] = chosen
    return mapping


def rewrite_surfaces(mapping: dict[str, str], *, apply: bool) -> tuple[int, int]:
    token = re.compile(r"\^(" + "|".join(re.escape(a) for a in mapping) + r")\b")
    files = hits = 0
    for pattern in ("*.md", "*.py", "*.json"):
        for path in PROJECT_ROOT.rglob(pattern):
            text = str(path)
            if any(part in text for part in SKIP_PARTS):
                continue
            try:
                body = path.read_text("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            new, count = token.subn(lambda m: "^" + mapping[m.group(1)], body)
            if count:
                files += 1
                hits += count
                if apply:
                    path.write_text(new, encoding="utf-8")
    return files, hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chatlas-root", type=Path, default=default_chatlas_root())
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    anchory = args.chatlas_root / "anchory"
    source = read_namespace(anchory / "chatlas2")
    target = read_namespace(anchory / "chatlas")
    print(f"chatlas2: {len(source)} records   chatlas: {len(target)} records")

    mapping = plan_labels(source, target)
    renamed = sum(1 for old, new in mapping.items() if new[1:] != old[1:])
    print(f"relabelling {len(mapping)}; reminted on collision: {renamed}")

    files, hits = rewrite_surfaces(mapping, apply=args.apply)
    print(f"citations: {hits} across {files} files")

    if not args.apply:
        print("\nreport only; pass --apply to write")
        for old in sorted(mapping)[:6]:
            print(f"  {old} -> {mapping[old]}")
        return 0

    # A record may name another relabelled anchor -- `predecessor_anchors` does. Moving
    # the ids without remapping the record bodies would leave those references dangling.
    internal = re.compile(r"\b(" + "|".join(re.escape(a) for a in mapping) + r")\b")
    by_shard: dict[str, dict[str, Any]] = {}
    remapped = 0
    for old, new in mapping.items():
        body = json.dumps(source[old])
        body, count = internal.subn(lambda m: mapping[m.group(1)], body)
        remapped += count
        by_shard.setdefault(shard_of(new), {})[new] = json.loads(body)
    print(f"remapped {remapped} anchor references inside moved records")
    written = 0
    for shard, batch in by_shard.items():
        path = anchory / "chatlas" / f"{shard}.json"
        existing = json.loads(path.read_text("utf-8")) if path.exists() else {}
        overlap = set(existing) & set(batch)
        if overlap:  # planning guarantees this cannot happen; assert rather than trust
            raise SystemExit(f"refusing to overwrite existing anchors: {sorted(overlap)[:5]}")
        existing.update(batch)
        path.write_text(
            json.dumps(existing, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written += len(batch)
    print(f"wrote {written} relabelled records into the chatlas namespace")

    tally = Counter(new[0] for new in mapping.values())
    print("prefixes now in use:", dict(tally))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
