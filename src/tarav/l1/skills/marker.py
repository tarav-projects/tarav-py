"""`.tarav/skill.json`: the identity a skill keeps beside its product."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Self
from uuid import uuid4

from pydantic import Field

from tarav.l0.kernel import LoadedRecord, Ship, TaravClass, TaravEntity, TypeShip, entity

from .workflow import SKILLS_WORKFLOW_SHIP

SKILL_JSON = Path(".tarav") / "skill.json"


# tarav.breadcrumb 34f5d8d552b2
# tarav.breadcrumb cfd7a4f15150
class SkillMarker(TaravEntity):
    """A skill's UUID, kept in its folder so that every copy carries it.

    A skill is not a Project: it always belongs to one, the Project whose
    Skillware builds it. The marker holds identity only; what the skill says
    of itself stays in its `SKILL.md`.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("b4ff2ebc-f93c-4829-9a71-636be4ffaa14"),
            name="Tarav.Skills.Marker", workflow=SKILLS_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravEntity.RecordInterface):
        id: Ship = Field(alias="skill_id")
        created_at: str

    def __init__(self, id: Ship, *, created_at: str) -> None:
        super().__init__(id)
        self.created_at = created_at

    @classmethod
    def of(cls, skill_root: Path | str) -> Self:
        """The marker in a skill folder; fails when the folder has none."""
        path = Path(skill_root) / SKILL_JSON
        marker = cls.records.from_record(json.loads(path.read_text(encoding="utf-8")))
        marker.source = path
        return marker

    @classmethod
    def create(cls, skill_root: Path | str) -> Self:
        """Give a skill folder a new identity; an existing marker is never replaced."""
        path = Path(skill_root) / SKILL_JSON
        if path.exists():
            raise FileExistsError(f"{path} already exists")
        marker = cls(Ship(str(uuid4())),
                     created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(marker.records.to_record(), indent=2) + "\n", encoding="utf-8")
        marker.source = path
        return marker

    @classmethod
    def _from_record(cls, loaded: LoadedRecord) -> Self:
        return cls(loaded.data.id, created_at=loaded.data.created_at)

    def _to_record(self) -> dict[str, object]:
        return {"type": entity(type(self)).name, "skill_id": str(self.id),
                "created_at": self.created_at}

    class Records(TaravEntity.Records):
        def record_example(self) -> dict[str, object]:
            return {"type": entity(self._owner).name,
                    "skill_id": "6f1c2d3e-4b5a-4c6d-8e7f-901a2b3c4d5e",
                    "created_at": "2026-01-01T00:00:00Z"}
