"""Skillware analysis as Situation Chains: one atomic Check per situation of a skill package.

A skill's Suite (`SkwSkillSuite`) loads the package once (`SkillLoad`), finds
its situations — the skill, each source, product, block, consumer file, link,
and dependency, and in its reading graph each declared node,
declaration, requirement, reading path and prose link — and runs the Check of
each one's chain with the situation it built. The rules stay in the native analysis (`tarav.l1.skw`),
split per subject: a Check runs the rules of its one subject and raises POIs
with exactly its situation. Open a POI's Type from finding.help for policy.
"""
import re
from collections import defaultdict
from copy import deepcopy
from urllib.parse import unquote, urlsplit

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.checks import CheckResult, CheckSuite, SituationCheck
from tarav.l1.checks.chains import SituationChain
from tarav.l1.references import Reference
from tarav.l1.skills import SKILL_JSON, SkillMarker
from tarav.l1.skw.annotations import GenerationAnnotation
from tarav.l1.skw.generation import _hash
from tarav.l1.skw.identity import SKW_SKILLS_WORKFLOW_SHIP
from tarav.l1.skw.skills import SkillLink
from tarav.l1.skw.pois import (
    AttachmentCycle, InclusionCycle, InvalidBlockReference, InvalidContextTarget,
    InvalidLoadingRoot, InvalidParent, LoadingAnalysisIncomplete, MissingContext,
    MissingMarkdownLink, PathDependentContext, RootHasParent, UndeclaredBlock, UnreachableBlock,
    ContextUnresolvable, DuplicateOutput, Finding, InvalidAnnotation, InvalidLoadingModel,
    InvalidProducedOutput, InvalidSource, LoadingDeclarationStale, LoadingRenderError,
    MissingConsumerFile, MissingContent, MissingDependency, MissingLinkTarget, OutputChanged,
    OutputNotDeployed, ProductDrift, ProductUnavailable,
    SkillMarkerMismatch, SkillMarkerMissing, SourceUncompiled, StaleContext, StaleGeneration,
    StaleProducedOutput, UnbundledLink, UndeclaredConsumerLink,
)

ANALYSIS_ERRORS = (OSError, ValueError, KeyError, TypeError)


def _where(subject):
    return ": ".join(str(subject[key]) for key in ("path", "block") if key in subject)


def _raise(check, finding, *, where=None):
    """The POI of one finding about the check's subject, with exactly its situation.

    `where` names the place for a reader when the subject only has ids for it.
    """
    subject = check.situation["subject"]
    details = {key: value for key, value in finding.data.items()
               if key not in subject and value not in (None, "")}
    return check.poi(finding.poi, details=details or None, message=finding.poi.sentence(
        where=where or _where(subject), target=finding.get("target", subject.get("target")),
        detail=finding.get("detail")))


def _result(check, findings, *, where=None, status="completed"):
    return CheckResult(check, status=status,
                       pois=tuple(_raise(check, finding, where=where) for finding in findings))


class SkillLoad:
    """A skill package loaded once for its Suite: its documents and reading graph,
    or why they do not load. Like `GitleaksHistory`, a resource its Checks share.
    """

    def __init__(self, package):
        self.package = package
        self.documents, self.graph, self.error = (), None, None
        try:
            self.documents = tuple(package.documents())
            self.graph = package.loading()
        except ANALYSIS_ERRORS as exc:
            self.error = str(exc)


# --- the skill ---------------------------------------------------------------

class SkillMarkerCheck(SituationCheck):
    """Does the skill folder hold the marker that names this skill?"""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("aa706659-3242-48a9-a5be-7d3c7317ec62"),
                          name="Tarav.SKW.Check.SkillMarker", workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, *, situation, package):
        super().__init__(situation=situation)
        self.package = package

    def _run(self):
        root = self.package.root
        if not (root / SKILL_JSON).is_file():
            return _result(self, [Finding(SkillMarkerMissing)])
        named = SkillMarker.of(root).id
        if named != self.package.skill_id:
            return _result(self, [Finding(SkillMarkerMismatch, detail=f"the marker names {named}")])
        return _result(self, [])


class SkillLoadingCheck(SituationCheck):
    """Do the sources and the loading model of the package load?"""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("2d9ad34b-5b7f-4311-b8a1-8a782e9431bc"),
                          name="Tarav.SKW.Check.SkillLoading", workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, *, situation, load):
        super().__init__(situation=situation)
        self.load = load

    def _run(self):
        if self.load.error is None:
            return _result(self, [])
        return _result(self, [Finding(InvalidLoadingModel, detail=self.load.error)])


# --- sources, products and blocks ---------------------------------------------

class SourceCheck(SituationCheck):
    """Can the source be read, and is it compiled with the loading model it has now?"""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e6c3d79a-ad56-454a-9b28-008c16d0c749"),
                          name="Tarav.SKW.Check.Source", workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, *, situation, document):
        super().__init__(situation=situation)
        self.document = document

    def _run(self):
        try:
            findings = self.document.source_findings()
        except ANALYSIS_ERRORS as exc:
            findings = [Finding(InvalidSource, detail=str(exc))]
        return _result(self, findings)


class ProductCheck(SituationCheck):
    """One compiled file: compiled from one source, listed among the files, readable."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("7b00d613-d5b3-4acb-bb70-df4aeb5b50db"),
                          name="Tarav.SKW.Check.Product", workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, *, situation, package, documents):
        super().__init__(situation=situation)
        self.package = package
        self.documents = tuple(documents)

    def _run(self):
        product = self.situation["subject"]["path"]
        findings = []
        if len(self.documents) > 1:
            findings.append(Finding(DuplicateOutput, detail=", ".join(
                document.key for document in self.documents)))
        if self.package.path(product) not in {self.package.path(p) for p in self.package.files}:
            findings.append(Finding(OutputNotDeployed))
        try:
            self.documents[0].product_text()
        except (OSError, UnicodeError) as exc:
            findings.append(Finding(ProductUnavailable, detail=str(exc)))
        return _result(self, findings)


class ProductDriftCheck(SituationCheck):
    """Does a compiled file hold what its source produces? Its caller read both texts."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("28ec7d20-6dad-4e38-83e2-8393ea82cef1"),
                          name="Tarav.SKW.Check.ProductDrift", workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, *, situation, package, document, actual, expected):
        super().__init__(situation=situation)
        self.package = package
        self.document = document
        self.actual = actual
        self.expected = expected

    def _run(self):
        if self.situation["actual"] == self.situation["expected"]:
            return _result(self, [])
        found = self.document.drift(self.actual, self.expected)
        product = self.situation["subject"]["path"]
        poi = self.poi(ProductDrift,
                       message=f"{self.package.root.name}: {product} differs from what its "
                               f"source produces ({found['detail']})",
                       # what helps whoever works on it: the source to edit, and the lines
                       details={"source": found["source"],
                                "difference": list(found["difference"])})
        return CheckResult(self, status="completed", pois=(poi,))


class BlockCheck(SituationCheck):
    """One block of a source: its content, and the output recorded for it."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("1c5ca03e-947f-4525-be08-2973bbdd620d"),
                          name="Tarav.SKW.Check.Block", workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, *, situation, document):
        super().__init__(situation=situation)
        self.document = document

    def _run(self):
        block = self.situation["subject"]["block"]
        return _result(self, self.document.block_findings(block, freshness=False))


# tarav.breadcrumb 815517b13112
class GenerationContextResolutionCheck(SituationCheck):
    """Resolve one declared generation-context entry."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("555f8dcd-b836-4b24-88fc-70440a576074"),
                          name="Tarav.SKW.Check.GenerationContextResolution",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, *, situation, document):
        super().__init__(situation=situation)
        self.document = document

    def _run(self):
        subject = self.situation["subject"]
        try:
            self.document._resolved_context(subject["block"], selected=subject["context_index"])
        except ANALYSIS_ERRORS as exc:
            return _result(self, [Finding(ContextUnresolvable, detail=str(exc))])
        return CheckResult(self, status="completed", data={**subject, "status": "resolved"})


def _freshness_result(check, *, poi_type, baseline_key, current_key):
    if check.situation[baseline_key] == check.situation[current_key]:
        return CheckResult(check, status="completed")
    # the situation holds both sides already; there is nothing more to tell
    poi = check.poi(poi_type, message=poi_type.sentence(where=_where(check.situation["subject"])))
    return CheckResult(check, status="completed", pois=(poi,))


# tarav.breadcrumb 9374fbc4f10a
class GenerationFreshnessCheck(SituationCheck):
    """Compare retained and current generation inputs from one bound snapshot."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("2378413d-f295-4034-8ce0-f92049f09f6b"),
                          name="Tarav.SKW.Check.GenerationFreshness",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def _run(self):
        return _freshness_result(self, poi_type=StaleGeneration,
                                 baseline_key="baseline_inputs", current_key="current_inputs")


class ContextFreshnessCheck(SituationCheck):
    """Compare retained and current tracked context from one bound snapshot."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("101a3e88-45c7-45de-b9ea-b28351099c93"),
                          name="Tarav.SKW.Check.ContextFreshness",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def _run(self):
        return _freshness_result(self, poi_type=StaleContext,
                                 baseline_key="baseline_context", current_key="current_context")


# --- what the package lists ----------------------------------------------------

class ConsumerFileCheck(SituationCheck):
    """Does a file that the package lists exist?"""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("f8bded79-7b9c-41cf-a2db-6a96ab41fc78"),
                          name="Tarav.SKW.Check.ConsumerFile", workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, *, situation, package):
        super().__init__(situation=situation)
        self.package = package

    def _run(self):
        found = not self.package.path(self.situation["subject"]["path"]).is_file()
        return _result(self, [Finding(MissingConsumerFile)] if found else [])


class ConsumerLinkCheck(SituationCheck):
    """One link in a Markdown file of the package: bundled, or owned by a declared
    consumer dependency, and pointing at a file. Output conformance only: a link
    never contributes loading edges.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("dbf7bc46-d8b1-46fc-9f1c-cc679fc2ed53"),
                          name="Tarav.SKW.Check.ConsumerLink", workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, *, situation, package):
        super().__init__(situation=situation)
        self.package = package

    def _run(self):
        package, subject = self.package, self.situation["subject"]
        link = subject["target"]
        target = (package.path(subject["path"]).parent
                  / unquote(urlsplit(link.strip("<>")).path)).resolve()
        findings = []
        if target.is_relative_to(package.root):
            if target not in {package.path(p) for p in package.files}:
                findings.append(Finding(UnbundledLink))
        else:
            owners = [(package.root / d["path"]).resolve() for d in package.dependencies
                      if d["kind"] == "skill" and "consumer" in d["purposes"]]
            if not any(target.is_relative_to(owner) for owner in owners):
                findings.append(Finding(UndeclaredConsumerLink))
        if not target.is_file():
            findings.append(Finding(MissingLinkTarget))
        return _result(self, findings)


class DependencyCheck(SituationCheck):
    """Does a declared dependency of the package exist?"""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("23f11ce5-1885-4867-957d-e09169746f20"),
                          name="Tarav.SKW.Check.Dependency", workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, *, situation, package, dependency):
        super().__init__(situation=situation)
        self.package = package
        self.dependency = deepcopy(dependency)

    def _run(self):
        target = (self.package.root / self.dependency["path"]).resolve()
        if self.dependency["kind"] == "skill":
            target /= "SKILL.md"
        if target.is_file():
            return _result(self, [])
        return _result(self, [Finding(MissingDependency,
                                      detail=",".join(self.dependency["purposes"]))])


# --- the chains -----------------------------------------------------------------

class SkillMarkerChain(SituationChain):
    """The marker of one skill folder."""
    Check = SkillMarkerCheck
    POIs = (SkillMarkerMissing, SkillMarkerMismatch)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("9d3d5b3d-b22e-4df2-a9a5-7b5406a3918b"),
                          name="Tarav.SKW.Chain.SkillMarker", workflow=SKW_SKILLS_WORKFLOW_SHIP)


class SkillLoadingChain(SituationChain):
    """The loading of one skill package."""
    Check = SkillLoadingCheck
    POIs = (InvalidLoadingModel,)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ba80de3d-9659-4096-a776-50ef0a4e7e93"),
                          name="Tarav.SKW.Chain.SkillLoading", workflow=SKW_SKILLS_WORKFLOW_SHIP)


class SourceChain(SituationChain):
    """One source of a package."""
    Check = SourceCheck
    POIs = (InvalidSource, SourceUncompiled, LoadingDeclarationStale, LoadingRenderError)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("07da01b7-7d92-49b1-bf4c-82d305547b10"),
                          name="Tarav.SKW.Chain.Source", workflow=SKW_SKILLS_WORKFLOW_SHIP)


class ProductChain(SituationChain):
    """One compiled file of a package."""
    Check = ProductCheck
    POIs = (DuplicateOutput, OutputNotDeployed, ProductUnavailable)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("7d25e718-5086-40a8-a6fd-8e8f3b46dc8a"),
                          name="Tarav.SKW.Chain.Product", workflow=SKW_SKILLS_WORKFLOW_SHIP)


class ProductDriftChain(SituationChain):
    """A compiled file and the text its source produces, as they were read."""
    Check = ProductDriftCheck
    POIs = (ProductDrift,)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("bf689637-d086-47c8-8b2f-8eeeaee31dfb"),
                          name="Tarav.SKW.Chain.ProductDrift", workflow=SKW_SKILLS_WORKFLOW_SHIP)


class BlockChain(SituationChain):
    """One block of a source."""
    Check = BlockCheck
    POIs = (MissingContent, OutputChanged, InvalidAnnotation, InvalidProducedOutput,
            StaleProducedOutput)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("6d301fc3-9c56-4d8f-a8af-54a572fbcc72"),
                          name="Tarav.SKW.Chain.Block", workflow=SKW_SKILLS_WORKFLOW_SHIP)


class GenerationContextResolutionChain(SituationChain):
    """One declared context entry of a generated block."""
    Check = GenerationContextResolutionCheck
    POIs = (ContextUnresolvable,)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("9556b00f-ee7d-4b3e-bf16-914f2fa7f1bd"),
                          name="Tarav.SKW.Chain.GenerationContextResolution",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)


class GenerationFreshnessChain(SituationChain):
    """The recorded and current generation inputs of one block."""
    Check = GenerationFreshnessCheck
    POIs = (StaleGeneration,)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("31cdde75-e4bc-4925-b5d0-751250f051d4"),
                          name="Tarav.SKW.Chain.GenerationFreshness",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)


class ContextFreshnessChain(SituationChain):
    """The recorded and current tracked context of one block."""
    Check = ContextFreshnessCheck
    POIs = (StaleContext,)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("64e5ee5a-0ec7-4b2e-8f60-edc99adb1dd5"),
                          name="Tarav.SKW.Chain.ContextFreshness",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)


class ConsumerFileChain(SituationChain):
    """One file that a package lists."""
    Check = ConsumerFileCheck
    POIs = (MissingConsumerFile,)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("9d12a07d-812b-48b0-845e-9ce719e16afd"),
                          name="Tarav.SKW.Chain.ConsumerFile", workflow=SKW_SKILLS_WORKFLOW_SHIP)


class ConsumerLinkChain(SituationChain):
    """One link in a Markdown file of a package."""
    Check = ConsumerLinkCheck
    POIs = (UnbundledLink, UndeclaredConsumerLink, MissingLinkTarget)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("3a62f461-5e1e-4fc1-95d2-4436b1f2c585"),
                          name="Tarav.SKW.Chain.ConsumerLink", workflow=SKW_SKILLS_WORKFLOW_SHIP)


class DependencyChain(SituationChain):
    """One declared dependency of a package."""
    Check = DependencyCheck
    POIs = (MissingDependency,)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("2d477830-34fe-41ba-8685-a346d9f9363f"),
                          name="Tarav.SKW.Chain.Dependency", workflow=SKW_SKILLS_WORKFLOW_SHIP)


# --- the reading graph -------------------------------------------------------------

# tarav.breadcrumb 0172e2d45dbd
class ReadingAnalysis:
    """The reading analysis of one package, run once for its Suite.

    It is one traversal of the whole graph: reachability, cycles and the paths
    that reach a block cannot be decided per block. So it is the native report,
    as Gitleaks' report is, and each reading Check reads its own subject's part.
    """

    def __init__(self, graph):
        self.graph = graph
        result = graph.analyze()
        self.complete = result["complete"]
        self.found = defaultdict(list)
        for finding in result["diagnostics"]:
            target = finding.get("target")
            self.found[(finding.get("block"), None if target is None else str(target))].append(
                finding)
        self.observations = result["requirements"]

    def findings(self, types, block=None, target=None):
        """What the analysis found of `types` about one subject, each Type once."""
        found = {}
        for finding in self.found[(block, target)]:
            if finding.poi in types:
                found.setdefault(finding.poi, finding)
        return list(found.values())

    # tarav.breadcrumb 15c7f0c5dc4c
    def ship(self, node):
        """A block as a situation names it: its Ship, or the node id it was declared with."""
        binding = self.graph.bindings.get(node)
        return str(binding[1].id) if binding else node

    def where(self, node):
        """A block as a reader knows it: its document and label."""
        binding = self.graph.bindings.get(node)
        return f"{binding[0].key}: {binding[1].label}" if binding else None

    def status(self):
        return "completed" if self.complete else "incomplete"


class ReadingGraphCheck(SituationCheck):
    """The graph as a whole: its root, and whether the analysis visited every path."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("05bff74a-5aee-4fb2-a95d-3feace1d260d"),
                          name="Tarav.SKW.Check.ReadingGraph", workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, *, situation, analysis):
        super().__init__(situation=situation)
        self.analysis = analysis

    def _run(self):
        graph, findings = self.analysis.graph, []
        if graph.root not in graph.bindings:
            findings.append(Finding(InvalidLoadingRoot, detail=f"root: {graph.root}"))
        elif graph.parents[graph.root]:
            findings.append(Finding(RootHasParent, detail=f"root: {self.analysis.where(graph.root)}"))
        findings.extend(self.analysis.findings((LoadingAnalysisIncomplete,)))
        return _result(self, findings, status=self.analysis.status())


class ReadingNodeCheck(SituationCheck):
    """One declared block of the loading model: bound, reached, in no cycle."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("45292b6a-4206-43d6-87d1-80042607472f"),
                          name="Tarav.SKW.Check.ReadingNode", workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, *, situation, analysis, node):
        super().__init__(situation=situation)
        self.analysis = analysis
        self.node = node

    def _run(self):
        found = self.analysis.findings(
            (InvalidBlockReference, UnreachableBlock, AttachmentCycle, InclusionCycle), self.node)
        return _result(self, found, where=self.analysis.where(self.node),
                       status=self.analysis.status())


class ReadingDeclarationCheck(SituationCheck):
    """One target a block declares, as a parent or in a reading declaration: does it resolve?"""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("870eecfd-9186-4c46-8634-93a71158e3ec"),
                          name="Tarav.SKW.Check.ReadingDeclaration",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, *, situation, analysis, node):
        super().__init__(situation=situation)
        self.analysis = analysis
        self.node = node

    def _run(self):
        found = self.analysis.findings((InvalidParent, InvalidContextTarget), self.node,
                                       self.situation["subject"]["target"])
        return _result(self, found, where=self.analysis.where(self.node))


class BlockBindingCheck(SituationCheck):
    """Is one block of a source declared in the loading model?"""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("aa628f66-98e4-45f9-ad19-64b1905d2aff"),
                          name="Tarav.SKW.Check.BlockBinding", workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, *, situation, graph, document):
        super().__init__(situation=situation)
        self.graph = graph
        self.document = document

    def _run(self):
        label = self.situation["subject"]["block"]
        bound = (self.document.source, label) in self.graph.by_block
        return _result(self, [] if bound else [Finding(UndeclaredBlock)])


class ReadingRequirementCheck(SituationCheck):
    """One context requirement of a block, over every path that reaches it: is it
    delivered on all of them or on none? Its caller gives the observations."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("2c4a0b22-d9e2-4118-95ee-d3558ca86bc8"),
                          name="Tarav.SKW.Check.ReadingRequirement",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, *, situation, analysis, node, observations):
        super().__init__(situation=situation)
        self.analysis = analysis
        self.node = node
        self.observations = tuple(observations)

    def _run(self):
        satisfied = [observation["satisfied"] for observation in self.observations]
        mixed = any(satisfied) and not all(satisfied)
        return _result(self, [Finding(PathDependentContext)] if mixed else [],
                       where=self.analysis.where(self.node), status=self.analysis.status())


# tarav.breadcrumb ba01fcb9a242
class ReadingPathCheck(SituationCheck):
    """One context requirement of a block on one reading path: is it delivered there?
    The path is part of the situation: a check names the unmet dependency and the
    path that misses it. Its caller gives what the analysis observed on that path."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d299550a-b1c2-4eba-990f-9e71b3bff122"),
                          name="Tarav.SKW.Check.ReadingPath", workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, *, situation, analysis, node, observation):
        super().__init__(situation=situation)
        self.analysis = analysis
        self.node = node
        self.observation = deepcopy(observation)

    def _run(self):
        found = [] if self.observation["satisfied"] else [Finding(
            MissingContext, inlined=self.observation["inlined"],
            referenced=self.observation["referenced"])]
        return _result(self, found, where=self.analysis.where(self.node),
                       status=self.analysis.status())


# tarav.breadcrumb d17fbd7e081f
class LinkProseCheck(SituationCheck):
    """Does the text of a block hold the link one of its declarations expects?

    The other reading checks trust the declarations; this one is for the
    maintainers, who care that the text holds what is declared.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ac970186-220f-43c4-984a-b6fd94a88227"),
                          name="Tarav.SKW.Check.LinkProse", workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, *, situation, analysis, node, link):
        super().__init__(situation=situation)
        self.analysis = analysis
        self.node = node
        self.link = link

    def _run(self):
        found = self.analysis.graph.link_prose_findings(self.node, self.link)
        return _result(self, [Finding(finding.poi) for finding in found],
                       where=self.analysis.where(self.node))


def reading_checks(package, analysis):
    """The reading Checks of one package, each with the situation built from the analysis."""

    graph, owner = analysis.graph, package.owner
    yield ReadingGraphChain({"subject": owner}).check(analysis=analysis)
    for node in graph.nodes:
        block = {**owner, "block": analysis.ship(node)}
        yield ReadingNodeChain({"subject": block}).check(analysis=analysis, node=node)
        targets = list(graph.parents.get(node, ()))
        if node in graph.bindings:
            targets.extend(declaration.target for declaration in graph.reading[node])
            bound = graph.bindings[node][1]
            if isinstance(bound, SkillLink):
                targets.append(bound["target"])
        for target in dict.fromkeys(str(target) for target in targets):
            yield ReadingDeclarationChain({"subject": {**block, "target": target}}).check(
                analysis=analysis, node=node)
    for document in graph.documents.values():
        for label in document.blocks:
            yield BlockBindingChain({"subject": {**owner, "path": document.key, "block": label}}).check(
                graph=graph, document=document)
    for node, requirements in graph.requirements.items():
        for declaration, target in requirements:
            requirement = {**owner, "block": analysis.ship(node), "target": str(target),
                           "delivery": declaration.delivery}
            observations = [observation for observation in analysis.observations
                            if (observation["block"], observation["target"],
                                observation["delivery"]) == (node, str(target),
                                                             declaration.delivery)]
            yield ReadingRequirementChain({"subject": requirement}).check(
                analysis=analysis, node=node, observations=observations)
            paths = {}
            for observation in observations:
                paths.setdefault(tuple(analysis.ship(step) for step in observation["path"]),
                                 observation)
            for path, observation in paths.items():
                yield ReadingPathChain({"subject": {**requirement, "path": list(path)}}).check(
                    analysis=analysis, node=node, observation=observation)
    for node, links in graph.links.items():
        for link in links:
            href = graph.prose_href(node, link)
            if href is not None:
                yield LinkProseChain({"subject": {**owner, "block": analysis.ship(node),
                                                  "target": href}}).check(
                    analysis=analysis, node=node, link=link)


class ReadingGraphChain(SituationChain):
    """The reading graph of one package as a whole."""
    Check = ReadingGraphCheck
    POIs = (InvalidLoadingRoot, RootHasParent, LoadingAnalysisIncomplete)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("625475a8-b78a-4d93-977b-bcb544f0f22c"),
                          name="Tarav.SKW.Chain.ReadingGraph", workflow=SKW_SKILLS_WORKFLOW_SHIP)


class ReadingNodeChain(SituationChain):
    """One declared block of a loading model."""
    Check = ReadingNodeCheck
    POIs = (InvalidBlockReference, UnreachableBlock, AttachmentCycle, InclusionCycle)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ff663df6-b0cc-42e0-9086-17ecf134ecce"),
                          name="Tarav.SKW.Chain.ReadingNode", workflow=SKW_SKILLS_WORKFLOW_SHIP)


class ReadingDeclarationChain(SituationChain):
    """One target a block declares."""
    Check = ReadingDeclarationCheck
    POIs = (InvalidParent, InvalidContextTarget)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ca2aff33-8a88-46ee-b6db-97aee73d4143"),
                          name="Tarav.SKW.Chain.ReadingDeclaration",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)


class BlockBindingChain(SituationChain):
    """One block of a source and the loading model that should declare it."""
    Check = BlockBindingCheck
    POIs = (UndeclaredBlock,)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("f93600cd-4cdd-44df-a8b0-3fe20745c952"),
                          name="Tarav.SKW.Chain.BlockBinding", workflow=SKW_SKILLS_WORKFLOW_SHIP)


class ReadingRequirementChain(SituationChain):
    """One context requirement of a block, over all its reading paths."""
    Check = ReadingRequirementCheck
    POIs = (PathDependentContext,)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("8c84935a-6c89-4631-bbe9-9178be9e48bf"),
                          name="Tarav.SKW.Chain.ReadingRequirement",
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)


class ReadingPathChain(SituationChain):
    """One context requirement of a block on one reading path."""
    Check = ReadingPathCheck
    POIs = (MissingContext,)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b66a61f8-cf08-48c8-b5b3-89bf7b4cce19"),
                          name="Tarav.SKW.Chain.ReadingPath", workflow=SKW_SKILLS_WORKFLOW_SHIP)


class LinkProseChain(SituationChain):
    """One declared link whose prose part the text of its block should hold."""
    Check = LinkProseCheck
    POIs = (MissingMarkdownLink,)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("52bdce1d-f566-4407-8bcd-e75634dfee24"),
                          name="Tarav.SKW.Chain.LinkProse", workflow=SKW_SKILLS_WORKFLOW_SHIP)


SKW_CHAINS = (
    SkillMarkerChain, SkillLoadingChain, SourceChain, ProductChain,
    ProductDriftChain, BlockChain, GenerationContextResolutionChain, GenerationFreshnessChain,
    ContextFreshnessChain, ConsumerFileChain, ConsumerLinkChain, DependencyChain,
    ReadingGraphChain, ReadingNodeChain, ReadingDeclarationChain, BlockBindingChain,
    ReadingRequirementChain, ReadingPathChain, LinkProseChain,
)


# --- the Suite --------------------------------------------------------------------

def document_checks(package, document, *, skip_unresolved=True):
    """The Checks of one source, each with the situation built from it now."""

    owner, source = package.owner, document.key
    yield SourceChain({"subject": {**owner, "path": source}}).check(document=document)
    expected = document.expected_text()
    try:
        actual = document.product_text()
    except (OSError, UnicodeError):
        actual = None  # the Product Check says so
    if actual is not None and expected is not None:
        product = document.target.relative_to(package.root).as_posix()
        yield ProductDriftChain({"subject": {**owner, "path": product},
                                 "actual": _hash(actual), "expected": _hash(expected)}).check(
            package=package, document=document, actual=actual, expected=expected)
    for label in document.blocks:
        yield BlockChain({"subject": {**owner, "path": source, "block": label}}).check(
            document=document)
    yield from _context_resolution_checks(package, document)
    yield from _freshness_checks(package, document, skip_unresolved=skip_unresolved)


def _context_resolution_checks(package, document):
    for block in document.blocks.values():
        annotation = block.annotation(GenerationAnnotation)
        if annotation is None:
            continue
        declarations = annotation.typed.context
        objects = annotation.context_objects(block)
        for index, (declaration, value) in enumerate(zip(declarations, objects, strict=True)):
            if not isinstance(value, Reference):
                continue
            subject = {**package.owner, "path": document.key, "block": block.label,
                       "context_index": index}
            yield GenerationContextResolutionChain(
                {"subject": subject, "declaration": deepcopy(declaration)}).check(
                document=document)


def _freshness_checks(package, document, *, skip_unresolved):
    """Resolve external inputs once; each Check compares from that snapshot."""
    entry = document.lock()["documents"].get(document.key, {})
    for block, baseline in entry.get("blocks", {}).items():
        if not isinstance(baseline, dict) or "input_hash" not in baseline:
            continue
        try:
            current = document.generation_fingerprint(block)
        except ANALYSIS_ERRORS as exc:
            if skip_unresolved:
                continue
            raise ValueError(
                f"Cannot build generation freshness Situation: {document.key}:{block}") from exc
        yield GenerationFreshnessChain({
            "subject": {**package.owner, "path": document.key, "block": block},
            "baseline_inputs": baseline["input_hash"], "current_inputs": current}).check()
    for block, baseline in entry.get("contexts", {}).items():
        try:
            current = document._context_hash(document._resolved_context(block))
        except ANALYSIS_ERRORS as exc:
            if skip_unresolved:
                continue
            raise ValueError(
                f"Cannot build context freshness Situation: {document.key}:{block}") from exc
        yield ContextFreshnessChain({
            "subject": {**package.owner, "path": document.key, "block": block},
            "baseline_context": baseline, "current_context": current}).check()


def _links(package, value):
    """The distinct local links of one Markdown file of the package."""
    found = {}
    for link in re.findall(r"\]\(([^\s)]+)\)", package.path(value).read_text()):
        parts = urlsplit(link.strip("<>"))
        if not (parts.scheme or parts.netloc or not parts.path):
            found[link] = None
    return tuple(found)


# tarav.breadcrumb 6878eaee3b17
class SkwSkillSuite(CheckSuite):
    """The Checks of one skill package: it loads the package once, finds the
    situations, and runs one atomic Check per situation. Each source's Checks
    are a nested suite named by the source.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("f1a87eca-c954-441e-a94c-29ef4099c442"),
                          name="Tarav.SKW.Suite.Skill", workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def __init__(self, package):
        self.package = package
        # keyed, so that an action knows which skill package detected it
        super().__init__(name=package.root.name, key=str(package.skill_id))

    def produce(self):
        package = self.package
        skill = {"subject": package.owner}
        yield SkillMarkerChain(skill).check(package=package)
        load = SkillLoad(package)
        yield SkillLoadingChain(skill).check(load=load)
        if load.error is not None:
            return
        products = defaultdict(list)
        for document in load.documents:
            products[document.target.relative_to(package.root).as_posix()].append(document)
        for product, documents in products.items():
            yield ProductChain({"subject": {**package.owner, "path": product}}).check(
                package=package, documents=documents)
        for document in load.documents:
            yield CheckSuite(document_checks(package, document), name=document.key)
        for value in package.files:
            subject = {**package.owner, "path": value}
            yield ConsumerFileChain({"subject": subject}).check(package=package)
            if value.endswith(".md") and package.path(value).is_file():
                for link in _links(package, value):
                    yield ConsumerLinkChain({"subject": {**subject, "target": link}}).check(
                        package=package)
        for dependency in package.dependencies:
            yield DependencyChain({"subject": {**package.owner, "path": dependency["path"]}}).check(
                package=package, dependency=dependency)
        yield CheckSuite(reading_checks(package, ReadingAnalysis(load.graph)), name="reading")


SKW_CHAIN_CHECK_TYPES = tuple(chain.Check for chain in SKW_CHAINS)
