"""User-turn purity (Impl.Req 513, Slice 1).

A user turn admits only normalized user input. A slash-command invocation
expands into several ``role=user`` records — the command wrapper, the injected
skill body, and a system reminder — and only the wrapper carries what the user
actually typed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tarav.chatlas.normalization.session_model._claude import (
    _normalize_claude_session,
)
from tarav.chatlas.normalization.session_model.events import normal_turn_kind


@dataclass(frozen=True)
class _FakeClaudeSession:
    transcript_path: Path
    source_ref_id: str | None = "src-1"


def _user_record(uuid: str, text: str, parent: str | None) -> dict:
    return {
        "type": "user",
        "uuid": uuid,
        "version": "2.0.0",
        "parentUuid": parent,
        "timestamp": "2026-07-26T10:36:59.214Z",
        "sessionId": "S1",
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def _assistant_record(uuid: str, text: str, parent: str) -> dict:
    return {
        "type": "assistant",
        "uuid": uuid,
        "version": "2.0.0",
        "parentUuid": parent,
        "timestamp": "2026-07-26T10:37:00.214Z",
        "sessionId": "S1",
        "requestId": f"request-{uuid}",
        "message": {
            "id": f"message-{uuid}",
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        },
    }


def _queued_command_record(
    uuid: str,
    prompt: str,
    parent: str,
    *,
    command_mode: str = "prompt",
    origin_kind: str | None = "human",
    is_meta: bool | None = None,
) -> dict:
    attachment = {
        "type": "queued_command",
        "prompt": prompt,
        "commandMode": command_mode,
        "timestamp": "2026-07-26T10:37:01.214Z",
    }
    if origin_kind is not None:
        attachment["origin"] = {"kind": origin_kind}
    if is_meta is not None:
        attachment["isMeta"] = is_meta
    return {
        "type": "attachment",
        "uuid": uuid,
        "version": "2.0.0",
        "parentUuid": parent,
        "timestamp": "2026-07-26T10:37:01.214Z",
        "sessionId": "S1",
        "attachment": attachment,
    }


COMMAND_WRAPPER = (
    "<command-message>agentos-hugentics-impl</command-message>\n"
    "<command-name>/agentos-hugentics-impl</command-name>\n"
    "<command-args>--design\nDesign the token-approval implementation.</command-args>"
)
SKILL_BODY = (
    "Base directory for this skill: /repo/.claude/skills/agentos-hugentics-impl\n\n"
    "# Tarav Hugentics Impl\n\nUnified workflow skill."
)
SYSTEM_REMINDER = "<system-reminder>\nDirectory-scoped variants exist.\n</system-reminder>"
BARE_COMMAND = (
    "<command-message>compact</command-message>\n"
    "<command-name>/compact</command-name>\n"
    "<command-args></command-args>"
)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )


def _user_events(path: Path) -> list[dict]:
    result = _normalize_claude_session(_FakeClaudeSession(transcript_path=path))
    assert result is not None
    return [
        event
        for event in result.events
        if event.get("kind") == "message"
        and (event.get("payload") or {}).get("role") == "user"
    ]


def _producer(event: dict) -> tuple[str | None, str | None]:
    producer = event.get("producer") or {}
    return producer.get("type"), producer.get("name")


def _text(event: dict) -> str:
    content = (event.get("payload") or {}).get("content") or []
    return "".join(block.get("text", "") for block in content)


def test_slash_command_expansion_yields_one_user_turn(tmp_path):
    path = tmp_path / "session.jsonl"
    _write_jsonl(
        path,
        [
            _user_record("u1", COMMAND_WRAPPER, None),
            _user_record("u2", SKILL_BODY, "u1"),
            _user_record("u3", SYSTEM_REMINDER, "u2"),
        ],
    )

    events = _user_events(path)
    assert len(events) == 3

    user_turns = [event for event in events if normal_turn_kind(event) == "user"]
    assert len(user_turns) == 1
    assert "Design the token-approval implementation." in _text(user_turns[0])


def test_injected_skill_body_is_not_a_user_turn(tmp_path):
    path = tmp_path / "session.jsonl"
    _write_jsonl(path, [_user_record("u1", SKILL_BODY, None)])

    (event,) = _user_events(path)
    assert _producer(event) == ("system", "skill-body")
    assert normal_turn_kind(event) is None


def test_bare_command_invocation_carries_no_user_input(tmp_path):
    """A command with no args carries no user input, so it is not a
    user turn — the invocation is an act, not a statement."""
    path = tmp_path / "session.jsonl"
    _write_jsonl(path, [_user_record("u1", BARE_COMMAND, None)])

    (event,) = _user_events(path)
    assert _producer(event) == ("system", "command")
    assert normal_turn_kind(event) is None


def test_plain_user_message_is_a_user_turn(tmp_path):
    path = tmp_path / "session.jsonl"
    _write_jsonl(path, [_user_record("u1", "lets design the linter side", None)])

    (event,) = _user_events(path)
    assert _producer(event) == ("human", None)
    assert normal_turn_kind(event) == "user"


def test_human_queued_command_opens_an_independent_user_turn(tmp_path):
    path = tmp_path / "session.jsonl"
    _write_jsonl(
        path,
        [
            _user_record("u1", "start the work", None),
            _assistant_record("a1", "working", "u1"),
            _queued_command_record("q1", "change the active plan", "a1"),
            _assistant_record("a2", "following the change", "a1"),
            _queued_command_record(
                "q2",
                "task notification",
                "a2",
                command_mode="task-notification",
                origin_kind=None,
            ),
            _queued_command_record(
                "q3",
                "coordinator instruction",
                "a2",
                origin_kind="coordinator",
            ),
            _queued_command_record(
                "q4",
                "meta instruction",
                "a2",
                is_meta=True,
            ),
        ],
    )

    result = _normalize_claude_session(_FakeClaudeSession(transcript_path=path))
    assert result is not None
    visible_messages = [
        event
        for event in result.events
        if event.get("kind") == "message"
        and (event.get("surfaces") or {}).get("transcript") == "visible"
    ]
    user_events = [
        event
        for event in visible_messages
        if (event.get("payload") or {}).get("role") == "user"
    ]

    assert [_text(event) for event in user_events] == [
        "start the work",
        "change the active plan",
    ]
    queued_user = user_events[1]
    assert _producer(queued_user) == ("human", None)
    assert normal_turn_kind(queued_user) == "user"
    assert (queued_user.get("annotations") or {}).get("normal_turn", {}).get(
        "id"
    ) == "q1"
    assert queued_user["timestamp"] == "2026-07-26T10:37:01.214Z"
    assert (queued_user.get("native") or {}).get("attachment", {}).get(
        "commandMode"
    ) == "prompt"
    assert (queued_user.get("source_refs") or [])[0]["record_index"] == 3

    following = next(
        event for event in visible_messages if _text(event) == "following the change"
    )
    assert (following.get("annotations") or {}).get("normal_turn", {}).get(
        "id"
    ) == "q1:assistant"
    assert queued_user["sequence"] < following["sequence"]


def test_prompt_mode_queued_command_without_origin_is_user_input(tmp_path):
    path = tmp_path / "session.jsonl"
    _write_jsonl(
        path,
        [
            _queued_command_record(
                "q1",
                "older prompt shape",
                "a1",
                origin_kind=None,
            )
        ],
    )

    (event,) = _user_events(path)
    assert _text(event) == "older prompt shape"
    assert _producer(event) == ("human", None)
    assert normal_turn_kind(event) == "user"
