from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

import pytest

from tarav._core.errors import CliError
from tarav.chatlas.lossless import chat_index_surface_path
from tarav.index.capture_manifest import (
    CAPTURE_MANIFEST_SCHEMA,
    capture_manifest,
    parse_capture_manifest,
)
from tarav.index.record import IndexStore


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _model(identity: str) -> dict[str, object]:
    events = []
    messages = []
    turns = []
    values = (
        ("user", "Please ground the disposable capture test block."),
        (
            "agent",
            "I propose - [CT] capture production path is complete. idx-edition:test",
        ),
        ("user", "Approved idx-edition:test"),
    )
    for index, (side, text) in enumerate(values, start=1):
        event = {
            "class": "User.Event" if side == "user" else "Agent.Event",
            "event_address": _digest(f"event-address-{index}"),
            "event_hash": _digest(f"event-hash-{index}"),
            "started_at": f"2026-08-21T00:00:0{index}Z",
        }
        message = {
            "class": "Chat.Message",
            "message_address": _digest(f"message-address-{index}"),
            "message_hash": _digest(f"message-hash-{index}"),
            "side": side,
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
            "turn_address": _digest(f"turn-address-{index}"),
            "turn_hash": _digest(f"turn-hash-{index}"),
            "side": side,
            "event_refs": deepcopy(message["event_refs"]),
            "message_refs": [
                {
                    "message_address": message["message_address"],
                    "message_hash": message["message_hash"],
                }
            ],
        }
        events.append(event)
        messages.append(message)
        turns.append(turn)
    return {
        "session": {
            "identity_hash": identity,
            "session_id": "capture-test",
            "provider": "codex",
        },
        "events": events,
        "annotations": {"chat_messages": messages, "chat_turns": turns},
        "turns": turns,
    }


class _Reader:
    def __init__(self, model: dict[str, object]) -> None:
        self.model = model
        self.metadata = {"model": {"session": deepcopy(model["session"])}}

    def iter_chat_message_records(
        self, *, message_addresses=None, limit=None, **_kwargs
    ):
        selected = set(message_addresses) if message_addresses is not None else None
        yielded = 0
        for message in self.model["annotations"]["chat_messages"]:
            if selected is not None and message["message_address"] not in selected:
                continue
            yield {"message": deepcopy(message)}
            yielded += 1
            if limit is not None and yielded >= limit:
                return

    def iter_chat_turns(self, **_kwargs):
        yield from deepcopy(self.model["turns"])

    def find_chat_turn(self, *, message_address=None, **_kwargs):
        for turn in self.model["turns"]:
            if any(
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


def _ref(model: dict[str, object], index: int, *contains: str) -> dict[str, object]:
    message = model["annotations"]["chat_messages"][index]
    event = model["events"][index]
    return {
        "session": model["session"]["identity_hash"],
        "message_address": message["message_address"],
        "message_hash": message["message_hash"],
        "hints": {"at": event["started_at"]},
        "expect": {"contains_all": list(contains)},
    }


def _manifest(model: dict[str, object]) -> dict[str, object]:
    return {
        "schema": CAPTURE_MANIFEST_SCHEMA,
        "chat_index": {"session": model["session"]["identity_hash"]},
        "items": [
            {
                "client_id": "capture-test-line",
                "action": "ground",
                "target": {
                    "surface": "skills/test/design/100-design.md",
                    "block": "test/design#Capture.Test",
                },
                "line": {
                    "type": "CT",
                    "body": "capture production path is complete.",
                },
                "support": [_ref(model, 0, "ground", "capture test block")],
                "gates": {
                    "tokenized_verbatim_approval": [
                        {
                            "token": "idx-edition:test",
                            "proposal": _ref(model, 1, "capture production path"),
                            "approval": _ref(model, 2, "Approved", "idx-edition:test"),
                        }
                    ]
                },
            }
        ],
    }


def _surface(project_root):
    depot = project_root / "skills/test"
    design = depot / "design"
    design.mkdir(parents=True)
    (depot / "000-INDEX.md").write_text("# Test Index\n", encoding="utf-8")
    path = design / "100-design.md"
    path.write_text(
        "****\n\n## Capture.Test\n\n"
        "- [CT] capture production path is complete.\n\n****\n",
        encoding="utf-8",
    )
    return path


def _skw_surface(project_root):
    config = project_root / ".skw/skw.json"
    config.parent.mkdir()
    config.write_text(
        json.dumps(
            {
                "code_surfaces": [
                    {
                        "language": "python",
                        "include": ["src/**/*.py"],
                        "allow_points": ["file", "class", "function"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    source = project_root / "src/check.py"
    source.parent.mkdir()
    source.write_text(
        "# $kw: Capture.Test --note [CT] capture production path is complete.\n"
        "def check():\n"
        "    pass\n",
        encoding="utf-8",
    )
    return source


def test_manifest_omits_redundant_side_and_checks_expected_content():
    identity = "a" * 64
    model = _model(identity)
    payload = _manifest(model)
    parsed = parse_capture_manifest(payload)
    assert parsed.items[0].support[0].contains_all == ("ground", "capture test block")

    payload["items"][0]["support"][0]["side"] = "user"
    with pytest.raises(CliError, match="invalid shape"):
        parse_capture_manifest(payload)


def test_shared_message_refs_build_one_message_projection_per_session(
    geo, project_root, tmp_path, monkeypatch
):
    source = _surface(project_root)
    source.write_text(
        "****\n\n## Capture.Test\n\n"
        "- [CT] capture production path is complete.\n"
        "- [CT] shared support is resolved once.\n\n****\n",
        encoding="utf-8",
    )
    identity = "f" * 64
    model = _model(identity)
    payload = _manifest(model)
    second = deepcopy(payload["items"][0])
    second["client_id"] = "capture-test-shared-support"
    second["line"] = {"type": "CT", "body": "shared support is resolved once."}
    second.pop("gates")
    payload["items"].append(second)

    from tarav.index import capture_manifest as capture_module

    original = capture_module.list_chat_messages
    projections = 0

    def counted(session_model):
        nonlocal projections
        projections += 1
        return original(session_model)

    model_loads = 0

    def load_model(_identity):
        nonlocal model_loads
        model_loads += 1
        return deepcopy(model)

    monkeypatch.setattr(capture_module, "list_chat_messages", counted)
    report = capture_manifest(
        geo,
        parse_capture_manifest(payload),
        land=False,
        chatlas_root=tmp_path,
        model_loader=load_model,
        reader_loader={identity: _Reader(model)}.__getitem__,
    )

    assert report.item_count == 2
    assert model_loads == 1
    assert projections == 1


def test_disposable_capture_test_block_runs_the_complete_production_path(
    geo, project_root, tmp_path
):
    source = _surface(project_root)
    original = source.read_text(encoding="utf-8")
    identity = "b" * 64
    model = _model(identity)
    parsed = parse_capture_manifest(_manifest(model))
    readers = {identity: _Reader(model)}

    preview = capture_manifest(
        geo,
        parsed,
        land=False,
        chatlas_root=tmp_path,
        model_loader=lambda _identity: deepcopy(model),
        reader_loader=readers.__getitem__,
    )
    assert preview.status == "ok"
    assert preview.effects["anchors"] == {"mint": 1, "reuse": 0}
    assert source.read_text(encoding="utf-8") == original
    assert IndexStore(geo).count() == 0

    landed = capture_manifest(
        geo,
        parsed,
        land=True,
        chatlas_root=tmp_path,
        model_loader=lambda _identity: deepcopy(model),
        reader_loader=readers.__getitem__,
    )
    assert landed.audit["ok"] is True
    label = landed.items[0]["anchor"]
    assert label in source.read_text(encoding="utf-8")
    record = IndexStore(geo).by_label(label)
    assert record is not None
    assert len(record.review) == 1
    assert record.review[0].token == "idx-edition:test"
    assert record.landing == record.review[0]
    head = chat_index_surface_path(identity, chatlas_root=tmp_path) / "HEAD.md"
    assert f"- [CT] capture production path is complete. {label}" in head.read_text(
        encoding="utf-8"
    )

    repeated = capture_manifest(
        geo,
        parsed,
        land=True,
        chatlas_root=tmp_path,
        model_loader=lambda _identity: deepcopy(model),
        reader_loader=readers.__getitem__,
    )
    assert repeated.effects["anchors"] == {"minted": 0, "reused": 1}
    assert repeated.effects["records"] == {
        "created": 0,
        "updated_gates": 0,
        "existing": 1,
    }
    assert repeated.effects["chat_index"]["changed"] is False

    # The probe surface is stable, not immutable. Remove the disposable test block; the
    # temporary project, record depot, Anchory depot, and Chat.Index disappear with tmp_path.
    source.write_text("", encoding="utf-8")
    assert "Capture.Test" not in source.read_text(encoding="utf-8")


def test_content_expectation_fails_before_any_durable_write(
    geo, project_root, tmp_path
):
    source = _surface(project_root)
    identity = "c" * 64
    model = _model(identity)
    payload = _manifest(model)
    payload["items"][0]["support"][0]["expect"] = {"contains_all": ["not present"]}

    with pytest.raises(CliError, match="contains_all"):
        capture_manifest(
            geo,
            parse_capture_manifest(payload),
            land=True,
            chatlas_root=tmp_path,
            model_loader=lambda _identity: deepcopy(model),
            reader_loader={identity: _Reader(model)}.__getitem__,
        )

    assert "^c" not in source.read_text(encoding="utf-8")
    assert IndexStore(geo).count() == 0


def test_manifest_grounds_a_skw_hosted_line_through_the_same_pipeline(
    geo, project_root, tmp_path
):
    source = _skw_surface(project_root)
    identity = "d" * 64
    model = _model(identity)
    payload = _manifest(model)
    payload["items"][0]["target"] = {
        "surface": "skw:src/check.py",
        "block": "@src/check.py/Capture.Test",
    }
    readers = {identity: _Reader(model)}

    report = capture_manifest(
        geo,
        parse_capture_manifest(payload),
        land=True,
        chatlas_root=tmp_path,
        model_loader=lambda _identity: deepcopy(model),
        reader_loader=readers.__getitem__,
    )

    assert report.audit["ok"] is True
    assert report.items[0]["anchor"] in source.read_text(encoding="utf-8")
    record = IndexStore(geo).by_label(report.items[0]["anchor"])
    assert record is not None
    assert record.scope.address == "@src/check.py/Capture.Test"


def test_manifest_grounds_an_explicit_live_markdown_heading(
    geo, project_root, tmp_path
):
    source = project_root / "notes/live/741-capture-impl-req.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "# Implementation requirement\n\n"
        "## Impl.Index\n\n"
        "- [CT] capture production path is complete.\n",
        encoding="utf-8",
    )
    identity = "e" * 64
    model = _model(identity)
    payload = _manifest(model)
    payload["items"][0]["target"] = {
        "surface": "notes/live/741-capture-impl-req.md",
        "block": "@notes/live/741-capture-impl-req.md/Impl.Index",
    }

    report = capture_manifest(
        geo,
        parse_capture_manifest(payload),
        land=True,
        chatlas_root=tmp_path,
        model_loader=lambda _identity: deepcopy(model),
        reader_loader={identity: _Reader(model)}.__getitem__,
    )

    assert report.audit["ok"] is True
    assert report.items[0]["anchor"] in source.read_text(encoding="utf-8")
    record = IndexStore(geo).by_label(report.items[0]["anchor"])
    assert record is not None
    assert record.scope.address == "@notes/live/741-capture-impl-req.md/Impl.Index"
