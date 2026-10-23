from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from chatlas._helpers import normal_model_fixture
from tarav.l1.chatlas.normal_model import ChatlasNormalModel
from tarav.l2.chatlas_typesense import TypesenseConfig, TypesenseError, TypesenseIndex
from tarav.l3.runtime import create_runtime


IDENTITY = "a" * 64


@pytest.fixture
def depot(tmp_path, engine):
    create_runtime(archive_root=tmp_path / "archive")
    root = tmp_path / "normal-model"
    fixture = normal_model_fixture(tmp_path / "ABSENT-raw.jsonl", identity_hash=IDENTITY,
                                   turns=(("user", "Where is the cache?"), ("agent", "Inside normal-model.")))
    model = ChatlasNormalModel.materialize(root / IDENTITY, fixture)
    config = TypesenseConfig(normal_model_root=root, api_key=engine["key"], url=engine["url"])
    return config, model, fixture


def cli(tmp_path, config, *arguments):
    path = tmp_path / "config.json"
    key = tmp_path / "api-key"
    key.write_text(config.api_key)
    path.write_text(json.dumps({"url": config.url, "api_key_file": str(key),
                               "normal_model_root": str(config.normal_model_root)}))
    env = {**os.environ, "TARAV_HOME": str(tmp_path / "home"), "TARAV_CLI_NO_ROUTE": "1"}
    env.pop("TARAV_TYPESENSE_API_KEY", None)
    env.pop("TARAV_TYPESENSE_API_KEY_FILE", None)
    return subprocess.run([str(Path(sys.executable).with_name("tarav")), "chatlas", "typesense",
                           *arguments, "--config", str(path), "--json"],
                          capture_output=True, text=True, env=env, timeout=20)


# tarav.context 0d8af26c:b37c76d4f28cb300
def test_cli_sync_search_and_exact_sources_with_no_raw_or_session_index(tmp_path, depot, engine):
    config, model, fixture = depot
    assert not (tmp_path / "ABSENT-raw.jsonl").exists()
    before = {f.name: sha256(f.read_bytes()).hexdigest() for f in model.directory.iterdir()}
    result = cli(tmp_path, config, "sync")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"indexed_sessions": 1, "unchanged_sessions": 0,
                                       "indexed_documents": 2, "errors": []}
    result = cli(tmp_path, config, "search", "cache", "--side", "user", "--provider", "codex",
                 "--since", "2026-10-18", "--limit", "5")
    assert result.returncode == 0, result.stderr
    hit = json.loads(result.stdout)["hits"][0]
    assert hit["text"] == "Where is the cache?"
    assert hit["source"]["message_ref"] == {
        k: fixture["messages"][0][k] for k in ("message_address", "message_hash")}
    assert hit["source"]["turn_refs"] == [{
        k: fixture["turns"][0][k] for k in ("turn_address", "turn_hash")}]
    assert engine["searches"][-1]["filter_by"] == ["side:=user && provider:=codex && started_at:>=1792281600"]
    assert engine["searches"][-1]["query_by"] == ["text,embedding"]
    assert config.api_key not in result.stdout + result.stderr
    assert before == {f.name: sha256(f.read_bytes()).hexdigest() for f in model.directory.iterdir()}


def test_status_does_not_create_a_collection_or_checkpoint(tmp_path, depot, engine):
    config, _, _ = depot
    result = cli(tmp_path, config, "status")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["collection_exists"] is False
    assert engine["schema"] is None and engine["imports"] == []
    assert not (tmp_path / "home/cache/chatlas-typesense").exists()


def test_sync_skips_unchanged_and_reimports_a_recreated_collection(tmp_path, depot, engine):
    config, _, _ = depot
    index = TypesenseIndex(config, state_path=tmp_path / "state.json")
    assert index.sync()["indexed_sessions"] == 1
    assert index.sync()["unchanged_sessions"] == 1
    assert len(engine["imports"]) == 1
    engine["schema"] = None
    engine["documents"].clear()
    assert index.sync()["indexed_documents"] == 2
    assert len(engine["imports"]) == 2


def test_failed_import_does_not_delete_or_checkpoint_and_can_resume(tmp_path, depot, engine):
    config, _, _ = depot
    state = tmp_path / "state.json"
    index = TypesenseIndex(config, state_path=state)
    engine["reject"] = True
    result = index.sync()
    assert result["indexed_sessions"] == 0
    assert "bulk import incomplete" in result["errors"][0]["error"]
    assert not state.exists() and engine["deletes"] == []
    engine["reject"] = False
    assert index.sync()["indexed_sessions"] == 1
    assert state.exists() and len(engine["deletes"]) == 1


def test_updated_messages_replace_old_versions_and_shrunk_chunks(tmp_path, depot, engine):
    config, model, fixture = depot
    config = replace(config, chunk_chars=12, chunk_overlap=2)
    index = TypesenseIndex(config, state_path=tmp_path / "state.json")
    assert index.sync()["indexed_documents"] == 4
    for path in model.directory.iterdir():
        path.unlink()
    model.directory.rmdir()
    fixture = normal_model_fixture(tmp_path / "missing", identity_hash=IDENTITY,
                                   turns=(("user", "short"),))
    ChatlasNormalModel.materialize(config.normal_model_root / IDENTITY, fixture)
    assert index.sync()["indexed_documents"] == 1
    assert [doc["text"] for doc in engine["documents"].values()] == ["short"]


def test_every_chunk_keeps_exact_offsets_and_model_references(tmp_path, depot, engine):
    config, _, fixture = depot
    config = replace(config, chunk_chars=10, chunk_overlap=2)
    assert TypesenseIndex(config, state_path=tmp_path / "state.json").sync()["indexed_documents"] == 6
    source_text = {m["message_hash"]: m["text"] for m in fixture["messages"]}
    for doc in engine["documents"].values():
        source = doc["source"]
        text = source_text[source["message_ref"]["message_hash"]]
        assert doc["text"] == text[source["text_start"]:source["text_end"]]
        assert len(doc["text"]) <= 10


@pytest.mark.parametrize("broken", ["main.json", "messages.jsonl", "events.jsonl", "turns.jsonl"])
def test_invalid_model_is_reported_without_import_or_fallback(tmp_path, depot, engine, broken):
    config, model, _ = depot
    (model.directory / broken).write_text("{broken")
    result = cli(tmp_path, config, "sync")
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["indexed_documents"] == 0 and len(report["errors"]) == 1
    assert engine["imports"] == [] and engine["deletes"] == []
    assert not (tmp_path / "ABSENT-raw.jsonl").exists()


def test_empty_depot_fails_without_creating_collection(tmp_path, depot, engine):
    config, _, _ = depot
    config = replace(config, normal_model_root=tmp_path / "missing-models")
    result = cli(tmp_path, config, "sync")
    assert result.returncode == 1 and "no stored Normal Models" in result.stderr
    assert "Traceback" not in result.stderr and engine["schema"] is None


def test_incompatible_existing_collection_is_not_modified(tmp_path, depot, engine):
    config, _, _ = depot
    engine["schema"] = {"name": config.collection, "fields": [], "metadata": {}}
    with pytest.raises(TypesenseError, match="incompatible"):
        TypesenseIndex(config).sync()
    assert engine["imports"] == [] and engine["deletes"] == []


def test_invalid_filter_and_limit_are_rejected_before_http(tmp_path, depot, engine):
    config, _, _ = depot
    index = TypesenseIndex(config)
    for arguments in ({"limit": 0}, {"side": "user || true"}, {"since": "not-a-date"}):
        with pytest.raises(TypesenseError):
            index.search("cache", **arguments)
    assert engine["searches"] == []


def test_endpoint_errors_never_reveal_the_key(tmp_path, depot):
    config, _, _ = depot
    result = cli(tmp_path, replace(config, api_key="incorrect-secret"), "status")
    assert result.returncode == 1 and "HTTP 401" in result.stderr
    assert "incorrect-secret" not in result.stderr and "Traceback" not in result.stderr


def test_commands_import_no_ssh_or_host_specific_behavior():
    root = Path(__file__).resolve().parents[2] / "src/tarav/l2/chatlas_typesense"
    for source in root.glob("*.py"):
        text = source.read_text().lower()
        assert "studio-pereiro" not in text and "subprocess" not in text
