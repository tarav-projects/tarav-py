"""Identified projects backed by their existing portable marker."""

from pathlib import Path
from typing import Literal

from pydantic import Field

from tarav.l0._core.project import project_marker_name, require_agentos_project
from tarav.l0.kernel import Ship, TaravClass, TaravEntity, TypeShip, entity
from tarav.l1.checks import CheckProvider
from tarav.l1.loading import LoadingProfile

from .workflow import PROJECT_WORKFLOW_SHIP


# tarav.breadcrumb 5cd4a1370534e180f82d31b551d9eb10ad12fe288b712dc707a8bb4faf489d2d
class TaravProject(TaravEntity, LoadingProfile, CheckProvider):
    """A Project; a subtype lists its checks in checks() (CheckProvider)."""

    @classmethod
    def loading_paths(cls) -> tuple[str, ...]:
        return (".tarav/project.json", "project.json")

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("4c621413-f7bf-46bf-bfd1-925b6ec99283"),
            name="Tarav.Project.Base",
            workflow=PROJECT_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravEntity.RecordInterface):
        id: Ship = Field(alias="project_id")
        marker_class: Literal["agentos.project"] = Field(alias="class")

    @classmethod
    def load_project(cls, *, path: Path | str = "."):
        """Discover a marker and load its declared, trusted Project Type.

        Unlike from_path(), this never replaces the Record's Type. The caller
        class constrains the resulting family, not the dispatch decision.
        Untyped markers require explicit migration before using this route.
        """
        from tarav.l0.kernel.current import current_records

        marker = require_agentos_project(path).marker_path
        project = current_records().load(marker)
        if not isinstance(project, cls):
            raise TypeError(f"Project marker must declare a subtype of {cls.__name__}")
        return project

    @classmethod
    def from_path(cls, path: Path | str = "."):
        """Discover the nearest project without modifying its marker."""
        handler = require_agentos_project(path)
        # Explicit class selection reprojects the Type tag in memory only.
        from tarav.l0.kernel.types import locate_record_type
        from copy import deepcopy

        record = deepcopy(handler.project_json)
        location = locate_record_type(record)
        if location is not None:
            target = record
            for key in location.path[:-1]:
                target = target[key]
            target[location.path[-1]] = entity(cls).name
        result = cls.from_record(record)
        result.source = handler.marker_path
        return result

    @property
    def root(self) -> Path:
        if self.source is None:
            raise ValueError("Detached Project has no filesystem location; use from_path()")
        return (
            self.source.parent.parent
            if self.source.parent.name == ".tarav"
            else self.source.parent
        )

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
