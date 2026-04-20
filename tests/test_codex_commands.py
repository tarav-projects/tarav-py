from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from agentos.cli import main


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_global_config(path: Path, payload: dict[str, object]) -> None:
    _write(
        path,
        json.dumps(
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                **payload,
            }
        ),
    )


def _readlink(path: Path) -> Path:
    target = Path(os.readlink(path))
    if target.is_absolute():
        return target
    return (path.parent / target).resolve()


def test_codex_command_switches_auth_symlink_and_runs_codex_with_default_launcher(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    managed_auth = agentos_home / "accounts" / "codex" / "mm" / "auth.json"
    _write(managed_auth, '{"token":"mm"}\n')

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "ambient-codex-home"))

    observed: dict[str, object] = {}

    def fake_run(
        command: list[str],
        *,
        env: dict[str, str],
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        observed["check"] = check
        observed["codex_home"] = env["CODEX_HOME"]
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert main(["codex", "--account", "mm"]) == 0

    auth_path = home / ".codex" / "auth.json"
    assert auth_path.is_symlink()
    assert _readlink(auth_path) == managed_auth
    assert observed == {
        "command": [
            "/opt/homebrew/bin/codex",
            "--dangerously-bypass-approvals-and-sandbox",
        ],
        "check": False,
        "codex_home": str(home / ".codex"),
    }


def test_codex_command_passes_through_args_and_raw_home_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    codex_home = tmp_path / "raw-codex-home"
    managed_auth = agentos_home / "accounts" / "codex" / "mm" / "auth.json"
    _write(managed_auth, '{"token":"mm"}\n')

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    observed: dict[str, object] = {}

    def fake_run(
        command: list[str],
        *,
        env: dict[str, str],
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        observed["codex_home"] = env["CODEX_HOME"]
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert main(
        [
            "codex",
            "--account",
            "mm",
            "--home",
            str(codex_home),
            "--",
            "exec",
            "--model",
            "gpt-5.4",
            "hello",
        ]
    ) == 0

    assert observed["command"] == [
        "/opt/homebrew/bin/codex",
        "--dangerously-bypass-approvals-and-sandbox",
        "exec",
        "--model",
        "gpt-5.4",
        "hello",
    ]
    assert observed["codex_home"] == str(codex_home.resolve())
    assert _readlink(codex_home / "auth.json") == managed_auth


def test_codex_command_reads_codex_mux_global_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    configured_home = tmp_path / "configured-codex-home"
    accounts_root = tmp_path / "codex-accounts-store"
    managed_auth = accounts_root / "mm" / "auth.json"
    _write(managed_auth, '{"token":"mm"}\n')
    _write_global_config(
        agentos_home / "config.json",
        {
            "codex": {
                "mux": {
                    "default_home": str(configured_home),
                    "accounts_root": str(accounts_root),
                    "executable": "/usr/local/bin/custom-codex",
                    "base_args": ["--fast", "--unsafe"],
                }
            }
        },
    )

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    observed: dict[str, object] = {}

    def fake_run(
        command: list[str],
        *,
        env: dict[str, str],
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        observed["codex_home"] = env["CODEX_HOME"]
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert main(["codex", "--account", "mm", "--", "exec", "hello"]) == 0

    assert observed["command"] == [
        "/usr/local/bin/custom-codex",
        "--fast",
        "--unsafe",
        "exec",
        "hello",
    ]
    assert observed["codex_home"] == str(configured_home.resolve())
    assert _readlink(configured_home / "auth.json") == managed_auth


def test_codex_command_just_link_switches_auth_without_launching_codex(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    codex_home = tmp_path / "just-link-home"
    managed_auth = agentos_home / "accounts" / "codex" / "tk" / "auth.json"
    _write(managed_auth, '{"token":"tk"}\n')

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    def fail_run(
        command: list[str],
        *,
        env: dict[str, str],
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        raise AssertionError(f"subprocess.run should not be called: {command!r}")

    monkeypatch.setattr(subprocess, "run", fail_run)

    assert main(["codex", "--account", "tk", "--home", str(codex_home), "--just-link"]) == 0

    assert _readlink(codex_home / "auth.json") == managed_auth


def test_codex_command_just_link_dry_run_prints_link_only(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    managed_auth = agentos_home / "accounts" / "codex" / "tk" / "auth.json"
    _write(managed_auth, '{"token":"tk"}\n')

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    assert main(["codex", "--account", "tk", "--just-link", "--dry-run"]) == 0

    captured = capsys.readouterr()
    assert str(home / ".codex" / "auth.json") in captured.out
    assert str(managed_auth) in captured.out
    assert "/opt/homebrew/bin/codex" not in captured.out
    assert not (home / ".codex" / "auth.json").exists()


def test_codex_command_refuses_to_replace_non_symlink_auth_file(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    managed_auth = agentos_home / "accounts" / "codex" / "mm" / "auth.json"
    existing_auth = home / ".codex" / "auth.json"
    _write(managed_auth, '{"token":"mm"}\n')
    _write(existing_auth, '{"token":"existing"}\n')

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    assert main(["codex", "--account", "mm"]) == 1

    captured = capsys.readouterr()
    assert "refusing to replace non-symlink codex auth file" in captured.err
    assert existing_auth.read_text(encoding="utf-8") == '{"token":"existing"}\n'


def test_codex_command_just_link_requires_account(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    assert main(["codex", "--just-link"]) == 1

    captured = capsys.readouterr()
    assert "--just-link requires --account" in captured.err


def test_codex_command_just_link_rejects_forwarded_codex_args(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    managed_auth = agentos_home / "accounts" / "codex" / "tk" / "auth.json"
    _write(managed_auth, '{"token":"tk"}\n')

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    assert main(["codex", "--account", "tk", "--just-link", "--", "exec", "hello"]) == 1

    captured = capsys.readouterr()
    assert "--just-link does not accept forwarded Codex arguments" in captured.err


def test_codex_command_dry_run_prints_full_launch_command_without_mutating(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    managed_auth = agentos_home / "accounts" / "codex" / "mm" / "auth.json"
    _write(managed_auth, '{"token":"mm"}\n')

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    assert main(["codex", "--account", "mm", "--dry-run", "--", "exec", "hello"]) == 0

    captured = capsys.readouterr()
    assert str(home / ".codex" / "auth.json") in captured.out
    assert str(managed_auth) in captured.out
    assert (
        f"CODEX_HOME={home / '.codex'} /opt/homebrew/bin/codex --dangerously-bypass-approvals-and-sandbox exec hello"
        in captured.out
    )
    assert not (home / ".codex" / "auth.json").exists()


def test_codex_command_fails_when_managed_auth_is_missing(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    assert main(["codex", "--account", "missing"]) == 1

    captured = capsys.readouterr()
    assert "codex account auth file does not exist" in captured.err
