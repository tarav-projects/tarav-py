import json
from pathlib import Path

import pytest

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.skills import SKILLS_WORKFLOW_SHIP, SkillsWorkflow, TaravSkill
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
    root = _folder(tmp_path, "made", "name: made\n")
    made = SkwSkill(root=root, entrypoint="SKILL.md")
    (root / ".skw").mkdir()
    (root / ".skw" / "main.json").write_text(json.dumps(made.records.to_record()), encoding="utf-8")

    loaded = load_skill(root, registry=create_runtime().records)

    assert loaded.records.to_record() == made.records.to_record()
    assert (loaded.root, loaded.entrypoint) == (made.root, made.entrypoint)
    assert loaded.skill_name == made.skill_name == "made"
    assert not hasattr(loaded, "_record")


def test_a_skill_not_yet_placed_has_state_but_no_root() -> None:
    skill = SkwSkill(files=["SKILL.md", "notes.md"])
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
