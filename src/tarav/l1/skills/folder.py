"""A skill described by an installed folder, independently of its source."""

from pathlib import Path
from typing import Self

from pydantic import BaseModel

from tarav.l0.kernel import TaravClass, TypeShip, entity

from .skill import TaravSkill
from .workflow import SKILLS_WORKFLOW_SHIP


# tarav.breadcrumb 1b535cbde91f
class FolderSkill(TaravSkill):
    """A concrete skill whose only supplied state is its folder."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("3c22a9f9-b245-4051-b435-edca89264184"),
            name="Tarav.Skills.FolderSkill", workflow=SKILLS_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravSkill.RecordInterface):
        root: str

    def __init__(self, root: Path | str) -> None:
        super().__init__()
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        return cls(record_data.root)

    def _to_record(self) -> dict[str, object]:
        return {"type": entity(type(self)).name, "root": str(self.root)}

    class Records(TaravSkill.Records):
        def record_example(self) -> dict[str, object]:
            return {"type": entity(self._owner).name, "root": "/example/skill"}
