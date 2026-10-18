import json
from pathlib import Path

import pytest

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l0.testing import write_project_marker
from tarav.l1.skills import SKILLS_WORKFLOW_SHIP, SkillMarker, SkillsWorkflow, TaravSkill
from tarav.l2.skw.skills import SkwSkill, load_skill
from tarav.l3.runtime import create_runtime


# tarav.breadcrumb adc147a6df5a
class _GivenFolderSkill(TaravSkill):
    """A test-only kind of skill that is handed its folder."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("5f0d7c8e-2b1a-4c3d-9e8f-7a6b5c4d3e2f"),
                          name="Tarav.Tests.GivenFolderSkill", workflow=SKILLS_WORKFLOW_SHIP)

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root

    @property
    def root(self) -> Path:
        return self._root


def _folder(tmp_path: Path, name: str, frontmatter: str = "") -> Path:
    path = tmp_path / name
    path.mkdir()
    (path / "SKILL.md").write_text(f"---\n{frontmatter}---\n\n# {name}\n", encoding="utf-8")
    return path


def test_a_skill_reads_what_its_folder_holds(tmp_path: Path) -> None:
    path = _folder(tmp_path, "folder-name", "name: tarav-pkg\ndescription: The root.\n")
    skill = _GivenFolderSkill(path)
    assert skill.entrypoint == path / "SKILL.md"
    assert (skill.skill_name, skill.description) == ("tarav-pkg", "The root.")
    plain = _GivenFolderSkill(_folder(tmp_path, "plain"))
    assert (plain.skill_name, plain.description) == ("plain", None)


def test_the_base_skill_is_abstract_and_skw_skills_are_skills() -> None:
    assert issubclass(SkwSkill, TaravSkill)
    assert entity(TaravSkill).workflow_ship == SkillsWorkflow().id
    with pytest.raises(NotImplementedError):
        TaravSkill.root.fget(_GivenFolderSkill(Path(".")))


def test_a_skill_built_in_code_and_one_loaded_from_disk_agree(tmp_path: Path) -> None:
    # tarav.breadcrumb 5529d6d81711
    write_project_marker(tmp_path)
    root = _folder(tmp_path, "made", "name: made\n")
    depot = tmp_path / ".tarav/skillware/skills/made"
    made = SkwSkill(skill_id=str(SkillMarker.create(root).id), product="made",
                    entrypoint="SKILL.md", depot=depot)
    depot.mkdir(parents=True)
    (depot / "main.json").write_text(json.dumps(made.records.to_record()), encoding="utf-8")

    # the folder is found through the Project above it, whose depot builds it
    loaded = load_skill(root, registry=create_runtime().records)

    assert loaded.records.to_record() == made.records.to_record()
    assert (loaded.root, loaded.entrypoint) == (made.root, made.entrypoint)
    assert loaded.skill_name == made.skill_name == "made"
    assert not hasattr(loaded, "_record")


def test_a_skill_not_yet_placed_has_state_but_no_root() -> None:
    skill = SkwSkill(skill_id="6f1c2d3e-4b5a-4c6d-8e7f-901a2b3c4d5e", product="skills/notes",
                     files=["SKILL.md", "notes.md"])
    assert skill.records.to_record()["files"] == ["SKILL.md", "notes.md"]
    with pytest.raises(ValueError, match="no retained source"):
        skill.root


def test_a_skill_keeps_its_uuid_in_its_marker(tmp_path):
    from uuid import UUID

    from tarav.l1.skills import SkillMarker
    from tarav.l1.skills.folder import FolderSkill

    made = SkillMarker.create(tmp_path)
    written = json.loads((tmp_path / ".tarav/skill.json").read_text())
    assert written == {"type": "Tarav.Skills.Marker", "skill_id": str(made.id),
                       "created_at": made.created_at}
    UUID(written["skill_id"])
    assert FolderSkill(tmp_path).skill_id == made.id
    # a copy is the same skill; a second marker would be another one
    with pytest.raises(FileExistsError):
        SkillMarker.create(tmp_path)
    assert SkillMarker.of(tmp_path).id == made.id


def _placed(tmp_path: Path) -> Path:
    """A Project with one skill folder and the depot that builds it."""
    write_project_marker(tmp_path)
    (tmp_path / "skills").mkdir(parents=True)
    root = _folder(tmp_path / "skills", "made", "name: made\n")
    depot = tmp_path / ".tarav/skillware/skills/made"
    made = SkwSkill(skill_id=str(SkillMarker.create(root).id), product="skills/made",
                    entrypoint="SKILL.md", depot=depot)
    depot.mkdir(parents=True)
    (depot / "main.json").write_text(json.dumps(made.records.to_record()), encoding="utf-8")
    return root


def test_a_skill_belongs_to_the_project_above_it(tmp_path: Path) -> None:
    alone = _folder(tmp_path, "alone")
    with pytest.raises(ValueError, match="A skill belongs to a Project"):
        load_skill(alone, registry=create_runtime().records)
    root = _placed(tmp_path / "project")
    other = _folder(tmp_path / "project" / "skills", "unbuilt")  # no depot builds it
    with pytest.raises(ValueError, match="No depot .* builds skills/unbuilt"):
        load_skill(other, registry=create_runtime().records)
    assert load_skill(root, registry=create_runtime().records).project == tmp_path / "project"


def test_the_depot_and_the_folder_must_name_the_same_skill(tmp_path: Path) -> None:
    from tarav.l1.skw.pois import SkillMarkerMismatch, SkillMarkerMissing

    root = _placed(tmp_path)
    skill = load_skill(root, registry=create_runtime().records)
    assert not [p for p in skill.check() if isinstance(p, (SkillMarkerMismatch, SkillMarkerMissing))]
    (root / ".tarav/skill.json").unlink()
    SkillMarker.create(root)
    (mismatch,) = [p for p in skill.check() if isinstance(p, SkillMarkerMismatch)]
    assert mismatch.situation["subject"]["skill"] == str(skill.skill_id)
    (root / ".tarav/skill.json").unlink()
    assert [type(p) for p in skill.check() if isinstance(p, SkillMarkerMissing)] == [SkillMarkerMissing]


def test_a_deployed_copy_carries_the_skill_marker(tmp_path: Path) -> None:
    root = _placed(tmp_path / "project")
    skill = load_skill(root, registry=create_runtime().records)
    result = skill.deploy(tmp_path / "copy")
    assert result["files"] == ["SKILL.md", ".tarav/skill.json"]
    assert SkillMarker.of(tmp_path / "copy").id == skill.skill_id


def test_the_skills_command_selects_a_skill_folder(tmp_path: Path, monkeypatch, capsys) -> None:
    from tarav.l3.cli.cli import main

    root = _placed(tmp_path)
    assert main(["skw", "skills", "ls", "--skill", str(root), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["total"] == 0
    monkeypatch.chdir(root)
    assert main(["skw", "skills", "ls", "--json"]) == 0
    monkeypatch.chdir(tmp_path)
    assert main(["skw", "skills", "ls", "--json"]) != 0
