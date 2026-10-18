"""What a Project learned from one run of its checks."""

from __future__ import annotations

from dataclasses import dataclass

from tarav.l1.checks import CheckSuite


# tarav.breadcrumb 9ea03b213fa0
@dataclass(frozen=True)
class ProjectStatus:
    """One Project's suite that ran, what its actions did with it, and the same for its members."""

    project: object
    checks: CheckSuite
    actions: dict
    members: tuple["ProjectStatus", ...] = ()

    def each(self) -> tuple["ProjectStatus", ...]:
        """This status and those of the members below it, in the order they ran."""
        return (self, *(found for member in self.members for found in member.each()))

    def suite(self) -> CheckSuite:
        """The suites of this Project and its members, gathered for one report."""
        return CheckSuite.gathered((status.checks for status in self.each()),
                                   name=getattr(self.project, "name", None))

    def acted(self) -> dict:
        """What the actions of all these Projects did, added up."""
        parts = [status.actions for status in self.each()]
        return {**{name: sum(part[name] for part in parts)
                   for name in ("opened", "reopened", "gone", "updated", "actions")},
                "projects": [part["project"] for part in parts],
                "changes": [{**change, "project": part["project"]["name"]}
                            for part in parts for change in part["changes"]],
                "signals": [signal for part in parts for signal in part["signals"]]}


__all__ = ["ProjectStatus"]
