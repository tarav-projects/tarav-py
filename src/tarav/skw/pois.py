"""SKW-owned POI classes. Open this source from finding.help for policy.

Checks live in skw/loading.py, skw/skills.py, skw/publication.py and
skw/document.py. Only annotation omissions and semantic freshness
questions permit attributed acceptance. Structural failures require repair.
"""
from tarav.l0.kernel import TaravClass
from tarav.l0.kernel import TypeShip
from tarav.poi import POI, POICollector
from tarav.skw.identity import SKW_SKILLS_WORKFLOW_SHIP


class SkwPOI(POI):
    """Ownership base for SKW checks represented as POI Record Types."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('6e215eaf-b1d4-4ff9-ae51-9a89e542ffd3'),
            name='Tarav.SKW.POI',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class UnannotatedOutputLink(SkwPOI):
    """An authored Markdown link has no SKW link primitive declaration.

    LoadingModel binds source blocks, then parses their authored output solely
    for conformance. This link contributes no simulated context edge. Bless
    only an intentionally unmodeled link after evaluating its consumer effect;
    an acceptance does not add an edge or satisfy a context requirement.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000001'),
            name='Tarav.SKW.POI.UnannotatedOutputLink',
        )
    blessable = True


class MissingContext(SkwPOI):
    """LoadingModel.analyze reached a requirement without its requested delivery.

    Evidence identifies the target, delivery and exact incoming path. Correct
    declarations or delivery primitives; this class does not permit blessing.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000002'),
            name='Tarav.SKW.POI.MissingContext',
        )
    blessable = False


class PathDependentContext(SkwPOI):
    """path-dependent-context: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000003'),
            name='Tarav.SKW.POI.PathDependentContext',
        )
    blessable = False


class UnreachableBlock(SkwPOI):
    """unreachable-block: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000004'),
            name='Tarav.SKW.POI.UnreachableBlock',
        )
    blessable = False


class AttachmentCycle(SkwPOI):
    """attachment-cycle: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000005'),
            name='Tarav.SKW.POI.AttachmentCycle',
        )
    blessable = False


class InclusionCycle(SkwPOI):
    """inclusion-cycle: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000006'),
            name='Tarav.SKW.POI.InclusionCycle',
        )
    blessable = False


class InvalidBlockReference(SkwPOI):
    """invalid-block-reference: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000007'),
            name='Tarav.SKW.POI.InvalidBlockReference',
        )
    blessable = False


class UndeclaredBlock(SkwPOI):
    """undeclared-block: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000008'),
            name='Tarav.SKW.POI.UndeclaredBlock',
        )
    blessable = False


class InvalidParent(SkwPOI):
    """invalid-parent: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000009'),
            name='Tarav.SKW.POI.InvalidParent',
        )
    blessable = False


class InvalidContextTarget(SkwPOI):
    """invalid-context-target: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000010'),
            name='Tarav.SKW.POI.InvalidContextTarget',
        )
    blessable = False


class InvalidLoadingRoot(SkwPOI):
    """invalid-loading-root: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000011'),
            name='Tarav.SKW.POI.InvalidLoadingRoot',
        )
    blessable = False


class RootHasParent(SkwPOI):
    """root-has-parent: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000012'),
            name='Tarav.SKW.POI.RootHasParent',
        )
    blessable = False


class LoadingAnalysisIncomplete(SkwPOI):
    """loading-analysis-incomplete: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000013'),
            name='Tarav.SKW.POI.LoadingAnalysisIncomplete',
        )
    blessable = False


class LoadingDeclarationStale(SkwPOI):
    """loading-declaration-stale: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000014'),
            name='Tarav.SKW.POI.LoadingDeclarationStale',
        )
    blessable = False


class LoadingRenderError(SkwPOI):
    """loading-render-error: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000015'),
            name='Tarav.SKW.POI.LoadingRenderError',
        )
    blessable = False


class InvalidLoadingModel(SkwPOI):
    """invalid-loading-model: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000016'),
            name='Tarav.SKW.POI.InvalidLoadingModel',
        )
    blessable = False


class InvalidPublication(SkwPOI):
    """invalid-publication: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000017'),
            name='Tarav.SKW.POI.InvalidPublication',
        )
    blessable = False


class DuplicateOutput(SkwPOI):
    """duplicate-output: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000018'),
            name='Tarav.SKW.POI.DuplicateOutput',
        )
    blessable = False


class OutputNotDeployed(SkwPOI):
    """output-not-deployed: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000019'),
            name='Tarav.SKW.POI.OutputNotDeployed',
        )
    blessable = False


class InvalidSource(SkwPOI):
    """invalid-source: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000020'),
            name='Tarav.SKW.POI.InvalidSource',
        )
    blessable = False


class MissingConsumerFile(SkwPOI):
    """missing-consumer-file: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000021'),
            name='Tarav.SKW.POI.MissingConsumerFile',
        )
    blessable = False


class UnbundledLink(SkwPOI):
    """unbundled-link: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000022'),
            name='Tarav.SKW.POI.UnbundledLink',
        )
    blessable = False


class UndeclaredConsumerLink(SkwPOI):
    """undeclared-consumer-link: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000023'),
            name='Tarav.SKW.POI.UndeclaredConsumerLink',
        )
    blessable = False


class MissingLinkTarget(SkwPOI):
    """missing-link-target: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000024'),
            name='Tarav.SKW.POI.MissingLinkTarget',
        )
    blessable = False


class MissingDependency(SkwPOI):
    """missing-dependency: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000025'),
            name='Tarav.SKW.POI.MissingDependency',
        )
    blessable = False


class PublicationUnresolvable(SkwPOI):
    """publication-unresolvable: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000026'),
            name='Tarav.SKW.POI.PublicationUnresolvable',
        )
    blessable = False


class PublicationStale(SkwPOI):
    """publication-stale: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000027'),
            name='Tarav.SKW.POI.PublicationStale',
        )
    blessable = False


class PublicationDrift(SkwPOI):
    """publication-drift: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000028'),
            name='Tarav.SKW.POI.PublicationDrift',
        )
    blessable = False


class ContextUnresolvable(SkwPOI):
    """context-unresolvable: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000029'),
            name='Tarav.SKW.POI.ContextUnresolvable',
        )
    blessable = False


class ContextUnobserved(SkwPOI):
    """context-unobserved: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000030'),
            name='Tarav.SKW.POI.ContextUnobserved',
        )
    blessable = False


class StaleContext(SkwPOI):
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
        )
    blessable = True


class MissingOutput(SkwPOI):
    """missing-output: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000032'),
            name='Tarav.SKW.POI.MissingOutput',
        )
    blessable = False


class InvalidInput(SkwPOI):
    """invalid-input: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000033'),
            name='Tarav.SKW.POI.InvalidInput',
        )
    blessable = False


class StaleGeneration(SkwPOI):
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
        )
    blessable = True


class OutputChanged(SkwPOI):
    """output-changed: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000035'),
            name='Tarav.SKW.POI.OutputChanged',
        )
    blessable = False


class InvalidAnnotation(SkwPOI):
    """invalid-annotation: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000036'),
            name='Tarav.SKW.POI.InvalidAnnotation',
        )
    blessable = False


class SourceUncompiled(SkwPOI):
    """source-uncompiled: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000037'),
            name='Tarav.SKW.POI.SourceUncompiled',
        )
    blessable = False


class ProductUnavailable(SkwPOI):
    """product-unavailable: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000038'),
            name='Tarav.SKW.POI.ProductUnavailable',
        )
    blessable = False


class ProductDrift(SkwPOI):
    """product-drift: inspect the retained evidence and owning check before acting."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000039'),
            name='Tarav.SKW.POI.ProductDrift',
        )
    blessable = False


class DiagramAssessment(SkwPOI):
    """A Diagram renderer returned an assessment finding; inspect its evidence."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('7e309479-ccae-4780-b2f1-bd3af54f9f42'),
            name='Tarav.SKW.POI.DiagramAssessment',
        )


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


def collect(package, findings):
    collector = POICollector()
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
    for raw in findings:
        kind = raw.get('kind')
        if kind is not None and kind not in CLASSES:
            raise ValueError(f'Unregistered SKW POI kind: {kind}')
        cls = CLASSES[kind] if kind is not None else DiagramAssessment
        subject = {'project': str(package.root),
                   **{k: raw[k] for k in ('block', 'path', 'target', 'delivery', 'code') if k in raw}}
        evidence = {'finding': raw, 'surface_state': state}
        if kind in ('stale-context', 'stale-generation'):
            try:
                document = next(d for d in package.documents()
                                if d.source == package.path(raw['path']))
                evidence['resolved_context'] = digest(document._resolved_context(raw['block']))
                evidence['resolved_inputs'] = document.inputs(raw['block'])[1]
            except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
                # Missing assessment material cannot authorize a stale blessing.
                cls = ContextUnresolvable
                evidence['resolution_error'] = str(exc)
        collector.emit(cls.finding(subject, evidence=evidence))
    return collector
