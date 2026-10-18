"""SKW reading-path checks built on the shared Checks and POI contracts."""

from collections import defaultdict

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.checks import Check, CheckResult
from tarav.l1.skw.identity import SKW_SKILLS_WORKFLOW_SHIP
from tarav.l1.skw.loading import SkillReadingGraph

from tarav.l1.skw.pois import (
    AttachmentCycle, Finding, InclusionCycle, InvalidBlockReference, InvalidContextTarget,
    InvalidLoadingRoot, InvalidParent, LoadingAnalysisIncomplete, MissingContext,
    PathDependentContext, RootHasParent, UndeclaredBlock, UnreachableBlock,
)

from .pois import surface_state


# tarav.breadcrumb 0172e2d45dbd
class ReadingGraphCheck(Check):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ba64a44f-d389-427c-9e47-306096ee82a2"),
                          name="Tarav.SKW.Check.ReadingGraph",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, graph: SkillReadingGraph, *, analysis=None):
        if not isinstance(graph, SkillReadingGraph):
            raise TypeError("Skill reading checks require a SkillReadingGraph")
        super().__init__()
        self.graph = graph
        self.analysis = analysis

    def _analysis(self):
        return self.graph.analyze() if self.analysis is None else self.analysis

# tarav.breadcrumb 15c7f0c5dc4c
    def _poi(self, finding):
        block = finding.get("block")
        binding = self.graph.bindings.get(block)
        subject = {"project": str(self.graph.package.root),
                   "block": str(binding[1].id) if binding else block}
        for key in ("target", "delivery"):
            if key in finding:
                subject[key] = finding[key]
        if "path" in finding:
            subject["path"] = [
                str(self.graph.bindings[node][1].id) if node in self.graph.bindings else node
                for node in finding["path"]]
        state = surface_state(self.graph.package)
        # a reader knows a block by its document and label, not by its node id
        where = f"{binding[0].key}: {binding[1].label}" if binding else None
        return finding.poi.poi(
            self,
            situation={"subject": subject, "surface_state": state},
            finding=finding,
            details={"loading": str(self.graph.source)},
            where=where,
        )

    def _result(self, analysis, findings):
        return CheckResult(self, status="completed" if analysis["complete"] else "incomplete",
                           pois=(self._poi(finding) for finding in findings),
                           data={"root": analysis["root"], "complete": analysis["complete"]})


class ReadingDeclarationsCheck(ReadingGraphCheck):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("bc349a05-97d8-4b8d-bd72-fc56fb487ebc"),
                          name="Tarav.SKW.Check.ReadingDeclarations",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def _run(self):
        analysis = self._analysis()
        mine = (InvalidBlockReference, UndeclaredBlock, InvalidParent, InvalidContextTarget,
                InvalidLoadingRoot, RootHasParent)
        return self._result(analysis, (found for found in analysis["diagnostics"]
                                       if found.poi in mine))


class ReadingDependenciesCheck(ReadingGraphCheck):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("7839e075-b5ce-48cc-ae76-1b515d08b9be"),
                          name="Tarav.SKW.Check.ReadingDependencies",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def _run(self):
        analysis = self._analysis()
        findings = []
        by_requirement = defaultdict(list)
        for observation in analysis["requirements"]:
            key = (observation["block"], observation["target"], observation["delivery"])
            by_requirement[key].append(observation)
            if not observation["satisfied"]:
                findings.append(Finding(MissingContext, **{
                    key: value for key, value in observation.items() if key != "satisfied"}))
        for (block, target, delivery), observations in by_requirement.items():
            if any(value["satisfied"] for value in observations) and not all(
                value["satisfied"] for value in observations
            ):
                findings.append(Finding(PathDependentContext, block=block, target=target,
                                        delivery=delivery))
        return self._result(analysis, findings)


class ReadingCoverageCheck(ReadingGraphCheck):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("bf7d3915-8ccf-4a23-b621-0eaa81414895"),
                          name="Tarav.SKW.Check.ReadingCoverage",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def _run(self):
        analysis = self._analysis()
        mine = (UnreachableBlock, AttachmentCycle, InclusionCycle, LoadingAnalysisIncomplete)
        return self._result(analysis, (found for found in analysis["diagnostics"]
                                       if found.poi in mine))


# tarav.breadcrumb d17fbd7e081f
class LinkProseCheck(ReadingGraphCheck):
    """Checks the text of each block against the prose parts of the links it declares.

    The other reading checks trust the declarations; this one is for the
    maintainers, who care that the text holds what is declared.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ac970186-220f-43c4-984a-b6fd94a88227"),
                          name="Tarav.SKW.Check.LinkProse",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def _run(self):
        root = self.graph.package.root
        return CheckResult(self, status="completed",
                           pois=(found.poi.from_finding(self, found, root=root)
                                 for found in self.graph.prose_findings()))


READING_CHECK_TYPES = (ReadingDeclarationsCheck, ReadingDependenciesCheck,
                       ReadingCoverageCheck, LinkProseCheck)


def reading_checks(graph: SkillReadingGraph, *, analysis=None):
    analysis = graph.analyze() if analysis is None else analysis
    return tuple(cls(graph, analysis=analysis) for cls in READING_CHECK_TYPES)
