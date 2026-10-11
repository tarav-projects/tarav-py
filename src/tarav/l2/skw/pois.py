"""SKW-owned POI classes. Open this source from finding.help for policy.

Checks live in skw/loading.py, skw/skills.py, skw/publication.py and
skw/document.py. Only annotation omissions and semantic freshness
questions permit attributed acceptance. Structural failures require repair.
"""
from copy import deepcopy

from tarav.l0.kernel import TaravClass, entity
from tarav.l0.kernel import TypeShip
from tarav.l1.poi.actionable import BlessablePOI
from tarav.l1.checks import Check, CheckPOI, CheckResult, SituationCheck
from tarav.l1.poi import POICollector
from tarav.l1.references import Reference
from tarav.l1.skw.annotations import GenerationAnnotation
from tarav.l1.skw.identity import SKW_SKILLS_WORKFLOW_SHIP


class SkwPOI(CheckPOI):
    """A workflow-owned SKW POI explained by the bound analysis Check."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('6e215eaf-b1d4-4ff9-ae51-9a89e542ffd3'),
            name='Tarav.SKW.POI',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )

    @classmethod
    # tarav.breadcrumb 358f9776a4d31e8930d727fec6ccb95407790af6d2893c204b16cb9cb572cde9
    def poi(cls, check, subject, *, situation, evidence=None):
        evidence = evidence or {}
        raw = evidence.get("finding", {})
        # The class already states the kind; the lint key only supplies a fallback message.
        message = (raw.get("detail") or raw.get("message") or raw.get("kind")
                   or entity(cls).name.rsplit(".", 1)[-1])
        return cls(
            check,
            str(message),
            situation=situation,
            details=evidence,
            subject=subject,
            evidence=evidence,
        )


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


class UnannotatedOutputLink(SkwPOI, BlessablePOI):
    """An authored Markdown link has no SKW link primitive declaration.

    SkillReadingGraph binds source blocks, then parses their authored output
    solely for conformance. This link contributes no simulated context edge.
    Bless only an intentionally unmodeled link after evaluating its consumer
    effect; an acceptance does not add an edge or satisfy a context requirement.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000001'),
            name='Tarav.SKW.POI.UnannotatedOutputLink',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class MissingContext(SkwPOI):
    """SkillReadingGraph found a requirement without its requested delivery.

    Evidence identifies the target, delivery and exact incoming path. Correct
    declarations or delivery primitives; this class does not permit blessing.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000002'),
            name='Tarav.SKW.POI.MissingContext',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class PathDependentContext(SkwPOI):
    """path-dependent-context: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000003'),
            name='Tarav.SKW.POI.PathDependentContext',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class UnreachableBlock(SkwPOI):
    """unreachable-block: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000004'),
            name='Tarav.SKW.POI.UnreachableBlock',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class AttachmentCycle(SkwPOI):
    """attachment-cycle: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000005'),
            name='Tarav.SKW.POI.AttachmentCycle',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class InclusionCycle(SkwPOI):
    """inclusion-cycle: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000006'),
            name='Tarav.SKW.POI.InclusionCycle',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class InvalidBlockReference(SkwPOI):
    """invalid-block-reference: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000007'),
            name='Tarav.SKW.POI.InvalidBlockReference',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class UndeclaredBlock(SkwPOI):
    """undeclared-block: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000008'),
            name='Tarav.SKW.POI.UndeclaredBlock',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class InvalidParent(SkwPOI):
    """invalid-parent: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000009'),
            name='Tarav.SKW.POI.InvalidParent',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class InvalidContextTarget(SkwPOI):
    """invalid-context-target: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000010'),
            name='Tarav.SKW.POI.InvalidContextTarget',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class InvalidLoadingRoot(SkwPOI):
    """invalid-loading-root: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000011'),
            name='Tarav.SKW.POI.InvalidLoadingRoot',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class RootHasParent(SkwPOI):
    """root-has-parent: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000012'),
            name='Tarav.SKW.POI.RootHasParent',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class LoadingAnalysisIncomplete(SkwPOI):
    """loading-analysis-incomplete: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000013'),
            name='Tarav.SKW.POI.LoadingAnalysisIncomplete',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class LoadingDeclarationStale(SkwPOI):
    """loading-declaration-stale: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000014'),
            name='Tarav.SKW.POI.LoadingDeclarationStale',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class LoadingRenderError(SkwPOI):
    """loading-render-error: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000015'),
            name='Tarav.SKW.POI.LoadingRenderError',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class InvalidLoadingModel(SkwPOI):
    """invalid-loading-model: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000016'),
            name='Tarav.SKW.POI.InvalidLoadingModel',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class InvalidPublication(SkwPOI):
    """invalid-publication: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000017'),
            name='Tarav.SKW.POI.InvalidPublication',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class DuplicateOutput(SkwPOI):
    """duplicate-output: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000018'),
            name='Tarav.SKW.POI.DuplicateOutput',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class OutputNotDeployed(SkwPOI):
    """output-not-deployed: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000019'),
            name='Tarav.SKW.POI.OutputNotDeployed',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class InvalidSource(SkwPOI):
    """invalid-source: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000020'),
            name='Tarav.SKW.POI.InvalidSource',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class MissingConsumerFile(SkwPOI):
    """missing-consumer-file: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000021'),
            name='Tarav.SKW.POI.MissingConsumerFile',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class UnbundledLink(SkwPOI):
    """unbundled-link: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000022'),
            name='Tarav.SKW.POI.UnbundledLink',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class UndeclaredConsumerLink(SkwPOI):
    """undeclared-consumer-link: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000023'),
            name='Tarav.SKW.POI.UndeclaredConsumerLink',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class MissingLinkTarget(SkwPOI):
    """missing-link-target: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000024'),
            name='Tarav.SKW.POI.MissingLinkTarget',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class MissingDependency(SkwPOI):
    """missing-dependency: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000025'),
            name='Tarav.SKW.POI.MissingDependency',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class PublicationUnresolvable(SkwPOI):
    """publication-unresolvable: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000026'),
            name='Tarav.SKW.POI.PublicationUnresolvable',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class PublicationStale(SkwPOI):
    """publication-stale: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000027'),
            name='Tarav.SKW.POI.PublicationStale',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class PublicationDrift(SkwPOI):
    """publication-drift: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000028'),
            name='Tarav.SKW.POI.PublicationDrift',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class ContextUnresolvable(SkwPOI):
    """context-unresolvable: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000029'),
            name='Tarav.SKW.POI.ContextUnresolvable',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


# tarav.breadcrumb 815517b13112101af47d38a935d2224f1a3b870950ba20bb5e375a605704cfa3
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
            "project": str(package.root),
            "path": document.key,
            "block": block.label,
            "context_index": index,
        }

    def _run(self):
        try:
            self.document._resolved_context(self.block.label, selected=self.index)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            finding = {
                "kind": "context-unresolvable",
                "path": self.document.key,
                "block": self.block.label,
                "context_index": self.index,
                "detail": str(exc),
            }
            evidence = {
                "finding": finding,
                "declaration": deepcopy(self.declaration),
            }
            poi = ContextUnresolvable.poi(
                self,
                self.subject,
                situation={
                    "subject": self.subject,
                    "declaration": deepcopy(self.declaration),
                },
                evidence=evidence,
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
            if annotation is None or annotation._record is None:
                continue
            declarations = annotation._record.get("context", ())
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


class ContextUnobserved(SkwPOI):
    """context-unobserved: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000030'),
            name='Tarav.SKW.POI.ContextUnobserved',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class StaleContext(SkwPOI, BlessablePOI):
    """Document.lint found changed maintenance context since explicit observation.

    An agent may accept the unchanged product after reviewing the new context.
    Blessing records that assessment; it never advances the document baseline.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000031'),
            name='Tarav.SKW.POI.StaleContext',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class MissingOutput(SkwPOI):
    """missing-output: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000032'),
            name='Tarav.SKW.POI.MissingOutput',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class InvalidInput(SkwPOI):
    """invalid-input: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000033'),
            name='Tarav.SKW.POI.InvalidInput',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


# tarav.breadcrumb 76d1a306cd3cd7ae489248cd3809e96b6bad28beb76e10c3d94c7bebae7a6444
class StaleGeneration(SkwPOI, BlessablePOI):
    """Document.lint found changed generation inputs against recorded provenance.

    Bless only after assessing that existing output is acceptable for the
    changed inputs. Source, output, and generation history are not rewritten.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000034'),
            name='Tarav.SKW.POI.StaleGeneration',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class OutputChanged(SkwPOI):
    """output-changed: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000035'),
            name='Tarav.SKW.POI.OutputChanged',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class InvalidAnnotation(SkwPOI):
    """invalid-annotation: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000036'),
            name='Tarav.SKW.POI.InvalidAnnotation',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class SourceUncompiled(SkwPOI):
    """source-uncompiled: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000037'),
            name='Tarav.SKW.POI.SourceUncompiled',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class ProductUnavailable(SkwPOI):
    """product-unavailable: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000038'),
            name='Tarav.SKW.POI.ProductUnavailable',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class ProductDrift(SkwPOI):
    """product-drift: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000039'),
            name='Tarav.SKW.POI.ProductDrift',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class DiagramAssessment(SkwPOI):
    """A Diagram renderer returned an assessment finding; inspect its evidence."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('7e309479-ccae-4780-b2f1-bd3af54f9f42'),
            name='Tarav.SKW.POI.DiagramAssessment',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


def _freshness_result(check, *, poi_type, kind, message, baseline_key, current_key):
    subject = check.situation["subject"]
    if not isinstance(subject, dict):
        raise TypeError("Freshness Situation subject must be an object")
    baseline = check.situation[baseline_key]
    current = check.situation[current_key]
    if baseline == current:
        return CheckResult(check, status="completed")
    finding = {"kind": kind, **{
        key: subject[key] for key in ("path", "block") if key in subject
    }}
    evidence = {
        "finding": finding,
        "baseline": baseline,
        "current": current,
    }
    poi = check.poi(
        poi_type,
        message=message,
        subject=subject,
        details=evidence,
        evidence=evidence,
    )
    return CheckResult(check, status="completed", pois=(poi,))


# tarav.breadcrumb 9374fbc4f10a36ba669026abe718b0960fad540c45bd1d08d5760beedd90f0c4
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
            kind="stale-generation",
            message="Generation inputs differ from the recorded baseline.",
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
            kind="stale-context",
            message="Tracked context differs from the recorded baseline.",
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
                "project": str(package.root),
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
                "project": str(package.root),
                "path": document.key,
                "block": block,
            }
            checks.append(ContextFreshnessCheck(situation={
                "subject": subject,
                "baseline_context": baseline,
                "current_context": current,
            }))
    return tuple(checks)


FRESHNESS_KINDS = frozenset({"stale-context", "stale-generation"})


CLASSES = {
    'unannotated-output-link': UnannotatedOutputLink,
    'missing-context': MissingContext,
    'path-dependent-context': PathDependentContext,
    'unreachable-block': UnreachableBlock,
    'attachment-cycle': AttachmentCycle,
    'inclusion-cycle': InclusionCycle,
    'invalid-block-reference': InvalidBlockReference,
    'undeclared-block': UndeclaredBlock,
    'invalid-parent': InvalidParent,
    'invalid-context-target': InvalidContextTarget,
    'invalid-loading-root': InvalidLoadingRoot,
    'root-has-parent': RootHasParent,
    'loading-analysis-incomplete': LoadingAnalysisIncomplete,
    'loading-declaration-stale': LoadingDeclarationStale,
    'loading-render-error': LoadingRenderError,
    'invalid-loading-model': InvalidLoadingModel,
    'invalid-publication': InvalidPublication,
    'duplicate-output': DuplicateOutput,
    'output-not-deployed': OutputNotDeployed,
    'invalid-source': InvalidSource,
    'missing-consumer-file': MissingConsumerFile,
    'unbundled-link': UnbundledLink,
    'undeclared-consumer-link': UndeclaredConsumerLink,
    'missing-link-target': MissingLinkTarget,
    'missing-dependency': MissingDependency,
    'publication-unresolvable': PublicationUnresolvable,
    'publication-stale': PublicationStale,
    'publication-drift': PublicationDrift,
    'context-unresolvable': ContextUnresolvable,
    'context-unobserved': ContextUnobserved,
    'stale-context': StaleContext,
    'missing-output': MissingOutput,
    'invalid-input': InvalidInput,
    'stale-generation': StaleGeneration,
    'output-changed': OutputChanged,
    'invalid-annotation': InvalidAnnotation,
    'source-uncompiled': SourceUncompiled,
    'product-unavailable': ProductUnavailable,
    'product-drift': ProductDrift,
}


def surface_state(package):
    """Current declared source and product bytes for POI evidence editions."""
    # Include declared source/lock bytes so an acceptance cannot float across
    # later source edits, even when the checker emits the same compact operands.
    from .publication import digest
    paths = {package.depot / 'main.json', package.depot / 'lock.json'}
    paths.update(package.path(s) for s in package.data['sources'])
    paths.update(package.path(s) for s in package.data.get('publications', []))
    paths.update(package.path(s) for s in package.data['files'])
    if 'loading' in package.data:
        paths.add(package.path(package.data['loading']))
    state = {}
    for path in sorted(paths):
        try:
            state[str(path)] = digest(path.read_bytes().hex())
        except OSError:
            state[str(path)] = None
    return state


def _analysis_pois(check):
    package = check.package
    state = surface_state(package)
    for raw in check.findings:
        kind = raw.get('kind')
        if kind in FRESHNESS_KINDS:
            raise ValueError("Freshness findings must be produced by SituationChecks")
        if kind is not None and kind not in CLASSES:
            raise ValueError(f'Unregistered SKW POI kind: {kind}')
        cls = CLASSES[kind] if kind is not None else DiagramAssessment
        subject = {'project': str(package.root),
                   **{k: raw[k] for k in ('block', 'path', 'target', 'delivery', 'code') if k in raw}}
        evidence = {'finding': raw, 'surface_state': state}
        yield cls.poi(
            check,
            subject,
            situation={"subject": subject, "surface_state": state},
            evidence=evidence,
        )


def collect(package, findings):
    collector = POICollector()
    for poi in SkwAnalysisCheck(package, findings).run().pois():
        collector.emit(poi)
    return collector
