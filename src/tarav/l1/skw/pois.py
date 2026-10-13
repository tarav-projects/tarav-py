"""Skillware POI Types, and the finding the analysis reports before a check raises one.

The analysis of a document, a loading model or a package says what it found
with the POI Type that states it: there is no second name for it. Only
annotation omissions and semantic freshness questions permit attributed
acceptance; structural failures require repair. The checks that run the
analysis are in `tarav.l2.skw`.
"""
from pathlib import Path
from typing import ClassVar

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.checks import CheckPOI
from tarav.l1.poi.actionable import BlessablePOI

from .identity import SKW_SKILLS_WORKFLOW_SHIP


class SkwPOI(CheckPOI):
    """A workflow-owned SKW POI explained by the bound analysis Check."""

    # tarav.breadcrumb 4d33a68da40966a0089b5dbed2e67a73af39a003f06f3a37b5a819aa76e8e120
    #: What a POI of this Type says, as one literal sentence without a full stop.
    statement: ClassVar[str] = ""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('6e215eaf-b1d4-4ff9-ae51-9a89e542ffd3'),
            name='Tarav.SKW.POI',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )

    @classmethod
    def sentence(cls, *, where=None, target=None, detail=None) -> str:
        """The Type's statement, then which one of that kind this is."""
        parts = [cls.statement + (f": {where}" if where else "")]
        if target:
            parts.append(f"to {target}")
        if detail:
            parts.append(f"({detail})")
        return " ".join(parts)

    @classmethod
    # tarav.breadcrumb 358f9776a4d31e8930d727fec6ccb95407790af6d2893c204b16cb9cb572cde9
    def poi(cls, check, *, situation, finding=None, details=None, where=None):
        """Build one SKW POI from what the analysis found.

        `where` names the place for a reader, when the finding itself only
        has an internal id for it. `details` is what the check adds for the
        reader beside the finding.
        """
        found = finding.data if finding is not None else {}
        if where is None:
            where = ": ".join(found[key] for key in ("path", "block")
                              if isinstance(found.get(key), str) and found[key])
        details = dict(details or {})
        if finding is not None:
            details["finding"] = finding.to_json()
        return cls(
            check,
            cls.sentence(where=where, target=found.get("target"), detail=found.get("detail")),
            situation=situation,
            details=details,
        )

    @classmethod
    def from_finding(cls, check, finding, *, root, state=None):
        """The POI of one analysis finding, raised by `check`.

        `root` is the folder the analysed document belongs to: a skill
        package, or a Project for its agents file. `state` is the file state
        of a package, when the check has one. This is the general Skillware
        line: the place of the finding, plus that state. A Type that can name
        its own state overrides it.
        """
        subject = {'project': str(root),
                   **{k: finding[k] for k in ('block', 'path', 'target', 'delivery')
                      if k in finding}}
        held = {} if state is None else {"surface_state": state}
        return cls.poi(check, situation={"subject": subject, **held}, finding=finding,
                       details=held)


# tarav.breadcrumb d745f68d7e9441efda0d3f5e255e9a09840c5b55a3aace602b3a188c481ef66c
# tarav.breadcrumb 34fac1a4d5bb2a797d5b30b3b8c092c283f84a2ac3b4475f81e36c26bf2066f5
class Finding:
    """What the analysis found, before a check raises it: the POI Type that states it,
    and the place and observations as plain data.

    The analysis also runs outside checks, and a POI of a check needs the
    check that raises it; so the analysis reports findings and a check
    raises their POIs. `to_json()` is how a command prints one.
    """

    __slots__ = ("poi", "data")

    def __init__(self, poi: type[SkwPOI], **data: object) -> None:
        if not (isinstance(poi, type) and issubclass(poi, SkwPOI)) or not poi.statement:
            raise TypeError("A finding names the atomic Skillware POI Type that states it")
        self.poi = poi
        self.data = data

    def __getitem__(self, key: str) -> object:
        return self.data[key]

    def __contains__(self, key: object) -> bool:
        return key in self.data

    def get(self, key: str, default: object = None) -> object:
        return self.data.get(key, default)

    def at(self, **place: object) -> "Finding":
        """The same finding, with more said about where it is."""
        return Finding(self.poi, **{**self.data, **place})

    def to_json(self) -> dict[str, object]:
        return {"type": entity(self.poi).name, **self.data}

    def __repr__(self) -> str:
        return f"Finding({self.poi.__name__}, {self.data!r})"


class UnannotatedOutputLink(SkwPOI, BlessablePOI):
    """An authored Markdown link has no SKW link primitive declaration.

    SkillReadingGraph binds source blocks, then parses their authored output
    solely for conformance. This link contributes no simulated context edge.
    Bless only an intentionally unmodeled link after evaluating its consumer
    effect; an acceptance does not add an edge or satisfy a context requirement.
    """

    statement = "An authored link has no declared link in its source"

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

    statement = "A block needs context that its reading path does not deliver"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000002'),
            name='Tarav.SKW.POI.MissingContext',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class PathDependentContext(SkwPOI):
    """A block gets the context it needs on some reading paths and not on others."""

    statement = "A block gets the context it needs on some reading paths and not on others"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000003'),
            name='Tarav.SKW.POI.PathDependentContext',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class UnreachableBlock(SkwPOI):
    """A declared block that no reading path from the package's root reaches. It does not say
    the block is wrong, only that a reader following the declared reading is never led to it.
    """

    statement = "A declared block is not reached by any reading path"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000004'),
            name='Tarav.SKW.POI.UnreachableBlock',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class AttachmentCycle(SkwPOI):
    """The declared attachments of a block form a cycle."""

    statement = "The declared attachments of a block form a cycle"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000005'),
            name='Tarav.SKW.POI.AttachmentCycle',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class InclusionCycle(SkwPOI):
    """The declared inclusions of a block form a cycle."""

    statement = "The declared inclusions of a block form a cycle"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000006'),
            name='Tarav.SKW.POI.InclusionCycle',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class InvalidBlockReference(SkwPOI):
    """A declaration of the loading model refers to a block that cannot be resolved."""

    statement = "A declaration of the loading model refers to a block that cannot be resolved"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000007'),
            name='Tarav.SKW.POI.InvalidBlockReference',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class UndeclaredBlock(SkwPOI):
    """A block of a source is not declared in the loading model."""

    statement = "A block of a source is not declared in the loading model"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000008'),
            name='Tarav.SKW.POI.UndeclaredBlock',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class InvalidParent(SkwPOI):
    """A block declares a parent that is not a declared block."""

    statement = "A block declares a parent that is not a declared block"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000009'),
            name='Tarav.SKW.POI.InvalidParent',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class InvalidContextTarget(SkwPOI):
    """A context requirement names a target that cannot be resolved."""

    statement = "A context requirement names a target that cannot be resolved"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000010'),
            name='Tarav.SKW.POI.InvalidContextTarget',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class InvalidLoadingRoot(SkwPOI):
    """The root of the loading model is not a declared block."""

    statement = "The root of the loading model is not a declared block"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000011'),
            name='Tarav.SKW.POI.InvalidLoadingRoot',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class RootHasParent(SkwPOI):
    """The root of the loading model declares a parent."""

    statement = "The root of the loading model declares a parent"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000012'),
            name='Tarav.SKW.POI.RootHasParent',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class LoadingAnalysisIncomplete(SkwPOI):
    """The reading analysis reached its limit before it visited every path."""

    statement = "The reading analysis reached its limit before it visited every path"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000013'),
            name='Tarav.SKW.POI.LoadingAnalysisIncomplete',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class LoadingDeclarationStale(SkwPOI):
    """The loading model changed since this document was compiled."""

    statement = "The loading model changed since this document was compiled"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000014'),
            name='Tarav.SKW.POI.LoadingDeclarationStale',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class LoadingRenderError(SkwPOI):
    """This document cannot be rendered with the loading model."""

    statement = "This document cannot be rendered with the loading model"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000015'),
            name='Tarav.SKW.POI.LoadingRenderError',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class InvalidLoadingModel(SkwPOI):
    """The sources or the loading model of the package cannot be loaded."""

    statement = "The sources or the loading model of the package cannot be loaded"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000016'),
            name='Tarav.SKW.POI.InvalidLoadingModel',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class DuplicateOutput(SkwPOI):
    """Two sources compile to the same file."""

    statement = "Two sources compile to the same file"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000018'),
            name='Tarav.SKW.POI.DuplicateOutput',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class OutputNotDeployed(SkwPOI):
    """A source compiles to a file that the package does not list among its files."""

    statement = "A source compiles to a file that the package does not list among its files"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000019'),
            name='Tarav.SKW.POI.OutputNotDeployed',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class InvalidSource(SkwPOI):
    """A source of the package cannot be read or analysed."""

    statement = "A source of the package cannot be read or analysed"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000020'),
            name='Tarav.SKW.POI.InvalidSource',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class MissingConsumerFile(SkwPOI):
    """A file that the package lists does not exist."""

    statement = "A file that the package lists does not exist"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000021'),
            name='Tarav.SKW.POI.MissingConsumerFile',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class UnbundledLink(SkwPOI):
    """A file the package delivers links to a file inside the package that the package does not
    list among its files.
    """

    statement = "A file of the package links to a file that the package does not bundle"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000022'),
            name='Tarav.SKW.POI.UnbundledLink',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class UndeclaredConsumerLink(SkwPOI):
    """A file of the package links outside the package to something no declared dependency owns."""

    statement = "A file of the package links outside the package to something no declared dependency owns"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000023'),
            name='Tarav.SKW.POI.UndeclaredConsumerLink',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class MissingLinkTarget(SkwPOI):
    """A link in a file of the package points at a file that does not exist."""

    statement = "A link in a file of the package points at a file that does not exist"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000024'),
            name='Tarav.SKW.POI.MissingLinkTarget',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class MissingDependency(SkwPOI):
    """A declared dependency of the package does not exist."""

    statement = "A declared dependency of the package does not exist"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000025'),
            name='Tarav.SKW.POI.MissingDependency',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class PublicationUnresolvable(SkwPOI):
    """A Model publication cannot be rendered."""

    statement = "A Model publication cannot be rendered"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000026'),
            name='Tarav.SKW.POI.PublicationUnresolvable',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class PublicationStale(SkwPOI):
    """The source or the Model of a publication changed since it was published."""

    statement = "The source or the Model of a publication changed since it was published"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000027'),
            name='Tarav.SKW.POI.PublicationStale',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class PublicationDrift(SkwPOI):
    """A published file differs from what its publication renders."""

    statement = "A published file differs from what its publication renders"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000028'),
            name='Tarav.SKW.POI.PublicationDrift',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class ContextUnresolvable(SkwPOI):
    """A declared context of a generated block cannot be resolved."""

    statement = "A declared context of a generated block cannot be resolved"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000029'),
            name='Tarav.SKW.POI.ContextUnresolvable',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class ContextUnobserved(SkwPOI):
    """A generated block declares context that was never observed."""

    statement = "A generated block declares context that was never observed"

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

    statement = "The tracked context of a generated block differs from the recorded baseline"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000031'),
            name='Tarav.SKW.POI.StaleContext',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


# tarav.breadcrumb 76d1a306cd3cd7ae489248cd3809e96b6bad28beb76e10c3d94c7bebae7a6444
class StaleGeneration(SkwPOI, BlessablePOI):
    """Document.lint found changed generation inputs against recorded provenance.

    Bless only after assessing that existing output is acceptable for the
    changed inputs. Source, output, and generation history are not rewritten.
    """

    statement = "The inputs of a generated block differ from the recorded baseline"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000034'),
            name='Tarav.SKW.POI.StaleGeneration',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class OutputChanged(SkwPOI):
    """A block's content no longer matches the output recorded for its generation: it was edited
    after that generation was recorded.
    """

    statement = "The content of a generated block changed after its generation was recorded"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000035'),
            name='Tarav.SKW.POI.OutputChanged',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class InvalidAnnotation(SkwPOI):
    """The generation record of a block disagrees with the lock."""

    statement = "The generation record of a block disagrees with the lock"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000036'),
            name='Tarav.SKW.POI.InvalidAnnotation',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class SourceUncompiled(SkwPOI):
    """A source changed since it was last compiled."""

    statement = "A source changed since it was last compiled"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000037'),
            name='Tarav.SKW.POI.SourceUncompiled',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class ProductUnavailable(SkwPOI):
    """The compiled file of a source cannot be read."""

    statement = "The compiled file of a source cannot be read"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000038'),
            name='Tarav.SKW.POI.ProductUnavailable',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class ProductDrift(SkwPOI):
    """A compiled file no longer matches what its source produces: the file was edited by hand,
    or the source changed without a build.
    """

    statement = "A compiled file differs from what its source produces"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-000000000039'),
            name='Tarav.SKW.POI.ProductDrift',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )

    context_notes = (
        'Either side may be the newer one: read the difference before compiling, since compiling '
        'replaces the file with what the source produces.',
        'It is no longer raised once the file and what its source produces are the same text.',
    )

    @classmethod
    # tarav.breadcrumb 3eb40ba8c8c58e9e0ce65142bc077c76f435c823ae1a3d357edfcc3c1e7ade5c
    # tarav.breadcrumb f41a5d6353932a38b2690134f9db371f0f2e6d656baf7b5079d954337e68520f
    def from_finding(cls, check, finding, *, root, state=None):
        """The situation is what was compared: the file, its text and the text its source produces."""
        root = Path(root)
        product = Path(finding['product'])
        return cls(
            check,
            f"{root.name}: {product.relative_to(root)} differs from what its "
            f"source produces ({finding['detail']})",
            situation={'product': str(product), 'actual': finding['actual'],
                       'expected': finding['expected']},
            details={'finding': finding.to_json()},
        )


class DiagramAssessment(SkwPOI):
    """A Diagram renderer returned an assessment finding; inspect its evidence."""

    statement = "A Diagram renderer returned an assessment finding"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('7e309479-ccae-4780-b2f1-bd3af54f9f42'),
            name='Tarav.SKW.POI.DiagramAssessment',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )



class PublicationDisconnected(SkwPOI):
    """A declared Model publication is not connected: publications await a redesign."""

    statement = "A declared Model publication is not connected: publications await a redesign"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-00000000003a'),
            name='Tarav.SKW.POI.PublicationDisconnected',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class MissingContent(SkwPOI):
    """A block has no content."""

    statement = "A block has no content"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-00000000003b'),
            name='Tarav.SKW.POI.MissingContent',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class InvalidProducedOutput(SkwPOI):
    """The output that a block produces cannot be computed."""

    statement = "The output that a block produces cannot be computed"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-00000000003c'),
            name='Tarav.SKW.POI.InvalidProducedOutput',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class StaleProducedOutput(SkwPOI):
    """The stored content of a produced block differs from what it produces now."""

    statement = "The stored content of a produced block differs from what it produces now"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('9a70b6c2-63ea-4b73-9273-00000000003d'),
            name='Tarav.SKW.POI.StaleProducedOutput',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )
