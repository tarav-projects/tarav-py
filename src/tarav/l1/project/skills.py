"""Project skill availability and folder bootstrap checks."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from tarav.l0.kernel import TaravClass, TaravObject, TypeShip
from tarav.l1.checks import Check, CheckPOI, CheckProvider, CheckResult, CheckSuite
from tarav.l1.skills.folder import FolderSkill

from .workflow import PROJECT_WORKFLOW_SHIP

if TYPE_CHECKING:
    from .base import TaravProject


TARAV_PACKAGE_SKILL = "tarav-pkg"


# tarav.breadcrumb f011d7009f1b32971b3f77364fe0233f55c8d1d9543a658f3fd8105a4db97f6b
class ProjectSkills(TaravObject, CheckProvider):
    """Skills visible to an agent entering this Project."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("abcb349a-f2da-4df9-9926-69c072fa17b9"),
            name="Tarav.Project.Agents.Skills", workflow=PROJECT_WORKFLOW_SHIP,
        )

    def __init__(self, project: TaravProject, *, home: Path | None = None) -> None:
        super().__init__()
        self.project = project
        self.home = Path.home() if home is None else Path(home)
        raw = project.records.to_record().get("agents", {})
        if not isinstance(raw, Mapping):
            raise ValueError("Project agents configuration must be an object")
        name = raw.get("package_skill")
        if name is not None and (not isinstance(name, str) or not name.strip()):
            raise ValueError("Project agents package_skill must be a nonempty name")
        self.package_skill = name

    @property
    def search_places(self) -> tuple[Path, Path]:
        return (self.project.root / ".agents/skills", self.home / ".agents/skills")

    def available(self) -> tuple[FolderSkill, ...]:
        found = []
        for place in self.search_places:
            if not place.is_dir():
                continue
            for folder in sorted(place.iterdir()):
                if folder.is_dir() and (folder / "SKILL.md").is_file():
                    found.append(FolderSkill(folder))
        return tuple(found)

    def find(self, name: str) -> tuple[FolderSkill, ...]:
        return tuple(skill for skill in self.available() if skill.skill_name == name)

    class Checks(CheckProvider.Checks):
        def suite(self) -> CheckSuite:
            skills = self.obj
            return CheckSuite([
                TaravPackageSkillCheck(skills), ProjectPackageSkillCheck(skills),
                SkillFoldersCheck(skills, skills.project.root, "project"),
                SkillFoldersCheck(skills, skills.home, "home"),
            ], name=f"{skills.project.name} skills")


class TaravPackageSkillPOI(CheckPOI):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("7c5bce92-5ece-48e9-b803-444f7b6166cc"),
                          name="Tarav.Project.Agents.TaravPackageSkillPOI",
                          workflow=PROJECT_WORKFLOW_SHIP)


class ProjectPackageSkillPOI(CheckPOI):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("1217d219-c0c4-48fc-9a4f-735a9d7e597b"),
                          name="Tarav.Project.Agents.ProjectPackageSkillPOI",
                          workflow=PROJECT_WORKFLOW_SHIP)


class SkillFoldersPOI(CheckPOI):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("0ef39065-28a2-4c91-ae45-a4c994b8e2b8"),
                          name="Tarav.Project.Agents.SkillFoldersPOI",
                          workflow=PROJECT_WORKFLOW_SHIP)


class _SkillsCheck(Check):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("60ae94ac-6572-4204-a118-2c311b60e533"),
                          name="Tarav.Project.Agents.SkillsCheck",
                          workflow=PROJECT_WORKFLOW_SHIP)

    def __init__(self, skills: ProjectSkills) -> None:
        super().__init__()
        self.skills = skills

    def finding(self, poi_type: type[CheckPOI], code: str, message: str,
                *, scope: str = "project") -> CheckPOI:
        return poi_type(
            self, code, message,
            situation={"project": str(self.skills.project.root), "scope": scope,
                       "code": code},
            details={"search_places": [str(p) for p in self.skills.search_places],
                     "repair": "tarav project skills import"},
        )


class TaravPackageSkillCheck(_SkillsCheck):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("5388bd9e-162b-412f-93be-c6495f11a986"),
                          name="Tarav.Project.Agents.TaravPackageSkillCheck",
                          workflow=PROJECT_WORKFLOW_SHIP)

    def _run(self) -> CheckResult:
        pois = () if self.skills.find(TARAV_PACKAGE_SKILL) else (
            self.finding(TaravPackageSkillPOI, "missing",
                         f"Required Tarav package skill {TARAV_PACKAGE_SKILL} is missing"),)
        return CheckResult(self, status="completed", pois=pois)


class ProjectPackageSkillCheck(_SkillsCheck):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("cc725244-9d74-4f47-b3fe-9a42c04cc375"),
                          name="Tarav.Project.Agents.ProjectPackageSkillCheck",
                          workflow=PROJECT_WORKFLOW_SHIP)

    def _run(self) -> CheckResult:
        name = self.skills.package_skill
        if name is None:
            pois = (self.finding(ProjectPackageSkillPOI, "undeclared",
                                 "Project agents package_skill is undeclared"),)
        elif not self.skills.find(name):
            pois = (self.finding(ProjectPackageSkillPOI, "missing",
                                 f"Project package skill {name} is missing"),)
        else:
            pois = ()
        return CheckResult(self, status="completed", pois=pois)


class SkillFoldersCheck(_SkillsCheck):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d617d719-94bf-473b-ba85-06d99dddeaa8"),
                          name="Tarav.Project.Agents.SkillFoldersCheck",
                          workflow=PROJECT_WORKFLOW_SHIP)

    def __init__(self, skills: ProjectSkills, root: Path, scope: str) -> None:
        super().__init__(skills)
        self.root = root
        self.scope = scope

    def _run(self) -> CheckResult:
        agents = self.root / ".agents/skills"
        claude = self.root / ".claude/skills"
        findings = []
        if not agents.is_dir():
            findings.append(("agents-skills-absent", f"Skills folder absent: {agents}"))
        if not claude.is_dir():
            findings.append(("claude-skills-absent", f"Claude skills folder absent: {claude}"))
        if agents.is_dir() and claude.is_dir() and agents.resolve() != claude.resolve():
            findings.append(("claude-skills-diverges",
                             f"Claude skills folder differs from agents skills: {claude}"))
        return CheckResult(
            self, status="completed",
            pois=tuple(self.finding(SkillFoldersPOI, code, message, scope=self.scope)
                       for code, message in findings),
        )


PROJECT_SKILLS_RECORD_TYPES = (
    ProjectSkills, TaravPackageSkillPOI, ProjectPackageSkillPOI, SkillFoldersPOI,
    TaravPackageSkillCheck, ProjectPackageSkillCheck, SkillFoldersCheck,
)
