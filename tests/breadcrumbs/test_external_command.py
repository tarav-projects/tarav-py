"""Real Chatlas-backed external submission, audit and maintainer relocation."""
# tarav.breadcrumb fb0b537de270

import json

import pytest

from tarav.l1.breadcrumbs import BreadcrumbStore
from tarav.l1.chatlas.index_writer import _upsert_session_index_rows
from tarav.l1.chatlas.normal_model import build_normal_model_from_row
from tarav.l1.chatlas.paths import SESSION_INDEX_ROOT
from tarav.l3.cli.cli import main


@pytest.fixture
def chat(tmp_path):
    root = tmp_path / "chatlas"
    root.mkdir()
    raw = root / "raw.jsonl"
    records = [
        {"timestamp": "2026-10-22T00:00:00Z", "type": "session_meta", "payload": {"id": "external-test"}},
        {"timestamp": "2026-10-22T00:00:01Z", "type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "Annotate without changing JSON."}]}},
        {"timestamp": "2026-10-22T00:00:02Z", "type": "response_item",
         "payload": {"type": "message", "role": "assistant",
                     "content": [{"type": "output_text", "text": "I will retain an external anchor."}]}},
    ]
    raw.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    row = {"provider": "codex", "instance": "work", "provider_instance_fingerprint": "f" * 64,
           "session_id": "external-test", "identity_hash": "a" * 64, "uri": "tarav://external-test",
           "last_activity_at": "2026-10-22T00:00:02Z",
           "backing_artifacts": [{"role": "transcript", "path": str(raw)}]}
    _upsert_session_index_rows(root / SESSION_INDEX_ROOT, rows=[row])
    model = build_normal_model_from_row(row)
    prefixes = {t["side"]: t["turn_hash"][:16] for t in model["turns"] if t["message_refs"]}
    return root, prefixes


def submit(path, store, chat, *, side="user"):
    root, prefixes = chat
    return main(["breadcrumbs", "submit", "chatlas-context", "--surface", str(path),
                 "--placement", "external", "--line", "2", "--fragment", '"name": "value"',
                 "--provider", "codex", "--session-id", "external-test",
                 "--turn-hash-prefix", prefixes[side], "--chatlas-root", str(root),
                 "--breadcrumbs-root", str(store.root), "--json"])


@pytest.mark.parametrize("suffix", [".json", ".txt", ".custom"])
def test_external_submission_audit_move_and_relocation(tmp_path, chat, capsys, suffix):
    path = tmp_path / ("source" + suffix)
    original = '{\n  "name": "value"\n}\n'
    path.write_text(original)
    modified_at = path.stat().st_mtime_ns
    store = BreadcrumbStore(tmp_path / "registry")
    assert submit(path, store, chat) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["placement"] == "external"
    identity = report["breadcrumbs"][0]["id"]
    assert path.read_bytes() == original.encode()
    assert path.stat().st_mtime_ns == modified_at
    [attachment] = store.attachments(identity)
    assert attachment["context"]["locator"]["session_identity"] == "a" * 64
    path.write_text("\n" + original)
    assert main(["breadcrumbs", "audit", "chatlas-context", "--surface", str(path),
                 "--chatlas-root", str(chat[0]), "--breadcrumbs-root", str(store.root),
                 "--refresh-positions", "--json"]) == 0
    audit = json.loads(capsys.readouterr().out)
    assert audit["breadcrumbs"][0]["placement"] == "external"
    assert audit["breadcrumbs"][0]["position"]["line"] == 3
    assert len(store.observations(identity)) == 2
    assert path.read_bytes() == ("\n" + original).encode()

    replacement = tmp_path / "replacement.json"
    replacement.write_text('{"replacement": true}\n')
    assert main(["breadcrumbs", "relocate", "--label", identity, "--surface", str(replacement),
                 "--line", "1", "--fragment", '"replacement"',
                 "--breadcrumbs-root", str(store.root), "--json"]) == 0
    capsys.readouterr()
    assert store.resolve(identity).position.path == replacement
    assert len(store.observations(identity)) == 3
    assert store.attachments(identity) == (attachment,)


def test_external_audit_reports_missing_anchor_without_implying_label_deletion(tmp_path, chat, capsys):
    path = tmp_path / "source.json"
    path.write_text('{\n  "name": "value"\n}\n')
    store = BreadcrumbStore(tmp_path / "registry")
    assert submit(path, store, chat) == 0
    identity = json.loads(capsys.readouterr().out)["breadcrumbs"][0]["id"]
    path.write_text('{"changed": true}\n')
    assert main(["breadcrumbs", "audit", "chatlas-context", "--surface", str(path),
                 "--chatlas-root", str(chat[0]), "--breadcrumbs-root", str(store.root), "--json"]) == 1
    audit = json.loads(capsys.readouterr().out)
    assert [p["type"] for p in audit["pois"]] == ["Tarav.Breadcrumbs.Audit.POI.ExternalAnchorMissing"]
    assert len(store.attachments(identity)) == 1
    assert len(store.observations(identity)) == 1


def test_external_chatlas_context_rejects_an_agent_turn_before_registering(tmp_path, chat, capsys):
    path = tmp_path / "source.json"
    path.write_text('{\n  "name": "value"\n}\n')
    store = BreadcrumbStore(tmp_path / "registry")
    assert submit(path, store, chat, side="agent") != 0
    assert "User Turn" in capsys.readouterr().err
    assert not store.root.exists()
