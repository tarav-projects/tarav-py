from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tarav.l0.testing import TaravTestEnvironment


def write_text_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_codex_work_profile(
    environment: TaravTestEnvironment,
    codex_home: Path,
) -> None:
    environment.write_profile(
        "codex-work",
        provider="codex",
        homes=[str(codex_home)],
    )


def write_chatlas_codex_source(
    environment: TaravTestEnvironment,
    codex_home: Path,
    *,
    chatlas_config: dict[str, object] | None = None,
) -> None:
    config: dict[str, object] = {
        "sources": [
            {
                "provider": "codex",
                "home": str(codex_home),
            },
        ],
    }
    if chatlas_config is not None:
        config.update(chatlas_config)
    environment.write_global_config(chatlas=config)


def read_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl_file(path: Path) -> list[Any]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def captured_json(capsys: object) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]


def _digest(*parts: object) -> str:
    from hashlib import sha256

    return sha256("/".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def normal_model_fixture(
    source: Path,
    *,
    identity_hash: str = "f" * 64,
    session_id: str = "session-one",
    turns: tuple[tuple[str, str], ...] = (("user", "hello"),),
) -> dict[str, Any]:
    """A valid Normal Model with one event and one message per (side, text) turn."""
    events, messages, chat_turns = [], [], []
    for index, (side, text) in enumerate(turns, start=1):
        event_ref = {
            "event_address": _digest(identity_hash, "event", index),
            "event_hash": _digest(identity_hash, "event-hash", index, text),
        }
        message_ref = {
            "message_address": _digest(identity_hash, "message", index),
            "message_hash": _digest(identity_hash, "message-hash", index, text),
        }
        events.append({
            "type": "User.Event" if side == "user" else "Agent.Event",
            **event_ref,
            "started_at": f"2026-10-18T00:00:{index:02d}Z",
            "origin": side,
            "observations": [{
                "observed_at": f"2026-10-18T00:00:{index:02d}Z",
                "source_ref": {"source_id": "source-one", "record_index": index, "line": index},
            }],
            "opaque_payload_hash": _digest(identity_hash, "payload", index),
        })
        messages.append({"type": "Chat.Message", **message_ref, "side": side,
                         "text": text, "event_refs": [event_ref]})
        chat_turns.append({
            "type": "Chat.Turn",
            "turn_address": _digest(identity_hash, "turn", index),
            "turn_hash": _digest(identity_hash, "turn-hash", index, text),
            "side": side,
            "event_refs": [event_ref],
            "message_refs": [message_ref],
        })
    return {
        "type": "Chatlas.Normal.Model",
        "schema_version": 1,
        "metadata": {"commit": None},
        "session": {"provider": "codex", "session_id": session_id,
                    "identity_hash": identity_hash},
        "sources": [{"source_id": "source-one", "path": str(source), "role": "transcript",
                     "raw_model_version": "codex.rollout.test", "status": "recognized"}],
        "events": events,
        "messages": messages,
        "turns": chat_turns,
        "loaded_contexts": [],
        "counts": {"events": len(events), "messages": len(messages),
                   "turns": len(chat_turns), "loaded_contexts": 0},
    }
