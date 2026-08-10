# $kw: ^test-workspaces-manifest --from Run.Workspace --note [DC] exactly one surface is required, an AGENTS.md declaring kind, purpose, provenance, status, and what was extracted --supp ^c20260809-88u ^<anchor-on-landing>
from __future__ import annotations

from pathlib import Path

import pytest

from agentos.workspaces.manifest import (
    ManifestError,
    Status,
    read_manifest,
    render_agents_md,
)
from agentos.workspaces.root import WORKSPACES_ENV_VAR, resolve_workspaces_root

FULL = """# 20260809-my-run

## Manifest

### manifest

- kind: improvement-loop
- created: 2026-08-09T12:00:00Z
- status: harvested
- extracted: merged into design/111-design.md
"""


def test_the_root_defaults_under_the_agentos_home(monkeypatch) -> None:
    monkeypatch.delenv(WORKSPACES_ENV_VAR, raising=False)
    assert resolve_workspaces_root(None).parts[-2:] == (".agentos", "workspaces")


def test_an_explicit_root_wins_over_the_environment(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv(WORKSPACES_ENV_VAR, str(tmp_path / "env"))
    assert resolve_workspaces_root(tmp_path / "explicit") == (
        tmp_path / "explicit"
    ).resolve()
    assert resolve_workspaces_root(None) == (tmp_path / "env").resolve()


def test_a_full_manifest_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text(FULL, encoding="utf-8")

    manifest = read_manifest(path)

    assert manifest.kind == "improvement-loop"
    assert manifest.status is Status.HARVESTED
    assert manifest.extracted == "merged into design/111-design.md"
    assert manifest.created == "2026-08-09T12:00:00Z"


def test_an_agents_md_without_a_manifest_section_reads_as_open(tmp_path: Path) -> None:
    """A hand-written workspace is still a workspace."""
    path = tmp_path / "AGENTS.md"
    path.write_text("# something a person wrote\n", encoding="utf-8")

    manifest = read_manifest(path)

    assert manifest.status is Status.OPEN
    assert manifest.extracted == "none"
    assert manifest.kind == "unknown"


def test_an_unknown_status_is_an_error_naming_the_file(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text("### manifest\n\n- status: sort-of-done\n", encoding="utf-8")

    with pytest.raises(ManifestError, match="AGENTS.md"):
        read_manifest(path)


def test_a_missing_agents_md_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ManifestError):
        read_manifest(tmp_path / "AGENTS.md")


def test_a_rendered_agents_md_reads_back(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text(
        render_agents_md(
            slug="20260809-my-run",
            kind="improvement-loop",
            purpose="does the registered type win",
            provenance="agentos-md@129580d design/111-design.md",
            created="2026-08-09T12:00:00Z",
        ),
        encoding="utf-8",
    )

    manifest = read_manifest(path)

    assert manifest.kind == "improvement-loop"
    assert manifest.status is Status.OPEN
    assert manifest.extracted == "none"
    # The prose an agent landing cold needs must survive the round trip too.
    text = path.read_text(encoding="utf-8")
    assert "does the registered type win" in text
    assert "agentos-md@129580d" in text
