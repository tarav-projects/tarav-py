"""Project-owned agents file and its bootstrap checks."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from tarav.l0.kernel import (
    TaravClass,
    TaravObject,
    TypeRegistry,
    TypeShip,
    current_records,
)
from tarav.l1.checks import Check, CheckPOI, CheckProvider, CheckResult, CheckSuite
from tarav.l1.settings import SettingsProvider, SettingsValues
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
_AGENTS_READING = "The agents file and its checks are described in tarav-md/notes/wiki/agents-bootstrap.md and in the agents file's own closing section."
_USER_FIRST = 'Its producer intends it to be raised to the User before anything is changed.'

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
class AgentsMd(TaravObject, CheckProvider, SettingsProvider):
    """A Project's main Skillware-produced agents file and declared aliases."""

    # tarav.breadcrumb 8a30ced371d61e9dcca3930e1297a64fd5e9872dc8ba4fffa8901835f3a8ab48
    class SettingsInterface(BaseModel):
        """Controls of the bootstrap checks; the marker's `agents` entry stores them."""

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
        # The two switches are settings stored in the marker; main and aliases are data.
        switches = {key: raw[key] for key in type(self).SettingsInterface.model_fields
                    if key in raw}
        self.settings.apply(values=SettingsValues.of(type(self), **switches),
                            origin=f"file:{project.source}")
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
    context_notes = (_AGENTS_READING, 'It is no longer raised once the Skillware source holds one TaravSystemPrompt block produced from the shipped text and the file is compiled.', _USER_FIRST)
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("715798b8-b431-431e-be0f-15338b7e2ea1"),
                          name="Tarav.Project.Agents.TaravSystemPromptPOI", workflow=PROJECT_WORKFLOW_SHIP)


class ProjectSystemPromptPOI(CheckPOI):
    """Family, never raised: the agents file lacks a Project System Prompt."""
    context_notes = (_AGENTS_READING, 'It is no longer raised once the Skillware source holds one ProjectSystemPrompt block with content, authored with the User, and the file is compiled.', _USER_FIRST)
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("64869199-6cbb-4653-808a-4cb03078fd0e"),
                          name="Tarav.Project.Agents.ProjectSystemPromptPOI", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsMdProductPOI(CheckPOI):
    """Family, never raised: the agents file and its source disagree or cannot be compared."""
    context_notes = (_AGENTS_READING, 'The source is what is edited, never the product; compiling makes them agree, and lint shows the finding.', _USER_FIRST)
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d8353b6d-e8a7-46a7-ba8b-f21a1bc2b775"),
                          name="Tarav.Project.Agents.ProductPOI", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsAliasPOI(CheckPOI):
    """Family, never raised: a declared alias is not a symlink to the main agents file."""
    context_notes = (_AGENTS_READING, 'It is no longer raised once each declared alias is a symlink to the main agents file.', _USER_FIRST)
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("7890040b-6928-430e-876b-a3bf282c2eb1"),
                          name="Tarav.Project.Agents.AliasPOI", workflow=PROJECT_WORKFLOW_SHIP)


class TaravSystemPromptSourceUnavailable(TaravSystemPromptPOI):
    """The agents file's Skillware source could not be loaded, so its Tarav System Prompt cannot be checked."""

    context_notes = (_AGENTS_READING, "It is no longer raised once the agents file's Skillware source loads and holds the TaravSystemPrompt block, and the file is compiled.", _USER_FIRST)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("f619b16d-89a7-4333-ac61-cf91cbdd4aa3"),
                          name="Tarav.Project.Agents.TaravSystemPrompt.SourceUnavailable", workflow=PROJECT_WORKFLOW_SHIP)


class TaravSystemPromptMissing(TaravSystemPromptPOI):
    """The agents file's source has no Tarav System Prompt block."""

    context_notes = (_AGENTS_READING, 'It is no longer raised once the Skillware source holds the TaravSystemPrompt block, made with `produce`, and the file is compiled.', _USER_FIRST)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("3db8ec7c-c299-42af-a6bd-acf1e3367514"),
                          name="Tarav.Project.Agents.TaravSystemPrompt.Missing", workflow=PROJECT_WORKFLOW_SHIP)


class TaravSystemPromptDuplicated(TaravSystemPromptPOI):
    """The agents file's source has more than one Tarav System Prompt block."""

    context_notes = (_AGENTS_READING, 'It is no longer raised once the Skillware source keeps a single TaravSystemPrompt block and the file is compiled.', _USER_FIRST)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a8e0a16a-ed7d-4701-b7a6-5f22479aee68"),
                          name="Tarav.Project.Agents.TaravSystemPrompt.Duplicated", workflow=PROJECT_WORKFLOW_SHIP)


class TaravSystemPromptStale(TaravSystemPromptPOI):
    """The agents file's Tarav System Prompt differs from the text shipped with Tarav."""

    context_notes = (_AGENTS_READING, 'It is no longer raised once the TaravSystemPrompt block is made again with `produce` from the shipped text and the file is compiled.', _USER_FIRST)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("aa038c70-c6e5-4c73-a9ee-0c21ba21dcab"),
                          name="Tarav.Project.Agents.TaravSystemPrompt.Stale", workflow=PROJECT_WORKFLOW_SHIP)


class ProjectSystemPromptSourceUnavailable(ProjectSystemPromptPOI):
    """The agents file's Skillware source could not be loaded, so its Project System Prompt cannot be checked."""

    context_notes = (_AGENTS_READING, "It is no longer raised once the agents file's Skillware source loads and holds a ProjectSystemPrompt block authored with the User, and the file is compiled.", _USER_FIRST)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("cddc4609-a050-48aa-be16-bfa1f88e451d"),
                          name="Tarav.Project.Agents.ProjectSystemPrompt.SourceUnavailable", workflow=PROJECT_WORKFLOW_SHIP)


class ProjectSystemPromptMissing(ProjectSystemPromptPOI):
    """The agents file's source has no Project System Prompt block."""

    context_notes = (_AGENTS_READING, 'It is no longer raised once a ProjectSystemPrompt block authored with the User is in the source and the file is compiled.', _USER_FIRST)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("6cdf1c59-cbf8-4a19-b01b-af390c43583d"),
                          name="Tarav.Project.Agents.ProjectSystemPrompt.Missing", workflow=PROJECT_WORKFLOW_SHIP)


class ProjectSystemPromptDuplicated(ProjectSystemPromptPOI):
    """The agents file's source has more than one Project System Prompt block."""

    context_notes = (_AGENTS_READING, 'It is no longer raised once the ProjectSystemPrompt blocks are merged into one with the User and the file is compiled.', _USER_FIRST)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("639df163-f1d4-4608-8c23-d168a511b59a"),
                          name="Tarav.Project.Agents.ProjectSystemPrompt.Duplicated", workflow=PROJECT_WORKFLOW_SHIP)


class ProjectSystemPromptEmpty(ProjectSystemPromptPOI):
    """The agents file's Project System Prompt block has no content."""

    context_notes = (_AGENTS_READING, 'It is no longer raised once the Project System Prompt has content written with the User and the file is compiled.', _USER_FIRST)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("2f73606f-67a5-4ea3-ba56-65eec05b73ce"),
                          name="Tarav.Project.Agents.ProjectSystemPrompt.Empty", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsMdSourceInvalid(AgentsMdProductPOI):
    """The agents file's Skillware source is absent, unreadable, or targets another file."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ce5e32ca-8a77-4262-9223-3f26889c6786"),
                          name="Tarav.Project.Agents.Product.SourceInvalid", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsMdSourceUncompiled(AgentsMdProductPOI):
    """The agents file's Skillware source changed since it was last compiled."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("fcef7496-c4e3-485a-984f-66e576fc5bc3"),
                          name="Tarav.Project.Agents.Product.SourceUncompiled", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsMdProductUnavailable(AgentsMdProductPOI):
    """The compiled agents file cannot be read."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("bad48c96-de97-4565-a239-7c1d37e744a3"),
                          name="Tarav.Project.Agents.Product.Unavailable", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsMdProductDrift(AgentsMdProductPOI):
    """The agents file differs from what its Skillware source compiles to."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("1d2ad6ad-b45f-4464-9693-1dc17d9dab74"),
                          name="Tarav.Project.Agents.Product.Drift", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsMdBlockContentMissing(AgentsMdProductPOI):
    """A block of the agents file's source has no content."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("f0e543fd-8895-42c2-bb3b-304a8d68ab62"),
                          name="Tarav.Project.Agents.Product.BlockContentMissing", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsMdGenerationStale(AgentsMdProductPOI):
    """A generated block of the agents file's source has changed inputs."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("fd214588-75f2-4038-97cc-e84bdb0ed5ec"),
                          name="Tarav.Project.Agents.Product.GenerationStale", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsMdContextUnresolvable(AgentsMdProductPOI):
    """A block of the agents file's source declares context that cannot be resolved."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("61f5339d-907a-41c7-8f2b-c8dbe1b2c42b"),
                          name="Tarav.Project.Agents.Product.ContextUnresolvable", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsMdContextUnobserved(AgentsMdProductPOI):
    """A block of the agents file's source has context that was never observed."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a0d942d7-d28e-439b-8850-35aa8efaf76b"),
                          name="Tarav.Project.Agents.Product.ContextUnobserved", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsMdContextStale(AgentsMdProductPOI):
    """A block of the agents file's source has context that changed since it was observed."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a408b430-ce4e-4dae-a827-0a9894a7cc0a"),
                          name="Tarav.Project.Agents.Product.ContextStale", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsMdOutputChanged(AgentsMdProductPOI):
    """A tracked block of the agents file's source was edited outside a recorded generation."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("94eb724b-3098-4775-9d70-9609a4b08340"),
                          name="Tarav.Project.Agents.Product.OutputChanged", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsMdAnnotationInvalid(AgentsMdProductPOI):
    """A generation annotation of the agents file's source disagrees with its lock."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a804590d-9ee9-42ba-aef3-68055833644f"),
                          name="Tarav.Project.Agents.Product.AnnotationInvalid", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsMdProducedOutputInvalid(AgentsMdProductPOI):
    """A produced block of the agents file's source cannot compute its output."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("c8c1e97f-8373-49b1-ade2-c1b9b3bd3447"),
                          name="Tarav.Project.Agents.Product.ProducedOutputInvalid", workflow=PROJECT_WORKFLOW_SHIP)


# tarav.breadcrumb e89ee6a0f00a183a370aee37c7e80d0a659a41c54ae6c552f30be16e18ca96f9
class AgentsMdLintKindUnrecognized(AgentsMdProductPOI):
    """Skillware lint reported an unknown kind about the agents file."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("454c1852-10ef-4901-bd77-6b64a977bd89"),
                          name="Tarav.Project.Agents.Product.LintKindUnrecognized", workflow=PROJECT_WORKFLOW_SHIP)


# Skillware lint kinds are that linter's keys; each selects one atomic POI Type here.
_PRODUCT_POI = {
    "invalid-source": AgentsMdSourceInvalid,
    "source-uncompiled": AgentsMdSourceUncompiled,
    "product-unavailable": AgentsMdProductUnavailable,
    "product-drift": AgentsMdProductDrift,
    "missing-content": AgentsMdBlockContentMissing,
    "stale-generation": AgentsMdGenerationStale,
    "context-unresolvable": AgentsMdContextUnresolvable,
    "context-unobserved": AgentsMdContextUnobserved,
    "stale-context": AgentsMdContextStale,
    "output-changed": AgentsMdOutputChanged,
    "invalid-annotation": AgentsMdAnnotationInvalid,
    "invalid-produced-output": AgentsMdProducedOutputInvalid,
}


class AgentsAliasMissing(AgentsAliasPOI):
    """A declared alias of the agents file does not exist."""

    context_notes = (_AGENTS_READING, 'It is no longer raised once the alias exists as a symlink to the main agents file.', _USER_FIRST)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("da0f07eb-2ace-4ffe-a3b3-c3e28d3ea2d6"),
                          name="Tarav.Project.Agents.Alias.Missing", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsAliasNotSymlink(AgentsAliasPOI):
    """A declared alias of the agents file is a regular file, not a symlink."""

    context_notes = (_AGENTS_READING, 'It is no longer raised once the file is replaced by a symlink to the main agents file. The regular file may hold content found nowhere else.', _USER_FIRST)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b6f0cb36-b99b-4151-86f1-52507a84fc91"),
                          name="Tarav.Project.Agents.Alias.NotSymlink", workflow=PROJECT_WORKFLOW_SHIP)


class AgentsAliasWrongTarget(AgentsAliasPOI):
    """A declared alias of the agents file is a symlink to something else."""

    context_notes = (_AGENTS_READING, 'It is no longer raised once the symlink points at the main agents file.', _USER_FIRST)

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
            findings = [{"kind": "invalid-source", "detail": str(exc)}]
        pois = tuple(
            self.poi(_PRODUCT_POI.get(finding["kind"], AgentsMdLintKindUnrecognized),
                         f"Agents file: {finding['kind']}",
                         detail=finding.get("detail", "") or finding["kind"])
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
    TaravSystemPromptPOI, ProjectSystemPromptPOI, AgentsMdProductPOI,
    AgentsAliasPOI, TaravSystemPromptCheck, ProjectSystemPromptCheck,
    AgentsMdProductCheck, AgentsAliasCheck,
    TaravSystemPromptSourceUnavailable, TaravSystemPromptMissing, TaravSystemPromptDuplicated,
    TaravSystemPromptStale, ProjectSystemPromptSourceUnavailable, ProjectSystemPromptMissing,
    ProjectSystemPromptDuplicated, ProjectSystemPromptEmpty, AgentsMdSourceInvalid,
    AgentsMdSourceUncompiled, AgentsMdProductUnavailable, AgentsMdProductDrift,
    AgentsMdBlockContentMissing, AgentsMdGenerationStale, AgentsMdContextUnresolvable,
    AgentsMdContextUnobserved, AgentsMdContextStale, AgentsMdOutputChanged,
    AgentsMdAnnotationInvalid, AgentsMdProducedOutputInvalid, AgentsMdLintKindUnrecognized,
    AgentsAliasMissing, AgentsAliasNotSymlink, AgentsAliasWrongTarget,
)

__all__ = [
    "AgentsAliasCheck", "AgentsAliasPOI", "AgentsMd", "AgentsMdProductCheck",
    "AgentsMdProductPOI", "PROJECT_AGENTS_RECORD_TYPES", "ProjectSystemPrompt",
    "ProjectSystemPromptCheck", "ProjectSystemPromptPOI", "PROMPT_SOURCE",
    "TaravSystemPrompt", "TaravSystemPromptCheck", "TaravSystemPromptPOI",
]
