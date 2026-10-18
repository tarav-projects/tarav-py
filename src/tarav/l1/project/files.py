"""The check of a Project's two files: `.tarav/project.json` and `.tarav/config.json`.

A Project that loaded has a project.json its Type accepts; what can still be
wrong is reported, never refused: a field no model declares, a harness that
cannot start it, a config section no workflow owns or that its owner rejects.
"""

from __future__ import annotations

from importlib import import_module

from pydantic import ValidationError

from tarav.l0.kernel import TaravClass, TypeShip, locate_record_type
from tarav.l0.kernel.types import RecordTypeReference
from tarav.l0.project import ProjectHarnessConfig, load_project_marker, project_id
from tarav.l1.checks import Check, CheckPOI, CheckResult

from .config import ProjectConfig, config_sections
from .workflow import PROJECT_WORKFLOW_SHIP

class ProjectFilesPOI(CheckPOI):
    """Family, never raised: a Project's project.json or config.json needs attention."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("3f8b2c61-0a7d-4e59-9c14-6d2e8f1a7b35"),
                          name="Tarav.Project.Files.POI", workflow=PROJECT_WORKFLOW_SHIP)


class UnknownProjectField(ProjectFilesPOI):
    """project.json holds a field neither the Project nor its Type declares."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b2d94e17-5c38-4a06-8f71-e3a9c0d52b84"),
                          name="Tarav.Project.Files.UnknownField", workflow=PROJECT_WORKFLOW_SHIP)


class NoHarness(ProjectFilesPOI):
    """project.json declares no harness, so the Project cannot be started as its Type."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("6a1e0f93-2b47-4d8c-a5e6-91c7d3b0f428"),
                          name="Tarav.Project.Files.NoHarness", workflow=PROJECT_WORKFLOW_SHIP)


class HarnessEnvironmentMissing(ProjectFilesPOI):
    """The environment the harness names does not exist."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d47c3a28-91e5-4b06-8f2d-5a0e6c9b1f73"),
                          name="Tarav.Project.Files.HarnessEnvironmentMissing",
                          workflow=PROJECT_WORKFLOW_SHIP)


class HarnessTypeMismatch(ProjectFilesPOI):
    """harness.type does not import here, or is not the Type project.json's tag names."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("8e05b7d1-3c64-4f29-a1b8-2d7f9e6c0a51"),
                          name="Tarav.Project.Files.HarnessTypeMismatch",
                          workflow=PROJECT_WORKFLOW_SHIP)


class UnknownConfigSection(ProjectFilesPOI):
    """config.json holds a section no workflow owns."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("0c9f6a42-e1d8-4b73-96a5-b4e2d7c18f06"),
                          name="Tarav.Project.Files.UnknownConfigSection",
                          workflow=PROJECT_WORKFLOW_SHIP)


class InvalidConfigSection(ProjectFilesPOI):
    """A config.json section does not validate with its owner's model."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("5b3d8e70-a6f2-4c19-8d4e-07c1f9a2b6e3"),
                          name="Tarav.Project.Files.InvalidConfigSection",
                          workflow=PROJECT_WORKFLOW_SHIP)


# tarav.breadcrumb 7409c52b5dad
class ProjectFilesCheck(Check):
    """Checks a Project's project.json and config.json against their models."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a9e2c5f7-14b8-4d36-b0c3-6f8d1e4a7c92"),
                          name="Tarav.Project.Files.Check", workflow=PROJECT_WORKFLOW_SHIP)

    def __init__(self, project) -> None:
        super().__init__()
        self.project = project

    def _poi(self, poi_type: type[ProjectFilesPOI], message: str, *, details: dict | None = None,
             **situation) -> ProjectFilesPOI:
        return poi_type(self, message, situation={"project": project_id(self.project.root),
                                                  **situation},
                        details={"root": str(self.project.root), **(details or {})})

    def _run(self) -> CheckResult:
        project = self.project
        pois = []
        declared = set(type(project).RecordInterface.model_fields) | {"project_id"}
        for field in sorted(set(project.fields) - declared):
            pois.append(self._poi(UnknownProjectField,
                                  f"project.json holds the undeclared field {field}",
                                  file="project.json", field=field))
        raw = load_project_marker(project.source)
        if project.harness is None:
            pois.append(self._poi(NoHarness, "project.json declares no harness"))
        else:
            pois.extend(self._harness(project.harness, raw))
        pois.extend(self._config())
        return CheckResult(self, status="completed", pois=pois)

    def _harness(self, harness: ProjectHarnessConfig, raw: dict) -> list[ProjectFilesPOI]:
        found = []
        environment = (self.project.root / harness.environment).resolve()
        if not (environment / "pyvenv.cfg").is_file():
            found.append(self._poi(HarnessEnvironmentMissing,
                                   f"The harness environment {harness.environment} does not exist",
                                   environment=harness.environment))
        module, _, name = harness.type.partition(":")
        location = locate_record_type(raw)
        reference = RecordTypeReference.parse(location.value) if location else None
        try:
            project_type = getattr(import_module(module), name)
            agrees = reference is not None and project_type.matches(reference)
            reason = None if agrees else "is not the Type project.json's tag names"
        except (ImportError, AttributeError) as exc:
            reason = f"does not import: {exc}"
        if reason is not None:
            found.append(self._poi(HarnessTypeMismatch, f"harness.type {harness.type} {reason}",
                                   harness_type=harness.type,
                                   record_type=reference.label if reference else None))
        return found

    def _config(self) -> list[ProjectFilesPOI]:
        found = []
        owners = config_sections()
        for section, value in sorted(ProjectConfig(self.project.root).data().items()):
            model = owners.get(section)
            if model is None:
                found.append(self._poi(UnknownConfigSection,
                                       f"config.json holds the section {section}, "
                                       "which no workflow owns", file="config.json",
                                       section=section))
                continue
            try:
                model.model_validate(value)
            except ValidationError as exc:
                found.append(self._poi(InvalidConfigSection,
                                       f"config.json section {section} is invalid",
                                       details={"error": str(exc)}, file="config.json",
                                       section=section))
        return found


PROJECT_FILES_RECORD_TYPES = (ProjectFilesPOI, *ProjectFilesPOI.__subclasses__())

__all__ = [
    "HarnessEnvironmentMissing", "HarnessTypeMismatch", "InvalidConfigSection", "NoHarness",
    "PROJECT_FILES_RECORD_TYPES", "ProjectFilesCheck", "ProjectFilesPOI",
    "UnknownConfigSection", "UnknownProjectField",
]
