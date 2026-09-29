from __future__ import annotations

import json
from pathlib import Path

from tarav.l3.cli.cli import main
from tarav.l1.reading_club import ReadingClub, ReadingClubError


def _project(
    club: Path,
    slug: str,
    *,
    title: str,
    status: str = "active",
    tags: tuple[str, ...] = (),
) -> Path:
    root = club / "projects" / slug
    root.mkdir(parents=True)
    (root / "transcript.md").write_text("# Transcript\n", encoding="utf-8")
    (root / "notes.md").write_text("# Notes\n", encoding="utf-8")
    (root / "project.json").write_text(
        json.dumps(
            {
                "class": "Tarav.Reading.Project",
                "schema_version": 1,
                "slug": slug,
                "title": title,
                "status": status,
                "tags": list(tags),
                "transcript": "transcript.md",
                "notes": "notes.md",
                "source": f"md-library:{slug}",
            }
        ),
        encoding="utf-8",
    )
    return root


def test_club_lists_active_projects_and_can_include_inactive(tmp_path: Path) -> None:
    club_root = tmp_path / "reading-club"
    _project(club_root, "paper-one", title="Paper One", tags=("metabolism",))
    _project(club_root, "paper-two", title="Paper Two", status="finished")

    club = ReadingClub.open(club_root)

    assert [item.slug for item in club.projects()] == ["paper-one"]
    assert [item.slug for item in club.projects(include_inactive=True)] == [
        "paper-one",
        "paper-two",
    ]
    assert [item.slug for item in club.find("METABOLISM")] == ["paper-one"]


def test_project_rejects_paths_that_escape_its_workspace(tmp_path: Path) -> None:
    club_root = tmp_path / "reading-club"
    project = _project(club_root, "paper-one", title="Paper One")
    manifest = json.loads((project / "project.json").read_text(encoding="utf-8"))
    manifest["transcript"] = "../outside.md"
    (project / "project.json").write_text(json.dumps(manifest), encoding="utf-8")

    try:
        ReadingClub.open(club_root).project("paper-one")
    except ReadingClubError as exc:
        assert "must stay inside" in str(exc)
    else:
        raise AssertionError("unsafe transcript path was accepted")


def test_reading_club_cli_lists_finds_and_shows_projects(
    tmp_path: Path, capsys
) -> None:
    club_root = tmp_path / "reading-club"
    project = _project(
        club_root,
        "paper-one",
        title="Metabolic Coordination",
        tags=("phd", "metabolism"),
    )
    base = ["reading-club", "--root", str(club_root)]

    assert main([*base, "list"]) == 0
    assert "active\tpaper-one\tMetabolic Coordination" in capsys.readouterr().out

    assert main([*base, "find", "metabolism", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 1
    assert payload["projects"][0]["slug"] == "paper-one"

    assert main([*base, "show", "paper-one", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["projects"][0]["transcript"] == str(project / "transcript.md")
