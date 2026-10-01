"""SKW reading-path checks built on the shared Checks and POI contracts."""

from collections import defaultdict

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.checks import Check, CheckResult
from tarav.l1.skw.identity import SKW_SKILLS_WORKFLOW_SHIP

from .pois import CLASSES, surface_state


# tarav.breadcrumb 0172e2d45dbdb798abc6c154643755217d95a7ff03a42343a5378cd3c75fd586
class ReadingGraphCheck(Check):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ba64a44f-d389-427c-9e47-306096ee82a2"),
                          name="Tarav.SKW.Check.ReadingGraph",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, graph, *, analysis=None):
        super().__init__()
        self.graph = graph
        self.analysis = analysis

    def _analysis(self):
        return self.graph.analyze() if self.analysis is None else self.analysis

    def _poi(self, finding):
        kind = finding["kind"]
        cls = CLASSES[kind]
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
        evidence = {"finding": finding,
                    "check": {"type": entity(type(self)).name},
                    "loading": str(self.graph.source),
                    "surface_state": surface_state(self.graph.package)}
        return cls.finding(
            self,
            subject,
            situation={
                "subject": subject,
                "surface_state": evidence["surface_state"],
            },
            evidence=evidence,
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
        kinds = {"invalid-block-reference", "undeclared-block", "invalid-parent",
                 "invalid-context-target", "invalid-loading-root", "root-has-parent",
                 "unannotated-output-link"}
        return self._result(analysis, ({"kind": d["code"], **{k: v for k, v in d.items()
                                                                if k != "code"}}
                                       for d in analysis["diagnostics"] if d["code"] in kinds))


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
                findings.append({"kind": "missing-context", **{
                    key: value for key, value in observation.items() if key != "satisfied"}})
        for (block, target, delivery), observations in by_requirement.items():
            if any(value["satisfied"] for value in observations) and not all(
                value["satisfied"] for value in observations
            ):
                findings.append({"kind": "path-dependent-context", "block": block,
                                 "target": target, "delivery": delivery})
        return self._result(analysis, findings)


class ReadingCoverageCheck(ReadingGraphCheck):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("bf7d3915-8ccf-4a23-b621-0eaa81414895"),
                          name="Tarav.SKW.Check.ReadingCoverage",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def _run(self):
        analysis = self._analysis()
        kinds = {"unreachable-block", "attachment-cycle", "inclusion-cycle",
                 "loading-analysis-incomplete"}
        return self._result(analysis, ({"kind": d["code"], **{k: v for k, v in d.items()
                                                                if k != "code"}}
                                       for d in analysis["diagnostics"] if d["code"] in kinds))


READING_CHECK_TYPES = (ReadingDeclarationsCheck, ReadingDependenciesCheck,
                       ReadingCoverageCheck)


def reading_checks(graph, *, analysis=None):
    analysis = graph.analyze() if analysis is None else analysis
    return tuple(cls(graph, analysis=analysis) for cls in READING_CHECK_TYPES)
