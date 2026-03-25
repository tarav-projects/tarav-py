from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agentos.cli import main


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_global_config(path: Path, *, provider_instances: list[dict[str, object]]) -> None:
    _write(
        path,
        json.dumps(
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                "chat": {
                    "archive": {
                        "provider_instances": provider_instances,
                    }
                },
            }
        ),
    )


def _git_output(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def test_chat_archive_mirrors_default_codex_home_and_commits(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write(home / ".codex" / "sessions" / "2026" / "03" / "25" / "rollout.jsonl", '{"ok":true}\n')
    _write(home / ".codex" / "notes.md", "# notes\n")
    _write(home / ".codex" / "log" / "skip.txt", "skip\n")
    _write(home / ".codex" / "auth.json", '{"token":"secret"}\n')

    assert main(["chat", "archive", "--provider", "codex"]) == 0

    payload = json.loads(capsys.readouterr().out)
    archive_root = agentos_home / "chat-archive"
    destination_root = archive_root / "codex" / "default"

    assert payload["command"] == "chat archive"
    assert payload["committed"] is True
    assert payload["synced_instance_count"] == 1
    assert payload["skipped_instance_count"] == 0
    assert payload["instances"][0]["instance"] == "default"
    assert payload["instances"][0]["synced"] is True
    assert (destination_root / "sessions" / "2026" / "03" / "25" / "rollout.jsonl").exists()
    assert (destination_root / "notes.md").exists()
    assert not (destination_root / "log" / "skip.txt").exists()
    assert not (destination_root / "auth.json").exists()

    log_subject = _git_output(archive_root, "log", "-1", "--pretty=%s")
    assert log_subject.startswith("checkpoint: ")


def test_chat_archive_second_run_skips_commit_when_unchanged(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write(home / ".codex" / "sessions" / "2026" / "03" / "25" / "rollout.jsonl", '{"ok":true}\n')

    assert main(["chat", "archive", "--provider", "codex"]) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chat", "archive", "--provider", "codex"]) == 0
    payload = json.loads(capsys.readouterr().out)

    archive_root = agentos_home / "chat-archive"
    assert payload["committed"] is False
    assert payload["commit_message"] is None
    assert _git_output(archive_root, "rev-list", "--count", "HEAD") == "1"


def test_chat_archive_uses_configured_extra_codex_instance(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    extra_codex_home = tmp_path / "codex-jp"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write(home / ".codex" / "sessions" / "2026" / "03" / "25" / "rollout.jsonl", '{"id":"default"}\n')
    _write(extra_codex_home / "sessions" / "2026" / "03" / "26" / "rollout.jsonl", '{"id":"jp"}\n')
    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "instance": "jp",
                "home": str(extra_codex_home),
            }
        ],
    )

    assert main(["chat", "archive", "--provider", "codex"]) == 0
    payload = json.loads(capsys.readouterr().out)

    archive_root = agentos_home / "chat-archive"
    instance_names = [instance["instance"] for instance in payload["instances"]]

    assert payload["instance_count"] == 2
    assert payload["synced_instance_count"] == 2
    assert instance_names == ["default", "jp"]
    assert (archive_root / "codex" / "default" / "sessions" / "2026" / "03" / "25" / "rollout.jsonl").exists()
    assert (archive_root / "codex" / "jp" / "sessions" / "2026" / "03" / "26" / "rollout.jsonl").exists()


def test_chat_archive_openclaw_allowlist_and_excludes(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    openclaw_home = home / ".openclaw"
    _write(openclaw_home / "agents" / "alpha" / "sessions" / "s1.jsonl", '{"session":"ok"}\n')
    _write(openclaw_home / "agents" / "alpha" / "agent" / "profile.md", "# profile\n")
    _write(openclaw_home / "agents" / "alpha" / "agent" / "auth.json", '{"secret":true}\n')
    _write(openclaw_home / "agents" / "alpha" / "agent" / "private.txt", "private\n")
    _write(openclaw_home / "workspace" / "SOUL.md", "# soul\n")
    _write(openclaw_home / "workspace" / "random.txt", "random\n")
    _write(openclaw_home / "cron" / "jobs.json", '{"jobs":[]}\n')

    assert main(["chat", "archive", "--provider", "openclaw"]) == 0
    payload = json.loads(capsys.readouterr().out)

    destination_root = agentos_home / "chat-archive" / "openclaw" / "default"
    assert payload["instances"][0]["synced"] is True
    assert (destination_root / "agents" / "alpha" / "sessions" / "s1.jsonl").exists()
    assert (destination_root / "agents" / "alpha" / "agent" / "profile.md").exists()
    assert (destination_root / "workspace" / "SOUL.md").exists()
    assert (destination_root / "cron" / "jobs.json").exists()
    assert not (destination_root / "agents" / "alpha" / "agent" / "auth.json").exists()
    assert not (destination_root / "agents" / "alpha" / "agent" / "private.txt").exists()
    assert not (destination_root / "workspace" / "random.txt").exists()


def test_chat_archive_skips_missing_sources_without_creating_repo(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    assert main(["chat", "archive", "--provider", "agents"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["committed"] is False
    assert payload["synced_instance_count"] == 0
    assert payload["skipped_instance_count"] == 1
    assert payload["instances"][0]["synced"] is False
    assert payload["instances"][0]["missing_home_keys"] == ["home"]
    assert not (agentos_home / "chat-archive").exists()
