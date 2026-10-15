"""Project skill discovery and bootstrap checks."""

import json
from pathlib import Path
from uuid import uuid4

from tarav.l1.project import TaravProject
from tarav.l1.project.skills import (
    AgentsSkillsFolderAbsent,
    ClaudeSkillsFolderAbsent,
    ClaudeSkillsFolderDiverges,
    ProjectPackageSkillMissing,
    ProjectPackageSkillUndeclared,
    ProjectSkills,
    SkillFoldersPOI,
    TaravPackageSkillPOI,
)
from tarav.l1.skills.folder import FolderSkill
from tarav.l3.runtime import create_runtime


def _project(root: Path, package_skill: str | None = "tarav-pkg") -> TaravProject:
    marker = root / ".tarav/project.json"
    marker.parent.mkdir(parents=True)
    agents = {} if package_skill is None else {"package_skill": package_skill}
    marker.write_text(json.dumps({"project_id": str(uuid4()),
                                  "created_at": "2026-10-15T00:00:00Z"}))
    (root / ".tarav/config.json").write_text(json.dumps({"agents": agents}))
    return TaravProject.from_path(root)


def _skill(place: Path, folder: str, name: str | None = None) -> Path:
    root = place / folder
    root.mkdir(parents=True)
    frontmatter = f"---\nname: {name}\n---\n" if name else "# No frontmatter\n"
    (root / "SKILL.md").write_text(frontmatter)
    return root


def _folders(root: Path) -> Path:
    agents = root / ".agents/skills"
    agents.mkdir(parents=True)
    claude = root / ".claude/skills"
    claude.parent.mkdir()
    claude.symlink_to(agents, target_is_directory=True)
    return agents


def _pois(skills: ProjectSkills):
    return tuple(skills.checks.run().pois())


# tarav.breadcrumb f95aa1c71f879b681944b1ab8e50a616be9c4390105dbc20badb2288fa18f84f

def test_folder_skill_identity_and_record_round_trip(tmp_path: Path) -> None:
    folder = _skill(tmp_path, "prefixed-tarav", "tarav-pkg")
    skill = FolderSkill(folder)
    assert skill.skill_name == "tarav-pkg"
    assert FolderSkill(_skill(tmp_path, "plain")).skill_name == "plain"
    loaded = create_runtime().records.from_record(skill.records.to_record())
    assert isinstance(loaded, FolderSkill) and loaded.root == folder


def test_project_and_home_discovery_and_required_skills(tmp_path: Path) -> None:
    project_root, home = tmp_path / "project", tmp_path / "home"
    local = _folders(project_root)
    global_skills = _folders(home)
    project = _project(project_root, "other-pkg")
    skills = ProjectSkills(project, home=home)
    assert skills.search_places == (local, global_skills)
    assert {type(p) for p in _pois(skills)} == {TaravPackageSkillPOI, ProjectPackageSkillMissing}

    tarav = _skill(global_skills, "prefixed-tarav", "tarav-pkg")
    other = _skill(local, "local-other", "other-pkg")
    (local / "empty").mkdir()
    assert [s.root for s in skills.find("tarav-pkg")] == [tarav]
    assert [s.root for s in skills.find("other-pkg")] == [other]
    assert len(skills.available()) == 2
    assert _pois(skills) == ()

    _skill(local, "another-tarav", "tarav-pkg")
    assert len(skills.find("tarav-pkg")) == 2
    assert _pois(skills) == ()


def test_undeclared_package_and_project_suite_composition(tmp_path: Path) -> None:
    root, home = tmp_path / "project", tmp_path / "home"
    local = _folders(root)
    _folders(home)
    _skill(local, "tarav-pkg")
    project = _project(root, None)
    skills = ProjectSkills(project, home=home)
    assert [type(p) for p in _pois(skills)] == [ProjectPackageSkillUndeclared]
    assert isinstance(project.agents.skills, ProjectSkills)
    assert any(isinstance(p, ProjectPackageSkillUndeclared)
               for p in project.checks.run().pois())


def test_folder_structure_accepts_shared_depot_and_reports_each_scope(tmp_path: Path) -> None:
    root, home, depot = tmp_path / "project", tmp_path / "home", tmp_path / "depot"
    depot.mkdir()
    for base in (root, home):
        (base / ".agents").mkdir(parents=True)
        (base / ".claude").mkdir()
        (base / ".agents/skills").symlink_to(depot, target_is_directory=True)
        (base / ".claude/skills").symlink_to(depot, target_is_directory=True)
    _skill(depot, "tarav-pkg")
    skills = ProjectSkills(_project(root), home=home)
    assert _pois(skills) == ()

    (root / ".claude/skills").unlink()
    cases = {(type(p), p.situation["scope"]) for p in _pois(skills) if isinstance(p, SkillFoldersPOI)}
    assert cases == {(ClaudeSkillsFolderAbsent, "project")}
    (root / ".claude/skills").mkdir()
    cases = {(type(p), p.situation["scope"]) for p in _pois(skills) if isinstance(p, SkillFoldersPOI)}
    assert cases == {(ClaudeSkillsFolderDiverges, "project")}

    (home / ".agents/skills").unlink()
    cases = {(type(p), p.situation["scope"]) for p in _pois(skills) if isinstance(p, SkillFoldersPOI)}
    assert cases == {(ClaudeSkillsFolderDiverges, "project"),
                     (AgentsSkillsFolderAbsent, "home")}
