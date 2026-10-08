"""Project-owned agents file and its bootstrap checks."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

from tarav.l0.kernel import (
    TaravClass,
    TaravObject,
    TypeRegistry,
    TypeShip,
    current_records,
)
from tarav.l1.checks import Check, CheckPOI, CheckProvider, CheckResult, CheckSuite
from tarav.l1.skw.document import Document, SKW_CODE_RECORD_TYPES, SkwBlock

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


# tarav.breadcrumb e99f2fd0ced1996742d62afb9de0effa682f21e481ba288061a184e135e99c45
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

    def output_findings(self, document: Document, lock_entry: dict) -> list[dict]:
        findings = super().output_findings(document, lock_entry)
        if self.get("content") != self.produce(document):
            findings.append({"kind": "stale-produced-output", "block": self.label,
                             "detail": str(PROMPT_SOURCE)})
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


# tarav.breadcrumb 8b97ed485eccff4720809b740f11215ef20ae593f5a29f0051b472138ef64c30
class AgentsMd(TaravObject, CheckProvider):
    """A Project's main Skillware-produced agents file and declared aliases."""

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
        raw = project.records.to_record().get("agents", {})
        if not isinstance(raw, Mapping):
            raise ValueError("Project agents configuration must be an object")
        self.main = _project_file(raw.get("main", "AGENTS.md"))
        aliases = raw.get("aliases", [])
        if not isinstance(aliases, list):
            raise ValueError("Project agents aliases must be an array")
        self._aliases = tuple(_project_file(alias) for alias in aliases)
        if len(set(self._aliases)) != len(self._aliases) or self.main in self._aliases:
            raise ValueError("Project agents files must have distinct paths")
        for key in ("tarav_system_prompt", "project_system_prompt"):
            if not isinstance(raw.get(key, True), bool):
                raise ValueError(f"Project agents {key} must be a boolean")
        self.tarav_prompt_enabled = raw.get("tarav_system_prompt", True)
        self.project_prompt_enabled = raw.get("project_system_prompt", True)
        self.source = self.depot / "src" / "AGENTS.skw.json"

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
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("715798b8-b431-431e-be0f-15338b7e2ea1"),
            name="Tarav.Project.Agents.TaravSystemPromptPOI",
            workflow=PROJECT_WORKFLOW_SHIP,
        )


class ProjectSystemPromptPOI(CheckPOI):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("64869199-6cbb-4653-808a-4cb03078fd0e"),
            name="Tarav.Project.Agents.ProjectSystemPromptPOI",
            workflow=PROJECT_WORKFLOW_SHIP,
        )


class AgentsMdProductPOI(CheckPOI):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("d8353b6d-e8a7-46a7-ba8b-f21a1bc2b775"),
            name="Tarav.Project.Agents.ProductPOI",
            workflow=PROJECT_WORKFLOW_SHIP,
        )


class AgentsAliasPOI(CheckPOI):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("7890040b-6928-430e-876b-a3bf282c2eb1"),
            name="Tarav.Project.Agents.AliasPOI",
            workflow=PROJECT_WORKFLOW_SHIP,
        )


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

    def finding(self, poi_type: type[CheckPOI], code: str, message: str,
                *, path: Path | None = None, detail: str = "") -> CheckPOI:
        target = path or self.agents.path
        details = {"path": str(target), "source": str(self.agents.source),
                   "tarav_prompt_source": str(PROMPT_SOURCE)}
        if detail:
            details["detail"] = detail
        return poi_type(self, code, message,
                        situation={"project": str(self.agents.project.root),
                                   "path": str(target), "code": code},
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
            poi = self.finding(TaravSystemPromptPOI, "no-source",
                               "Tarav System Prompt source is unavailable",
                               path=self.agents.source)
        else:
            blocks = [block for block in document.blocks.values()
                      if isinstance(block, TaravSystemPrompt)]
            if not blocks:
                poi = self.finding(TaravSystemPromptPOI, "missing",
                                   "Tarav System Prompt block is missing")
            elif len(blocks) > 1:
                poi = self.finding(TaravSystemPromptPOI, "multiple",
                                   "Multiple Tarav System Prompt blocks found")
            elif blocks[0].get("content") != _prompt_lines():
                poi = self.finding(TaravSystemPromptPOI, "stale",
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
            poi = self.finding(ProjectSystemPromptPOI, "no-source",
                               "Project System Prompt source is unavailable",
                               path=self.agents.source)
        else:
            blocks = [block for block in document.blocks.values()
                      if isinstance(block, ProjectSystemPrompt)]
            if not blocks:
                poi = self.finding(ProjectSystemPromptPOI, "missing",
                                   "Project System Prompt block is missing")
            elif len(blocks) > 1:
                poi = self.finding(ProjectSystemPromptPOI, "multiple",
                                   "Multiple Project System Prompt blocks found")
            elif not any(line.strip() for line in blocks[0].get("content") or []):
                poi = self.finding(ProjectSystemPromptPOI, "empty",
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
            findings = [{"kind": "invalid-source", "detail": str(exc)}]
        pois = tuple(
            self.finding(AgentsMdProductPOI, finding["kind"],
                         f"Agents file: {finding['kind']}",
                         detail=finding.get("detail", ""))
            for finding in findings
            if finding["kind"] != "stale-produced-output"
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
            code = "missing"
        elif not self.alias.is_symlink():
            code = "not-symlink"
        elif self.alias.resolve() != self.agents.path.resolve():
            code = "wrong-target"
        else:
            code = None
        pois = () if code is None else (
            self.finding(AgentsAliasPOI, code, f"Agents alias: {code}", path=self.alias),
        )
        return CheckResult(self, status="completed", pois=pois)


PROJECT_AGENTS_RECORD_TYPES = (
    AgentsMd, TaravSystemPrompt, ProjectSystemPrompt,
    TaravSystemPromptPOI, ProjectSystemPromptPOI, AgentsMdProductPOI,
    AgentsAliasPOI, TaravSystemPromptCheck, ProjectSystemPromptCheck,
    AgentsMdProductCheck, AgentsAliasCheck,
)

__all__ = [
    "AgentsAliasCheck", "AgentsAliasPOI", "AgentsMd", "AgentsMdProductCheck",
    "AgentsMdProductPOI", "PROJECT_AGENTS_RECORD_TYPES", "ProjectSystemPrompt",
    "ProjectSystemPromptCheck", "ProjectSystemPromptPOI", "PROMPT_SOURCE",
    "TaravSystemPrompt", "TaravSystemPromptCheck", "TaravSystemPromptPOI",
]
