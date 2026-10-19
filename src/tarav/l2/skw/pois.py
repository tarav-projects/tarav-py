"""The checks that raise Skillware POIs. Open a POI's Type from finding.help for policy.

The analysis lives in tarav.l1.skw (document.py, loading.py, skills.py) and
in skw/skills.py and skw/publication.py here; it reports findings that name
their POI Type (tarav.l1.skw.pois). The checks here bind a finding to the
package it was found in and raise its POI.
"""
from copy import deepcopy
import os

from tarav.l0.kernel import TaravClass
from tarav.l0.kernel import TypeShip
from tarav.l1.checks import Check, CheckResult, SituationCheck
from tarav.l1.poi import POICollector
from tarav.l1.references import Reference
from tarav.l1.skw.annotations import GenerationAnnotation
from tarav.l1.skw.identity import SKW_SKILLS_WORKFLOW_SHIP
from tarav.l1.skw.pois import ContextUnresolvable, Finding, StaleContext, StaleGeneration


class SkwAnalysisCheck(Check):
    """Adapt existing SKW analysis output to bound workflow-owned POIs."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("fdfb213f-fb73-4fb6-882a-4782a66eb656"),
            name="Tarav.SKW.Check.Analysis",
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )

    def __init__(self, package, findings):
        super().__init__()
        self.package = package
        self.findings = tuple(findings)

    def _run(self):
        return CheckResult(self, status="completed", pois=_analysis_pois(self))


# tarav.breadcrumb 815517b13112
class GenerationContextResolutionCheck(Check):
    """Resolve one declared generation-context entry when explicitly run."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("555f8dcd-b836-4b24-88fc-70440a576074"),
            name="Tarav.SKW.Check.GenerationContextResolution",
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )

    def __init__(self, package, document, block, index, declaration):
        super().__init__()
        self.package = package
        self.document = document
        self.block = block
        self.index = index
        self.declaration = deepcopy(declaration)
        self.subject = {
            **package.owner,
            "path": document.key,
            "block": block.label,
            "context_index": index,
        }

    def _run(self):
        try:
            self.document._resolved_context(self.block.label, selected=self.index)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            poi = ContextUnresolvable.poi(
                self,
                situation={
                    "subject": self.subject,
                    "declaration": deepcopy(self.declaration),
                },
                finding=Finding(ContextUnresolvable, path=self.document.key,
                                block=self.block.label, context_index=self.index,
                                detail=str(exc)),
            )
            return CheckResult(self, status="completed", pois=(poi,))
        return CheckResult(
            self,
            status="completed",
            data={**self.subject, "status": "resolved"},
        )


def generation_context_resolution_checks(package, *, documents=None):
    """One independently runnable Check per typed context declaration."""

    selected = package.documents() if documents is None else documents
    checks = []
    for document in selected:
        for block in document.blocks.values():
            annotation = block.annotation(GenerationAnnotation)
            if annotation is None:
                continue
            declarations = annotation.typed.context
            objects = annotation.context_objects(block)
            for index, (declaration, value) in enumerate(
                zip(declarations, objects, strict=True)
            ):
                if not isinstance(value, Reference):
                    continue
                checks.append(
                    GenerationContextResolutionCheck(
                        package, document, block, index, declaration
                    )
                )
    return tuple(checks)


def _freshness_result(check, *, poi_type, baseline_key, current_key):
    subject = check.situation["subject"]
    if not isinstance(subject, dict):
        raise TypeError("Freshness Situation subject must be an object")
    baseline = check.situation[baseline_key]
    current = check.situation[current_key]
    if baseline == current:
        return CheckResult(check, status="completed")
    # the situation holds both sides already; there is nothing more to tell
    where = ": ".join(str(subject[key]) for key in ("path", "block") if key in subject)
    poi = check.poi(poi_type, message=poi_type.sentence(where=where))
    return CheckResult(check, status="completed", pois=(poi,))


# tarav.breadcrumb 9374fbc4f10a
class GenerationFreshnessCheck(SituationCheck):
    """Compare retained and current generation inputs from one bound snapshot."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("2378413d-f295-4034-8ce0-f92049f09f6b"),
            name="Tarav.SKW.Check.GenerationFreshness",
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )

    def _run(self):
        return _freshness_result(
            self,
            poi_type=StaleGeneration,
            baseline_key="baseline_inputs",
            current_key="current_inputs",
        )


class ContextFreshnessCheck(SituationCheck):
    """Compare retained and current tracked context from one bound snapshot."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("101a3e88-45c7-45de-b9ea-b28351099c93"),
            name="Tarav.SKW.Check.ContextFreshness",
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )

    def _run(self):
        return _freshness_result(
            self,
            poi_type=StaleContext,
            baseline_key="baseline_context",
            current_key="current_context",
        )


def freshness_checks(package, *, skip_unresolved=False, documents=None):
    """Resolve external inputs once and return independently runnable checks."""

    checks = []
    selected = package.documents() if documents is None else documents
    for document in selected:
        entry = document.lock()["documents"].get(document.key, {})
        for block, baseline in entry.get("blocks", {}).items():
            if not isinstance(baseline, dict) or "input_hash" not in baseline:
                continue
            try:
                current = document.generation_fingerprint(block)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                if skip_unresolved:
                    continue
                raise ValueError(
                    f"Cannot build generation freshness Situation: {document.key}:{block}"
                ) from exc
            subject = {
                **package.owner,
                "path": document.key,
                "block": block,
            }
            checks.append(GenerationFreshnessCheck(situation={
                "subject": subject,
                "baseline_inputs": baseline["input_hash"],
                "current_inputs": current,
            }))
        for block, baseline in entry.get("contexts", {}).items():
            try:
                current = document._context_hash(document._resolved_context(block))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                if skip_unresolved:
                    continue
                raise ValueError(
                    f"Cannot build context freshness Situation: {document.key}:{block}"
                ) from exc
            subject = {
                **package.owner,
                "path": document.key,
                "block": block,
            }
            checks.append(ContextFreshnessCheck(situation={
                "subject": subject,
                "baseline_context": baseline,
                "current_context": current,
            }))
    return tuple(checks)


#: The Types that only the freshness checks raise, each from one bound snapshot.
FRESHNESS = (StaleContext, StaleGeneration)


# tarav.breadcrumb f47dbffc1e5d
def surface_state(package):
    """Current declared source and product bytes, by path relative to the package's Project.

    A detail of the POIs, never part of their situation: it changes with any
    file of the package, and a problem keeps its identity across unrelated
    edits. Skillware POIs pin it, so a blessing cannot float across later
    source edits.
    """
    from .publication import digest
    paths = {package.depot / 'main.json', package.depot / 'lock.json'}
    paths.update(package.depot_path(s) for s in package.sources)
    paths.update(package.depot_path(s) for s in package.publications or [])
    paths.update(package.path(s) for s in package.files)
    if package.loading_file is not None:
        paths.add(package.depot_path(package.loading_file))
    project = package.project
    state = {}
    for path in sorted(paths):
        key = os.path.relpath(path, project)
        try:
            state[key] = digest(path.read_bytes().hex())
        except OSError:
            state[key] = None
    return state


# tarav.breadcrumb d778cc4afbfa
def _analysis_pois(check):
    state = surface_state(check.package)
    for finding in check.findings:
        if finding.poi in FRESHNESS:
            raise ValueError("Freshness findings must be produced by SituationChecks")
        yield finding.poi.from_finding(check, finding, root=check.package.root,
                                       owner=check.package.owner, state=state)


def collect(package, findings):
    collector = POICollector()
    for poi in SkwAnalysisCheck(package, findings).run().pois():
        collector.emit(poi)
    return collector
