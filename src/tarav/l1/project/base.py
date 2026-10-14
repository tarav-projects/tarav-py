"""Identified projects backed by their existing portable marker."""

from pathlib import Path
from typing import Literal

from pydantic import Field

from tarav.l0.project import project_marker_name, require_agentos_project
from tarav.l0.kernel import NamespaceBase, Ship, TaravClass, TaravEntity, TypeShip, entity
from tarav.l1.checks import CheckProvider, CheckSuite
from tarav.l1.loading import LoadingProfile

from .workflow import PROJECT_WORKFLOW_SHIP


# tarav.breadcrumb 5cd4a1370534e180f82d31b551d9eb10ad12fe288b712dc707a8bb4faf489d2d
class TaravProject(TaravEntity, LoadingProfile, CheckProvider):
    """A Project with shared bootstrap checks and subtype-specific checks."""

    # tarav.breadcrumb 2493391ddebfa2966685ca8cf21006aa0fe701329a5dc3bfe27dc78d238a31ba
    class Agents(NamespaceBase["TaravProject"]):
        @property
        def agents_md(self):
            from .agents import AgentsMd

            return AgentsMd(self.obj)

        # tarav.breadcrumb 54df434f7c894a8c84736fa05c502a8697a1293f2bb1fc6aebdf4d9745c09c90
        @property
        def skills(self):
            from .skills import ProjectSkills

            return ProjectSkills(self.obj)

    @property
    def agents(self) -> Agents:
        return type(self).Agents(self)

    class Checks(CheckProvider.Checks):
        # tarav.breadcrumb c1c38799380f065d088e5c7e704ac0e46755ff33a8171e0247bd531f899012ce
        def suite(self) -> CheckSuite:
            return CheckSuite([self.obj.agents.agents_md.checks.suite(),
                               self.obj.agents.skills.checks.suite()],
                              name=self.obj.name, repositories=self.obj.repositories())

        # tarav.breadcrumb 47c83896e2f3b52b8445023094aea20efa16beb513be9c96d448cf803024086a
        def own(self) -> CheckSuite:
            """The checks of this Project alone, without those of its member Projects."""
            return self.suite()

    # tarav.breadcrumb a0b3336717d2a701c4ffecb72778440cc9c4df2a0cf9eff07400b3edd5aa6e49
    def repositories(self) -> tuple[Path, ...]:
        """Folders in the Git repositories this Project's checks read; its suites declare them.

        By default the Project's root. A Project whose checks read another
        repository says so here.
        """
        return (self.root,)

    def members(self) -> tuple["TaravProject", ...]:
        """The Projects this one contains and can load here. None for a plain Project."""
        return ()

    # tarav.breadcrumb 023d66755f096ecc913a16d886cbe2725017dbda9b4e3b368e0214517b04eb23
    @property
    def actions(self):
        """The actions registered under this Project."""
        from tarav.l1.actions.project import ProjectActions

        return ProjectActions.for_project(self)

    # tarav.breadcrumb c480857f3a5c1669df7d3f312f134b4771e05dc92cfcc7f954c10e7c2caa87b4
    def status(self, *, select=None, on_result=None):
        """Run this Project's checks and hand the suite that ran to its actions.

        The checks only run and the actions never run a check; this is where
        the two meet. A Project with members does this for its own checks and
        asks each member to do the same for itself. `select` filters what
        runs; what it leaves out is known as not run, so no action closes
        for it.
        """
        from .status import ProjectStatus

        checks = self.checks.own().run(select=select, on_result=on_result)
        return ProjectStatus(self, checks, self.actions.update(checks),
                             tuple(member.status(select=select, on_result=on_result)
                                   for member in self.members()))

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
        result = cls.records.from_record(record)
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
        return project_marker_name(self.records.to_record()) or self.root.name

    def _to_record(self):
        if self._record is not None:
            return self._record
        return {
            "type": entity(type(self)).name,
            "class": "agentos.project",
            "project_id": str(self.id),
        }

    class Records(TaravEntity.Records):
        def record_example(self):
            cls = self._owner
            return {
                "type": entity(cls).name,
                "class": "agentos.project",
                "project_id": "20c26be7-a8e5-4974-9ec0-0b5a3a125a94",
            }
