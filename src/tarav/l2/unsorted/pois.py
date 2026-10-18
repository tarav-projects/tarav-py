"""Atomic identified POIs raised by Diagram validation and projection."""

from __future__ import annotations

# tarav.breadcrumb 7dc321876afc

from collections.abc import Mapping

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.poi import SituationPOI, fingerprint, plain
from tarav.l2.unsorted.identity import UNSORTED_WORKFLOW_SHIP
from tarav.l0.kernel import LoadedRecord


class DiagramPOI(SituationPOI):
    """A state of a Diagram object that merits inspection.

    Its situation is the `path` of the object inside the Diagram. `evidence`
    is a field of this line: free data the raising code observed, such as
    the error it met. It is not part of the identity.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d220cb8c-c05f-493c-8190-21117e2d4f7a"),
                          name="Tarav.Diagram.POI", workflow=UNSORTED_WORKFLOW_SHIP)

    def __init__(self, *, path: str, message: str, evidence: Mapping[str, object] | None = None):
        if type(self) not in CASE_TYPES:
            raise TypeError("Diagram POI families cannot be raised")
        super().__init__(message, situation={"path": path})
        self.evidence = dict(evidence or {})

    @property
    def path(self) -> str:
        return str(self.situation["path"])

    class RecordInterface(SituationPOI.RecordInterface):
        evidence: dict

    def _to_record(self) -> dict[str, object]:
        return {**super()._to_record(), "evidence": plain(self.evidence)}

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        result = super()._from_record(loaded)
        result.evidence = dict(loaded.data.evidence)
        return result

    class Records(SituationPOI.Records):
        def record_example(self) -> dict[str, object]:
            class_id, situation = str(entity(self._owner).id), {"path": "example"}
            return {**super().record_example(), "id": fingerprint([class_id, situation]),
                    "situation": situation, "evidence": {}}


class AnnotationPOI(DiagramPOI):
    """POIs concerning Diagram Annotation objects."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("69429163-e540-58e1-9809-6c23146deeeb"),
                          name="Tarav.Diagram.Annotation.POI", workflow=UNSORTED_WORKFLOW_SHIP)


class AnnotationAnnotationSpecializationUnavailable(AnnotationPOI):
    """The Annotation Type cannot be specialized."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("da574cdc-981f-5127-a157-86e81696842d"),
                          name="Tarav.Diagram.Annotation.AnnotationSpecializationUnavailable", workflow=UNSORTED_WORKFLOW_SHIP)


class AnnotationAnnotationTypeNotAllowed(AnnotationPOI):
    """The Namespace does not allow this Annotation Type."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("4a5b9f3d-677b-5678-b35c-2ab4811165cc"),
                          name="Tarav.Diagram.Annotation.AnnotationTypeNotAllowed", workflow=UNSORTED_WORKFLOW_SHIP)


class AnnotationArchiveGroundingUnassessable(AnnotationPOI):
    """Chatlas-to-Archive grounding is not yet mechanically assessable."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d771a7b8-35ba-5de5-93cf-591833569460"),
                          name="Tarav.Diagram.Annotation.ArchiveGroundingUnassessable", workflow=UNSORTED_WORKFLOW_SHIP)


class AnnotationEmptySupportSet(AnnotationPOI):
    """Annotation has no rooted User.Turn support."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("55f5af3d-d05e-5a98-a8b9-5f66c70ff6c8"),
                          name="Tarav.Diagram.Annotation.EmptySupportSet", workflow=UNSORTED_WORKFLOW_SHIP)


class AnnotationLineAnnotationArgumentUnresolved(AnnotationPOI):
    """The Line Annotation argument does not resolve in its Namespace."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("8bf7a40c-2926-5336-ac99-171e433c9e0e"),
                          name="Tarav.Diagram.Annotation.LineAnnotationArgumentUnresolved", workflow=UNSORTED_WORKFLOW_SHIP)


class AnnotationLineAnnotationProducerMissing(AnnotationPOI):
    """Supported Line.Annotation edition has no producer Turn."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("45887fe3-ac89-5ccb-9b58-36de0baeefbb"),
                          name="Tarav.Diagram.Annotation.LineAnnotationProducerMissing", workflow=UNSORTED_WORKFLOW_SHIP)


class AnnotationSemanticRecordUnasserted(AnnotationPOI):
    """The semantic record is missing one or more required Assertion scores."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("5c72a457-0b2c-5dfd-9773-eb2b0c14a6eb"),
                          name="Tarav.Diagram.Annotation.SemanticRecordUnasserted", workflow=UNSORTED_WORKFLOW_SHIP)


class BlockPOI(DiagramPOI):
    """POIs concerning Diagram Block objects."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a9d4d023-80c2-56fd-abc8-2e7edf271403"),
                          name="Tarav.Diagram.Block.POI", workflow=UNSORTED_WORKFLOW_SHIP)


class BlockDeclarationMissing(BlockPOI):
    """Lines name a Block Ship with no Block Edition."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("8b91e552-1445-5903-9637-15cca18da19f"),
                          name="Tarav.Diagram.Block.DeclarationMissing", workflow=UNSORTED_WORKFLOW_SHIP)


class BlockHasNoLines(BlockPOI):
    """Block contains no Line editions."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("490da9bd-7a76-5577-823e-70224e91d97a"),
                          name="Tarav.Diagram.Block.HasNoLines", workflow=UNSORTED_WORKFLOW_SHIP)


class BlockLabelSelectionUnresolved(BlockPOI):
    """Block has no label edition."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("7bec31f6-8d75-5497-8ff1-467b156a33ab"),
                          name="Tarav.Diagram.Block.LabelSelectionUnresolved", workflow=UNSORTED_WORKFLOW_SHIP)


class BlockTypeMissing(BlockPOI):
    """Block Editions do not retain a Block.Type."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b8f91f29-688d-5914-9b4a-6224690a90fd"),
                          name="Tarav.Diagram.Block.TypeMissing", workflow=UNSORTED_WORKFLOW_SHIP)


class BlockTypeNotAllowed(BlockPOI):
    """The Namespace does not allow the selected Block Type."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("37a33342-93d1-520b-b69d-6b953088e465"),
                          name="Tarav.Diagram.Block.TypeNotAllowed", workflow=UNSORTED_WORKFLOW_SHIP)


class BlockTypeUnknown(BlockPOI):
    """The selected Block Type is not registered."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("aef24ea3-2eaa-5866-a750-0b56803420fc"),
                          name="Tarav.Diagram.Block.TypeUnknown", workflow=UNSORTED_WORKFLOW_SHIP)


class BlockIssueOpen(BlockPOI):
    """Issue.Block has no reviewed Issue.Line.Resolve with a passing Verbatim.Gate."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("810a912a-ce11-5657-b468-840a7f37c29e"),
                          name="Tarav.Diagram.Block.IssueOpen", workflow=UNSORTED_WORKFLOW_SHIP)


class CaptureAuthorizationPOI(DiagramPOI):
    """POIs concerning Diagram CaptureAuthorization objects."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("569b9960-43b2-5440-b1b9-eaa61477e82b"),
                          name="Tarav.Diagram.CaptureAuthorization.POI", workflow=UNSORTED_WORKFLOW_SHIP)


class CaptureAuthorizationGateUnresolved(CaptureAuthorizationPOI):
    """The Capture Authorization Gate does not resolve."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("87ce1aac-4806-59bd-bd11-c5dacc476178"),
                          name="Tarav.Diagram.CaptureAuthorization.GateUnresolved", workflow=UNSORTED_WORKFLOW_SHIP)


class CaptureAuthorizationPermissionNotUser(CaptureAuthorizationPOI):
    """Capture authorization permission evidence is not a User turn."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("7e46834f-4e60-565d-af9a-a5e9003ba39a"),
                          name="Tarav.Diagram.CaptureAuthorization.PermissionNotUser", workflow=UNSORTED_WORKFLOW_SHIP)


class CaptureAuthorizationPermissionUnresolved(CaptureAuthorizationPOI):
    """The Capture authorization permission Turn does not resolve."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("dd100a5b-1270-5eaa-89a6-678d17239b2c"),
                          name="Tarav.Diagram.CaptureAuthorization.PermissionUnresolved", workflow=UNSORTED_WORKFLOW_SHIP)


class CaptureAuthorizationScopeUnassessable(CaptureAuthorizationPOI):
    """Cross-Namespace authorization scope requires Diagram-level resolution."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("beb6153e-f79d-5ad0-a610-03608474a11e"),
                          name="Tarav.Diagram.CaptureAuthorization.ScopeUnassessable", workflow=UNSORTED_WORKFLOW_SHIP)


class CaptureAuthorizationScopeUnresolved(CaptureAuthorizationPOI):
    """One or more authorization targets do not resolve."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("bdbd3d22-c84b-5717-b721-991110575106"),
                          name="Tarav.Diagram.CaptureAuthorization.ScopeUnresolved", workflow=UNSORTED_WORKFLOW_SHIP)


class CaptureAuthorizationTokenMissing(CaptureAuthorizationPOI):
    """Authorization token does not occur in its permission evidence."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("8cee6a67-43bc-5488-9305-7f08a051129e"),
                          name="Tarav.Diagram.CaptureAuthorization.TokenMissing", workflow=UNSORTED_WORKFLOW_SHIP)


class CaptureAuthorizationUnassessable(CaptureAuthorizationPOI):
    """Capture.Authorization.Gate requires Chatlas evidence."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b6901ab7-5b04-5453-a550-f51840bdc64f"),
                          name="Tarav.Diagram.CaptureAuthorization.Unassessable", workflow=UNSORTED_WORKFLOW_SHIP)


class CollectionPOI(DiagramPOI):
    """POIs concerning Diagram Collection objects."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("15f1a81a-bb07-5065-8737-d800c58dd057"),
                          name="Tarav.Diagram.Collection.POI", workflow=UNSORTED_WORKFLOW_SHIP)


class CollectionHostCycle(CollectionPOI):
    """Diagram.Collection hosting contains a cycle."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("7aa7e3ac-1ff9-5dd4-89bf-fc586f6eed43"),
                          name="Tarav.Diagram.Collection.HostCycle", workflow=UNSORTED_WORKFLOW_SHIP)


class CollectionHostModelMismatch(CollectionPOI):
    """Collection host names a different Model."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("2df07bb2-6eea-556b-b53d-d9944ddb9a8a"),
                          name="Tarav.Diagram.Collection.HostModelMismatch", workflow=UNSORTED_WORKFLOW_SHIP)


class CollectionHostUnresolved(CollectionPOI):
    """Parent Diagram.Collection does not resolve in this Model."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("f4567de9-816c-5ee7-8d50-1bdec9c4ddb5"),
                          name="Tarav.Diagram.Collection.HostUnresolved", workflow=UNSORTED_WORKFLOW_SHIP)


class CollectionReferenceUnresolved(CollectionPOI):
    """Diagram.Collection reference does not resolve."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("5390e3d6-f94f-5028-8f32-ab13ae5e03e0"),
                          name="Tarav.Diagram.Collection.ReferenceUnresolved", workflow=UNSORTED_WORKFLOW_SHIP)


class CollectionTypeNotAllowed(CollectionPOI):
    """The Namespace does not allow the selected Collection Type."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("decf5cd0-8815-5b60-bd2e-28aba5f73e02"),
                          name="Tarav.Diagram.Collection.TypeNotAllowed", workflow=UNSORTED_WORKFLOW_SHIP)


class CollectionTypeUnknown(CollectionPOI):
    """The selected Collection Type is not registered."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("be1b26f5-bd33-5f48-aa73-134cb68941ef"),
                          name="Tarav.Diagram.Collection.TypeUnknown", workflow=UNSORTED_WORKFLOW_SHIP)


class ImplReqPOI(DiagramPOI):
    """POIs concerning Diagram ImplReq objects."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("16fece02-e73d-5890-b613-a72f191c2c55"),
                          name="Tarav.Diagram.ImplReq.POI", workflow=UNSORTED_WORKFLOW_SHIP)


class ImplReqClosedWrite(ImplReqPOI):
    """Normal capture added or revised content in a Closed Impl.Req.Collection."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("730997e4-facc-5e6e-81bb-4fdc3f72cdc7"),
                          name="Tarav.Diagram.ImplReq.ClosedWrite", workflow=UNSORTED_WORKFLOW_SHIP)


class ImplReqReopenWindowInvalid(ImplReqPOI):
    """Impl.Req.Collection reopening is outside its declared window."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("8031c18b-9698-5f06-9c60-41f691e3fed5"),
                          name="Tarav.Diagram.ImplReq.ReopenWindowInvalid", workflow=UNSORTED_WORKFLOW_SHIP)


class ImplReqStateInvalid(ImplReqPOI):
    """Impl.Req.Collection state must be Open or Closed."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("7bda8ea2-5092-583d-8457-e00a1c1042b9"),
                          name="Tarav.Diagram.ImplReq.StateInvalid", workflow=UNSORTED_WORKFLOW_SHIP)


class LinePOI(DiagramPOI):
    """POIs concerning Diagram Line objects."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("f362188e-d04f-5a04-8314-034780f0f2fd"),
                          name="Tarav.Diagram.Line.POI", workflow=UNSORTED_WORKFLOW_SHIP)


class LineTypeMissing(LinePOI):
    """Line Editions do not retain a Line.Type."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("26250dd9-73d9-5bbf-b823-e0c9d708971b"),
                          name="Tarav.Diagram.Line.TypeMissing", workflow=UNSORTED_WORKFLOW_SHIP)


class LineTypeNotAllowedByBlock(LinePOI):
    """The Block Type does not allow the selected Line Type."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b4144cc6-a29b-501f-9615-6a5700eb738d"),
                          name="Tarav.Diagram.Line.TypeNotAllowedByBlock", workflow=UNSORTED_WORKFLOW_SHIP)


class LineTypeUnknown(LinePOI):
    """The selected Line Type is not registered."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b292c1c3-b1c9-5a8e-b2b3-abc7f2067bb2"),
                          name="Tarav.Diagram.Line.TypeUnknown", workflow=UNSORTED_WORKFLOW_SHIP)


class LineUnreviewed(LinePOI):
    """Line ship has no Annotation with a passing Verbatim.Gate."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("2d2b89ff-67e6-587a-b288-5619ef3bd62f"),
                          name="Tarav.Diagram.Line.Unreviewed", workflow=UNSORTED_WORKFLOW_SHIP)


class LineWordingMissing(LinePOI):
    """Line records name a Line Ship with no wording Edition."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("9b876976-e88d-52a6-a444-f57a68486fe6"),
                          name="Tarav.Diagram.Line.WordingMissing", workflow=UNSORTED_WORKFLOW_SHIP)


class ManifestPOI(DiagramPOI):
    """POIs concerning Diagram Manifest objects."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("4032ad41-46c5-5fbf-95fb-4009d5491579"),
                          name="Tarav.Diagram.Manifest.POI", workflow=UNSORTED_WORKFLOW_SHIP)


class ManifestAnnotationIdentityRebound(ManifestPOI):
    """One Annotation identity names different content."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("373154f7-b63b-5110-992e-2695ea775632"),
                          name="Tarav.Diagram.Manifest.AnnotationIdentityRebound", workflow=UNSORTED_WORKFLOW_SHIP)


class ManifestCaptureModelMismatch(ManifestPOI):
    """Annotation is not located in the Capture.Manifest Model."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("9a2fbe6a-69df-55f0-ba55-e26172e94217"),
                          name="Tarav.Diagram.Manifest.CaptureModelMismatch", workflow=UNSORTED_WORKFLOW_SHIP)


class ManifestDuplicateAnnotationId(ManifestPOI):
    """Capture.Manifest repeats one Annotation identity."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("58b858ce-3c75-53a6-bee5-7200914b1712"),
                          name="Tarav.Diagram.Manifest.DuplicateAnnotationId", workflow=UNSORTED_WORKFLOW_SHIP)


class ManifestDuplicateShipId(ManifestPOI):
    """Capture.Manifest repeats one Ship identity."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("74b3af2b-6493-531c-b614-9343c0b337b0"),
                          name="Tarav.Diagram.Manifest.DuplicateShipId", workflow=UNSORTED_WORKFLOW_SHIP)


class ManifestEditionHostUnresolved(ManifestPOI):
    """Edition host Collection does not resolve."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("6f63a350-2f1b-5f81-8a7b-623133318f04"),
                          name="Tarav.Diagram.Manifest.EditionHostUnresolved", workflow=UNSORTED_WORKFLOW_SHIP)


class ManifestShipEditionInAnnotationCollection(ManifestPOI):
    """Ship editions belong in Capture.Manifest.ships, not annotations."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("581dae59-2aba-54f1-af68-57734c92e855"),
                          name="Tarav.Diagram.Manifest.ShipEditionInAnnotationCollection", workflow=UNSORTED_WORKFLOW_SHIP)


class ManifestShipIdentityRebound(ManifestPOI):
    """One Ship identity names incompatible content."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ecd6c718-4b31-5c15-b955-0a2ee9d32ba7"),
                          name="Tarav.Diagram.Manifest.ShipIdentityRebound", workflow=UNSORTED_WORKFLOW_SHIP)


class ManifestShipSpecializationUnavailable(ManifestPOI):
    """The captured Ship Type cannot be specialized."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("2ae5515a-8775-5ba3-96e1-2622a7c05079"),
                          name="Tarav.Diagram.Manifest.ShipSpecializationUnavailable", workflow=UNSORTED_WORKFLOW_SHIP)


class ManifestShipTypeNotAllowed(ManifestPOI):
    """The Namespace does not allow the captured Ship Type."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a527d238-9789-5c5b-8830-d5d8b90fb51d"),
                          name="Tarav.Diagram.Manifest.ShipTypeNotAllowed", workflow=UNSORTED_WORKFLOW_SHIP)


class ModelPOI(DiagramPOI):
    """POIs concerning Diagram Model objects."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("947588e7-1de0-5a71-9b88-bad895cd5bd5"),
                          name="Tarav.Diagram.Model.POI", workflow=UNSORTED_WORKFLOW_SHIP)


class ModelHasNoBlocks(ModelPOI):
    """Model contains no Block Ships."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("9ec10d24-d515-5af7-b6fa-cc096a063a00"),
                          name="Tarav.Diagram.Model.HasNoBlocks", workflow=UNSORTED_WORKFLOW_SHIP)


class ModelStaleness(ModelPOI):
    """The newest Line Ship edition is hosted outside the Model primary surface."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("8b094066-a636-5f1c-9ed1-7dbeaf872ead"),
                          name="Tarav.Diagram.Model.Staleness", workflow=UNSORTED_WORKFLOW_SHIP)


class ObjectTypePOI(DiagramPOI):
    """POIs concerning Diagram ObjectType objects."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("37c4b28e-8be7-5bf9-919c-2032f31180a7"),
                          name="Tarav.Diagram.ObjectType.POI", workflow=UNSORTED_WORKFLOW_SHIP)


class ObjectTypeDefinitionBlockMissing(ObjectTypePOI):
    """Object.Type has no Definition.Block."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("df4e7d2b-3ee7-511f-9a5a-8134f64199bf"),
                          name="Tarav.Diagram.ObjectType.DefinitionBlockMissing", workflow=UNSORTED_WORKFLOW_SHIP)


class ObjectTypeDefinitionBlockUnresolved(ObjectTypePOI):
    """The Object Type Definition Block does not resolve."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("f9193d32-fd9a-5221-b477-1f437abe2235"),
                          name="Tarav.Diagram.ObjectType.DefinitionBlockUnresolved", workflow=UNSORTED_WORKFLOW_SHIP)


class SupportPOI(DiagramPOI):
    """POIs concerning Diagram Support objects."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("92b51ca9-6991-5785-8f61-936d62e136d6"),
                          name="Tarav.Diagram.Support.POI", workflow=UNSORTED_WORKFLOW_SHIP)


class SupportProducerTurnNotAgent(SupportPOI):
    """Annotation producer is not an Agent turn."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ee78d295-9938-5dfb-b4e5-7a1a1d43d5a7"),
                          name="Tarav.Diagram.Support.ProducerTurnNotAgent", workflow=UNSORTED_WORKFLOW_SHIP)


class SupportProducerTurnUnresolved(SupportPOI):
    """The Annotation producer Turn does not resolve."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("1a6ccbb1-d312-54d2-a40d-7b1e4f4d86ad"),
                          name="Tarav.Diagram.Support.ProducerTurnUnresolved", workflow=UNSORTED_WORKFLOW_SHIP)


class SupportContextUnassessable(SupportPOI):
    """The support context cannot be assessed."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("51b32429-702c-55fa-8426-6ae1465cc3a1"),
                          name="Tarav.Diagram.Support.ContextUnassessable", workflow=UNSORTED_WORKFLOW_SHIP)


class SupportNeighborhoodTurnUnresolved(SupportPOI):
    """A support neighborhood Turn does not resolve."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b8177b60-f6ba-5e28-aa68-8e4f14a82a9d"),
                          name="Tarav.Diagram.Support.NeighborhoodTurnUnresolved", workflow=UNSORTED_WORKFLOW_SHIP)


class SupportNotInProducerContext(SupportPOI):
    """Selected support content was not present before the Annotation producer turn."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("65e213f4-0b86-5b4a-a368-19caf3510057"),
                          name="Tarav.Diagram.Support.NotInProducerContext", workflow=UNSORTED_WORKFLOW_SHIP)


class SupportRenderUnavailable(SupportPOI):
    """The support evidence cannot be rendered."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d8dfdfe3-8ff5-50e9-a51c-4f4d7f466dca"),
                          name="Tarav.Diagram.Support.RenderUnavailable", workflow=UNSORTED_WORKFLOW_SHIP)


class SupportRootNotUser(SupportPOI):
    """Support.Member root is not a User turn."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("0e7e1637-d09f-5b00-9ec4-1b1404b9e443"),
                          name="Tarav.Diagram.Support.RootNotUser", workflow=UNSORTED_WORKFLOW_SHIP)


class SupportRootUnresolved(SupportPOI):
    """A support root Turn does not resolve."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("2f0a2620-b0b9-57ad-be2f-f787722e2eed"),
                          name="Tarav.Diagram.Support.RootUnresolved", workflow=UNSORTED_WORKFLOW_SHIP)


class SupportTurnUnresolved(SupportPOI):
    """The referenced Chatlas Turn does not resolve."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("cf74edf6-d4e3-594c-9183-e84b1f490080"),
                          name="Tarav.Diagram.Support.TurnUnresolved", workflow=UNSORTED_WORKFLOW_SHIP)


class VerbatimGatePOI(DiagramPOI):
    """POIs concerning Diagram VerbatimGate objects."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("04c9aff8-e432-577f-bda9-b15ab5947d46"),
                          name="Tarav.Diagram.VerbatimGate.POI", workflow=UNSORTED_WORKFLOW_SHIP)


class VerbatimGateLineGateTargetUnresolved(VerbatimGatePOI):
    """Line Gate target does not resolve to a Line Edition."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("1c47b991-8486-5a69-a14b-ffaa9b3d4a0c"),
                          name="Tarav.Diagram.VerbatimGate.LineGateTargetUnresolved", workflow=UNSORTED_WORKFLOW_SHIP)


class VerbatimGateApprovalNotUser(VerbatimGatePOI):
    """Verbatim.Gate approval is not a User turn."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a5a6f2fe-4c1d-5975-84bb-91ee1ab89ee2"),
                          name="Tarav.Diagram.VerbatimGate.ApprovalNotUser", workflow=UNSORTED_WORKFLOW_SHIP)


class VerbatimGateApprovalUnresolved(VerbatimGatePOI):
    """The Verbatim Gate approval Turn does not resolve."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("469c2854-8a15-50c0-bc26-b6b1ca6a50fe"),
                          name="Tarav.Diagram.VerbatimGate.ApprovalUnresolved", workflow=UNSORTED_WORKFLOW_SHIP)


class VerbatimGateContentMismatch(VerbatimGatePOI):
    """The proposal turn does not contain materially equivalent Line wording."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a58ebf7e-3008-545e-965a-31c64546647e"),
                          name="Tarav.Diagram.VerbatimGate.ContentMismatch", workflow=UNSORTED_WORKFLOW_SHIP)


class VerbatimGateOrderMismatch(VerbatimGatePOI):
    """Verbatim.Gate approval does not follow its proposal in one chat."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("bcdff5f2-3bef-5cbe-b26e-c9c6a8b52dd2"),
                          name="Tarav.Diagram.VerbatimGate.OrderMismatch", workflow=UNSORTED_WORKFLOW_SHIP)


class VerbatimGateProposalNotAgent(VerbatimGatePOI):
    """Verbatim.Gate proposal is not an Agent turn."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("1c609a34-788c-53d1-abc7-5af9d3190e08"),
                          name="Tarav.Diagram.VerbatimGate.ProposalNotAgent", workflow=UNSORTED_WORKFLOW_SHIP)


class VerbatimGateProposalUnresolved(VerbatimGatePOI):
    """The Verbatim Gate proposal Turn does not resolve."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("59546cca-af6f-5409-8c69-707f77a73804"),
                          name="Tarav.Diagram.VerbatimGate.ProposalUnresolved", workflow=UNSORTED_WORKFLOW_SHIP)


class VerbatimGateTokenMismatch(VerbatimGatePOI):
    """Gate token is not present in the proposal and explicitly approved by the User."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("2fafe1cd-2d0a-505b-86ec-a8259b53ff69"),
                          name="Tarav.Diagram.VerbatimGate.TokenMismatch", workflow=UNSORTED_WORKFLOW_SHIP)


class VerbatimGateUnassessable(VerbatimGatePOI):
    """Verbatim.Gate requires Chatlas evidence for assessment."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e0c0238f-1b79-560e-aaf5-05f7d5cca806"),
                          name="Tarav.Diagram.VerbatimGate.Unassessable", workflow=UNSORTED_WORKFLOW_SHIP)


class ViewPOI(DiagramPOI):
    """POIs concerning Diagram View objects."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("80cff9ce-b976-5d51-a7e3-21367fec7953"),
                          name="Tarav.Diagram.View.POI", workflow=UNSORTED_WORKFLOW_SHIP)


class ViewBlockDuplicate(ViewPOI):
    """A Block occurs more than once in the View."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("1cfa5908-c1aa-5540-b6f9-d477104e2b37"),
                          name="Tarav.Diagram.View.BlockDuplicate", workflow=UNSORTED_WORKFLOW_SHIP)


class ViewDeepSupportUnassessable(ViewPOI):
    """Deep support disclosure requires Chatlas evidence."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("3ea0da2d-a636-5850-87b6-a53df6e4187a"),
                          name="Tarav.Diagram.View.DeepSupportUnassessable", workflow=UNSORTED_WORKFLOW_SHIP)


class ViewDeepSupportUnresolved(ViewPOI):
    """The View deep support disclosure cannot resolve its evidence."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("4a3123aa-4328-582d-86de-4e5babda6081"),
                          name="Tarav.Diagram.View.DeepSupportUnresolved", workflow=UNSORTED_WORKFLOW_SHIP)


class ViewDependencyAmbiguous(ViewPOI):
    """A dependency label resolves to several Blocks."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("16916f93-18ab-5a4c-aea4-828e639f9a18"),
                          name="Tarav.Diagram.View.DependencyAmbiguous", workflow=UNSORTED_WORKFLOW_SHIP)


class ViewDisclosureLevelInvalid(ViewPOI):
    """The View disclosure level is outside the supported ladder."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("6f0e64aa-a47f-558f-bb78-554472ab412c"),
                          name="Tarav.Diagram.View.DisclosureLevelInvalid", workflow=UNSORTED_WORKFLOW_SHIP)


class ViewInvalid(ViewPOI):
    """The retained View is invalid."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("3b1d3953-cd38-5677-b2ee-041e78457385"),
                          name="Tarav.Diagram.View.Invalid", workflow=UNSORTED_WORKFLOW_SHIP)


class ViewLineMaterializationMismatch(ViewPOI):
    """Visible Line material does not match the retained Line selection."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("aac80d08-10a3-520f-a112-b91c5b7bb3a2"),
                          name="Tarav.Diagram.View.LineMaterializationMismatch", workflow=UNSORTED_WORKFLOW_SHIP)


class ViewLineSelectionDuplicate(ViewPOI):
    """A Line ship occurs more than once in one Block selection."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a248b224-6bbc-5f82-9309-3fc66f6da1e9"),
                          name="Tarav.Diagram.View.LineSelectionDuplicate", workflow=UNSORTED_WORKFLOW_SHIP)


class ViewMentionCheckUnassessable(ViewPOI):
    """Session mentions cannot be assessed against this View."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("91f99f6e-f003-5ed0-a64b-ac8c3fb18809"),
                          name="Tarav.Diagram.View.MentionCheckUnassessable", workflow=UNSORTED_WORKFLOW_SHIP)


class ViewMentionedBlockAbsent(ViewPOI):
    """Session mentions Block , but it is outside this View."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("c2296db1-be37-5376-9f8a-ee19af13b27c"),
                          name="Tarav.Diagram.View.MentionedBlockAbsent", workflow=UNSORTED_WORKFLOW_SHIP)


class ViewSessionIdentityMissing(ViewPOI):
    """Session.Diagram.View has no Chatlas session identity."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("81431b44-a324-558c-b36f-48d1a1a5b29b"),
                          name="Tarav.Diagram.View.SessionIdentityMissing", workflow=UNSORTED_WORKFLOW_SHIP)


class ViewSourceStale(ViewPOI):
    """The View source edition differs from the Namespace HEAD."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("60d12d98-73b0-565e-a3cd-fa7845993a82"),
                          name="Tarav.Diagram.View.SourceStale", workflow=UNSORTED_WORKFLOW_SHIP)


class ViewSourceUnresolved(ViewPOI):
    """The View source does not resolve."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("38a7a0ca-9042-5543-800e-1d7d1d2583db"),
                          name="Tarav.Diagram.View.SourceUnresolved", workflow=UNSORTED_WORKFLOW_SHIP)


class ViewVisibleLineBudgetExceeded(ViewPOI):
    """The View exceeds its configured visible Line budget."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("6da88ed4-874f-54d3-910d-134bf759b3d3"),
                          name="Tarav.Diagram.View.VisibleLineBudgetExceeded", workflow=UNSORTED_WORKFLOW_SHIP)


class ViewMaterializationRowUnrecognized(ViewPOI):
    """A retained View materialization row has an unrecognized POI Type."""
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("692e9dc8-e1f8-5781-8c78-ee9a6b9d1700"),
                          name="Tarav.Diagram.View.MaterializationRowUnrecognized", workflow=UNSORTED_WORKFLOW_SHIP)


CASE_TYPES: tuple[type[DiagramPOI], ...] = (
    AnnotationAnnotationSpecializationUnavailable,
    AnnotationAnnotationTypeNotAllowed,
    AnnotationArchiveGroundingUnassessable,
    AnnotationEmptySupportSet,
    AnnotationLineAnnotationArgumentUnresolved,
    AnnotationLineAnnotationProducerMissing,
    AnnotationSemanticRecordUnasserted,
    BlockDeclarationMissing,
    BlockHasNoLines,
    BlockLabelSelectionUnresolved,
    BlockTypeMissing,
    BlockTypeNotAllowed,
    BlockTypeUnknown,
    BlockIssueOpen,
    CaptureAuthorizationGateUnresolved,
    CaptureAuthorizationPermissionNotUser,
    CaptureAuthorizationPermissionUnresolved,
    CaptureAuthorizationScopeUnassessable,
    CaptureAuthorizationScopeUnresolved,
    CaptureAuthorizationTokenMissing,
    CaptureAuthorizationUnassessable,
    CollectionHostCycle,
    CollectionHostModelMismatch,
    CollectionHostUnresolved,
    CollectionReferenceUnresolved,
    CollectionTypeNotAllowed,
    CollectionTypeUnknown,
    ImplReqClosedWrite,
    ImplReqReopenWindowInvalid,
    ImplReqStateInvalid,
    LineTypeMissing,
    LineTypeNotAllowedByBlock,
    LineTypeUnknown,
    LineUnreviewed,
    LineWordingMissing,
    ManifestAnnotationIdentityRebound,
    ManifestCaptureModelMismatch,
    ManifestDuplicateAnnotationId,
    ManifestDuplicateShipId,
    ManifestEditionHostUnresolved,
    ManifestShipEditionInAnnotationCollection,
    ManifestShipIdentityRebound,
    ManifestShipSpecializationUnavailable,
    ManifestShipTypeNotAllowed,
    ModelHasNoBlocks,
    ModelStaleness,
    ObjectTypeDefinitionBlockMissing,
    ObjectTypeDefinitionBlockUnresolved,
    SupportProducerTurnNotAgent,
    SupportProducerTurnUnresolved,
    SupportContextUnassessable,
    SupportNeighborhoodTurnUnresolved,
    SupportNotInProducerContext,
    SupportRenderUnavailable,
    SupportRootNotUser,
    SupportRootUnresolved,
    SupportTurnUnresolved,
    VerbatimGateLineGateTargetUnresolved,
    VerbatimGateApprovalNotUser,
    VerbatimGateApprovalUnresolved,
    VerbatimGateContentMismatch,
    VerbatimGateOrderMismatch,
    VerbatimGateProposalNotAgent,
    VerbatimGateProposalUnresolved,
    VerbatimGateTokenMismatch,
    VerbatimGateUnassessable,
    ViewBlockDuplicate,
    ViewDeepSupportUnassessable,
    ViewDeepSupportUnresolved,
    ViewDependencyAmbiguous,
    ViewDisclosureLevelInvalid,
    ViewInvalid,
    ViewLineMaterializationMismatch,
    ViewLineSelectionDuplicate,
    ViewMentionCheckUnassessable,
    ViewMentionedBlockAbsent,
    ViewSessionIdentityMissing,
    ViewSourceStale,
    ViewSourceUnresolved,
    ViewVisibleLineBudgetExceeded,
    ViewMaterializationRowUnrecognized,
)
POI_BY_NAME: dict[str, type[DiagramPOI]] = {entity(cls).name: cls for cls in CASE_TYPES}


def load_poi(record: Mapping[str, object]) -> DiagramPOI:
    """Load one retained Diagram POI from its record, through the Type the record names."""
    try:
        cls = POI_BY_NAME[record.get("type")]  # type: ignore[index]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Unrecognized Diagram POI Type in record: {record!r}") from exc
    return cls.records.from_record(record)
