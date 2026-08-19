from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from tarav._core.errors import CliError
from tarav.chatlas.lossless.anchory import (
    CHATLAS2_NAMESPACE,
    build_line_anchor_dossier,
    lossless_anchory_depot,
    ensure_lossless_namespace,
)
from tarav.chatlas.lossless.chat_index import (
    apply_chat_index_capture_plan,
    chat_index_surface_path,
    surface_state,
    validate_chat_index_capture_plan,
)
from tarav.chatlas.lossless.chat_index_plan import (
    CAPTURE_PLAN_SCHEMA,
    parse_capture_plan,
)


class _Reader:
    def __init__(self, model: dict[str, object]) -> None:
        self.model = deepcopy(model)
        self.metadata = {"model": {"session": deepcopy(model["session"])}}

    def iter_chat_message_records(
        self,
        *,
        message_addresses=None,
        side=None,
        limit=None,
        **_kwargs,
    ):
        selected = set(message_addresses) if message_addresses is not None else None
        yielded = 0
        for record in self.model["messages"]:
            message = record["message"]
            if selected is not None and message["message_address"] not in selected:
                continue
            if side is not None and message["side"] != side:
                continue
            yield deepcopy(record)
            yielded += 1
            if limit is not None and yielded >= limit:
                return

    def iter_chat_turns(self, *, side=None, limit=None, **_kwargs):
        yielded = 0
        for turn in self.model["turns"]:
            if side is not None and turn["side"] != side:
                continue
            yield deepcopy(turn)
            yielded += 1
            if limit is not None and yielded >= limit:
                return

    def find_chat_turn(self, *, turn_address=None, message_address=None):
        for turn in self.model["turns"]:
            if turn_address is not None and turn["turn_address"] == turn_address:
                return deepcopy(turn)
            if message_address is not None and any(
                ref["message_address"] == message_address
                for ref in turn["message_refs"]
            ):
                return deepcopy(turn)
        return None

    def iter_events(self, *, addresses=None):
        selected = set(addresses) if addresses is not None else None
        for event in self.model["events"]:
            if selected is None or event["event_address"] in selected:
                yield deepcopy(event)


def _model(identity: str, *, offset: int = 0) -> dict[str, object]:
    events = []
    messages = []
    turns = []
    for index, text in enumerate(("first support", "second support"), start=1):
        event = {
            "class": "User.Event",
            "event_address": _digest(f"event-address-{index + offset}"),
            "event_hash": _digest(f"event-hash-{index + offset}"),
            "started_at": f"2026-08-16T00:00:0{index}Z",
        }
        message = {
            "class": "Chat.Message",
            "message_address": _digest(f"message-address-{index + offset}"),
            "message_hash": _digest(f"message-hash-{index + offset}"),
            "side": "user",
            "text": text,
            "event_refs": [
                {
                    "event_address": event["event_address"],
                    "event_hash": event["event_hash"],
                }
            ],
        }
        turn = {
            "class": "Chat.Turn",
            "turn_address": _digest(f"turn-address-{index + offset}"),
            "turn_hash": _digest(f"turn-hash-{index + offset}"),
            "side": "user",
            "event_refs": deepcopy(message["event_refs"]),
            "message_refs": [
                {
                    "message_address": message["message_address"],
                    "message_hash": message["message_hash"],
                }
            ],
        }
        events.append(event)
        messages.append({"message": message, "at": event["started_at"]})
        turns.append(turn)
    return {
        "session": {
            "identity_hash": identity,
            "session_id": f"session-{offset}",
            "provider": "codex",
        },
        "events": events,
        "messages": messages,
        "turns": turns,
    }


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _member(model: dict[str, object], index: int) -> dict[str, object]:
    record = model["messages"][index]
    message = record["message"]
    return {
        "session": model["session"]["identity_hash"],
        "message_address": message["message_address"],
        "message_hash": message["message_hash"],
        "at": record["at"],
    }


def _register_line(
    root: Path,
    *,
    anchor: str,
    line: str,
    members: list[dict[str, object]],
    predecessors: tuple[str, ...] = (),
) -> None:
    depot = lossless_anchory_depot(root)
    ensure_lossless_namespace(depot)
    depot.register(
        build_line_anchor_dossier(
            anchor=anchor,
            line_content=line,
            members=members,
            predecessors=predecessors,
        ),
        anchor=anchor,
        namespace=CHATLAS2_NAMESPACE,
    )


def _plan(
    identity: str,
    *,
    base_surface,
    lines: list[tuple[str, str, str]],
):
    return parse_capture_plan(
        {
            "schema": CAPTURE_PLAN_SCHEMA,
            "session": {"identity_hash": identity},
            "base_surface": base_surface,
            "landed_lines": [
                {
                    "client_id": client_id,
                    "concept": concept,
                    "line_content": line,
                    "anchor": anchor,
                }
                for client_id, concept, line, anchor in (
                    (f"line-{index}", concept, line, anchor)
                    for index, (concept, line, anchor) in enumerate(lines, start=1)
                )
            ],
            "status": "ready",
        }
    )


def test_apply_projects_head_and_batches_receipts_at_latest_support_turn(
    tmp_path: Path,
) -> None:
    identity = "a" * 64
    model = _model(identity)
    first = "- [DC] First landed edition."
    second = "- [CT] Second landed edition."
    _register_line(
        tmp_path,
        anchor="d20260816-1u",
        line=first,
        members=[_member(model, 0)],
    )
    _register_line(
        tmp_path,
        anchor="d20260816-2u",
        line=second,
        members=[_member(model, 1)],
    )
    readers = {identity: _Reader(model)}
    plan = _plan(
        identity,
        base_surface=None,
        lines=[
            ("Real.Time.Capture", first, "d20260816-1u"),
            ("Index.HEAD.Backpropagation", second, "d20260816-2u"),
        ],
    )

    validated = validate_chat_index_capture_plan(
        plan,
        chatlas_root=tmp_path,
        reader_loader=readers.__getitem__,
    )
    assert validated["horizon"]["turn_ref"] == {
        "turn_address": model["turns"][1]["turn_address"],
        "turn_hash": model["turns"][1]["turn_hash"],
    }
    assert validated["head_only_gaps"] == []

    applied = apply_chat_index_capture_plan(
        plan,
        chatlas_root=tmp_path,
        reader_loader=readers.__getitem__,
    )
    assert applied["changed"] is True
    surface = chat_index_surface_path(identity, chatlas_root=tmp_path)
    head = (surface / "HEAD.md").read_text(encoding="utf-8")
    assert f"{first} ^d20260816-1u" in head
    assert f"{second} ^d20260816-2u" in head
    deltas = list((surface / "deltas").glob("*.md"))
    assert len(deltas) == 1
    delta = deltas[0].read_text(encoding="utf-8")
    assert f"{first} ^d20260816-1u" in delta
    assert f"{second} ^d20260816-2u" in delta
    assert model["turns"][1]["turn_hash"] in delta

    repeated = apply_chat_index_capture_plan(
        plan,
        chatlas_root=tmp_path,
        reader_loader=readers.__getitem__,
    )
    assert repeated["changed"] is False
    assert repeated["already_applied"] is True


def test_new_landed_edition_replaces_head_predecessor_without_rewriting_tape(
    tmp_path: Path,
) -> None:
    identity = "b" * 64
    model = _model(identity)
    old = "- [DC] The old current edition."
    new = "- [DC] The new current edition."
    _register_line(
        tmp_path,
        anchor="d20260816-3u",
        line=old,
        members=[_member(model, 0)],
    )
    readers = {identity: _Reader(model)}
    first_plan = _plan(
        identity,
        base_surface=None,
        lines=[("Edition", old, "d20260816-3u")],
    )
    apply_chat_index_capture_plan(
        first_plan,
        chatlas_root=tmp_path,
        reader_loader=readers.__getitem__,
    )
    surface = chat_index_surface_path(identity, chatlas_root=tmp_path)
    old_deltas = {path.name: path.read_bytes() for path in (surface / "deltas").glob("*.md")}
    _register_line(
        tmp_path,
        anchor="d20260816-4u",
        line=new,
        members=[_member(model, 1)],
        predecessors=("d20260816-3u",),
    )
    second_plan = _plan(
        identity,
        base_surface=surface_state(surface),
        lines=[("Edition", new, "d20260816-4u")],
    )

    apply_chat_index_capture_plan(
        second_plan,
        chatlas_root=tmp_path,
        reader_loader=readers.__getitem__,
    )

    head = (surface / "HEAD.md").read_text(encoding="utf-8")
    assert f"{old} ^d20260816-3u" not in head
    assert f"{new} ^d20260816-4u" in head
    for name, content in old_deltas.items():
        assert (surface / "deltas" / name).read_bytes() == content


def test_external_support_still_lands_on_head_and_reports_tape_gap(
    tmp_path: Path,
) -> None:
    identity = "c" * 64
    external_identity = "d" * 64
    current = _model(identity)
    external = _model(external_identity, offset=4)
    line = "- [DF] Current projection with external support."
    _register_line(
        tmp_path,
        anchor="d20260816-5u",
        line=line,
        members=[_member(external, 0)],
    )
    readers = {identity: _Reader(current), external_identity: _Reader(external)}
    plan = _plan(
        identity,
        base_surface=None,
        lines=[("External.Support", line, "d20260816-5u")],
    )

    applied = apply_chat_index_capture_plan(
        plan,
        chatlas_root=tmp_path,
        reader_loader=readers.__getitem__,
    )

    surface = chat_index_surface_path(identity, chatlas_root=tmp_path)
    assert f"{line} ^d20260816-5u" in (surface / "HEAD.md").read_text(
        encoding="utf-8"
    )
    assert not list((surface / "deltas").glob("*.md"))
    assert applied["head_only_gaps"] == [
        {
            "client_id": "line-1",
            "reason": "NO_TARGET_SESSION_SUPPORT",
        }
    ]


def test_stale_base_refuses_unrelated_surface_change(tmp_path: Path) -> None:
    identity = "e" * 64
    model = _model(identity)
    line = "- [DC] Planned edition."
    _register_line(
        tmp_path,
        anchor="d20260816-6u",
        line=line,
        members=[_member(model, 0)],
    )
    plan = _plan(
        identity,
        base_surface=None,
        lines=[("Stale.Base", line, "d20260816-6u")],
    )
    surface = chat_index_surface_path(identity, chatlas_root=tmp_path)
    surface.mkdir(parents=True)
    (surface / "HEAD.md").write_text("# Chat.Index.HEAD\n", encoding="utf-8")

    with pytest.raises(CliError, match="surface changed since scaffold"):
        apply_chat_index_capture_plan(
            plan,
            chatlas_root=tmp_path,
            reader_loader={identity: _Reader(model)}.__getitem__,
        )
