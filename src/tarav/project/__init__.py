"""Identified projects backed by their existing portable marker."""

from pathlib import Path
from typing import Literal

from pydantic import Field

from tarav._core.project import project_marker_name, require_agentos_project
from tarav.kernel import Ship, TaravClass, TaravEntity, TypeShip, entity

from .workflow import PROJECT_WORKFLOW_SHIP, ProjectWorkflow


class Project(TaravEntity):
    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("a5f2412f-1c41-4299-9bcd-90cf38685516"),
            name="Tarav.Project",
            workflow=PROJECT_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravEntity.RecordInterface):
        id: Ship = Field(alias="project_id")
        marker_class: Literal["agentos.project"] = Field(alias="class")

    @classmethod
    def from_path(cls, path: Path | str = "."):
        """Discover the nearest project without modifying its marker."""
        handler = require_agentos_project(path)
        result = cls.from_record(handler.project_json)
        result.source = handler.marker_path
        return result

    @property
    def root(self) -> Path:
        if self.source is None:
            raise ValueError("Detached Project has no filesystem location; use from_path()")
        return self.source.parent.parent

    @property
    def name(self) -> str:
        return project_marker_name(self.to_record()) or self.root.name

    def _to_record(self):
        if self._record is not None:
            return self._record
        return {
            "type": entity(type(self)).name,
            "class": "agentos.project",
            "project_id": str(self.id),
        }

    @classmethod
    def record_example(cls):
        return {
            "type": entity(cls).name,
            "class": "agentos.project",
            "project_id": "20c26be7-a8e5-4974-9ec0-0b5a3a125a94",
        }


__all__ = ["Project", "ProjectWorkflow"]
