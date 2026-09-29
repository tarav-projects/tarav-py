"""Session navigation and loading boundaries, using only disposable depots."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tarav.l0._core.errors import CliError
from tarav.l0.explorer_testing import check_collection
from tarav.l0.kernel import RecordTypeMismatch, TaravObject, entity
from tarav.l1.chatlas import normal_model_cache as cache
from tarav.l1.chatlas.index_store import session_index_shard_path
from tarav.l1.chatlas.normal_model import ChatlasNormalModel
from tarav.l1.chatlas.paths import SESSION_INDEX_ROOT
from tarav.l1.chatlas.session_identity import session_identity_hash
from tarav.l1.chatlas.session_resolver import ChatlasSessionAmbiguous
from tarav.l1.chatlas.sessions import ChatSession, ChatSessions
from tarav.l1.chatlas.workflow import ChatlasWorkflow
from tarav.l3.runtime import create_runtime


def _index(
    root: Path, *, provider="codex", instance="one", session_id="session", source=None
):
    row = {
        "provider": provider,
        "instance": instance,
        "session_id": session_id,
        "identity_hash": session_identity_hash(
            provider=provider, instance=instance, session_id=session_id
        ),
        "backing_artifacts": [{"role": "transcript", "path": str(source)}]
        if source
        else [],
    }
    path = session_index_shard_path(
        root / SESSION_INDEX_ROOT, provider=provider, identity_hash=row["identity_hash"]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row) + "\n")
    return row


def _snapshot(root: Path):
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_indexed_navigation_is_read_only_and_keys_round_trip(tmp_path, monkeypatch):
    from tarav.l1.chatlas import core

    def forbidden(*args, **kwargs):
        pytest.fail("Session navigation must not capture or normalize")

    monkeypatch.setattr(core, "chatlas_update", forbidden)
    monkeypatch.setattr(cache, "build_normal_model_from_row", forbidden)
    root = tmp_path / "depot"
    rows = [
        _index(root),
        _index(root, instance="two"),
        _index(root, provider="claude-code"),
        _index(root, session_id="a" * 64),
    ]
    before = _snapshot(root)
    sessions = ChatSessions(chatlas_root=root)
    with pytest.raises(ChatlasSessionAmbiguous):
        sessions.get("session")
    with pytest.raises(ChatlasSessionAmbiguous):
        sessions.ls()
    with pytest.raises(ChatlasSessionAmbiguous):
        ChatSessions(chatlas_root=root, provider="codex").get("session")

    scoped = ChatSessions(chatlas_root=root, provider="codex", instance="one")
    check_collection(scoped, ("session", "a" * 64))
    entry = scoped.get("session")
    assert entry.name == "session"
    assert "codex" in entry.description
    assert entry.open().identity_hash == rows[0]["identity_hash"]
    # Even a native ID that looks like a digest remains a native ID.
    assert scoped.get("a" * 64).open().session_id == "a" * 64

    identities = ChatSessions(chatlas_root=root, key_by="identity_hash")
    check_collection(identities, tuple(row["identity_hash"] for row in rows))
    for row in rows:
        loaded = sessions.get_by_identity(identity_hash=row["identity_hash"]).open()
        assert (loaded.provider, loaded.instance, loaded.session_id) == (
            row["provider"],
            row["instance"],
            row["session_id"],
        )
    with pytest.raises(KeyError):
        scoped.get_by_identity(identity_hash=rows[1]["identity_hash"])
    check_collection(ChatSessions(chatlas_root=tmp_path / "missing"), ())
    check_collection(
        ChatSessions(chatlas_root=tmp_path / "missing", key_by="identity_hash"), ()
    )
    assert _snapshot(root) == before
    assert not (tmp_path / "missing").exists()


def test_portable_record_dispatch_and_runtime_root_isolation(tmp_path, monkeypatch):
    import tarav.l1.chatlas.sessions as module

    default_root = tmp_path / "default"
    monkeypatch.setattr(module, "default_chatlas_root", lambda: default_root)
    original = ChatSession(
        provider="codex",
        instance="one",
        session_id="session",
        chatlas_root=tmp_path / "custom",
    )
    record = original.to_record()
    assert set(record) == {
        "type",
        "provider",
        "instance",
        "session_id",
        "identity_hash",
    }
    runtime = create_runtime()
    loaded = runtime.records.from_record(record)
    assert type(loaded) is ChatSession
    assert loaded.to_record() == record
    assert loaded.chatlas_root == default_root
    assert entity(ChatSession).workflow is ChatlasWorkflow()
    assert original.chatlas_root == tmp_path / "custom"

    # A default-depot match cannot satisfy an explicitly selected custom depot.
    _index(default_root)
    loaded.bind_root(tmp_path / "custom")
    with pytest.raises(KeyError):
        loaded.model()
    assert not loaded.chatlas_root.exists()
    assert not (default_root / "normal-model").exists()

    path = tmp_path / "session.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    assert type(runtime.load_object(path, expected_type=ChatSession)) is ChatSession
    with pytest.raises(RecordTypeMismatch):
        runtime.load_object(path, expected_type=TaravObject)
    for invalid in (
        {**record, "identity_hash": "f" * 64},
        {**record, "session_id": ""},
        {**record, "provider": 1},
        {key: value for key, value in record.items() if key != "instance"},
    ):
        with pytest.raises(ValidationError):
            ChatSession.from_record(invalid)
    with pytest.raises(ValidationError):
        ChatSession(
            provider="codex",
            instance="one",
            session_id="session",
            identity_hash="f" * 64,
        )


def test_session_model_uses_real_normalization_and_existing_cache(
    tmp_path, monkeypatch
):
    root = tmp_path / "depot"
    source = tmp_path / "retained.jsonl"
    records = [
        {
            "timestamp": "2026-09-28T00:00:00Z",
            "type": "session_meta",
            "payload": {"id": "session", "originator": "codex_cli_rs"},
        },
        {
            "timestamp": "2026-09-28T00:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "id": "user-1",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello tarav"}],
            },
        },
        {
            "timestamp": "2026-09-28T00:00:02Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "id": "assistant-1",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "hello"}],
            },
        },
    ]
    source.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )
    retained = source.read_bytes()
    row = _index(root, source=source)
    build = cache.build_normal_model_from_row
    builds = []

    def tracked(selected, **kwargs):
        builds.append(selected["identity_hash"])
        return build(selected, **kwargs)

    monkeypatch.setattr(cache, "build_normal_model_from_row", tracked)
    session = ChatSessions(chatlas_root=root, provider="codex").get("session").open()
    assert not builds
    reader = session.model()
    assert isinstance(reader, ChatlasNormalModel)
    assert reader.to_record()["session"]["identity_hash"] == session.identity_hash
    assert [message["text"] for message in reader.iter_messages()] == [
        "hello tarav",
        "hello",
    ]
    assert cache.normal_model_cache_status_from_row(row, chatlas_root=root) == "FRESH"
    assert session.model().to_record() == reader.to_record()
    assert builds == [session.identity_hash]
    session.model(refresh=True)
    assert builds == [session.identity_hash] * 2
    assert source.read_bytes() == retained


def test_session_availability_and_normalization_errors_remain_explicit(tmp_path):
    root = tmp_path / "depot"
    _index(root, provider="unsupported")
    session = ChatSessions(chatlas_root=root).get("session").open()
    with pytest.raises(CliError, match="supports only Codex and Claude Code"):
        session.model()
    _index(root, session_id="missing-source", source=tmp_path / "absent.jsonl")
    unavailable = ChatSessions(chatlas_root=root).get("missing-source").open()
    with pytest.raises(CliError, match="cannot fingerprint chat transcript source"):
        unavailable.model()
    assert not (root / "normal-model" / session.identity_hash).exists()
    assert not (root / "normal-model" / unavailable.identity_hash).exists()
