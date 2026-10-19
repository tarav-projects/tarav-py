"""The Action Types of Skillware POIs. The checks that raise them are Situation
Chains (`tarav.l2.skw.chains`); open a POI's Type from finding.help for policy.
"""
from tarav.l0.kernel import TaravClass
from tarav.l0.kernel import TypeShip
from tarav.l1.actions.pois import BlessableResolution, POIResolutionAction
from tarav.l1.skw.identity import SKW_SKILLS_WORKFLOW_SHIP
from tarav.l1.skw.pois import (
    MissingMarkdownLink,
    MissingContext,
    PathDependentContext,
    UnreachableBlock,
    AttachmentCycle,
    InclusionCycle,
    InvalidBlockReference,
    UndeclaredBlock,
    InvalidParent,
    InvalidContextTarget,
    InvalidLoadingRoot,
    RootHasParent,
    LoadingAnalysisIncomplete,
    LoadingDeclarationStale,
    LoadingRenderError,
    InvalidLoadingModel,
    DuplicateOutput,
    OutputNotDeployed,
    InvalidSource,
    MissingConsumerFile,
    SkillMarkerMissing,
    SkillMarkerMismatch,
    UnbundledLink,
    UndeclaredConsumerLink,
    MissingLinkTarget,
    MissingDependency,
    PublicationUnresolvable,
    PublicationStale,
    PublicationDrift,
    ContextUnresolvable,
    ContextUnobserved,
    OutputChanged,
    InvalidAnnotation,
    SourceUncompiled,
    ProductUnavailable,
    ProductDrift,
    DiagramAssessment,
    PublicationDisconnected,
    MissingContent,
    InvalidProducedOutput,
    StaleProducedOutput,
)


class StaleContextResolution(BlessableResolution):
    """The action of a StaleContext: an agent may bless it after reviewing the new context."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("0ce3f735-0427-42e6-8e06-db82b3ba7686"),
                          name="Tarav.SKW.POI.StaleContext.Resolution", workflow=SKW_SKILLS_WORKFLOW_SHIP)


class StaleGenerationResolution(BlessableResolution):
    """The action of a StaleGeneration: blessed once the output is assessed acceptable."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("c904ffa1-26c5-40f8-a526-90a5776784e2"),
                          name="Tarav.SKW.POI.StaleGeneration.Resolution", workflow=SKW_SKILLS_WORKFLOW_SHIP)


def _resolution(poi_type, id):
    """The Action Type a Skillware POI Type names: it closes when the situation is gone."""

    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip(id), name=poi_type.action,
                          workflow=SKW_SKILLS_WORKFLOW_SHIP)

    name = f"{poi_type.__name__}Resolution"
    return type(name, (POIResolutionAction,), {
        "__module__": __name__, "__qualname__": name,
        "__doc__": f"The action of a {poi_type.__name__}.",
        "class_entity": classmethod(class_entity)})


#: The Action Type of every other Skillware POI Type, each with its own id.
RESOLUTIONS = tuple(_resolution(poi_type, id) for poi_type, id in (
    (MissingMarkdownLink, "f2e14fcd-12f1-4b8c-8e35-0c9b942782d1"),
    (MissingContext, "625f21d5-fe6d-41e6-b4f6-74f9012262fe"),
    (PathDependentContext, "433b2267-f88e-4691-a397-4478c7df40fc"),
    (UnreachableBlock, "e5f3fc26-4e01-407a-8911-892f8f182006"),
    (AttachmentCycle, "b95a8741-b72d-4a09-a207-b16e1b94d899"),
    (InclusionCycle, "7cd3302c-ee28-4592-b72b-8f9cd51d5cf5"),
    (InvalidBlockReference, "922541d4-be35-412f-9135-71941129d49a"),
    (UndeclaredBlock, "e511f370-1a7e-471c-be5b-a47db2d6dd16"),
    (InvalidParent, "0c4e2c4b-e5f3-431c-9b23-130c523c1656"),
    (InvalidContextTarget, "30af5439-601d-4282-97a7-4088d9b8e591"),
    (InvalidLoadingRoot, "67b5becc-3a40-4048-86b5-b0d33f912bca"),
    (RootHasParent, "71bc9bc6-8f49-4a1d-8c4b-93137200285e"),
    (LoadingAnalysisIncomplete, "9b7920bd-81e5-48c9-9304-e3a3bb7c9699"),
    (LoadingDeclarationStale, "d18989d8-0c71-45e4-aa1d-bcf157a05e15"),
    (LoadingRenderError, "74e74a40-9fd4-4b37-a3a7-f3ebc1060efe"),
    (InvalidLoadingModel, "f92eae95-4a8d-46f9-a2ba-646b41999f2d"),
    (DuplicateOutput, "876876f4-ce16-4577-b63d-398d8e710d17"),
    (OutputNotDeployed, "9d884532-30da-4c85-8602-73b3258b25a5"),
    (InvalidSource, "dbf5406d-aa32-4c7b-9de3-572364ae73c2"),
    (MissingConsumerFile, "0d9819e5-dc14-4a8f-8cb0-73c316dd7328"),
    (SkillMarkerMissing, "7ff6c759-933e-4fc9-b657-627fffbf5323"),
    (SkillMarkerMismatch, "b35e3b9c-1684-4053-b247-1d56e5d67b97"),
    (UnbundledLink, "70b101b4-2511-466f-b2b1-e84aa11569cc"),
    (UndeclaredConsumerLink, "290f8d8c-dc4a-4b89-abea-8b33004405af"),
    (MissingLinkTarget, "48d55b70-7191-4b77-8230-74ecc1f4e655"),
    (MissingDependency, "e62ea20a-627d-4a09-93cd-2c95dc232353"),
    (PublicationUnresolvable, "1dac0a08-fa3d-4d76-9fe3-3639429a24d7"),
    (PublicationStale, "605a46fb-44ff-4cb0-960a-fcbcb6cf2fc9"),
    (PublicationDrift, "f2293bc4-d39a-4944-8447-345b6708a42f"),
    (ContextUnresolvable, "00425566-4179-47f4-8fdb-a82ed501d192"),
    (ContextUnobserved, "c7aef7a5-0441-4a14-970d-649e7525999c"),
    (OutputChanged, "a91ee706-455c-489c-83c0-26b8791c44c3"),
    (InvalidAnnotation, "1ad54ad7-49f6-46e1-a9c9-a09a6d442e1b"),
    (SourceUncompiled, "ed7306df-2b26-46b2-ba2a-d78862e9a0f0"),
    (ProductUnavailable, "521a5149-76d1-43f4-8b0c-1bea0f7174af"),
    (ProductDrift, "9687b4e0-40d8-4e9d-8ceb-ef97289cfe12"),
    (DiagramAssessment, "01c2810a-1b87-4ed5-9e79-f79bc0f9212b"),
    (PublicationDisconnected, "d3f62f6a-a4e0-468a-b012-a8f9ba924594"),
    (MissingContent, "e590e909-d827-4fed-b946-d11fa59640fc"),
    (InvalidProducedOutput, "20573fa0-f458-4413-990b-0786e086ebd5"),
    (StaleProducedOutput, "af9ef599-ffaf-4129-9035-ab0c74fbfbd0"),
))

SKW_ACTION_TYPES = (StaleContextResolution, StaleGenerationResolution, *RESOLUTIONS)
