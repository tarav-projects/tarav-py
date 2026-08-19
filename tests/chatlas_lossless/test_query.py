from __future__ import annotations

from pathlib import Path
import json
from copy import deepcopy
from hashlib import sha256

import pytest

from tarav.cli.cli import main


def test_session_query_reuses_index_selection_and_projects_compact_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from tarav.chatlas.lossless import query

    captured: dict[str, object] = {}

    def select(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "index_matched_row_count": 2,
            "returned_row_count": 2,
            "rows": [
                {
                    "uri": "agentos://chat-session/codex/one/session-one",
                    "provider": "codex",
                    "instance": "one",
                    "identity_hash": "a" * 64,
                    "session_id": "session-one",
                    "last_activity_at": "2026-08-16T12:00:00Z",
                    "project_path": "/work/alpha",
                    "backing_artifacts": [{"path": "/private/raw.jsonl"}],
                },
                {
                    "uri": "agentos://chat-session/claude-code/two/session-two",
                    "provider": "claude-code",
                    "instance": "two",
                    "identity_hash": "b" * 64,
                    "session_id": "session-two",
                    "last_activity_at": "2026-08-16T11:00:00Z",
                    "project_path": "/work/beta",
                },
            ],
        }

    monkeypatch.setattr(query, "chatlas_index_query", select)

    result = query.query_sessions(
        providers=("codex",),
        project_base="alpha",
        active_after="2026-08-16T00:00:00Z",
        sort="newest",
        limit=7,
        chatlas_root=tmp_path,
    )

    assert captured == {
        "providers": ("codex",),
        "project_base": "alpha",
        "active_after": "2026-08-16T00:00:00Z",
        "sort": "newest",
        "limit": 7,
        "chatlas_root": tmp_path,
        "uri": None,
        "identity_hash": None,
        "project": None,
        "instances": None,
        "provider_instance_fingerprint": None,
        "session_id": None,
        "display_name": None,
        "extractable_only": False,
    }
    assert result["class"] == "tarav.chatlas2.session-query"
    assert result["session_count"] == 2
    assert result["index_matched_session_count"] == 2
    assert result["sessions"][0] == {
        "uri": "agentos://chat-session/codex/one/session-one",
        "provider": "codex",
        "instance": "one",
        "identity_hash": "a" * 64,
        "session_id": "session-one",
        "last_activity_at": "2026-08-16T12:00:00Z",
        "project_path": "/work/alpha",
    }
    assert "backing_artifacts" not in result["sessions"][0]


def test_session_query_rejects_unsupported_provider() -> None:
    from tarav.chatlas.lossless.query import query_sessions

    with pytest.raises(ValueError, match="supports only"):
        query_sessions(providers=("copilot-cli",))


def test_session_query_cli_exposes_metadata_selectors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tarav.chatlas.lossless import commands

    captured: dict[str, object] = {}

    def run(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"class": "tarav.chatlas2.session-query", "sessions": []}

    monkeypatch.setattr(commands, "query_sessions", run)
    assert (
        main(
            [
                "chatlas",
                "sessions",
                "query",
                "--provider",
                "codex",
                "--project-base",
                "alpha",
                "--active-after",
                "2026-08-16T00:00:00Z",
                "--sort",
                "newest",
                "--limit",
                "8",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["sessions"] == []
    assert captured["providers"] == ("codex",)
    assert captured["project_base"] == "alpha"
    assert captured["active_after"] == "2026-08-16T00:00:00Z"
    assert captured["sort"] == "newest"
    assert captured["limit"] == 8


class _Reader:
    def __init__(self, records: list[dict[str, object]]) -> None:
        self.records = records

    def iter_chat_message_records(self, **_kwargs: object):
        yield from deepcopy(self.records)

    def find_chat_turn(self, **kwargs: object) -> dict[str, object] | None:
        address = kwargs.get("message_address")
        if address is None:
            return None
        return {
            "class": "Chat.Turn",
            "turn_address": _address(f"turn-{address}"),
            "turn_hash": _address(f"turn-hash-{address}"),
            "side": "user",
            "event_refs": [],
            "message_refs": [],
        }


def _message_record(
    address: str,
    *,
    side: str,
    text: str,
    at: str,
) -> dict[str, object]:
    message_address = _address(address)
    return {
        "at": at,
        "message": {
            "class": "Chat.Message",
            "message_address": message_address,
            "message_hash": _address(f"hash-{address}"),
            "side": side,
            "text": text,
            "event_refs": [],
        },
    }


def _address(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_single_session_chat_query_verifies_message_predicates_and_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tarav.chatlas.lossless import query

    identity = "a" * 64
    session = {
        "provider": "codex",
        "identity_hash": identity,
        "session_id": "session-one",
        "last_activity_at": "2026-08-16T12:00:00Z",
    }
    reader = _Reader(
        [
            _message_record(
                "one",
                side="user",
                text="Hello, Query World!",
                at="2026-08-16T10:00:00Z",
            ),
            _message_record(
                "two",
                side="agent",
                text="An answer",
                at="2026-08-16T10:01:00Z",
            ),
            _message_record(
                "three",
                side="user",
                text="Final validation MVP",
                at="2026-08-16T10:02:00Z",
            ),
        ]
    )
    monkeypatch.setattr(
        query,
        "query_sessions",
        lambda **_kwargs: {
            "class": "tarav.chatlas2.session-query",
            "sessions": [session],
        },
    )
    monkeypatch.setattr(query, "provide_normal_model_reader", lambda **_kwargs: reader)

    contains = query.query_chat_messages(
        identity_hash=identity,
        side="user",
        text_contains="query world",
        after="2026-08-16T09:59:00Z",
        before="2026-08-16T10:01:00Z",
        include_turn_ref=True,
    )
    assert contains["status"] == "ok"
    assert contains["query_matched_message_count"] == 1
    result = contains["messages"][0]
    assert result["message_ref"] == {
        "message_address": _address("one"),
        "message_hash": _address("hash-one"),
    }
    assert result["turn_ref"] == {
        "turn_address": _address(f"turn-{_address('one')}"),
        "turn_hash": _address(f"turn-hash-{_address('one')}"),
    }
    assert result["session"]["identity_hash"] == identity

    assert query.query_chat_messages(
        identity_hash=identity,
        text_verbatim="HELLO query-world",
    )["messages"][0]["message"]["message_address"] == _address("one")
    assert query.query_chat_messages(
        identity_hash=identity,
        text_regex=r"Final\s+validation",
    )["messages"][0]["message"]["message_address"] == _address("three")
    assert query.query_chat_messages(
        identity_hash=identity,
        text_exact="An answer",
    )["messages"][0]["message"]["message_address"] == _address("two")
    assert query.query_chat_messages(
        identity_hash=identity,
        message_address=_address("three"),
    )["messages"][0]["message"]["message_address"] == _address("three")


def test_single_session_chat_query_sorts_then_limits_verified_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tarav.chatlas.lossless import query

    identity = "a" * 64
    monkeypatch.setattr(
        query,
        "query_sessions",
        lambda **_kwargs: {
            "sessions": [
                {
                    "provider": "codex",
                    "identity_hash": identity,
                    "session_id": "session-one",
                }
            ]
        },
    )
    monkeypatch.setattr(
        query,
        "provide_normal_model_reader",
        lambda **_kwargs: _Reader(
            [
                _message_record(
                    "one", side="user", text="match one", at="2026-08-16T10:00:00Z"
                ),
                _message_record(
                    "skip", side="agent", text="skip", at="2026-08-16T10:01:00Z"
                ),
                _message_record(
                    "two", side="user", text="match two", at="2026-08-16T10:02:00Z"
                ),
            ]
        ),
    )

    result = query.query_chat_messages(
        identity_hash=identity,
        side="user",
        text_contains="match",
        sort="newest",
        limit=1,
    )
    assert result["query_matched_message_count"] == 2
    assert result["returned_message_count"] == 1
    assert result["messages"][0]["message"]["message_address"] == _address("two")


def test_chat_query_pages_verified_matches_after_sorting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tarav.chatlas.lossless import query

    identity = "a" * 64
    monkeypatch.setattr(
        query,
        "query_sessions",
        lambda **_kwargs: {
            "sessions": [{"provider": "codex", "identity_hash": identity}]
        },
    )
    monkeypatch.setattr(
        query,
        "provide_normal_model_reader",
        lambda **_kwargs: _Reader(
            [
                _message_record(
                    str(index),
                    side="user",
                    text=f"message {index}",
                    at=f"2026-08-16T10:0{index}:00Z",
                )
                for index in range(4)
            ]
        ),
    )

    first = query.query_chat_messages(
        identity_hash=identity,
        sort="oldest",
        offset=0,
        limit=2,
    )
    second = query.query_chat_messages(
        identity_hash=identity,
        sort="oldest",
        offset=first["next_offset"],
        limit=2,
    )

    assert [item["message"]["text"] for item in first["messages"]] == [
        "message 0",
        "message 1",
    ]
    assert first["offset"] == 0
    assert first["next_offset"] == 2
    assert [item["message"]["text"] for item in second["messages"]] == [
        "message 2",
        "message 3",
    ]
    assert second["next_offset"] is None


def test_chat_query_cli_exposes_single_session_message_query(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tarav.chatlas.lossless import commands

    captured: dict[str, object] = {}

    def run(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"class": "tarav.chatlas2.chat-query", "messages": []}

    monkeypatch.setattr(commands, "query_chat_messages", run)
    assert (
        main(
            [
                "chatlas",
                "chat",
                "query",
                "--uri",
                "agentos://chat-session/codex/one/session-one",
                "--identity-hash",
                "a" * 64,
                "--side",
                "user",
                "--contains",
                "query world",
                "--after",
                "2026-08-16T09:00:00Z",
                "--include-turn-ref",
                "--sort",
                "newest",
                "--limit",
                "2",
                "--offset",
                "3",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["messages"] == []
    assert captured["uri"] == "agentos://chat-session/codex/one/session-one"
    assert captured["identity_hash"] == "a" * 64
    assert captured["side"] == "user"
    assert captured["text_contains"] == "query world"
    assert captured["after"] == "2026-08-16T09:00:00Z"
    assert captured["include_turn_ref"] is True
    assert captured["sort"] == "newest"
    assert captured["limit"] == 2
    assert captured["offset"] == 3


def test_chat_query_composes_session_set_and_reports_incomplete_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tarav._core.errors import CliError
    from tarav.chatlas.lossless import query

    identities = ("a" * 64, "b" * 64, "c" * 64)
    sessions = [
        {
            "provider": provider,
            "identity_hash": identity,
            "session_id": f"session-{index}",
        }
        for index, (provider, identity) in enumerate(
            zip(("codex", "claude-code", "claude-code"), identities, strict=True),
            start=1,
        )
    ]
    monkeypatch.setattr(
        query,
        "query_sessions",
        lambda **_kwargs: {"sessions": sessions},
    )

    def reader(*, identity_hash: str, **_kwargs: object) -> _Reader:
        if identity_hash == identities[2]:
            raise CliError("unrecognized raw model")
        if identity_hash == identities[0]:
            return _Reader(
                [
                    _message_record(
                        "codex",
                        side="user",
                        text="shared query token",
                        at="2026-08-16T10:02:00Z",
                    )
                ]
            )
        return _Reader(
            [
                _message_record(
                    "claude",
                    side="user",
                    text="shared query token",
                    at="2026-08-16T10:01:00Z",
                )
            ]
        )

    monkeypatch.setattr(query, "provide_normal_model_reader", reader)
    result = query.query_chat_messages(
        providers=("codex", "claude-code"),
        text_contains="shared query",
        session_limit=3,
        limit=10,
    )

    assert result["status"] == "partial"
    assert result["selected_session_count"] == 3
    assert result["queried_session_count"] == 2
    assert result["failure_count"] == 1
    assert result["failures"][0]["session"]["identity_hash"] == identities[2]
    assert [
        item["session"]["identity_hash"] for item in result["messages"]
    ] == [identities[1], identities[0]]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"text_exact": "one", "text_regex": "two"}, "one text predicate"),
        ({"text_contains": ""}, "non-empty"),
        ({"text_verbatim": "---"}, "alphanumeric"),
        ({"text_regex": "["}, "invalid regular expression"),
        ({"after": "not-a-time"}, "ISO 8601"),
    ],
)
def test_chat_query_rejects_invalid_predicates(
    kwargs: dict[str, object],
    message: str,
) -> None:
    from tarav.chatlas.lossless.query import query_chat_messages

    with pytest.raises(ValueError, match=message):
        query_chat_messages(**kwargs)
