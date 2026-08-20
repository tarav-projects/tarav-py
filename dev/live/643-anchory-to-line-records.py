#!/usr/bin/env python3
# $kw: --from Migration.Current.Only --note [DC] one target schema; every legacy family is mapped onto Index.Line.Record rather than preserved beside it
"""Convert the whole anchory corpus into `Index.Line.Record`s (impl-req 641, slice 7b).

Input is the restoration set from `642` — the union of HEAD with `ce67f3fc1`, which holds
every support member and gate either tree ever had, including the 17 members and 354 gates
that `546` dropped.

**One target schema.** Four legacy families arrive here — `chatlas.support-set.v3` through
`v6`, `chatlas.line-anchor-dossier.v1`, and `tarav.chatlas2.line-anchor-dossier.v1`/`v2` —
and all four leave as `LineRecord`. Nothing is preserved beside the new model; mapping the
old shape onto the new one *is* the job.

**Conservation governs.** A record is never skipped for being incomplete. An anchor with no
citing surface line has no recoverable body — a dossier carries a triplet *hash*, never the
text — and converts empty-bodied into a quarantine scope, where the linter reports it. That
is a loud POI rather than a silent omission, and roughly 1,600 of them is the correct
outcome of migrating a corpus whose older half was never line-attached.

**Coordinates are mapped, never invented.** A turn-addressed support member becomes a
`SupportRef` whose `archive` says `chat-turn`, so nothing claims a turn id is a message
address. Proving turn-to-message equivalence resolves through Chatlas2 and is its own step;
asserting it here would be the `Durable.Evidence.Audit` stop-trigger — silent purity repair.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from tarav.index.gates import GateRef  # noqa: E402
from tarav.index.record.model import (  # noqa: E402
    Line,
    LineRecord,
    SupportRef,
    new_line_id,
    new_trace_id,
)
from tarav.index.scope import ScopeError, parse_scope  # noqa: E402

PROJECT = Path(__file__).resolve().parents[3]
SURFACE_ROOTS = ("tarav-md", "tarav-chatlas-md", "_DEPRECATED/tarav2", "tarav-py")

#: Where an anchor lands when no surface cites it. A real address that resolves to no
#: concept, so every one of them is a linter finding rather than a plausible-looking line.
QUARANTINE = "tarav-pkg/design#Unattached"

_CITE = re.compile(r"\^([cd]\d{8}-\d+[a-z])\s*$")
_TYPED = re.compile(
    r"^\s*-\s*(?:\[(?P<type>[A-Z]{2})\]\s*)?(?P<body>.*?)\s*\^[cd]\d{8}-\d+[a-z]\s*$"
)
_HEADING = re.compile(r"^##\s+(?P<concept>\S+)")
_CHAPTER = re.compile(r"^\d+-(?P<chapter>[a-z-]+)\.md$")


def surface_inventory() -> dict[str, dict]:
    """Anchor → the line that cites it, and the block it sits in.

    This is the only place a body and a `Line.Type` can come from: the dossier stores a
    hash of the triplet, which proves a line without reproducing it.
    """
    found: dict[str, dict] = {}
    for root in SURFACE_ROOTS:
        for path in (PROJECT / root).rglob("*.md"):
            if ".git/" in str(path):
                continue
            try:
                lines = path.read_text("utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            concept = None
            for raw in lines:
                heading = _HEADING.match(raw)
                if heading:
                    concept = heading.group("concept")
                    continue
                typed, cite = _TYPED.match(raw), _CITE.search(raw)
                if not typed or not cite:
                    continue
                found.setdefault(
                    cite.group(1),
                    {
                        "path": path,
                        "concept": concept,
                        "type": typed.group("type"),
                        "body": typed.group("body").strip(),
                    },
                )
    return found


def scope_for(entry: dict) -> str:
    """The line's address, from where it is written.

    A chapter line is a `Block.Path`; anything else is a `Locator.Name` naming the file it
    lives on, which is the honest address for a line that is not in an index chapter.
    """
    path: Path = entry["path"]
    relative = path.relative_to(PROJECT)
    parts = relative.parts
    chapter = _CHAPTER.match(path.name)
    if chapter and entry["concept"] and "skills" in parts:
        depot = parts[parts.index("skills") + 1]
        return f"{depot}/{chapter.group('chapter')}#{entry['concept']}"
    return f"@{relative.as_posix()}"


def safe_scope(address: str, entry: dict | None) -> tuple[str, str]:
    """A legal scope, and how it was reached.

    Some index headings use a `Concept::Sub` form that `Skw.Address.Schema` does not admit.
    The record is never dropped for it: the line falls back to the file it is written on,
    which is a true address, and the mismatch is counted so it can be fixed rather than
    discovered later as a missing record.
    """
    try:
        parse_scope(address)
        return address, "block" if "#" in address else "locator"
    except ScopeError:
        if entry is None:
            return QUARANTINE, "quarantine"
        fallback = f"@{entry['path'].relative_to(PROJECT).as_posix()}"
        try:
            parse_scope(fallback)
            return fallback, "locator_fallback"
        except ScopeError:
            return QUARANTINE, "quarantine_fallback"


def support_refs(members: list[dict]) -> tuple[list[SupportRef], Counter]:
    """Every member, in the space it was written in.

    `archive` carries the space rather than a uniform `chat`, because a turn id resolved as
    a message address is not a failed lookup — it is a wrong one that looks like evidence.
    """
    refs, stats = [], Counter()
    for member in members:
        session = member.get("session")
        if not session:
            stats["member_without_session"] += 1
            continue
        if member.get("space") == "message" and member.get("message_address"):
            refs.append(SupportRef("chat", session, str(member["message_address"])))
            stats["support_message"] += 1
        elif member.get("turn_id"):
            refs.append(SupportRef("chat-turn", session, str(member["turn_id"])))
            stats["support_turn"] += 1
        elif member.get("message_hash") or member.get("turn_hash"):
            refs.append(
                SupportRef(
                    "chat-hash",
                    session,
                    str(member.get("message_hash") or member.get("turn_hash")),
                )
            )
            stats["support_hash_only"] += 1
        else:
            stats["member_unaddressable"] += 1
    return refs, stats


def _endpoint(value: object) -> tuple[str | None, str | None]:
    """One side of a gate: `(session, turn-or-message id)`, across four spellings."""
    if isinstance(value, str) and ":" in value:
        session, _, rest = value.partition(":")
        return session, rest
    if isinstance(value, dict):
        return (
            value.get("session"),
            value.get("message_address") or value.get("turn_id") or value.get("turn_hash"),
        )
    return None, None


def gate_refs(gates: list[dict]) -> tuple[list[GateRef], Counter]:
    """Legacy and current gates onto one `GateRef`.

    `GateRef` is already turn-shaped — `user_turn_id` / `agent_turn_id` — so the legacy
    form needs no coercion: `approval_turn` is the user side, `verbatim_turn` or
    `proposal_turn` the agent side. Approval is user-side and proposal agent-side under the
    settled gate model, so the mapping is a rename, not a reinterpretation.
    """
    refs, stats = [], Counter()
    for gate in gates:
        entry = gate.get("entry")
        if not isinstance(entry, dict) or not entry:
            stats["gate_empty"] += 1
            continue
        user_session, user_id = _endpoint(
            entry.get("approval_turn") or entry.get("approval")
        )
        agent_session, agent_id = _endpoint(
            entry.get("verbatim_turn") or entry.get("proposal_turn") or entry.get("proposal")
        )
        token = entry.get("token")
        session = user_session or agent_session
        if not (session and token and user_id and agent_id):
            stats["gate_incomplete_but_kept"] += 1
        if not session or not token:
            stats["gate_unmappable"] += 1
            continue
        refs.append(
            GateRef(
                archive="chat" if gate.get("space") == "message" else "chat-turn",
                session_id=str(session),
                token=str(token),
                user_turn_id=str(user_id or ""),
                agent_turn_id=str(agent_id or ""),
            )
        )
        stats[f"gate_{gate.get('space')}"] += 1
    return refs, stats


def convert(restoration: dict[str, dict], surfaces: dict[str, dict]) -> tuple[list[LineRecord], Counter]:
    stats = Counter()
    # A predecessor chain is one indexed semantic, so its members share a trace.
    trace_of: dict[str, str] = {}
    for anchor in sorted(restoration):
        entry = restoration[anchor]
        root = anchor
        seen = set()
        while True:
            predecessors = restoration.get(root, {}).get("provenance") or []
            nxt = next((p for p in predecessors if p in restoration and p not in seen), None)
            if nxt is None:
                break
            seen.add(nxt)
            root = nxt
        trace_of[anchor] = trace_of.setdefault(root, new_trace_id())
        del entry

    records: list[LineRecord] = []
    for anchor in sorted(restoration):
        entry = restoration[anchor]
        surface = surfaces.get(anchor)
        if surface:
            scope, how = safe_scope(scope_for(surface), surface)
            line_type, body = surface["type"], surface["body"]
            stats[f"scope_{how}"] += 1
            stats["attached"] += 1
        else:
            scope, line_type, body = QUARANTINE, None, ""
            stats["quarantined"] += 1

        support, support_stats = support_refs(entry["support"])
        gates, gate_stats = gate_refs(entry["gates"])
        stats.update(support_stats)
        stats.update(gate_stats)

        records.append(
            LineRecord(
                id=new_line_id(),
                trace=trace_of[anchor],
                scope=parse_scope(scope),
                line=Line(type=line_type, body=body, label=f"^{anchor}"),
                support=tuple(support),
                review=tuple(gates),
            )
        )
        stats["records"] += 1
    return records, stats


def main() -> int:
    restoration = json.loads(Path(sys.argv[1]).read_text("utf-8"))
    out = Path(sys.argv[2])
    surfaces = surface_inventory()
    records, stats = convert(restoration, surfaces)

    # Conservation, checked rather than asserted: every member and gate that survived the
    # restoration set has to appear on a record, and every anchor has to become one.
    expected_support = sum(len(e["support"]) for e in restoration.values())
    expected_gates = sum(len(e["gates"]) for e in restoration.values())
    got_support = sum(len(r.support) for r in records)
    got_gates = sum(len(r.review) for r in records)
    labels = {r.line.label for r in records}

    for key in sorted(stats):
        print(f"{key}: {stats[key]}")
    print(f"\nanchors in  : {len(restoration)}   records out: {len(records)}")
    print(f"support in  : {expected_support}   out: {got_support}")
    print(f"gates in    : {expected_gates}   out: {got_gates}")

    failures = []
    if len(records) != len(restoration):
        failures.append("anchor count not conserved")
    if len(labels) != len(restoration):
        failures.append("labels are not distinct")
    dropped_s = expected_support - got_support
    dropped_g = expected_gates - got_gates
    if dropped_s != stats["member_without_session"] + stats["member_unaddressable"]:
        failures.append(f"{dropped_s} support members unaccounted for")
    if dropped_g != stats["gate_empty"] + stats["gate_unmappable"]:
        failures.append(f"{dropped_g} gates unaccounted for")

    if failures:
        print("\nFAILED")
        for line in failures:
            print(" ", line)
        return 1

    out.write_text(
        json.dumps([r.to_json() for r in records], indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"\nOK — every drop is named and counted. Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
