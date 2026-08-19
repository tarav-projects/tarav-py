#!/usr/bin/env python3
"""One-shot homogenization of legacy `chatlas` anchor dossiers into the Chatlas2 model.

Impl.Req 546. `527` specifies this as an operational transformation written against the
actual data and protected by git history, not a maintained subsystem — so this is a live
script and is deleted once it has run.

The join is `Legacy.Support.Join`: a legacy `{session, turn_id, turn_hash, at}` resolves
against the current Normal Model by exact `started_at` plus the turn's resolved text.
`521` governs what happens when it does not: unresolved evidence is a reported finding and
never relocation, and its stop-trigger — "an invalid support member is moved to similar
text" — is why text equality is only ever a *check* on a candidate selected by identity.

Migration is not correction. An anchor migrates with the members that join; an incomplete
gate is omitted so the linter raises it, rather than the migration inventing evidence.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
from typing import Any

from tarav.chatlas._payload_helpers import dict_list
from tarav.chatlas.index_query import select_one_chatlas_index_row
from tarav.chatlas.lossless.anchory import (
    CHATLAS2_NAMESPACE,
    ensure_lossless_namespace,
    lossless_anchory_depot,
)
from tarav.chatlas.lossless.messages import list_chat_messages
from tarav.chatlas.lossless.pipeline import build_normal_model
from tarav.chatlas.lossless.turns import list_chat_turns
from tarav.chatlas.normalization.session_model import (
    build_chatlas_session_model_from_index_row,
)
from tarav.chatlas.normalization.session_model.events import normal_turn_id
from tarav.chatlas.normalization.session_model.messages import content_text

ANCHOR_PATTERN = re.compile(r"\^(c\d{8}-\d+[a-z])")
PROJECT_ROOT = Path("/Users/pereiro/projects/taravangian-project")
SKIP_PARTS = ("/.skw/", "_DEPRECATED", "/.git/")


def legacy_store(chatlas_root: Path) -> dict[str, Any]:
    store: dict[str, Any] = {}
    for shard in sorted((chatlas_root / "anchory" / "chatlas").glob("*.json")):
        payload = json.loads(shard.read_text("utf-8"))
        if isinstance(payload, dict):
            store.update(payload)
    return store


def referenced_anchors(store: dict[str, Any]) -> set[str]:
    """Anchors any maintained surface actually cites.

    Unreferenced dossiers are history: they are neither migrated nor deleted.
    """
    found: set[str] = set()
    for pattern in ("*.md", "*.py"):
        for path in PROJECT_ROOT.rglob(pattern):
            text = str(path)
            if any(part in text for part in SKIP_PARTS):
                continue
            try:
                body = path.read_text("utf-8", errors="ignore")
            except OSError:
                continue
            found.update(a for a in ANCHOR_PATTERN.findall(body) if a in store)
    return found


class SessionJoin:
    """The two models of one session, joined by event start time.

    Both are built because the legacy coordinate is only interpretable in the old model
    and the new coordinate only exists in the new one. That is the whole migration.
    """

    def __init__(self, session: str) -> None:
        row = select_one_chatlas_index_row(command="migrate", identity_hash=session)
        old = build_chatlas_session_model_from_index_row(row)
        self.new = build_normal_model(identity_hash=session)
        self.session = session

        self.turn_text: dict[str, str] = {}
        for event in dict_list((old.get("chat") or {}).get("events")):
            turn = normal_turn_id(event)
            if turn is None or self.turn_text.get(turn):
                continue
            self.turn_text[turn] = content_text((event.get("payload") or {}).get("content"))

        self.events = {e["event_address"]: e for e in self.new.get("events", [])}
        self.messages = list_chat_messages(self.new)
        self.turns = list_chat_turns(self.new)
        self.start: dict[str, str | None] = {}
        for message in self.messages:
            refs = message.get("event_refs") or []
            first = self.events.get(refs[0]["event_address"]) if refs else None
            self.start[message["message_address"]] = first.get("started_at") if first else None

    def _message_at(self, at: str) -> list[dict[str, Any]]:
        return [m for m in self.messages if self.start.get(m["message_address"]) == at]

    def _through_turn(self, at: str) -> list[dict[str, Any]]:
        """Bridge an agent-side ref through its containing `Chat.Turn`.

        A legacy gate proposal addresses the turn's *first* event, which is frequently no
        `Chat.Message` at all. `541` keeps both gate sides as messages, so the turn is the
        bridge and never the stored ref. Selection is by exact containment — identity, not
        similarity — and the caller still checks the text.
        """
        source = [e for e in self.new.get("events", []) if e.get("started_at") == at]
        if not source:
            return []
        address = source[0]["event_address"]
        owning = [
            turn
            for turn in self.turns
            if any(r["event_address"] == address for r in turn.get("event_refs", []))
        ]
        if len(owning) != 1:
            return []
        wanted = {r["message_address"] for r in owning[0].get("message_refs", [])}
        return [
            m
            for m in self.messages
            if m["message_address"] in wanted and m.get("side") == owning[0].get("side")
        ]

    def resolve(self, ref: dict[str, Any], *, bridge: bool) -> tuple[str, dict | None]:
        at = ref.get("at")
        text = (self.turn_text.get(ref.get("turn_id", "")) or "").strip()
        candidates = [m for m in self._message_at(at) if (m.get("text") or "").strip() == text]
        if not candidates and bridge:
            candidates = [
                m for m in self._through_turn(at) if (m.get("text") or "").strip() == text
            ]
        if len(candidates) > 1:
            return "AMBIGUOUS", None
        if not candidates:
            return "NO_JOIN", None
        message = candidates[0]
        return "EXACT", {
            "session": self.session,
            "message_address": message["message_address"],
            "message_hash": message["message_hash"],
            "at": at,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chatlas-root", type=Path, default=Path.home() / "Documents/chatlas")
    parser.add_argument("--apply", action="store_true", help="Write; otherwise report only.")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    store = legacy_store(args.chatlas_root)
    anchors = sorted(referenced_anchors(store))
    if args.limit:
        anchors = anchors[: args.limit]
    print(f"referenced anchors: {len(anchors)} of {len(store)} in store")

    sessions: dict[str, SessionJoin | None] = {}

    def joiner(session: str) -> SessionJoin | None:
        if session not in sessions:
            try:
                sessions[session] = SessionJoin(session)
            except Exception as exc:  # session unreadable is a finding, not a crash
                print(f"  session unavailable {session[:12]}: {str(exc)[:90]}")
                sessions[session] = None
        return sessions[session]

    depot = lossless_anchory_depot(args.chatlas_root)
    ensure_lossless_namespace(depot)

    tally: Counter[str] = Counter()
    findings: list[tuple[str, str, str]] = []
    converted: dict[str, Any] = {}

    for anchor in anchors:
        legacy = store[anchor]
        relationships = legacy.get("relationships", {})
        members: list[dict[str, Any]] = []
        dropped = 0
        for member in relationships.get("support", {}).get("members", []):
            join = joiner(member["session"])
            if join is None:
                tally["support:SESSION_UNAVAILABLE"] += 1
                dropped += 1
                continue
            status, coordinate = join.resolve(member, bridge=False)
            tally[f"support:{status}"] += 1
            if coordinate is None:
                dropped += 1
                findings.append((anchor, "support", status))
            else:
                members.append(coordinate)

        gates: list[dict[str, Any]] = []
        for gate in relationships.get("gates", {}).get("tokenized_verbatim_approval", []) or []:
            sides: dict[str, Any] = {}
            for legacy_side, side in (("proposal_turn", "proposal"), ("approval_turn", "approval")):
                ref = gate.get(legacy_side)
                join = joiner(ref["session"]) if isinstance(ref, dict) else None
                if join is None:
                    tally[f"{side}:SESSION_UNAVAILABLE"] += 1
                    continue
                status, coordinate = join.resolve(ref, bridge=(side == "proposal"))
                tally[f"{side}:{status}"] += 1
                if coordinate is not None:
                    sides[side] = coordinate
                else:
                    findings.append((anchor, side, status))
            # An incomplete gate is omitted, not half-written: the linter must be able to
            # see that this line has no licensing gate.
            if {"proposal", "approval"} <= set(sides):
                gates.append({"token": gate.get("token"), **sides})
            else:
                tally["gate:INCOMPLETE"] += 1

        if not members:
            tally["anchor:NO_SUPPORT"] += 1
            findings.append((anchor, "anchor", "no member joined"))
            continue

        provenance = relationships.get("provenance", {})
        converted[anchor] = {
            "app": "chatlas2",
            "schema": "tarav.chatlas2.line-anchor-dossier.v2",
            "attachment": dict(legacy.get("attachment", {})),
            "relationships": {
                "support": {"members": members},
                "gates": {
                    "semantic_approval": [],
                    "tokenized_verbatim_approval": gates,
                },
                "provenance": {
                    "predecessor_anchors": list(provenance.get("predecessor_anchors", [])),
                    "issue_context": list(provenance.get("issue_context", [])),
                },
            },
        }
        tally["anchor:CONVERTED"] += 1
        if dropped:
            tally["anchor:PARTIAL"] += 1

    print("\n=== TALLY ===")
    for key, count in sorted(tally.items()):
        print(f"  {key:34} {count}")
    print(f"\nfindings: {len(findings)}")
    for finding in findings[:15]:
        print("  ", finding)

    if not args.apply:
        print("\nreport only; pass --apply to write")
        return 0

    for anchor, record in converted.items():
        depot.write_record(CHATLAS2_NAMESPACE, anchor, record)
    print(f"\nwrote {len(converted)} dossiers to the {CHATLAS2_NAMESPACE} namespace")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
