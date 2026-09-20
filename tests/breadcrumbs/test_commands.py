from __future__ import annotations

import json

from tarav.cli.cli import main


IDENTITY = "12345678" + "0" * 56
TURN_HASH = "d" * 64


class _Reader:
    def model_header(self):
        return {"session": {"identity_hash": IDENTITY}}

    def iter_turns(self):
        yield {
            "type": "Chat.Turn",
            "turn_address": "e" * 64,
            "turn_hash": TURN_HASH,
            "side": "user",
            "message_refs": [],
            "event_refs": [
                {"event_address": "a" * 64, "event_hash": "b" * 64}
            ],
        }

    def iter_messages(self):
        return iter(())

    def iter_events(self):
        yield {
            "type": "User.Event",
            "event_address": "a" * 64,
            "event_hash": "b" * 64,
            "started_at": "2026-09-20T00:00:00Z",
            "origin": "user",
            "observations": [
                {
                    "observed_at": "2026-09-20T00:00:00Z",
                    "source_ref": {
                        "source_id": "source-one",
                        "record_index": 1,
                        "line": 1,
                    },
                }
            ],
            "opaque_payload_hash": "c" * 64,
        }


def test_show_and_resolve_commands_report_one_breadcrumb(tmp_path, capsys):
    root = tmp_path / "breadcrumbs"
    surface = tmp_path / "note.md"
    breadcrumb_id = "c" * 64

    from tarav.breadcrumbs import BreadcrumbStore, breadcrumb_label

    store = BreadcrumbStore(root)
    store.create(breadcrumb_id)
    surface.write_text(f"<!-- {breadcrumb_label(breadcrumb_id)} -->\n")
    store.observe_position(breadcrumb_id, file=str(surface), line=1)

    assert main(
        ["breadcrumbs", "show", "--label", breadcrumb_id, "--breadcrumbs-root", str(root), "--json"]
    ) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["breadcrumb"]["id"] == breadcrumb_id

    assert main(
        ["breadcrumbs", "resolve", "--label", breadcrumb_id, "--breadcrumbs-root", str(root), "--json"]
    ) == 0
    resolved = json.loads(capsys.readouterr().out)
    assert resolved["position"] == {
        "file": str(surface),
        "line": 1,
        "text": f"<!-- {breadcrumb_label(breadcrumb_id)} -->",
    }


def test_submit_command_runs_chatlas_context_workflow(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(
        "tarav.breadcrumbs.surfaces.provide_normal_model_reader",
        lambda **_kwargs: _Reader(),
    )
    root = tmp_path / "breadcrumbs"
    surface = tmp_path / "note.md"
    surface.write_text(
        f"<!-- tarav.context {IDENTITY[:8]}:{TURN_HASH[:16]} -->\n",
        encoding="utf-8",
    )

    assert main(
        [
            "breadcrumbs",
            "submit",
            "--surface",
            str(surface),
            "--provider",
            "codex",
            "--session-id",
            "session",
            "--breadcrumbs-root",
            str(root),
            "--json",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["workflow"] == "Tarav.Breadcrumbs.ChatlasContext"
    assert len(payload["breadcrumbs"]) == 1
    assert "tarav.breadcrumb" in surface.read_text()
