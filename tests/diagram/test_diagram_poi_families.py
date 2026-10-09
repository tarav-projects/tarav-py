"""Drive each Diagram POI family through the method that emits it."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from tarav.l2.lines.block import DiagramBlock, IssueBlock
from tarav.l2.lines.collection import DiagramCollection, ImplReqCollection
from tarav.l2.lines.line import DiagramLineEdition, DiagramLineShip
from tarav.l2.lines.projection import DiagramProjection, DiagramProjectionBuilder
from tarav.l2.lines.rendering import DiagramRenderTarget, _kernel_model, _render_line, DiagramRenderContext
from tarav.l2.lines.records import LineEditionRecord
from tarav.l2.lines.types import DiagramBlockType, DiagramObjectTypeRegistry
from tarav.l2.models import Model
from tarav.l2.unsorted.assessment import AssertionEngine, CaptureAuthorizationAssertionEvaluator, _assess_verbatim_gate
from tarav.l2.unsorted.authorization import CaptureAuthorizationGateRecord
from tarav.l2.unsorted.capture import CaptureManifest
from tarav.l2.unsorted.contracts import ShipDraftInterface
from tarav.l2.unsorted.evidence import ChatlasEvidence
from tarav.l2.unsorted.records import DiagramAnnotation
from tarav.l2.unsorted.storage import DiagramNamespace
from tarav.l2.unsorted.views import DiagramView
from tarav.l2.unsorted import pois as cases


def _id() -> str:
    return str(uuid4())


def _namespace(tmp_path):
    return DiagramNamespace(tmp_path, _id(), "test", (), ())


# tarav.breadcrumb e784d8aea43803cd5d9e334233da17545fa595bd14a384cf94caea3ae78b0838
def test_manifest_and_annotation_emit_typed_pois(tmp_path, monkeypatch) -> None:
    namespace = _namespace(tmp_path)
    # Models is currently disconnected; Capture's validation continues past projection.
    monkeypatch.setattr(DiagramNamespace, "project", lambda self, *args, **kwargs:
                        DiagramProjection(_id(), self.id, (), (), ()))
    ship_id = _id()
    draft = ShipDraftInterface.from_record(ship_id, {"type": "Unknown.Ship", "editions": []})
    manifest = CaptureManifest.create(_id(), ships=(draft, draft))
    assert any(isinstance(poi, cases.ManifestDuplicateShipId)
               for poi in manifest.check(namespace))

    annotation = DiagramAnnotation(_id(), namespace, {"type": "Unknown.Annotation"})
    assert any(isinstance(poi, cases.AnnotationAnnotationSpecializationUnavailable)
               for poi in namespace.pois(annotation, path="annotation"))


def test_block_collection_and_impl_req_emit_typed_pois(tmp_path) -> None:
    block = IssueBlock(_id(), _id(), (), (), (), ())
    assert any(isinstance(poi, cases.BlockIssueOpen)
               for poi in block.assess(AssertionEngine()).pois)

    collection = ImplReqCollection(_id(), _id(),
                                   (SimpleNamespace(id=_id(), data={"state": "Invalid"}),),
                                   (), (), ())
    assert any(isinstance(poi, cases.ImplReqStateInvalid)
               for poi in collection.mechanical_pois())

    namespace = _namespace(tmp_path)
    builder = DiagramProjectionBuilder(namespace, _id(), ())
    first, second = _id(), _id()
    cycle = (
        DiagramCollection(first, builder.model_ship,
                          (SimpleNamespace(host=SimpleNamespace(kind="collection", id=second)),),
                          (), (), ()),
        DiagramCollection(second, builder.model_ship,
                          (SimpleNamespace(host=SimpleNamespace(kind="collection", id=first)),),
                          (), (), ()),
    )
    assert any(isinstance(poi, cases.CollectionHostCycle)
               for poi in builder._collection_cycle_pois(cycle))


def test_support_gate_and_authorization_emit_typed_pois(tmp_path) -> None:
    ref = SimpleNamespace(session_identity="missing", turn_address="missing", turn_hash="missing")
    evidence = ChatlasEvidence(model_loader=lambda identity: {"turns": []})
    assert any(isinstance(poi, cases.SupportProducerTurnUnresolved)
               for poi in evidence.check(SimpleNamespace(producer=ref, support=()), path="annotation"))

    gate = SimpleNamespace(proposal_turn=ref, approval_turn=ref, token="token")
    assessment = _assess_verbatim_gate(evidence=evidence, annotation_id=_id(),
                                      target=SimpleNamespace(id=_id()), gate=gate, path="gate")
    assert any(isinstance(poi, cases.VerbatimGateProposalUnresolved)
               for poi in assessment.pois)

    authorization = object.__new__(CaptureAuthorizationGateRecord)
    result = CaptureAuthorizationAssertionEvaluator().evaluate(
        authorization, evidence=None, path="gate")
    assert any(isinstance(poi, cases.CaptureAuthorizationUnassessable)
               for poi in result.pois)


def test_object_type_view_and_model_emit_typed_pois(tmp_path, monkeypatch) -> None:
    registry = DiagramObjectTypeRegistry((DiagramBlockType("Example.Block", DiagramBlock, ()),))
    assert any(isinstance(poi, cases.ObjectTypeDefinitionBlockMissing)
               for poi in registry.definition_pois(lambda ship: None))

    assert any(isinstance(poi, cases.ViewInvalid)
               for poi in DiagramView(tmp_path / _id()).check())

    namespace = SimpleNamespace(
        id=_id(),
        edition=lambda identity: SimpleNamespace(record={"data": {"label": "Example"}}),
    )
    model = object.__new__(Model)
    object.__setattr__(model, "ship", _id())
    object.__setattr__(model, "namespace", namespace)
    object.__setattr__(model, "current_edition_id", _id())
    monkeypatch.setattr(Model, "project", lambda self: DiagramProjection(
        self.ship, namespace.id, (), (), ()))
    target = DiagramRenderTarget("model", model.ship, namespace.id, model)
    _, pois = _kernel_model(target, DiagramRenderContext(None, AssertionEngine()))
    assert any(isinstance(poi, cases.ModelHasNoBlocks) for poi in pois)


def test_line_renderer_emits_unreviewed_poi(tmp_path) -> None:
    namespace = _namespace(tmp_path)
    model_ship, block_ship, line_ship = _id(), _id(), _id()
    record = LineEditionRecord.records.record_example()
    record["location"] = {"model_ship": model_ship, "block_ship": block_ship,
                          "line_ship": line_ship}
    record["data"] = {"text": "Example wording"}
    annotation = DiagramAnnotation(_id(), namespace, record)
    wording = LineEditionRecord(annotation)
    line = DiagramLineShip(line_ship, block_ship, (wording,),
                           (DiagramLineEdition(wording, None),), (), ())
    target = DiagramRenderTarget("line", line_ship, namespace.id, line)
    _, pois = _render_line(target, with_support=False,
                           context=DiagramRenderContext(None, AssertionEngine()))
    assert any(isinstance(poi, cases.LineUnreviewed) for poi in pois)
