"""`Session.Model.Artifact` — the on-disk multi-file form of one `Chatlas.Session.Model`.

The artifact splits the assembled model into a small head (`session.json`), the
complete current `Session.Event.Tape` (`events.jsonl`), and sibling projections.
Materialization rewrites this derived snapshot when raw evidence or normalizer
semantics change; JSONL is a storage encoding, not an immutability claim.
"""

# $kw: ^session-model-artifact-jsonl --from Chatlas.Session.Model --from Session.Event.Tape --note [CT] artifact loading splits only on the JSONL LF delimiter so Unicode line separators inside canonical event strings remain data ^c20260728-16u

from __future__ import annotations

import json
from pathlib import Path

SESSION_MODEL_HEAD_ARTIFACT = "session.json"
SESSION_MODEL_TAPE_ARTIFACT = "events.jsonl"

_PROJECTION_ARTIFACTS = (
    ("messages", "messages.json"),
    ("model_runs", "model_runs.json"),
    ("tool_invocations", "tool_invocations.json"),
    ("usage", "usage.json"),
)

SESSION_MODEL_ARTIFACTS = (
    SESSION_MODEL_HEAD_ARTIFACT,
    SESSION_MODEL_TAPE_ARTIFACT,
    *(filename for _key, filename in _PROJECTION_ARTIFACTS),
)


def _json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def session_model_artifact_files(model: dict[str, object]) -> dict[str, bytes]:
    chat = model.get("chat")
    if not isinstance(chat, dict):
        raise ValueError("session model has no chat payload to split")

    head = {key: value for key, value in model.items() if key != "chat"}
    files: dict[str, bytes] = {SESSION_MODEL_HEAD_ARTIFACT: _json_bytes(head)}

    events = chat.get("events") or []
    files[SESSION_MODEL_TAPE_ARTIFACT] = "".join(
        json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in events
    ).encode("utf-8")

    for key, filename in _PROJECTION_ARTIFACTS:
        files[filename] = _json_bytes(chat.get(key) or [])
    return files


def write_session_model_artifact(model: dict[str, object], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for filename, content in session_model_artifact_files(model).items():
        (directory / filename).write_bytes(content)


def load_session_model_artifact(directory: Path) -> dict[str, object]:
    head = json.loads(
        (directory / SESSION_MODEL_HEAD_ARTIFACT).read_text(encoding="utf-8")
    )
    if not isinstance(head, dict):
        raise ValueError(f"invalid session model head artifact in {directory}")

    tape_path = directory / SESSION_MODEL_TAPE_ARTIFACT
    events = [
        json.loads(line)
        for line in tape_path.read_text(encoding="utf-8").split("\n")
        if line.strip()
    ]

    chat: dict[str, object] = {"events": events}
    for key, filename in _PROJECTION_ARTIFACTS:
        chat[key] = json.loads((directory / filename).read_text(encoding="utf-8"))

    model = dict(head)
    model["chat"] = {
        "messages": chat["messages"],
        "model_runs": chat["model_runs"],
        "tool_invocations": chat["tool_invocations"],
        "events": chat["events"],
        "usage": chat["usage"],
    }
    return model


__all__ = [
    "SESSION_MODEL_ARTIFACTS",
    "SESSION_MODEL_HEAD_ARTIFACT",
    "SESSION_MODEL_TAPE_ARTIFACT",
    "load_session_model_artifact",
    "session_model_artifact_files",
    "write_session_model_artifact",
]
