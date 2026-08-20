#!/usr/bin/env python3
# $kw: --from Durable.Evidence.Audit --note [DC] restoration reads immutable history rather than a rewritten store, so the source of truth is a commit and not a copy
"""Build the loss-free restoration set for the anchory corpus (impl-req 641, slice 7a).

`e251cd336` (impl-req 546) homogenized the legacy dossiers and, in doing so, dropped
**17 support members across 12 anchors** and **354 gates across 349 anchors**. Anchor
identity survived intact: 0 lost, 145 added.

Nothing is actually gone. `ce67f3fc1` is the commit immediately before that migration and
holds every dropped member and gate permanently. So restoration does not mean writing the
material back into the current store — it means **reading from the commit that still has
it**, and proving the union is complete.

That ordering matters. The current dossier validator does exact key-set checks at every
level, so conserving untranslatable legacy material in the live store would need a schema
version on a format slice 7b deletes. Reading from history costs nothing, versions nothing,
and keeps the authority immutable rather than a copy this script authored.

What comes out is one artifact per anchor:

```text
anchor      the label, unchanged across the migration
current     the HEAD record, whatever shape it is in
support     every distinct member, from both trees, in the coordinate space it was written
gates       every distinct gate, from both trees, in the space it was written
provenance  predecessors from both trees
```

**Coordinates are never translated here.** A legacy gate is turn-addressed and a current
one is message-addressed; proving equivalence between them requires resolving through
Chatlas2 and is a separate, checkable step. Conserving a member in the space it was written
in states exactly what is known. Translating it on a guess would state more.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

CHATLAS = Path.home() / "Documents" / "chatlas"
BEFORE = "ce67f3fc1"
AFTER = "HEAD"


def _tree(ref: str) -> dict[str, dict]:
    """Every anchor record in one commit, keyed by anchor."""
    names = subprocess.run(
        ["git", "-C", str(CHATLAS), "ls-tree", "-r", "--name-only", ref, "anchory/"],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    out: dict[str, dict] = {}
    for name in names:
        if not name.endswith(".json") or name.endswith("meta.json"):
            continue
        blob = subprocess.run(
            ["git", "-C", str(CHATLAS), "show", f"{ref}:{name}"],
            capture_output=True, text=True, check=True,
        ).stdout
        try:
            shard = json.loads(blob)
        except ValueError:
            continue
        if isinstance(shard, dict):
            for anchor, record in shard.items():
                if isinstance(record, dict):
                    out[anchor] = record
    return out


def _support(record: dict) -> list[dict]:
    """Support members in whatever space the record was written in.

    A message-addressed member and a turn-addressed one are not interchangeable, so each
    carries the space it was written in rather than being coerced into one shape.
    """
    members: list[dict] = []
    relationships = record.get("relationships") or {}
    for member in ((relationships.get("support") or {}).get("members") or []):
        members.append({"space": "message", **member})
    for member in (record.get("members") or []):
        members.append({"space": "turn", **{k: v for k, v in member.items() if k != "types"}})
    return members


def _gate_space(entry: object) -> str:
    """How a gate addresses, not where it was stored.

    The `v1` dossier kept turn-addressed gates under `relationships.gates`, the same place
    `v2` keeps message-addressed ones, so location is not the coordinate space. Reading the
    space off the entry is what makes two representations of one token recognisable as
    such instead of looking like two gates.
    """
    if isinstance(entry, dict) and not entry:
        return "empty"
    text = json.dumps(entry)
    if "message_address" in text:
        return "message"
    if "turn_id" in text or "turn_hash" in text:
        return "turn"
    # `support-set.v4` serialized a turn ref as the string `<session>:<turn>`, which names
    # the same coordinate without naming the field. Same space, older spelling.
    if isinstance(entry, dict) and any(
        isinstance(entry.get(field), str) and ":" in entry[field]
        for field in ("approval_turn", "verbatim_turn", "proposal_turn")
    ):
        return "turn"
    return "unknown"


def _gates(record: dict) -> list[dict]:
    """Every gate, under the three legacy spellings and the current one."""
    gates: list[dict] = []
    relationships = record.get("relationships") or {}
    for kind, entries in (relationships.get("gates") or {}).items():
        for entry in entries or []:
            gates.append({"space": _gate_space(entry), "kind": kind, "entry": entry})
    for member in (record.get("members") or []):
        for kind, entry in (member.get("types") or {}).items():
            gates.append({"space": _gate_space(entry), "kind": kind, "entry": entry})
    return gates


def _provenance(record: dict) -> list[str]:
    relationships = record.get("relationships") or {}
    provenance = relationships.get("provenance") or {}
    return list(provenance.get("predecessor_anchors") or []) + list(
        record.get("predecessors") or []
    )


def _merge(items: list[dict]) -> list[dict]:
    """Union by exact content. Two identical members are one member, not two."""
    seen: dict[str, dict] = {}
    for item in items:
        seen.setdefault(json.dumps(item, sort_keys=True), item)
    return list(seen.values())


def build() -> tuple[dict[str, dict], Counter]:
    before, after = _tree(BEFORE), _tree(AFTER)
    stats = Counter()
    restoration: dict[str, dict] = {}

    for anchor in sorted(set(before) | set(after)):
        old, new = before.get(anchor, {}), after.get(anchor, {})
        support = _merge(_support(old) + _support(new))
        gates = _merge(_gates(old) + _gates(new))
        provenance = sorted(set(_provenance(old)) | set(_provenance(new)))

        restoration[anchor] = {
            "anchor": anchor,
            "current": new or None,
            "legacy_schema": old.get("schema"),
            "support": support,
            "gates": gates,
            "provenance": provenance,
        }
        stats["anchors"] += 1
        stats["support_members"] += len(support)
        stats["gates"] += len(gates)
        if len(_support(old)) > len(_support(new)):
            stats["anchors_with_restored_support"] += 1
            stats["restored_support_members"] += len(_support(old)) - len(_support(new))
        if len(_gates(old)) > len(_gates(new)):
            stats["anchors_with_restored_gates"] += 1
            stats["restored_gates"] += len(_gates(old)) - len(_gates(new))
        if not new:
            stats["anchors_missing_from_head"] += 1
    return restoration, stats


def verify(restoration: dict[str, dict]) -> list[str]:
    """The check slice 7a exists for: the set loses nothing either tree holds.

    Asserted against both trees rather than against the migration's own log, because a
    migration's self-report is not evidence about the migration.
    """
    failures: list[str] = []
    for ref in (BEFORE, AFTER):
        for anchor, record in _tree(ref).items():
            entry = restoration.get(anchor)
            if entry is None:
                failures.append(f"{anchor}: present in {ref}, absent from the restoration set")
                continue
            have_support = {json.dumps(m, sort_keys=True) for m in entry["support"]}
            for member in _support(record):
                if json.dumps(member, sort_keys=True) not in have_support:
                    failures.append(f"{anchor}: support member from {ref} not conserved")
            have_gates = {json.dumps(g, sort_keys=True) for g in entry["gates"]}
            for gate in _gates(record):
                if json.dumps(gate, sort_keys=True) not in have_gates:
                    failures.append(f"{anchor}: gate from {ref} not conserved")
    return failures


def _identity_tokens(value: object) -> set[str]:
    """Every session, address, hash, turn id and token string anywhere in a record.

    This is the check that is not self-referential. Conserving the *members my extractor
    returned* is true by construction; conserving every identity string the raw record
    contains is not, and it fails loudly if a shape family exists that `_support` or
    `_gates` never learned to read.
    """
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"session", "message_address", "message_hash", "turn_hash",
                       "turn_id", "token", "approval_turn", "verbatim_turn",
                       "proposal_turn"} and isinstance(item, str):
                found.add(item)
            found |= _identity_tokens(item)
    elif isinstance(value, list):
        for item in value:
            found |= _identity_tokens(item)
    return found


def verify_no_identity_is_dropped(restoration: dict[str, dict]) -> list[str]:
    failures: list[str] = []
    for ref in (BEFORE, AFTER):
        for anchor, record in _tree(ref).items():
            entry = restoration.get(anchor)
            if entry is None:
                continue
            missing = _identity_tokens(record) - _identity_tokens(entry)
            for token in sorted(missing):
                failures.append(f"{anchor}: identity {token[:24]}... from {ref} is not conserved")
    return failures


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dev/live/642-restoration-set.json")
    restoration, stats = build()
    failures = verify(restoration) + verify_no_identity_is_dropped(restoration)

    for key in sorted(stats):
        print(f"{key}: {stats[key]}")
    print(f"space split: {Counter(m['space'] for e in restoration.values() for m in e['support'])}")
    print(f"gate space split: {Counter(g['space'] for e in restoration.values() for g in e['gates'])}")

    if failures:
        print(f"\nFAILED — {len(failures)} conservation failures")
        for line in failures[:20]:
            print(" ", line)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(restoration, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nOK — nothing either tree holds is missing. Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
