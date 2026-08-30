from __future__ import annotations

from pathlib import Path

import pytest

from tarav.testing import TaravTestEnvironment, write_project_marker
from tarav.cli.cli import build_parser, main
from _helpers import captured_json, write_text_file


def _create_skill(path: Path, *, description: str) -> None:
    write_text_file(
        path / "SKILL.md",
        f"---\nname: {path.name}\ndescription: {description}\n---\n\n# {path.name}\n",
    )


def _make_project(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    write_project_marker(path)


def _skills(argv: list[str]) -> list[str]:
    return ["project", *argv, "--project"]


def test_skills_list_and_path_use_selected_profile(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = TaravTestEnvironment.create(tmp_path / "home")
    environment.apply_environment(monkeypatch.setenv)
    workspace = tmp_path / "workspace"
    source_root = tmp_path / "source"
    _make_project(workspace)
    _create_skill(source_root / "alpha-skill", description="Alpha skill")
    environment.write_global_config(
        skills={
            "routing": {
                "sources": {"base": {"path": str(source_root)}},
                "profiles": {"default": {"sources": [{"name": "base"}]}},
            }
        }
    )
    monkeypatch.chdir(workspace)

    assert main(_skills(["skills", "list", "--json"])) == 0
    listed = captured_json(capsys)
    assert listed == [
        {
            "name": "base-alpha-skill",
            "description": "Alpha skill",
            "source": "base",
            "paths": [
                str(workspace / ".agents" / "skills" / "base-alpha-skill"),
                str(workspace / ".claude" / "skills" / "base-alpha-skill"),
            ],
        }
    ]

    assert main(_skills(["skills", "path", "base-alpha-skill"])) == 0
    assert capsys.readouterr().out.strip().splitlines() == [
        str(workspace / ".agents" / "skills" / "base-alpha-skill"),
        str(workspace / ".claude" / "skills" / "base-alpha-skill"),
    ]


def test_skills_import_and_status_materialize_default_depots(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = TaravTestEnvironment.create(tmp_path / "home")
    environment.apply_environment(monkeypatch.setenv)
    workspace = tmp_path / "workspace"
    source_skill = workspace / "skills" / "alpha-skill"
    _make_project(workspace)
    _create_skill(source_skill, description="Base alpha skill")
    environment.write_global_config(
        skills={
            "routing": {
                "sources": {"base": {"path": str(workspace / "skills")}},
                "profiles": {"default": {"sources": [{"name": "base"}]}},
            }
        }
    )
    monkeypatch.chdir(workspace)

    assert main(_skills(["skills", "import"])) == 0
    out = capsys.readouterr().out
    assert "Skills import complete" in out
    assert "- catalog: 1" in out

    agents_depot = workspace / ".agents" / "skills"
    claude_depot = workspace / ".claude" / "skills"
    assert agents_depot.is_symlink()
    assert claude_depot.is_symlink()
    assert (agents_depot / "base-alpha-skill").resolve() == source_skill.resolve()
    assert (claude_depot / "base-alpha-skill").resolve() == source_skill.resolve()

    assert main(_skills(["skills", "status", "--json"])) == 0
    status = captured_json(capsys)
    assert status["profile"] == "default"
    assert status["expected"] == 1
    assert [depot["depot"] for depot in status["depots"]] == [
        str(agents_depot),
        str(claude_depot),
    ]
    assert all(
        depot["missing"] == [] and depot["broken"] == [] and depot["conflicts"] == []
        for depot in status["depots"]
    )


def test_skills_project_source_and_config_errors(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = TaravTestEnvironment.create(tmp_path / "home")
    environment.apply_environment(monkeypatch.setenv)
    workspace = tmp_path / "workspace"
    source_project = tmp_path / "source-project"
    _make_project(workspace)
    source_project.mkdir()
    environment.write_global_config(
        skills={
            "routing": {
                "sources": {"project": {"project": str(source_project)}},
                "profiles": {"default": {"sources": [{"name": "project"}]}},
            }
        }
    )
    monkeypatch.chdir(workspace)

    assert main(_skills(["skills", "list"])) == 1
    error = capsys.readouterr().err
    assert "is not a tarav project" in error
    assert ".tarav/project.json" in error

    write_project_marker(source_project)
    _create_skill(
        source_project / "skills" / "alpha-skill", description="Project alpha"
    )
    assert main(_skills(["skills", "list", "--json"])) == 0
    listed = captured_json(capsys)
    assert listed[0]["name"] == "project-alpha-skill"


def test_skills_import_recursive_materializes_descendant_projects(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = TaravTestEnvironment.create(tmp_path / "home")
    environment.apply_environment(monkeypatch.setenv)
    workspace = tmp_path / "workspace"
    source_skill = tmp_path / "source" / "alpha-skill"
    _create_skill(source_skill, description="Base alpha skill")

    _make_project(workspace)
    nested = workspace / "team" / "nested"
    _make_project(nested)
    too_deep = workspace / "a" / "b" / "c" / "d" / "e" / "f"
    _make_project(too_deep)

    environment.write_global_config(
        skills={
            "routing": {
                "sources": {"base": {"path": str(tmp_path / "source")}},
                "profiles": {"default": {"sources": [{"name": "base"}]}},
            }
        }
    )
    monkeypatch.chdir(workspace)

    assert main(_skills(["skills", "import", "--recursive"])) == 0
    out = capsys.readouterr().out
    assert str(workspace) in out
    assert str(nested) in out
    assert "Recursive skills import: 2 project(s), 0 failed (depth 5)" in out
    # depth 5 excludes the project six levels below the root
    assert str(too_deep) not in out

    for project_root in (workspace, nested):
        assert (project_root / ".agents" / "skills" / "base-alpha-skill").resolve() == source_skill.resolve()
    assert not (too_deep / ".agents" / "skills").exists()


def test_skills_import_recursive_noops_on_non_project_root(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = TaravTestEnvironment.create(tmp_path / "home")
    environment.apply_environment(monkeypatch.setenv)
    source_skill = tmp_path / "source" / "alpha-skill"
    _create_skill(source_skill, description="Base alpha skill")

    # workspace is a plain directory, not a tarav project
    workspace = tmp_path / "workspace"
    child_a = workspace / "child-a"
    child_b = workspace / "team" / "child-b"
    _make_project(child_a)
    _make_project(child_b)

    environment.write_global_config(
        skills={
            "routing": {
                "sources": {"base": {"path": str(tmp_path / "source")}},
                "profiles": {"default": {"sources": [{"name": "base"}]}},
            }
        }
    )
    monkeypatch.chdir(workspace)

    assert main(_skills(["skills", "import", "--recursive"])) == 0
    out = capsys.readouterr().out
    assert "Recursive skills import: 2 project(s), 0 failed (depth 5)" in out
    for project_root in (child_a, child_b):
        assert (project_root / ".agents" / "skills" / "base-alpha-skill").resolve() == source_skill.resolve()


def test_skills_import_non_recursive_still_requires_project(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = TaravTestEnvironment.create(tmp_path / "home")
    environment.apply_environment(monkeypatch.setenv)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    assert main(_skills(["skills", "import"])) == 1
    assert "not inside a tarav project" in capsys.readouterr().err


def test_skills_import_recursive_depth_zero_targets_only_root(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = TaravTestEnvironment.create(tmp_path / "home")
    environment.apply_environment(monkeypatch.setenv)
    workspace = tmp_path / "workspace"
    source_skill = tmp_path / "source" / "alpha-skill"
    _create_skill(source_skill, description="Base alpha skill")

    _make_project(workspace)
    nested = workspace / "nested"
    _make_project(nested)

    environment.write_global_config(
        skills={
            "routing": {
                "sources": {"base": {"path": str(tmp_path / "source")}},
                "profiles": {"default": {"sources": [{"name": "base"}]}},
            }
        }
    )
    monkeypatch.chdir(workspace)

    assert main(_skills(["skills", "import", "--recursive", "--depth", "0"])) == 0
    out = capsys.readouterr().out
    assert "Recursive skills import: 1 project(s), 0 failed (depth 0)" in out
    assert not (nested / ".agents" / "skills").exists()


def test_skills_surface_only_exposes_supported_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = build_parser()
    assert parser.parse_args(["project", "skills", "status"]).skills_command == "status"

    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["project", "skills", "query"])
    assert excinfo.value.code == 2
    assert "invalid choice: 'query'" in capsys.readouterr().err




def _global_depot(capsys_out: str) -> Path:
    for line in capsys_out.splitlines():
        if line.startswith("- global depot: "):
            return Path(line.split(": ", 1)[1])
    raise AssertionError(f"no global depot in output:\n{capsys_out}")


def _import_env(tmp_path: Path, monkeypatch, *, skills: list[str]) -> Path:
    environment = TaravTestEnvironment.create(tmp_path / "home")
    environment.apply_environment(monkeypatch.setenv)
    workspace = tmp_path / "workspace"
    source_root = tmp_path / "source"
    _make_project(workspace)
    for name in skills:
        _create_skill(source_root / name, description=f"{name} description")
    environment.write_global_config(
        skills={
            "routing": {
                "sources": {"base": {"path": str(source_root)}},
                "profiles": {"default": {"sources": [{"name": "base"}]}},
            }
        }
    )
    monkeypatch.chdir(workspace)
    return workspace


def test_skills_import_rebuilds_the_depot_from_the_catalog(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The depot is derived, so an import restates it rather than patching it.

    A link nobody selected - left by an earlier catalog, or written by hand - is
    gone after the next import without any record of who put it there.
    """

    _import_env(tmp_path, monkeypatch, skills=["alpha-skill"])

    assert main(_skills(["skills", "import"])) == 0
    depot = _global_depot(capsys.readouterr().out)
    assert {entry.name for entry in depot.iterdir()} == {"base-alpha-skill"}

    (depot / "stowaway").symlink_to(tmp_path / "source" / "alpha-skill", target_is_directory=True)

    assert main(_skills(["skills", "import"])) == 0
    output = capsys.readouterr().out
    assert {entry.name for entry in depot.iterdir()} == {"base-alpha-skill"}
    global_section = output.split(f"Global depot: {depot}\n", 1)[1].split("\n\n", 1)[0]
    assert "- removed: 1" in global_section


def test_skills_import_reports_change_by_diffing_the_rebuild(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Rebuilding everything must not report everything as new.

    created/removed/matching are computed from the listing taken before the
    rebuild against the one written after, so a no-op import reports no change.
    """

    _import_env(tmp_path, monkeypatch, skills=["alpha-skill", "beta-skill"])

    assert main(_skills(["skills", "import"])) == 0
    capsys.readouterr()

    assert main(_skills(["skills", "import"])) == 0
    second = capsys.readouterr().out
    global_section = second.split("Global depot: ", 1)[1].split("\n\n", 1)[0]
    assert "- created: 0" in global_section
    assert "- removed: 0" in global_section
    assert "- matching: 2" in global_section


def test_skills_import_refuses_a_project_depot_it_did_not_generate(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Replaceability is structural now, with no ownership ledger behind it.

    A directory of nothing but symlinks is a depot from before the shared-depot
    shape existed and is replaced. Anything holding real content belongs to a
    person and is refused.
    """

    workspace = _import_env(tmp_path, monkeypatch, skills=["alpha-skill"])
    handmade = workspace / ".agents" / "skills"
    handmade.mkdir(parents=True)
    (handmade / "my-own-skill").mkdir()

    assert main(_skills(["skills", "import"])) == 1
    assert "cannot be replaced safely" in capsys.readouterr().err

    for child in handmade.iterdir():
        child.rmdir()
    (handmade / "generated").symlink_to(tmp_path / "source" / "alpha-skill", target_is_directory=True)

    assert main(_skills(["skills", "import"])) == 0
    capsys.readouterr()
    assert handmade.is_symlink()
