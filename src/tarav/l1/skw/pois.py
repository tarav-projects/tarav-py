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

from .identity import SKW_SKILLS_WORKFLOW_SHIP



class SkwPOI(CheckPOI):
    """A workflow-owned SKW POI explained by the bound analysis Check."""

    # tarav.breadcrumb 4d33a68da409
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

    # tarav.breadcrumb ccf024a804b7
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # every Skillware POI Type has its own Action Type, named after it (tarav.l2.skw.pois)
        cls.action = f"{entity(cls).name}.Resolution"

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
    # tarav.breadcrumb 358f9776a4d3
    def poi(cls, check, *, situation, finding=None, details=None, where=None):
        """Build one SKW POI from what the analysis found.

        `where` names the place for a reader, when the finding itself only
        has an internal id for it. The details are what the finding observed
        beyond the situation, and what the check adds for the reader; nothing
        of the situation is repeated in them.
        """
        found = finding.data if finding is not None else {}
        if where is None:
            where = ": ".join(found[key] for key in ("path", "block")
                              if isinstance(found.get(key), str) and found[key])
        place = situation.get("subject") or {}
        details = {**{key: value for key, value in found.items()
                      if key not in place and value not in (None, "")},
                   **(details or {})}
        return cls(
            check,
            cls.sentence(where=where, target=found.get("target"), detail=found.get("detail")),
            situation=situation,
            details=details,
        )

    @classmethod
    def from_finding(cls, check, finding, *, root, owner):
        """The POI of one analysis finding, raised by `check`.

        `root` is the folder the analysed document belongs to: a skill
        package, or a Project for its agents file; `owner` names that skill
        or Project by its UUID, as `{"skill": id}` or `{"project": id}`.
        This is the general Skillware line: the situation is the place of the
        finding, which is the whole problem. A Type whose problem is a state
        it compared names that state in its situation by overriding this.
        """
        subject = {**owner,
                   **{k: finding[k] for k in ('block', 'path', 'target', 'delivery')
                      if k in finding}}
        return cls.poi(check, situation={"subject": subject}, finding=finding)


# tarav.breadcrumb d745f68d7e94
# tarav.breadcrumb 34fac1a4d5bb
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


# tarav.breadcrumb 9b73451a9adc
class MissingMarkdownLink(SkwPOI):
    """A block declares a link whose prose part is Markdown, and its text holds no Markdown link
    to the declared target. Either the declaration or the text is wrong.
    """

    statement = "A declared Markdown link is missing from the text of its block"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('83887afe-9c07-445a-94c8-4eafaf8039a0'),
            name='Tarav.SKW.POI.MissingMarkdownLink',
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


class SkillMarkerMissing(SkwPOI):
    """The folder the depot builds has no `.tarav/skill.json`: the skill has no identity there."""

    statement = "The skill folder the depot builds has no .tarav/skill.json"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('a11c7a39-3a98-4b95-a2e1-b63361d924d2'),
            name='Tarav.SKW.POI.SkillMarkerMissing',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class SkillMarkerMismatch(SkwPOI):
    """The skill folder's `.tarav/skill.json` names another skill than the depot builds."""

    statement = "The skill folder's .tarav/skill.json names another skill than its depot"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('ec7d92bf-a64c-4ca4-b09c-e7e93cfcc0e5'),
            name='Tarav.SKW.POI.SkillMarkerMismatch',
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


class StaleContext(SkwPOI):
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


# tarav.breadcrumb 76d1a306cd3c
class StaleGeneration(SkwPOI):
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

    @classmethod
    # tarav.breadcrumb 3eb40ba8c8c5
    # tarav.breadcrumb f41a5d635393
    def from_finding(cls, check, finding, *, root, owner):
        """The situation is what was compared: the file, its text and the text its source produces."""
        root = Path(root)
        product = Path(finding['product'])
        return cls(
            check,
            f"{root.name}: {product.relative_to(root)} differs from what its "
            f"source produces ({finding['detail']})",
            situation={'product': str(product), 'actual': finding['actual'],
                       'expected': finding['expected']},
            # what helps whoever works on it: the source to edit, and the lines
            details={'source': finding.get('source'),
                     'difference': list(finding.get('difference') or ())},
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
