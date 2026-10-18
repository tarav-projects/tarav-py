"""Identified Projects backed by their `.tarav/project.json`."""

from pathlib import Path
from pydantic import Field

from tarav.l0._core.errors import CliError
from tarav.l0.project import ProjectHarnessConfig, project_marker_name, require_agentos_project
from tarav.l0.kernel import NamespaceBase, Ship, TaravClass, TaravEntity, TypeShip, entity
from tarav.l1.checks import CheckProvider, CheckSuite
from tarav.l1.loading import LoadingProfile

from .workflow import PROJECT_WORKFLOW_SHIP
from tarav.l0.kernel import LoadedRecord


# tarav.breadcrumb 5cd4a1370534
class TaravProject(TaravEntity, LoadingProfile, CheckProvider):
    """A Project with shared bootstrap checks and subtype-specific checks."""

    # A Project is located by the marker it was loaded from.
    keeps_source = True

    # tarav.breadcrumb 2493391ddebf
    class Agents(NamespaceBase["TaravProject"]):
        @property
        def agents_md(self):
            from .agents import AgentsMd

            return AgentsMd(self.obj)

        # tarav.breadcrumb 54df434f7c89
        @property
        def skills(self):
            from .skills import ProjectSkills

            return ProjectSkills(self.obj)

    @property
    def agents(self) -> Agents:
        return type(self).Agents(self)

    class Checks(CheckProvider.Checks):
        # tarav.breadcrumb c1c38799380f
        def suite(self) -> CheckSuite:
            from tarav.l1.git.hooks import git_hooks_suite

            from .files import ProjectFilesCheck

            return CheckSuite([ProjectFilesCheck(self.obj),
                               self.obj.agents.agents_md.checks.suite(),
                               self.obj.agents.skills.checks.suite(),
                               git_hooks_suite(self.obj)],
                              name=self.obj.name, repositories=self.obj.repositories())

        # tarav.breadcrumb 47c83896e2f3
        def own(self) -> CheckSuite:
            """The checks of this Project alone, without those of its member Projects."""
            return self.suite()

    # tarav.breadcrumb a0b3336717d2
    def repositories(self) -> tuple[Path, ...]:
        """Folders in the Git repositories this Project's checks read; its suites declare them.

        By default the Project's root. A Project whose checks read another
        repository says so here.
        """
        return (self.root,)

    def members(self) -> tuple["TaravProject", ...]:
        """The Projects this one contains and can load here. None for a plain Project."""
        return ()

    # tarav.breadcrumb 023d66755f09
    @property
    def actions(self):
        """The actions registered under this Project."""
        from tarav.l1.actions.project import ProjectActions

        return ProjectActions.for_project(self)

    # tarav.breadcrumb c480857f3a5c
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

    # tarav.breadcrumb 953bd0d528d7
    class RecordInterface(TaravEntity.RecordInterface):
        """`.tarav/project.json`: the Project's Record and the Project workflow's
        own configuration. Other workflows configure a Project in config.json."""

        id: Ship = Field(alias="project_id")
        created_at: str
        project_name: str | None = None
        harness: ProjectHarnessConfig | None = None

    # tarav.breadcrumb 930bba78649d
    @classmethod
    def load_project(cls, *, path: Path | str = "."):
        """Load a Project as its harness says.

        `harness.type` is imported from the running environment and
        `project.json` is loaded as its Record; the Record's Type tag must name
        the same class. The caller class constrains the family.
        """
        from importlib import import_module

        from pydantic import ValidationError

        from tarav.l0.kernel.current import current_records
        from tarav.l0.kernel.types import UnknownRecordType

        handler = require_agentos_project(path)
        raw = handler.project_json.get("harness")
        if raw is None:
            raise CliError(f"{handler.marker_path} declares no harness: "
                           "harness.environment and harness.type")
        try:
            harness = ProjectHarnessConfig.model_validate(raw)
        except ValidationError as exc:
            raise CliError(f"{handler.marker_path}: invalid harness: {exc}") from exc
        module, _, name = harness.type.partition(":")
        try:
            project_type = getattr(import_module(module), name)
        except (ImportError, AttributeError) as exc:
            raise CliError(f"{handler.marker_path}: harness.type {harness.type} does not "
                           f"import in this environment: {exc}") from exc
        if not isinstance(project_type, type) or not issubclass(project_type, cls):
            raise TypeError(f"harness.type {harness.type} is not a {cls.__name__}")
        registry = current_records()
        type_name = entity(project_type).name
        try:
            known = registry.resolve_type(type_name)
        except UnknownRecordType:
            known = None
        if known is None:
            registry.environment.bind_type(type_name, project_type)
        project = registry.load(handler.marker_path)
        if type(project) is not project_type:
            raise TypeError(f"{handler.marker_path} names the Type {entity(type(project)).name}"
                            f" but harness.type is {harness.type}")
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

    _BASE_FIELDS = frozenset({"type", "id", "project_id", "created_at", "project_name", "harness"})

    def __init__(self, id: Ship, *, created_at: str, project_name: str | None = None,
                 harness: ProjectHarnessConfig | None = None,
                 fields: dict[str, object] | None = None) -> None:
        super().__init__(id)
        self.created_at, self.project_name, self.harness = created_at, project_name, harness
        # what a Type adds (a Root's children), and anything else the file holds
        self.fields = dict(fields or {})

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        values = loaded.data.model_dump(mode="json", by_alias=True, exclude_unset=True)
        return cls(loaded.data.id, created_at=loaded.data.created_at,
                   project_name=loaded.data.project_name, harness=loaded.data.harness,
                   fields={key: value for key, value in values.items()
                           if key not in cls._BASE_FIELDS})

    def _to_record(self):
        record = {"type": entity(type(self)).name, "project_id": str(self.id),
                  "created_at": self.created_at}
        if self.project_name is not None:
            record["project_name"] = self.project_name
        if self.harness is not None:
            record["harness"] = self.harness.model_dump(mode="json")
        return {**record, **self.fields}

    class Records(TaravEntity.Records):
        def record_example(self):
            cls = self._owner
            return {
                "type": entity(cls).name,
                "project_id": "20c26be7-a8e5-4974-9ec0-0b5a3a125a94",
                "created_at": "2026-01-01T00:00:00Z",
            }
