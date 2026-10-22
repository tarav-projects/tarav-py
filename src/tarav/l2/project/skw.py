"""Project integration with deployable Skillware packages."""

from pathlib import Path

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.checks import Check, CheckResult, CheckSuite
from tarav.l1.project.skw import SkwManager as DocumentSkwManager
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP
from tarav.l2.skw.skills import load_depot, project_skills


class SkillLoadCheck(Check):
    """A skill depot could not be loaded to collect its checks."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("bf257488-4865-4608-a6ee-86b7b23033dc"),
                          name="Tarav.Project.Dev.SkillLoad", workflow=PROJECT_WORKFLOW_SHIP)

    def __init__(self, skill, reason: str) -> None:
        super().__init__()
        self.skill, self.reason = Path(skill), reason

    def _run(self) -> CheckResult:
        return CheckResult(self, status="incomplete", reason=f"{self.skill.name}: {self.reason}")


# tarav.breadcrumb 327819b251e4
class SkwManager(DocumentSkwManager):
    """Discover this Project's skill depots and contribute their checks."""

    def skill_depots(self):
        return project_skills(self.obj.root)

    def checks(self) -> CheckSuite:
        """Build a lazy suite; loading errors leave the affected checks incomplete."""
        return CheckSuite(lambda run: self._checks(), name="Skillware",
                          repositories=self.obj.repositories())

    def _checks(self):
        for depot in self.skill_depots():
            try:
                yield load_depot(depot, registry=self.obj.records.types).checks.suite()
            except (OSError, ValueError, TypeError, RuntimeError) as exc:
                yield SkillLoadCheck(depot, f"{type(exc).__name__}: {exc}")


__all__ = ["SkwManager", "SkillLoadCheck"]
