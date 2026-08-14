# $kw: ^test-workspaces-commands --from Run.Workspace --from Poi.Unlock.Token --note [DC] creating a workspace is gated on an unlock receipt, so one is never initialized blind --supp ^c20260809-92u ^<anchor-on-landing>
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from tarav._core.errors import CliError
from tarav.workspaces import guide_token
from tarav.workspaces.commands import register_workspace_commands


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    register_workspace_commands(parser.add_subparsers(dest="command"))
    return parser


def _run(argv: list[str]) -> str:
    args = _parser().parse_args(argv)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        args.handler(args)
    return buffer.getvalue()


def _init(root: Path, slug: str = "my-run", **extra: str) -> str:
    argv = [
        "workspace", "init", "--root", str(root), "--slug", slug,
        "--kind", "improvement-loop", "--unlock", guide_token(),
    ]
    for key, value in extra.items():
        argv += [f"--{key}", value]
    return _run(argv)


def test_guide_prints_the_surface_with_its_token_last() -> None:
    output = _run(["workspace", "guide"])
    lines = [line for line in output.splitlines() if line.strip()]
    assert guide_token() in lines[-1]


def test_init_without_a_receipt_refuses(tmp_path: Path) -> None:
    with pytest.raises(CliError) as caught:
        _run(["workspace", "init", "--root", str(tmp_path), "--slug", "x",
              "--kind", "k"])
    # Refusal identifies the surface without disclosing its token.
    assert "workspace guide" in str(caught.value)
    assert guide_token() not in str(caught.value)


def test_init_with_a_stale_receipt_refuses_without_disclosing_the_token(
    tmp_path: Path,
) -> None:
    with pytest.raises(CliError) as caught:
        _run(["workspace", "init", "--root", str(tmp_path), "--slug", "x",
              "--kind", "k", "--unlock", "aws-unlock:deadbeef0000"])
    assert guide_token() not in str(caught.value)


def test_init_with_the_receipt_creates_a_workspace(tmp_path: Path) -> None:
    payload = json.loads(_init(tmp_path, purpose="does typing carry signal"))
    created = Path(payload["path"])

    assert created.parent == tmp_path
    assert created.name.endswith("-my-run")
    assert (created / "AGENTS.md").is_file()
    assert (created / ".git").is_dir()
    assert "does typing carry signal" in (created / "AGENTS.md").read_text()


def test_the_new_workspace_has_one_commit(tmp_path: Path) -> None:
    created = Path(json.loads(_init(tmp_path))["path"])
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=created, capture_output=True, text=True
    )
    assert log.returncode == 0
    assert len(log.stdout.strip().splitlines()) == 1


def test_a_duplicate_slug_on_the_same_date_refuses(tmp_path: Path) -> None:
    _init(tmp_path)
    with pytest.raises(CliError, match="already exists"):
        _init(tmp_path)


def test_init_refuses_inside_a_git_worktree(tmp_path: Path) -> None:
    """Git inside a workspace, never around one."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    with pytest.raises(CliError, match="git"):
        _init(tmp_path / "workspaces")


# $kw: ^test-workspaces-read --from Run.Workspace --note [PR] status and extracted are what make sweeping possible --supp ^c20260809-89u ^<anchor-on-landing>


def test_list_on_an_empty_root_reports_nothing_rather_than_failing(
    tmp_path: Path,
) -> None:
    payload = json.loads(_run(["workspace", "list", "--root", str(tmp_path), "--json"]))
    assert payload["workspaces"] == []


def test_list_reports_each_workspace_with_its_disposal_state(tmp_path: Path) -> None:
    _init(tmp_path, "first", purpose="one")
    _init(tmp_path, "second", purpose="two")

    payload = json.loads(_run(["workspace", "list", "--root", str(tmp_path), "--json"]))

    slugs = {row["slug"] for row in payload["workspaces"]}
    assert len(slugs) == 2
    row = payload["workspaces"][0]
    assert row["status"] == "open"
    assert row["extracted"] == "none"
    assert row["kind"] == "improvement-loop"
    assert isinstance(row["age_days"], int)


def test_an_unreadable_workspace_is_listed_as_unreadable_not_hidden(
    tmp_path: Path,
) -> None:
    """Silence is the one thing a disposal listing must never do."""
    created = Path(json.loads(_init(tmp_path))["path"])
    (created / "AGENTS.md").write_text("### manifest\n\n- status: nonsense\n")

    payload = json.loads(_run(["workspace", "list", "--root", str(tmp_path), "--json"]))

    assert len(payload["workspaces"]) == 1
    assert payload["workspaces"][0]["status"] == "unreadable"


def test_a_directory_without_an_agents_md_is_listed_as_unreadable(
    tmp_path: Path,
) -> None:
    (tmp_path / "20260809-hand-made").mkdir(parents=True)
    payload = json.loads(_run(["workspace", "list", "--root", str(tmp_path), "--json"]))
    assert payload["workspaces"][0]["status"] == "unreadable"


def test_show_prints_one_workspace_and_its_top_level_files(tmp_path: Path) -> None:
    created = Path(json.loads(_init(tmp_path, purpose="a stated purpose"))["path"])
    (created / "run.py").write_text("print('hi')\n")

    payload = json.loads(
        _run(["workspace", "show", "--root", str(tmp_path), "--slug", created.name,
              "--json"])
    )

    assert payload["slug"] == created.name
    assert payload["status"] == "open"
    assert "run.py" in payload["files"]
    assert "a stated purpose" in payload["agents_md"]


def test_show_on_an_unknown_slug_errors(tmp_path: Path) -> None:
    with pytest.raises(CliError, match="no workspace"):
        _run(["workspace", "show", "--root", str(tmp_path), "--slug", "nope", "--json"])


# $kw: ^test-workspaces-sweep --from Run.Workspace --from Volatile.Surface --note [PR] the one-way arrow is what makes deletion routine rather than a decision requiring an audit --supp ^c20260809-83u ^<anchor-on-landing>

def _age(path: Path, days: int) -> None:
    old = time.time() - days * 86400
    os.utime(path, (old, old))


def _set_status(path: Path, status: str) -> None:
    agents = path / "AGENTS.md"
    agents.write_text(
        agents.read_text().replace("- status: open", f"- status: {status}"),
        encoding="utf-8",
    )
    _age(path, 40)


def test_sweep_without_apply_deletes_nothing(tmp_path: Path) -> None:
    created = Path(json.loads(_init(tmp_path))["path"])
    _set_status(created, "harvested")

    payload = json.loads(_run(["workspace", "sweep", "--root", str(tmp_path), "--json"]))

    assert [row["slug"] for row in payload["candidates"]] == [created.name]
    assert payload["applied"] is False
    assert created.is_dir()


def test_sweep_names_why_each_candidate_qualified(tmp_path: Path) -> None:
    created = Path(json.loads(_init(tmp_path))["path"])
    _set_status(created, "abandoned")

    payload = json.loads(_run(["workspace", "sweep", "--root", str(tmp_path), "--json"]))

    assert "abandoned" in payload["candidates"][0]["reason"]


def test_sweep_apply_removes_exactly_the_listed_set(tmp_path: Path) -> None:
    stale = Path(json.loads(_init(tmp_path, "stale"))["path"])
    fresh = Path(json.loads(_init(tmp_path, "fresh"))["path"])
    _set_status(stale, "harvested")

    payload = json.loads(
        _run(["workspace", "sweep", "--root", str(tmp_path), "--apply", "--json"])
    )

    assert payload["applied"] is True
    assert [row["slug"] for row in payload["candidates"]] == [stale.name]
    assert not stale.exists()
    assert fresh.is_dir()


def test_a_recently_touched_open_workspace_is_never_a_candidate(
    tmp_path: Path,
) -> None:
    _init(tmp_path)
    payload = json.loads(_run(["workspace", "sweep", "--root", str(tmp_path), "--json"]))
    assert payload["candidates"] == []


def test_an_old_open_workspace_qualifies_on_the_longer_horizon(tmp_path: Path) -> None:
    created = Path(json.loads(_init(tmp_path))["path"])
    _age(created, 200)

    payload = json.loads(_run(["workspace", "sweep", "--root", str(tmp_path), "--json"]))

    assert [row["slug"] for row in payload["candidates"]] == [created.name]
    assert "idle" in payload["candidates"][0]["reason"]
