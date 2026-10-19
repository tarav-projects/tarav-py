"""Skillware analysis as Situation Chains: one atomic Check per situation of a skill package.

A skill's Suite (`SkwSkillSuite`) loads the package once (`SkillLoad`), finds
its situations — the skill, each source, product, block, consumer file, link,
dependency and publication — and runs the Check of each one's chain with the
situation it built. The rules stay in the native analysis (`tarav.l1.skw`),
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
from tarav.l1.skw.pois import (
    ContextUnresolvable, DuplicateOutput, Finding, InvalidAnnotation, InvalidLoadingModel,
    InvalidProducedOutput, InvalidSource, LoadingDeclarationStale, LoadingRenderError,
    MissingConsumerFile, MissingContent, MissingDependency, MissingLinkTarget, OutputChanged,
    OutputNotDeployed, ProductDrift, ProductUnavailable, PublicationDisconnected,
    SkillMarkerMismatch, SkillMarkerMissing, SourceUncompiled, StaleContext, StaleGeneration,
    StaleProducedOutput, UnbundledLink, UndeclaredConsumerLink,
)

from .reading_checks import reading_checks

ANALYSIS_ERRORS = (OSError, ValueError, KeyError, TypeError)


def _where(subject):
    return ": ".join(str(subject[key]) for key in ("path", "block") if key in subject)


def _raise(check, finding):
    """The POI of one finding about the check's subject, with exactly its situation."""
    subject = check.situation["subject"]
    details = {key: value for key, value in finding.data.items()
               if key not in subject and value not in (None, "")}
    return check.poi(finding.poi, details=details or None, message=finding.poi.sentence(
        where=_where(subject), target=finding.get("target", subject.get("target")),
        detail=finding.get("detail")))


def _result(check, findings):
    return CheckResult(check, status="completed",
                       pois=tuple(_raise(check, finding) for finding in findings))


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


class PublicationCheck(SituationCheck):
    """A declared Model publication: none is connected while publications await a redesign."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("24504ebc-9ac4-411d-b26b-f256b9ee28c0"),
                          name="Tarav.SKW.Check.Publication", workflow=SKW_SKILLS_WORKFLOW_SHIP)

    def _run(self):
        return _result(self, [Finding(PublicationDisconnected,
                                      detail="Models publication is disconnected pending redesign.")])


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


class PublicationChain(SituationChain):
    """One declared Model publication."""
    Check = PublicationCheck
    POIs = (PublicationDisconnected,)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d4f59755-5fd6-4ad1-93cf-82557c7a20e9"),
                          name="Tarav.SKW.Chain.Publication", workflow=SKW_SKILLS_WORKFLOW_SHIP)


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


SKW_CHAINS = (
    SkillMarkerChain, SkillLoadingChain, PublicationChain, SourceChain, ProductChain,
    ProductDriftChain, BlockChain, GenerationContextResolutionChain, GenerationFreshnessChain,
    ContextFreshnessChain, ConsumerFileChain, ConsumerLinkChain, DependencyChain,
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
        for source in package.publications or []:
            yield PublicationChain({"subject": {**package.owner, "path": source}}).check()
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
        yield from reading_checks(load.graph)


SKW_CHAIN_CHECK_TYPES = tuple(chain.Check for chain in SKW_CHAINS)
