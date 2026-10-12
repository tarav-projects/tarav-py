"""What a Project learned from one run of its checks."""

from __future__ import annotations

from dataclasses import dataclass

from tarav.l1.checks import CheckRun


# tarav.breadcrumb 9ea03b213fa06c650029b7c469cf4605672c9ddf1415140f3013f3a7c4a61e6f
@dataclass(frozen=True)
class ProjectStatus:
    """One Project's check run, what its actions did with it, and the same for its members."""

    project: object
    checks: CheckRun
    actions: dict
    members: tuple["ProjectStatus", ...] = ()

    def each(self) -> tuple["ProjectStatus", ...]:
        """This status and those of the members below it, in the order they ran."""
        return (self, *(found for member in self.members for found in member.each()))

    def run(self) -> CheckRun:
        """Every result, of this Project and its members, as one run for a report."""
        whole = CheckRun()
        for status in self.each():
            for result in status.checks.results:
                whole.add(result)
        return whole

    def acted(self) -> dict:
        """What the actions of all these Projects did, added up."""
        parts = [status.actions for status in self.each()]
        return {**{name: sum(part[name] for part in parts)
                   for name in ("opened", "reopened", "gone", "updated", "actions")},
                "projects": [part["project"] for part in parts],
                "signals": [signal for part in parts for signal in part["signals"]]}


__all__ = ["ProjectStatus"]
