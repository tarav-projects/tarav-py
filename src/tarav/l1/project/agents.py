"""Project-owned agents file and its bootstrap checks."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tarav.l0.kernel import (
    TaravClass,
    TaravObject,
    TypeRegistry,
    TypeShip,
    current_records,
)
from tarav.l1.checks import Check, CheckPOI, CheckProvider, CheckResult, CheckSuite
from tarav.l1.settings import SettingsProvider, SettingsValues
from tarav.l1.skw import pois as skw
from tarav.l1.skw.document import Document, SKW_CODE_RECORD_TYPES, SkwBlock

from .config import ProjectConfig
from .workflow import PROJECT_WORKFLOW_SHIP

if TYPE_CHECKING:
    from .base import TaravProject


PROMPT_SOURCE = Path(__file__).with_name("tarav-system-prompt.md")


def _project_file(value: object) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("Agents file names must be nonempty project-relative paths")
    path = Path(value)
    if path.is_absolute() or any(part in {".", ".."} for part in value.split("/")):
        raise ValueError("Agents file paths must stay inside the Project")
    if value.endswith("/"):
        raise ValueError("Agents file names must identify files")
    return path


def _prompt_lines() -> list[str]:
    return PROMPT_SOURCE.read_text(encoding="utf-8").splitlines()


class TaravSystemPrompt(SkwBlock):
    """Code-produced, identical Tarav bootstrap text."""

    def __init__(self, record: Mapping[str, object]) -> None:
        super().__init__(record)
        self._prompt_record = deepcopy(self._record)

    def _to_record(self) -> Mapping[str, object]:
        return self._prompt_record

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("c6ea3339-1285-49fd-bba9-0609875f0d9d"),
            name="Tarav.Project.Agents.TaravSystemPrompt",
            workflow=PROJECT_WORKFLOW_SHIP,
        )

    def produce(self, document: Document) -> list[str]:
        return _prompt_lines()

    def output_findings(self, document: Document, lock_entry: dict) -> list[skw.Finding]:
        findings = super().output_findings(document, lock_entry)
        if self.get("content") != self.produce(document):
            findings.append(skw.Finding(skw.StaleProducedOutput, block=self.label,
                                        detail=str(PROMPT_SOURCE)))
        return findings


class ProjectSystemPrompt(SkwBlock):
    """Project-authored bootstrap text retained as a typed Skillware block."""

    def __init__(self, record: Mapping[str, object]) -> None:
        super().__init__(record)
        self._prompt_record = deepcopy(self._record)

    def _to_record(self) -> Mapping[str, object]:
        return self._prompt_record

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("7a19813a-e370-437c-a727-d3ab7cb870d4"),
            name="Tarav.Project.Agents.ProjectSystemPrompt",
            workflow=PROJECT_WORKFLOW_SHIP,
        )


class AgentsConfig(BaseModel):
    """The `agents` section of a Project's config: its agents files, the two
    prompt switches (settings of `AgentsMd`) and the skill that holds its package."""

    model_config = ConfigDict(strict=True, extra="forbid")
    main: str = "AGENTS.md"
    aliases: list[str] = []
    tarav_system_prompt: bool | None = None
    project_system_prompt: bool | None = None
    package_skill: str | None = None

    @field_validator("package_skill")
    @classmethod
    def _named(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("package_skill must be a nonempty name")
        return value


# tarav.breadcrumb 8b97ed485eccff4720809b740f11215ef20ae593f5a29f0051b472138ef64c30
class AgentsMd(TaravObject, CheckProvider, SettingsProvider):
    """A Project's main Skillware-produced agents file and declared aliases."""

    # tarav.breadcrumb 8a30ced371d61e9dcca3930e1297a64fd5e9872dc8ba4fffa8901835f3a8ab48
    class SettingsInterface(BaseModel):
        """Controls of the bootstrap checks; the `agents` section of the config stores them."""

        tarav_system_prompt: bool = Field(
            True, description="Require the Tarav System Prompt in the agents file.")
        project_system_prompt: bool = Field(
            True, description="Require a Project System Prompt in the agents file.")

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("5ba399ba-7d7d-4529-b897-a1db208c71fd"),
            name="Tarav.Project.Agents.AgentsMd",
            workflow=PROJECT_WORKFLOW_SHIP,
        )

    def __init__(self, project: TaravProject) -> None:
        super().__init__()
        self.project = project
        config = ProjectConfig(project.root)
        agents = config.section("agents", AgentsConfig) or AgentsConfig()
        self.main = _project_file(agents.main)
        self._aliases = tuple(_project_file(alias) for alias in agents.aliases)
        if len(set(self._aliases)) != len(self._aliases) or self.main in self._aliases:
            raise ValueError("Project agents files must have distinct paths")
        # The two switches are settings stored in the config; main and aliases are data.
        switches = {key: getattr(agents, key) for key in type(self).SettingsInterface.model_fields
                    if getattr(agents, key) is not None}
        self.settings.apply(values=SettingsValues.of(type(self), **switches),
                            origin=f"file:{config.path}")
        self.source = self.depot / "src" / "AGENTS.skw.json"

    @property
    def tarav_prompt_enabled(self) -> bool:
        return self.settings.get("tarav_system_prompt")

    @property
    def project_prompt_enabled(self) -> bool:
        return self.settings.get("project_system_prompt")

    @property
    def path(self) -> Path:
        return self.project.root / self.main

    @property
    def depot(self) -> Path:
        return self.project.root / ".tarav" / "skillware"

    @property
    def aliases(self) -> tuple[Path, ...]:
        return tuple(self.project.root / alias for alias in self._aliases)

    def document(self) -> Document:
        try:
            registry = current_records()
        except RuntimeError:
            registry = TypeRegistry(
                TaravObject,
                (*SKW_CODE_RECORD_TYPES, TaravSystemPrompt, ProjectSystemPrompt),
            )
        return Document(self.source, root=self.project.root, depot=self.depot,
                        registry=registry)

    class Checks(CheckProvider.Checks):
        def suite(self) -> CheckSuite:
            agents = self.obj
            checks: list[Check] = []
            if agents.tarav_prompt_enabled:
                checks.append(TaravSystemPromptCheck(agents))
            if agents.project_prompt_enabled:
                checks.append(ProjectSystemPromptCheck(agents))
            checks.append(AgentsMdProductCheck(agents))
            checks.extend(AgentsAliasCheck(agents, alias) for alias in agents.aliases)
            return CheckSuite(checks, name=str(agents.path))


class TaravSystemPromptPOI(CheckPOI):
    """Family, never raised: the agents file lacks the current Tarav System Prompt."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("715798b8-b431-431e-be0f-15338b7e2ea1"),
                          name="Tarav.Project.Agents.TaravSystemPromptPOI", workflow=PROJECT_WORKFLOW_SHIP)


class ProjectSystemPromptPOI(CheckPOI):
    """Family, never raised: the agents file lacks a Project System Prompt."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("64869199-6cbb-4653-808a-4cb03078fd0e"),
                          name="Tarav.Project.Agents.ProjectSystemPromptPOI", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsAliasPOI(CheckPOI):
    """Family, never raised: a declared alias is not a symlink to the main agents file."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("7890040b-6928-430e-876b-a3bf282c2eb1"),
                          name="Tarav.Project.Agents.AliasPOI", workflow=PROJECT_WORKFLOW_SHIP)


class TaravSystemPromptSourceUnavailable(TaravSystemPromptPOI):
    """The agents file's Skillware source could not be loaded, so its Tarav System Prompt cannot be checked."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("f619b16d-89a7-4333-ac61-cf91cbdd4aa3"),
                          name="Tarav.Project.Agents.TaravSystemPrompt.SourceUnavailable", workflow=PROJECT_WORKFLOW_SHIP)


class TaravSystemPromptMissing(TaravSystemPromptPOI):
    """The agents file's source has no Tarav System Prompt block."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("3db8ec7c-c299-42af-a6bd-acf1e3367514"),
                          name="Tarav.Project.Agents.TaravSystemPrompt.Missing", workflow=PROJECT_WORKFLOW_SHIP)


class TaravSystemPromptDuplicated(TaravSystemPromptPOI):
    """The agents file's source has more than one Tarav System Prompt block."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a8e0a16a-ed7d-4701-b7a6-5f22479aee68"),
                          name="Tarav.Project.Agents.TaravSystemPrompt.Duplicated", workflow=PROJECT_WORKFLOW_SHIP)


class TaravSystemPromptStale(TaravSystemPromptPOI):
    """The agents file's Tarav System Prompt differs from the text shipped with Tarav."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("aa038c70-c6e5-4c73-a9ee-0c21ba21dcab"),
                          name="Tarav.Project.Agents.TaravSystemPrompt.Stale", workflow=PROJECT_WORKFLOW_SHIP)


class ProjectSystemPromptSourceUnavailable(ProjectSystemPromptPOI):
    """The agents file's Skillware source could not be loaded, so its Project System Prompt cannot be checked."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("cddc4609-a050-48aa-be16-bfa1f88e451d"),
                          name="Tarav.Project.Agents.ProjectSystemPrompt.SourceUnavailable", workflow=PROJECT_WORKFLOW_SHIP)


class ProjectSystemPromptMissing(ProjectSystemPromptPOI):
    """The agents file's source has no Project System Prompt block."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("6cdf1c59-cbf8-4a19-b01b-af390c43583d"),
                          name="Tarav.Project.Agents.ProjectSystemPrompt.Missing", workflow=PROJECT_WORKFLOW_SHIP)


class ProjectSystemPromptDuplicated(ProjectSystemPromptPOI):
    """The agents file's source has more than one Project System Prompt block."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("639df163-f1d4-4608-8c23-d168a511b59a"),
                          name="Tarav.Project.Agents.ProjectSystemPrompt.Duplicated", workflow=PROJECT_WORKFLOW_SHIP)


class ProjectSystemPromptEmpty(ProjectSystemPromptPOI):
    """The agents file's Project System Prompt block has no content."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("2f73606f-67a5-4ea3-ba56-65eec05b73ce"),
                          name="Tarav.Project.Agents.ProjectSystemPrompt.Empty", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsAliasMissing(AgentsAliasPOI):
    """A declared alias of the agents file does not exist."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("da0f07eb-2ace-4ffe-a3b3-c3e28d3ea2d6"),
                          name="Tarav.Project.Agents.Alias.Missing", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsAliasNotSymlink(AgentsAliasPOI):
    """A declared alias of the agents file is a regular file, not a symlink."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b6f0cb36-b99b-4151-86f1-52507a84fc91"),
                          name="Tarav.Project.Agents.Alias.NotSymlink", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsAliasWrongTarget(AgentsAliasPOI):
    """A declared alias of the agents file is a symlink to something else."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("8ce3929f-d93e-4f93-9f91-afecb7858b75"),
                          name="Tarav.Project.Agents.Alias.WrongTarget", workflow=PROJECT_WORKFLOW_SHIP)


class _AgentsCheck(Check):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("df0827b8-8832-4635-bf7d-eb69e306f55e"),
            name="Tarav.Project.Agents.Check",
            workflow=PROJECT_WORKFLOW_SHIP,
        )

    def __init__(self, agents: AgentsMd) -> None:
        super().__init__()
        self.agents = agents

    def poi(self, poi_type: type[CheckPOI], message: str,
                *, path: Path | None = None, detail: str = "") -> CheckPOI:
        target = path or self.agents.path
        details = {"path": str(target), "source": str(self.agents.source),
                   "tarav_prompt_source": str(PROMPT_SOURCE)}
        if detail:
            details["detail"] = detail
        return poi_type(self, message,
                        situation={"project": str(self.agents.project.root),
                                   "path": str(target)},
                        details=details)

    def _document(self) -> Document | None:
        try:
            return self.agents.document()
        except (OSError, ValueError, TypeError, KeyError):
            return None


class TaravSystemPromptCheck(_AgentsCheck):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("9c9e02e9-483c-4aec-8436-4107b2e4d175"),
            name="Tarav.Project.Agents.TaravSystemPromptCheck",
            workflow=PROJECT_WORKFLOW_SHIP,
        )

    def _run(self) -> CheckResult:
        document = self._document()
        if document is None:
            poi = self.poi(TaravSystemPromptSourceUnavailable,
                               "Tarav System Prompt source is unavailable",
                               path=self.agents.source)
        else:
            blocks = [block for block in document.blocks.values()
                      if isinstance(block, TaravSystemPrompt)]
            if not blocks:
                poi = self.poi(TaravSystemPromptMissing,
                                   "Tarav System Prompt block is missing")
            elif len(blocks) > 1:
                poi = self.poi(TaravSystemPromptDuplicated,
                                   "Multiple Tarav System Prompt blocks found")
            elif blocks[0].get("content") != _prompt_lines():
                poi = self.poi(TaravSystemPromptStale,
                                   "Tarav System Prompt differs from shipped text")
            else:
                poi = None
        return CheckResult(self, status="completed", pois=() if poi is None else (poi,))


class ProjectSystemPromptCheck(_AgentsCheck):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("23697484-4623-46c5-b825-889fc07b69ee"),
            name="Tarav.Project.Agents.ProjectSystemPromptCheck",
            workflow=PROJECT_WORKFLOW_SHIP,
        )

    def _run(self) -> CheckResult:
        document = self._document()
        if document is None:
            poi = self.poi(ProjectSystemPromptSourceUnavailable,
                               "Project System Prompt source is unavailable",
                               path=self.agents.source)
        else:
            blocks = [block for block in document.blocks.values()
                      if isinstance(block, ProjectSystemPrompt)]
            if not blocks:
                poi = self.poi(ProjectSystemPromptMissing,
                                   "Project System Prompt block is missing")
            elif len(blocks) > 1:
                poi = self.poi(ProjectSystemPromptDuplicated,
                                   "Multiple Project System Prompt blocks found")
            elif not any(line.strip() for line in blocks[0].get("content") or []):
                poi = self.poi(ProjectSystemPromptEmpty,
                                   "Project System Prompt has no content")
            else:
                poi = None
        return CheckResult(self, status="completed", pois=() if poi is None else (poi,))


class AgentsMdProductCheck(_AgentsCheck):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("03e03024-6003-4cd4-848d-f7f589e0e404"),
            name="Tarav.Project.Agents.ProductCheck",
            workflow=PROJECT_WORKFLOW_SHIP,
        )

    def _run(self) -> CheckResult:
        try:
            document = self.agents.document()
            if document.target != self.agents.path.resolve():
                raise ValueError("Skillware source targets a different agents file")
            findings = document.lint()
        except (OSError, ValueError, TypeError, KeyError) as exc:
            findings = [skw.Finding(skw.InvalidSource, detail=str(exc))]
        # tarav.breadcrumb 774da0f859f206730f229473c73f2a6ce3e7b8d32299b76d0daa715235dc5a7f
        # the agents file is a Skillware document: what its lint finds is said by the
        # Skillware POI Types themselves, as it is for a document of a skill package
        root = Path(self.agents.project.root)
        source = self.agents.source
        source = str(source.relative_to(root) if source.is_relative_to(root) else source)
        pois = tuple(
            finding.poi.from_finding(self, finding.at(path=source), root=root)
            for finding in findings
            # the Tarav System Prompt check states that case itself
            if finding.poi is not skw.StaleProducedOutput
        )
        return CheckResult(self, status="completed", pois=pois)


# tarav.breadcrumb 0e97a77903e3f10987cb5e0de86ce10987cc5d1b101d7807a63215d18a5a511f
class AgentsAliasCheck(_AgentsCheck):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("a171ecf3-aa9a-4537-a446-e4949b3af790"),
            name="Tarav.Project.Agents.AliasCheck",
            workflow=PROJECT_WORKFLOW_SHIP,
        )

    def __init__(self, agents: AgentsMd, alias: Path) -> None:
        super().__init__(agents)
        self.alias = alias

    def _run(self) -> CheckResult:
        if not self.alias.exists() and not self.alias.is_symlink():
            case, state = AgentsAliasMissing, "missing"
        elif not self.alias.is_symlink():
            case, state = AgentsAliasNotSymlink, "not a symlink"
        elif self.alias.resolve() != self.agents.path.resolve():
            case, state = AgentsAliasWrongTarget, "a symlink to another target"
        else:
            case, state = None, ""
        pois = () if case is None else (
            self.poi(case, f"Agents alias is {state}", path=self.alias),
        )
        return CheckResult(self, status="completed", pois=pois)


PROJECT_AGENTS_RECORD_TYPES = (
    AgentsMd, TaravSystemPrompt, ProjectSystemPrompt,
    TaravSystemPromptPOI, ProjectSystemPromptPOI,
    AgentsAliasPOI, TaravSystemPromptCheck, ProjectSystemPromptCheck,
    AgentsMdProductCheck, AgentsAliasCheck,
    TaravSystemPromptSourceUnavailable, TaravSystemPromptMissing, TaravSystemPromptDuplicated,
    TaravSystemPromptStale, ProjectSystemPromptSourceUnavailable, ProjectSystemPromptMissing,
    ProjectSystemPromptDuplicated, ProjectSystemPromptEmpty,
    AgentsAliasMissing, AgentsAliasNotSymlink, AgentsAliasWrongTarget,
)

__all__ = [
    "AgentsAliasCheck", "AgentsAliasPOI", "AgentsMd", "AgentsMdProductCheck",
    "PROJECT_AGENTS_RECORD_TYPES", "ProjectSystemPrompt",
    "ProjectSystemPromptCheck", "ProjectSystemPromptPOI", "PROMPT_SOURCE",
    "TaravSystemPrompt", "TaravSystemPromptCheck", "TaravSystemPromptPOI",
]
