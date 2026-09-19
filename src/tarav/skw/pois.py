"""SKW-owned POI classes. Open this source from finding.help for policy.

Checks live in skw/loading.py, skw/skills.py, skw/publication.py and
skw/document.py. Only annotation omissions and semantic freshness
questions permit attributed acceptance. Structural failures require repair.
"""
from tarav.harness import TypeShip
from tarav.poi import POI, POICollector

class UnannotatedOutputLink(POI):
    """An authored Markdown link has no SKW link primitive declaration.

    LoadingModel binds source blocks, then parses their authored output solely
    for conformance. This link contributes no simulated context edge. Bless
    only an intentionally unmodeled link after evaluating its consumer effect;
    an acceptance does not add an edge or satisfy a context requirement.
    """

    type_name = 'Tarav.SKW.POI.UnannotatedOutputLink'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000001')
    blessable = True


class MissingContext(POI):
    """LoadingModel.analyze reached a requirement without its requested delivery.

    Evidence identifies the target, delivery and exact incoming path. Correct
    declarations or delivery primitives; this class does not permit blessing.
    """

    type_name = 'Tarav.SKW.POI.MissingContext'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000002')
    blessable = False


class PathDependentContext(POI):
    """path-dependent-context: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.PathDependentContext'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000003')
    blessable = False


class UnreachableBlock(POI):
    """unreachable-block: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.UnreachableBlock'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000004')
    blessable = False


class AttachmentCycle(POI):
    """attachment-cycle: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.AttachmentCycle'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000005')
    blessable = False


class InclusionCycle(POI):
    """inclusion-cycle: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.InclusionCycle'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000006')
    blessable = False


class InvalidBlockReference(POI):
    """invalid-block-reference: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.InvalidBlockReference'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000007')
    blessable = False


class UndeclaredBlock(POI):
    """undeclared-block: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.UndeclaredBlock'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000008')
    blessable = False


class InvalidParent(POI):
    """invalid-parent: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.InvalidParent'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000009')
    blessable = False


class InvalidContextTarget(POI):
    """invalid-context-target: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.InvalidContextTarget'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000010')
    blessable = False


class InvalidLoadingRoot(POI):
    """invalid-loading-root: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.InvalidLoadingRoot'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000011')
    blessable = False


class RootHasParent(POI):
    """root-has-parent: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.RootHasParent'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000012')
    blessable = False


class LoadingAnalysisIncomplete(POI):
    """loading-analysis-incomplete: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.LoadingAnalysisIncomplete'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000013')
    blessable = False


class LoadingDeclarationStale(POI):
    """loading-declaration-stale: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.LoadingDeclarationStale'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000014')
    blessable = False


class LoadingRenderError(POI):
    """loading-render-error: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.LoadingRenderError'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000015')
    blessable = False


class InvalidLoadingModel(POI):
    """invalid-loading-model: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.InvalidLoadingModel'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000016')
    blessable = False


class InvalidPublication(POI):
    """invalid-publication: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.InvalidPublication'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000017')
    blessable = False


class DuplicateOutput(POI):
    """duplicate-output: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.DuplicateOutput'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000018')
    blessable = False


class OutputNotDeployed(POI):
    """output-not-deployed: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.OutputNotDeployed'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000019')
    blessable = False


class InvalidSource(POI):
    """invalid-source: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.InvalidSource'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000020')
    blessable = False


class MissingConsumerFile(POI):
    """missing-consumer-file: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.MissingConsumerFile'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000021')
    blessable = False


class UnbundledLink(POI):
    """unbundled-link: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.UnbundledLink'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000022')
    blessable = False


class UndeclaredConsumerLink(POI):
    """undeclared-consumer-link: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.UndeclaredConsumerLink'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000023')
    blessable = False


class MissingLinkTarget(POI):
    """missing-link-target: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.MissingLinkTarget'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000024')
    blessable = False


class MissingDependency(POI):
    """missing-dependency: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.MissingDependency'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000025')
    blessable = False


class PublicationUnresolvable(POI):
    """publication-unresolvable: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.PublicationUnresolvable'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000026')
    blessable = False


class PublicationStale(POI):
    """publication-stale: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.PublicationStale'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000027')
    blessable = False


class PublicationDrift(POI):
    """publication-drift: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.PublicationDrift'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000028')
    blessable = False


class ContextUnresolvable(POI):
    """context-unresolvable: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.ContextUnresolvable'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000029')
    blessable = False


class ContextUnobserved(POI):
    """context-unobserved: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.ContextUnobserved'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000030')
    blessable = False


class StaleContext(POI):
    """Document.lint found changed maintenance context since explicit observation.

    An agent may accept the unchanged product after reviewing the new context.
    Blessing records that assessment; it never advances the document baseline.
    """

    type_name = 'Tarav.SKW.POI.StaleContext'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000031')
    blessable = True


class MissingOutput(POI):
    """missing-output: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.MissingOutput'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000032')
    blessable = False


class InvalidInput(POI):
    """invalid-input: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.InvalidInput'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000033')
    blessable = False


class StaleGeneration(POI):
    """Document.lint found changed generation inputs against recorded provenance.

    Bless only after assessing that existing output is acceptable for the
    changed inputs. Source, output, and generation history are not rewritten.
    """

    type_name = 'Tarav.SKW.POI.StaleGeneration'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000034')
    blessable = True


class OutputChanged(POI):
    """output-changed: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.OutputChanged'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000035')
    blessable = False


class InvalidAnnotation(POI):
    """invalid-annotation: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.InvalidAnnotation'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000036')
    blessable = False


class SourceUncompiled(POI):
    """source-uncompiled: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.SourceUncompiled'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000037')
    blessable = False


class ProductUnavailable(POI):
    """product-unavailable: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.ProductUnavailable'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000038')
    blessable = False


class ProductDrift(POI):
    """product-drift: inspect the retained evidence and owning check before acting."""

    type_name = 'Tarav.SKW.POI.ProductDrift'
    type_ship = TypeShip('9a70b6c2-63ea-4b73-9273-000000000039')
    blessable = False


class DiagramAssessment(POI):
    """A Diagram renderer returned an assessment finding; inspect its evidence."""

    type_name = 'Tarav.SKW.POI.DiagramAssessment'
    type_ship = TypeShip('7e309479-ccae-4780-b2f1-bd3af54f9f42')


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
