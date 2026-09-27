from __future__ import annotations

import json
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest

from tarav.cli.cli import main
from tarav.unsorted import commands as diagram_commands
from tarav.unsorted.constants import BLOCK_SHIP_TYPE, BLOCK_TYPE_ANNOTATION_TYPE, DESIGN_BLOCK_OBJECT_TYPE, DESIGN_LINE_EXAMPLE_TYPE, DESIGN_LINE_PRINCIPLE_TYPE, DIAGRAM_ATTIC, IMPL_REQ_BLOCK_OBJECT_TYPE, ISSUE_BLOCK_OBJECT_TYPE, ISSUE_LINE_RESOLVE_TYPE, LINE_EDITION_TYPE, LINE_GATE_ANNOTATION_TYPE, LINE_SHIP_TYPE, LINE_TYPE_ANNOTATION_TYPE, MODEL_EDITION_TYPE, MODEL_SHIP_TYPE, USER_TOUCHED_CHATLAS_INDEX
from tarav.unsorted.contracts import AnnotationDraftInterface, ChatlasTurnReferenceInterface, ShipDraftInterface, SupportMemberInterface, VerbatimGate
from tarav.unsorted.assessment import AssertionEngine, AssertionEvaluation
from tarav.lines.records import BlockEditionRecord, BlockTypeAnnotation, LineEditionRecord, LineGateAnnotation, LineTypeAnnotation
from tarav.unsorted.capture import CaptureManifest, CaptureReceipt
from tarav.unsorted.evidence import ChatlasEvidence
from tarav.unsorted.storage import Diagram, DiagramConfiguration, DiagramNamespace
from tarav.unsorted.primitives import DiagramAnnotationSpecializationError, DiagramError, DiagramModelError
from tarav.lines.references import DiagramBlockLocationInterface, DiagramLocationInterface, DiagramArgumentReferenceInterface, DiagramHostReferenceInterface
from tarav.lines.block import DesignBlock, ImplReqBlock, IssueBlock
from tarav.lines.line import DesignLinePrinciple, DesignPrincipleLineShip, IssueLineResolve, IssueResolveLineShip
from tarav.unsorted.standalone import default_diagram_record_type_registry
from tarav.unsorted.drafts import DiagramDraft
from tarav.unsorted.views import (
    DiagramViewAbout,
    DiagramViewConfiguration,
    DiagramViewManifest,
    DiagramViewRepositoryRecord,
    DiagramViewScopeInterface,
    DiagramViewState,
)
from tarav.kernel import (
    TaravAssertion,
    TaravPOIInstance,
    TaravObject,
)


def test_diagram_record_interfaces_share_the_tarav_root() -> None:
    interfaces = (
        ChatlasTurnReferenceInterface,
        SupportMemberInterface,
        DiagramLocationInterface,
        DiagramBlockLocationInterface,
        DiagramArgumentReferenceInterface,
        DiagramHostReferenceInterface,
        AnnotationDraftInterface,
        ShipDraftInterface,
        DiagramViewScopeInterface,
    )

    assert all(
        issubclass(interface, TaravObject.RecordInterface) for interface in interfaces
    )


def test_standalone_diagram_records_have_registered_type_authority() -> None:
    registry = default_diagram_record_type_registry()
    expected = {
        CaptureManifest,
        CaptureReceipt,
        DiagramConfiguration,
        DiagramDraft,
        DiagramViewManifest,
        DiagramViewConfiguration,
        DiagramViewState,
        DiagramViewAbout,
        DiagramViewRepositoryRecord,
    }

    assert expected == set(registry.record_types)
    assert all(
        issubclass(record_type.RecordInterface, TaravObject.RecordInterface)
        for record_type in registry.record_types
    )


def _line(
    model_ship: str,
    *,
    edition_id: str | None = None,
    support: bool = True,
    block_ship: str | None = None,
    line_ship: str | None = None,
    line_type: str | None = None,
    text: str = "Capture concerns only the present Model.",
    gates: list[dict[str, object]] | None = None,
) -> ShipDraftInterface:
    ref = {
        "session_identity": "a" * 64,
        "turn_address": "b" * 64,
        "turn_hash": "c" * 64,
    }
    edition: dict[str, object] = {
        "id": edition_id or str(uuid4()),
        "producer": ref,
        "support": [{"root": ref, "neighborhood": []}] if support else [],
        "data": {"text": text},
    }
    if line_type is not None:
        edition["line_type"] = line_type
    if gates is not None:
        edition["gates"] = gates
    return ShipDraftInterface.from_record(
        line_ship or str(uuid4()),
        {
            "type": LINE_SHIP_TYPE,
            "model_ship": model_ship,
            "block_ship": block_ship or str(uuid4()),
            "editions": [edition],
        },
    )


def _edition(ship: ShipDraftInterface) -> dict[str, object]:
    return ship.editions[0]


def _edition_id(ship: ShipDraftInterface) -> str:
    return str(_edition(ship)["id"])


def _block(
    model_ship: str,
    *,
    block_ship: str | None = None,
    edition_id: str | None = None,
    label: str,
    block_type: str | None = None,
) -> ShipDraftInterface:
    edition: dict[str, object] = {
        "id": edition_id or str(uuid4()),
        "data": {"label": label},
    }
    if block_type is not None:
        edition["block_type"] = block_type
    return ShipDraftInterface.from_record(
        block_ship or str(uuid4()),
        {
            "type": BLOCK_SHIP_TYPE,
            "model_ship": model_ship,
            "editions": [edition],
        },
    )


def _project(root: Path) -> Path:
    (root / ".tarav").mkdir(parents=True)
    (root / ".tarav" / "project.json").write_text(
        json.dumps(
            {
                "class": "agentos.project",
                "project_id": str(uuid4()),
                "preserved": True,
            }
        ),
        encoding="utf-8",
    )
    return root


def test_namespace_is_an_independent_flat_git_semantic_database(tmp_path: Path) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")

    assert (namespace.root / ".git").is_dir()
    assert (namespace.root / "namespace.json").is_file()
    assert (namespace.root / "ships").is_dir()
    assert (namespace.root / "annotations").is_dir()
    assert not (namespace.root / "models").exists()
    assert namespace.name == USER_TOUCHED_CHATLAS_INDEX


def test_legacy_null_namespace_object_type_policy_uses_builtin_defaults(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    path = namespace.root / "namespace.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["allowed_block_types"] = None
    data["require_block_type"] = None
    path.write_text(json.dumps(data), encoding="utf-8")

    reopened = DiagramNamespace.open(namespace.root)

    assert reopened.allowed_block_types == (
        "Diagram.Block",
        "Design.Block",
        "Impl.Req.Block",
        "Issue.Block",
    )
    assert reopened.require_block_type is True


def test_only_type_is_universal_and_specialization_is_explicit(tmp_path: Path) -> None:
    namespace = DiagramNamespace.create(tmp_path / "generic", name="Experiments")
    draft = AnnotationDraftInterface.from_record(
        str(uuid4()), {"type": "Example.Free.Annotation"}
    )
    namespace.append((draft,))

    annotation = namespace.annotation(draft.id)
    assert annotation.type == "Example.Free.Annotation"
    assert annotation.to_record()["type"] == "Example.Free.Annotation"
    with pytest.raises(DiagramAnnotationSpecializationError):
        annotation.specialize()


def test_diagram_types_participate_in_harness_without_schema_changes() -> None:
    from tarav.unsorted.contracts import DiagramObjectAssertion, Finding
    from tarav.unsorted.records import TypedAnnotation, TypedShip

    assert issubclass(TypedShip, TaravObject)
    assert issubclass(TypedAnnotation, TaravObject)
    assert issubclass(DiagramObjectAssertion, TaravAssertion)
    assert issubclass(Finding, TaravPOIInstance)


def test_models_are_typed_ships_and_project_their_editions(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    line = _line(model.ship)
    namespace.apply(CaptureManifest.create(model.ship, (line,)))

    assert namespace.edition(model.current_edition_id).type == MODEL_EDITION_TYPE
    assert [item.id for item in model.projection_records()] == [_edition_id(line)]
    assert model.annotations() == ()
    assert isinstance(
        namespace.edition(_edition_id(line)).specialize(), LineEditionRecord
    )


def test_native_capture_stores_entities_as_typed_ships(tmp_path: Path) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    block_ship = str(uuid4())
    block_edition = str(uuid4())
    line_ship = str(uuid4())
    line_edition = str(uuid4())
    ref = {
        "session_identity": "a" * 64,
        "turn_address": "b" * 64,
        "turn_hash": "c" * 64,
    }
    manifest = CaptureManifest.create(
        model.ship,
        ships=(
            ShipDraftInterface.from_record(
                block_ship,
                {
                    "type": BLOCK_SHIP_TYPE,
                    "model_ship": model.ship,
                    "editions": [
                        {
                            "id": block_edition,
                            "block_type": DESIGN_BLOCK_OBJECT_TYPE,
                            "data": {"label": "Storage.Model"},
                        }
                    ],
                },
            ),
            ShipDraftInterface.from_record(
                line_ship,
                {
                    "type": LINE_SHIP_TYPE,
                    "model_ship": model.ship,
                    "block_ship": block_ship,
                    "editions": [
                        {
                            "id": line_edition,
                            "line_type": DESIGN_LINE_PRINCIPLE_TYPE,
                            "producer": ref,
                            "support": [{"root": ref, "neighborhood": []}],
                            "data": {"text": "Ships create semantic entities."},
                        }
                    ],
                },
            ),
        ),
    )

    receipt = namespace.apply(manifest)

    assert receipt.created_ships == (block_ship, line_ship)
    assert receipt.created == (block_edition, line_edition)
    assert (namespace.ships_root / f"{block_ship}.json").is_file()
    assert (namespace.ships_root / f"{line_ship}.json").is_file()
    assert tuple(namespace.annotations_root.iterdir()) == ()
    assert namespace.ship(line_ship).type == LINE_SHIP_TYPE
    assert namespace.edition(line_edition).type == LINE_EDITION_TYPE
    assert model.project().line(line_ship).editions[0].text == (
        "Ships create semantic entities."
    )


def test_ship_editions_grow_one_semantic_lineage_without_rebinding(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Old.Name")
    new_edition = str(uuid4())

    receipt = namespace.apply(
        CaptureManifest.create(
            model.ship,
            ships=(
                ShipDraftInterface.from_record(
                    model.ship,
                    {
                        "type": MODEL_SHIP_TYPE,
                        "editions": [
                            {"id": new_edition, "data": {"label": "New.Name"}}
                        ],
                    },
                ),
            ),
        )
    )

    assert receipt.created_ships == ()
    assert receipt.updated_ships == (model.ship,)
    assert namespace.model(model.ship).current_edition_id == new_edition
    assert [item["data"]["label"] for item in model.record.editions] == [
        "Old.Name",
        "New.Name",
    ]

    with pytest.raises(DiagramError, match="edition identity cannot be rebound"):
        namespace.apply(
            CaptureManifest.create(
                model.ship,
                ships=(
                    ShipDraftInterface.from_record(
                        model.ship,
                        {
                            "type": MODEL_SHIP_TYPE,
                            "editions": [
                                {"id": new_edition, "data": {"label": "Other"}}
                            ],
                        },
                    ),
                ),
            )
        )


def test_annotations_make_claims_about_existing_ships_without_creating_them(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    block_ship = str(uuid4())
    block = _block(model.ship, block_ship=block_ship, label="Claims")
    namespace.apply(CaptureManifest.create(model.ship, (block,)))
    claim = AnnotationDraftInterface.from_record(
        str(uuid4()),
        {
            "type": BLOCK_TYPE_ANNOTATION_TYPE,
            "location": DiagramBlockLocationInterface(
                model_ship=model.ship, block_ship=block_ship
            ).model_dump(mode="json"),
            "block_type": DESIGN_BLOCK_OBJECT_TYPE,
        },
    )

    namespace.apply(CaptureManifest.create(model.ship, annotations=(claim,)))

    assert (namespace.annotations_root / f"{claim.id}.json").is_file()
    assert not (namespace.ships_root / f"{claim.id}.json").exists()
    assert namespace.ship(block_ship).type == BLOCK_SHIP_TYPE


def test_annotation_collection_rejects_ship_editions(tmp_path: Path) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    invalid = AnnotationDraftInterface.from_record(
        str(uuid4()),
        {
            "type": LINE_EDITION_TYPE,
            "producer": {
                "session_identity": "a" * 64,
                "turn_address": "b" * 64,
                "turn_hash": "c" * 64,
            },
            "support": [],
            "location": DiagramLocationInterface(
                model_ship=model.ship, block_ship=str(uuid4()), line_ship=str(uuid4())
            ).model_dump(mode="json"),
            "data": {"text": "This does not create a Line Ship."},
        },
    )
    manifest = CaptureManifest.create(model.ship, annotations=(invalid,))

    assert "ship-edition-in-annotation-collection" in {
        finding.code for finding in manifest.check(namespace)
    }
    with pytest.raises(DiagramError, match="cannot be stored in annotations"):
        namespace.apply(manifest)


def test_block_annotation_is_a_structural_attachment_point(tmp_path: Path) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    block_ship = str(uuid4())
    block = _block(model.ship, block_ship=block_ship, label="Kernel.Writing")

    receipt = namespace.apply(CaptureManifest.create(model.ship, (block,)))
    typed = namespace.edition(_edition_id(block)).specialize()

    assert receipt.created == (_edition_id(block),)
    assert receipt.committed is True
    assert receipt.commit is not None
    assert receipt.commit != receipt.base_commit
    assert isinstance(typed, BlockEditionRecord)
    assert typed.location.block_ship == block_ship
    assert typed.label == "Kernel.Writing"
    assert "producer" not in typed.to_record()
    assert "support" not in typed.to_record()


def test_capture_reports_pois_but_remains_writable(tmp_path: Path) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model()
    line = _line(model.ship, support=False)

    receipt = namespace.apply(CaptureManifest.create(model.ship, (line,)))

    assert receipt.created == (_edition_id(line),)
    assert {item.code for item in receipt.findings} == {
        "semantic-record-unasserted",
        "archive-grounding-unassessable",
        "empty-support-set",
        "block-declaration-missing",
        "line-type-missing",
    }
    assert namespace.edition(_edition_id(line)).standing == "UnAsserted"


def test_capture_apply_cli_can_write_without_committing(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config_path = tmp_path / "diagram.json"
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    DiagramConfiguration.load(config_path, create=True).mount(namespace, default=True)
    line = _line(model.ship)
    manifest_path = tmp_path / "capture.json"
    manifest_path.write_text(
        json.dumps(CaptureManifest.create(model.ship, (line,)).to_record()),
        encoding="utf-8",
    )
    base_commit = subprocess.run(
        ("git", "-C", str(namespace.root), "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    monkeypatch.setattr(diagram_commands, "_diagram_evidence", lambda _: None)

    assert (
        main(
            [
                "diagram",
                "capture",
                "apply",
                "--manifest",
                str(manifest_path),
                "--diagram-config",
                str(config_path),
                "--no-commit",
                "--json",
            ]
        )
        == 0
    )

    receipt = json.loads(capsys.readouterr().out)["receipt"]
    head = subprocess.run(
        ("git", "-C", str(namespace.root), "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ("git", "-C", str(namespace.root), "status", "--short"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert receipt["committed"] is False
    assert receipt["base_commit"] == base_commit
    assert receipt["commit"] is None
    assert head == base_commit
    line_ship = line.id
    assert status == f"?? ships/{line_ship}.json"


def test_capture_model_resolves_the_only_writable_namespace(tmp_path: Path) -> None:
    first = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "first")
    second = DiagramNamespace.create(tmp_path / "second", name="Experiments")
    model = first.create_model()
    line = _line(model.ship)
    diagram = Diagram((second, first), default_namespace_id=second.id)

    receipt = diagram.apply(CaptureManifest.create(model.ship, (line,)))

    assert receipt.namespace_id == first.id
    line_ship = line.id
    assert (first.ships_root / f"{line_ship}.json").is_file()
    assert not (second.ships_root / f"{line_ship}.json").exists()


def test_diagram_attic_uses_chatlas_index_record_policy(tmp_path: Path) -> None:
    namespace = DiagramNamespace.create_diagram_attic(tmp_path / "attic")
    model = namespace.create_model(label="Legacy.Index")
    line = _line(model.ship)

    receipt = namespace.apply(CaptureManifest.create(model.ship, (line,)))
    typed = namespace.edition(_edition_id(line)).specialize()

    assert namespace.name == DIAGRAM_ATTIC
    assert isinstance(typed, LineEditionRecord)
    assert receipt.created == (_edition_id(line),)
    assert {item.code for item in receipt.findings} == {
        "semantic-record-unasserted",
        "archive-grounding-unassessable",
        "block-declaration-missing",
        "line-type-missing",
    }


def test_full_projector_specializes_design_block_and_full_line_type(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    block_ship = str(uuid4())
    line_ship = str(uuid4())
    block = _block(
        model.ship,
        block_ship=block_ship,
        label="Diagram.Object.Type",
        block_type=DESIGN_BLOCK_OBJECT_TYPE,
    )
    line = _line(
        model.ship,
        block_ship=block_ship,
        line_ship=line_ship,
        line_type=DESIGN_LINE_PRINCIPLE_TYPE,
    )

    receipt = namespace.apply(CaptureManifest.create(model.ship, (block, line)))
    projection = model.project()
    projected_block = projection.block(block_ship)
    projected_line = projection.line(line_ship)

    assert isinstance(projected_block, DesignBlock)
    assert projected_block.object_type == DESIGN_BLOCK_OBJECT_TYPE
    assert projected_line.object_type == DESIGN_LINE_PRINCIPLE_TYPE
    assert isinstance(projected_line, DesignPrincipleLineShip)
    assert isinstance(projected_line.editions[0], DesignLinePrinciple)
    assert not {
        "block-type-missing",
        "line-type-missing",
        "line-type-not-allowed-by-block",
    } & {item.code for item in receipt.findings}
    assertion_ids = [item.id for item in projected_block.assertions()]
    assert len(assertion_ids) == len(set(assertion_ids))


def test_impl_req_block_reuses_design_line_types_without_becoming_design_block(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    block_ship = str(uuid4())
    line_ship = str(uuid4())
    block = _block(
        model.ship,
        block_ship=block_ship,
        label="502.Impl.Req",
        block_type=IMPL_REQ_BLOCK_OBJECT_TYPE,
    )
    line = _line(
        model.ship,
        block_ship=block_ship,
        line_ship=line_ship,
        line_type=DESIGN_LINE_PRINCIPLE_TYPE,
    )

    receipt = namespace.apply(CaptureManifest.create(model.ship, (block, line)))
    projected_block = model.project().block(block_ship)
    projected_line = model.project().line(line_ship)

    assert isinstance(projected_block, ImplReqBlock)
    assert not isinstance(projected_block, DesignBlock)
    assert projected_block.object_type == IMPL_REQ_BLOCK_OBJECT_TYPE
    assert projected_block.labels == ("502.Impl.Req",)
    assert isinstance(projected_line, DesignPrincipleLineShip)
    assert not {
        "block-type-not-allowed",
        "line-type-not-allowed-by-block",
    } & {item.code for item in receipt.findings}


def test_issue_block_is_open_and_surfaces_a_nonblocking_poi(tmp_path: Path) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    block_ship = str(uuid4())
    line = _line(
        model.ship,
        block_ship=block_ship,
        line_type=DESIGN_LINE_PRINCIPLE_TYPE,
    )
    block = _block(
        model.ship,
        block_ship=block_ship,
        label="Parking.Workflow",
        block_type=ISSUE_BLOCK_OBJECT_TYPE,
    )

    receipt = namespace.apply(CaptureManifest.create(model.ship, (block, line)))
    projected = model.project().block(block_ship)
    assessment = projected.assess(AssertionEngine())

    assert isinstance(projected, IssueBlock)
    assert projected.object_type == ISSUE_BLOCK_OBJECT_TYPE
    assert assessment.state == "Open"
    assert assessment.resolution_line_ships == ()
    assert "issue-open" in {item.code for item in receipt.findings}
    assert receipt.created == (_edition_id(block), _edition_id(line))


def test_issue_block_closes_only_with_a_passing_reviewed_resolve_line(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    block_ship = str(uuid4())
    resolution_ship = str(uuid4())
    identity = "d" * 64
    token = "review:issue-resolved"
    text = "The Issue is resolved."
    normal_model = _normal_model(
        identity,
        ("user", "The implementation now resolves the parked concern."),
        ("agent", f"{text}\n\n::approve {token}"),
        ("user", f"::approve {token}"),
    )
    user_ref = {
        "session_identity": identity,
        "turn_address": "1" * 64,
        "turn_hash": "2" * 64,
    }
    producer_ref = {
        "session_identity": identity,
        "turn_address": "5" * 64,
        "turn_hash": "6" * 64,
    }
    block = _block(
        model.ship,
        block_ship=block_ship,
        label="Issue.Lifecycle",
        block_type=ISSUE_BLOCK_OBJECT_TYPE,
    )
    resolution = ShipDraftInterface.from_record(
        resolution_ship,
        {
            "type": LINE_SHIP_TYPE,
            "model_ship": model.ship,
            "block_ship": block_ship,
            "editions": [
                {
                    "id": str(uuid4()),
                    "line_type": ISSUE_LINE_RESOLVE_TYPE,
                    "producer": producer_ref,
                    "support": [{"root": user_ref, "neighborhood": []}],
                    "data": {"text": text},
                    "gates": [
                        VerbatimGate(
                            token,
                            ChatlasTurnReferenceInterface(
                                session_identity=identity,
                                turn_address="5" * 64,
                                turn_hash="6" * 64,
                            ),
                            ChatlasTurnReferenceInterface(
                                session_identity=identity,
                                turn_address="9" * 64,
                                turn_hash="a" * 64,
                            ),
                        ).to_dict()
                    ],
                }
            ],
        },
    )
    evidence = ChatlasEvidence(model_loader=lambda _: normal_model)

    receipt = namespace.apply(
        CaptureManifest.create(model.ship, (block, resolution)), evidence=evidence
    )
    projected = model.project().block(block_ship)
    projected_resolution = model.project().line(resolution_ship)
    assessment = projected.assess(AssertionEngine(evidence=evidence))

    assert isinstance(projected, IssueBlock)
    assert isinstance(projected_resolution, IssueResolveLineShip)
    assert isinstance(projected_resolution.editions[0], IssueLineResolve)
    assert assessment.state == "Closed"
    assert assessment.resolution_line_ships == (resolution_ship,)
    assert assessment.gate_assessments[0].standing == "Passed"
    assert "issue-open" not in {item.code for item in receipt.findings}

    followup = ShipDraftInterface.from_record(
        str(uuid4()),
        {
            "type": LINE_SHIP_TYPE,
            "model_ship": model.ship,
            "block_ship": block_ship,
            "editions": [
                {
                    "id": str(uuid4()),
                    "line_type": DESIGN_LINE_EXAMPLE_TYPE,
                    "producer": producer_ref,
                    "support": [{"root": user_ref, "neighborhood": []}],
                    "data": {
                        "text": "Later Issue material does not stale its resolution."
                    },
                }
            ],
        },
    )
    later = namespace.apply(
        CaptureManifest.create(model.ship, (followup,)), evidence=evidence
    )

    assert (
        model.project()
        .block(block_ship)
        .assess(AssertionEngine(evidence=evidence))
        .state
        == "Closed"
    )
    assert "issue-open" not in {item.code for item in later.findings}


def test_unassessable_resolve_gate_leaves_issue_open(tmp_path: Path) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    block_ship = str(uuid4())
    resolution = _line(
        model.ship,
        block_ship=block_ship,
        line_type=ISSUE_LINE_RESOLVE_TYPE,
        text="The Issue is resolved.",
        gates=[
            VerbatimGate(
                "review:unassessable",
                ChatlasTurnReferenceInterface(
                    session_identity="d" * 64, turn_address="1" * 64, turn_hash="2" * 64
                ),
                ChatlasTurnReferenceInterface(
                    session_identity="d" * 64, turn_address="5" * 64, turn_hash="6" * 64
                ),
            ).to_dict()
        ],
    )
    block = _block(
        model.ship,
        block_ship=block_ship,
        label="Issue.Unassessable.Resolution",
        block_type=ISSUE_BLOCK_OBJECT_TYPE,
    )

    receipt = namespace.apply(CaptureManifest.create(model.ship, (block, resolution)))
    assessment = model.project().block(block_ship).assess(AssertionEngine())

    assert assessment.state == "Open"
    assert assessment.gate_assessments[0].standing == "Unassessable"
    assert "issue-open" in {item.code for item in receipt.findings}


def test_type_annotations_classify_existing_objects_without_user_support(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    block_ship = str(uuid4())
    line_ship = str(uuid4())
    block = _block(model.ship, block_ship=block_ship, label="Capture.First")
    line = _line(model.ship, block_ship=block_ship, line_ship=line_ship)
    namespace.apply(CaptureManifest.create(model.ship, (block, line)))
    block_type = AnnotationDraftInterface.from_record(
        str(uuid4()),
        {
            "type": BLOCK_TYPE_ANNOTATION_TYPE,
            "location": DiagramBlockLocationInterface(
                model_ship=model.ship, block_ship=block_ship
            ).model_dump(mode="json"),
            "block_type": DESIGN_BLOCK_OBJECT_TYPE,
        },
    )
    line_type = AnnotationDraftInterface.from_record(
        str(uuid4()),
        {
            "type": LINE_TYPE_ANNOTATION_TYPE,
            "location": DiagramLocationInterface(
                model_ship=model.ship, block_ship=block_ship, line_ship=line_ship
            ).model_dump(mode="json"),
            "line_type": DESIGN_LINE_PRINCIPLE_TYPE,
        },
    )

    receipt = namespace.apply(
        CaptureManifest.create(model.ship, annotations=(block_type, line_type))
    )
    projection = model.project()
    projected_block = projection.block(block_ship)
    projected_line = projection.line(line_ship)
    typed_block_annotation = namespace.annotation(block_type.id).specialize()
    typed_line_annotation = namespace.annotation(line_type.id).specialize()

    assert isinstance(typed_block_annotation, BlockTypeAnnotation)
    assert isinstance(typed_line_annotation, LineTypeAnnotation)
    assert "support" not in typed_block_annotation.to_record()
    assert "producer" not in typed_block_annotation.to_record()
    assert "support" not in typed_line_annotation.to_record()
    assert "producer" not in typed_line_annotation.to_record()
    assert typed_block_annotation.annotation.assertions() == (
        {"type": "Semantic.Record.Representation.Assertion"},
        {"type": "Block.Type.Conformance.Assertion"},
    )
    assert typed_line_annotation.annotation.assertions() == (
        {"type": "Semantic.Record.Representation.Assertion"},
        {"type": "Line.Type.Conformance.Assertion"},
    )
    assert isinstance(projected_block, DesignBlock)
    assert projected_block.object_type == DESIGN_BLOCK_OBJECT_TYPE
    assert isinstance(projected_line, DesignPrincipleLineShip)
    assert projected_line.object_type == DESIGN_LINE_PRINCIPLE_TYPE
    projected_record = projection.to_dict()["blocks"][0]
    assert projected_record["editions"] == [_edition_id(block)]
    assert projected_record["annotations"] == [block_type.id]
    assert projected_record["lines"][0]["editions"] == [_edition_id(line)]
    assert projected_record["lines"][0]["annotations"] == [line_type.id]
    assert {item.code for item in receipt.findings} == {"semantic-record-unasserted"}


def test_untyped_line_in_design_block_uses_generic_recovery_without_disallowed_poi(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    block_ship = str(uuid4())
    block = _block(
        model.ship,
        block_ship=block_ship,
        label="Unsettled.Type",
        block_type=DESIGN_BLOCK_OBJECT_TYPE,
    )
    line = _line(model.ship, block_ship=block_ship)

    receipt = namespace.apply(CaptureManifest.create(model.ship, (block, line)))
    codes = {item.code for item in receipt.findings}

    assert "line-type-missing" in codes
    assert "line-type-not-allowed-by-block" not in codes


def test_unknown_object_types_remain_writable_and_surface_projection_pois(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model()
    block_ship = str(uuid4())
    line = _line(
        model.ship,
        block_ship=block_ship,
        line_type="Unknown.Line.Type",
    )
    block = _block(
        model.ship,
        block_ship=block_ship,
        label="Unknown",
        block_type="Unknown.Block.Type",
    )

    receipt = namespace.apply(CaptureManifest.create(model.ship, (block, line)))

    assert receipt.created == (_edition_id(block), _edition_id(line))
    assert {"block-type-unknown", "block-type-not-allowed", "line-type-unknown"} <= {
        item.code for item in receipt.findings
    }


def test_annotation_identity_is_non_rebinding(tmp_path: Path) -> None:
    namespace = DiagramNamespace.create(tmp_path / "generic", name="Experiments")
    annotation_id = str(uuid4())
    namespace.append(
        (AnnotationDraftInterface.from_record(annotation_id, {"type": "Example.One"}),)
    )
    with pytest.raises(DiagramError, match="cannot be rebound"):
        namespace.append(
            (
                AnnotationDraftInterface.from_record(
                    annotation_id, {"type": "Example.Two"}
                ),
            )
        )


def test_project_main_model_bootstraps_in_default_user_namespace(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    (project / ".tarav").mkdir(parents=True)
    marker = {"class": "agentos.project", "project_id": str(uuid4())}
    (project / ".tarav" / "project.json").write_text(
        json.dumps(marker), encoding="utf-8"
    )
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    diagram = Diagram((namespace,), namespace.id)

    model = diagram.ensure_project_model(project)
    again = diagram.ensure_project_model(project)

    stored = json.loads((project / ".tarav" / "project.json").read_text())
    assert stored["diagram"] == {"main_model": model.ship}
    assert again.ship == model.ship


def test_several_projects_can_share_one_main_model(tmp_path: Path) -> None:
    first_project = _project(tmp_path / "tarav-md")
    second_project = _project(tmp_path / "tarav-py")
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    diagram = Diagram((namespace,), namespace.id)

    diagram.set_project_main_model(first_project, model.ship)
    diagram.set_project_main_model(second_project, model.ship)

    for project in (first_project, second_project):
        marker = json.loads((project / ".tarav" / "project.json").read_text())
        assert marker["diagram"] == {"main_model": model.ship}
        assert marker["preserved"] is True
    assert len(namespace.ships()) == 1
    assert namespace.annotations() == ()


def test_project_main_model_is_not_changed_when_model_is_missing(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")
    marker_path = project / ".tarav" / "project.json"
    before = marker_path.read_text()
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")

    with pytest.raises(DiagramError, match="does not resolve uniquely"):
        Diagram((namespace,), namespace.id).set_project_main_model(
            project, str(uuid4())
        )

    assert marker_path.read_text() == before


def test_namespace_cli_and_project_capture_template(tmp_path: Path, capsys) -> None:
    config = tmp_path / "diagram.json"
    namespace = tmp_path / "index"
    project = tmp_path / "project"
    manifest = tmp_path / "capture.json"
    (project / ".tarav").mkdir(parents=True)
    (project / ".tarav" / "project.json").write_text(
        json.dumps({"class": "agentos.project", "project_id": str(uuid4())}),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "diagram",
                "namespace",
                "create",
                "--location",
                str(namespace),
                "--name",
                USER_TOUCHED_CHATLAS_INDEX,
                "--default",
                "--diagram-config",
                str(config),
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "diagram",
                "capture",
                "template",
                "--manifest",
                str(manifest),
                "--project",
                str(project),
                "--diagram-config",
                str(config),
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    capture = json.loads(manifest.read_text())
    project_marker = json.loads((project / ".tarav" / "project.json").read_text())
    assert payload["status"] == "ok"
    assert capture["model_ship"] == project_marker["diagram"]["main_model"]
    assert capture["ships"] == []
    assert capture["annotations"] == []

    assert (
        main(
            [
                "diagram",
                "ship",
                "show",
                "--ship",
                capture["model_ship"],
                "--diagram-config",
                str(config),
                "--json",
            ]
        )
        == 0
    )
    ship_payload = json.loads(capsys.readouterr().out)
    assert ship_payload["ship"]["type"] == MODEL_SHIP_TYPE
    assert len(ship_payload["ship"]["editions"]) == 1
    assert DiagramConfiguration.load(config).default_namespace_id is not None


def test_line_show_cli_separates_ship_editions_from_annotations(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "diagram.json"
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    line = _line(model.ship)
    line_ship = line.id
    namespace.apply(CaptureManifest.create(model.ship, (line,)))
    DiagramConfiguration.load(config_path, create=True).mount(namespace, default=True)

    assert (
        main(
            [
                "diagram",
                "line",
                "show",
                "--line-ship",
                line_ship,
                "--diagram-config",
                str(config_path),
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert [edition["id"] for edition in payload["editions"]] == [_edition_id(line)]
    assert payload["annotations"] == []


def test_projection_queries_objects_by_kind_type_and_label(tmp_path: Path) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    initial_impl_block = _block(
        model.ship,
        label="Legacy.Impl.Req",
        block_type=IMPL_REQ_BLOCK_OBJECT_TYPE,
    )
    impl_block = ShipDraftInterface.from_record(
        initial_impl_block.id,
        {
            **initial_impl_block.record,
            "editions": [
                *initial_impl_block.record["editions"],
                {
                    "id": str(uuid4()),
                    "block_type": IMPL_REQ_BLOCK_OBJECT_TYPE,
                    "data": {"label": "770.Impl.Req"},
                },
            ],
        },
    )
    design_block = _block(
        model.ship,
        label="Diagram.Query",
        block_type=DESIGN_BLOCK_OBJECT_TYPE,
    )
    impl_line = _line(
        model.ship,
        block_ship=impl_block.id,
        line_type=DESIGN_LINE_PRINCIPLE_TYPE,
        support=False,
    )
    namespace.apply(
        CaptureManifest.create(model.ship, (impl_block, design_block, impl_line))
    )

    projection = model.project()

    assert projection.objects(
        kind="block",
        object_type=IMPL_REQ_BLOCK_OBJECT_TYPE,
        label="Legacy.Impl.Req",
    ) == (projection.block(impl_block.id),)
    assert projection.block(impl_block.id).current_label == "770.Impl.Req"
    assert projection.objects(kind="line") == (projection.line(impl_line.id),)
    assert projection.objects(label="Diagram.Query") == (
        projection.block(design_block.id),
    )
    with pytest.raises(DiagramModelError, match="unsupported Diagram object kind"):
        projection.objects(kind="annotation")


def test_object_list_cli_returns_compact_scoped_standing(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "diagram.json"
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    impl_block = _block(
        model.ship,
        label="770.Impl.Req",
        block_type=IMPL_REQ_BLOCK_OBJECT_TYPE,
    )
    impl_line = _line(
        model.ship,
        block_ship=impl_block.id,
        line_type=DESIGN_LINE_PRINCIPLE_TYPE,
        support=False,
    )
    unrelated_legacy_block = _block(model.ship, label="Legacy")
    namespace.apply(
        CaptureManifest.create(
            model.ship, (impl_block, impl_line, unrelated_legacy_block)
        )
    )
    DiagramConfiguration.load(config_path, create=True).mount(namespace, default=True)

    assert (
        main(
            [
                "diagram",
                "object",
                "list",
                "--model-ship",
                model.ship,
                "--kind",
                "block",
                "--object-type",
                IMPL_REQ_BLOCK_OBJECT_TYPE,
                "--diagram-config",
                str(config_path),
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "poi"
    assert payload["filters"] == {
        "kind": "block",
        "object_type": IMPL_REQ_BLOCK_OBJECT_TYPE,
        "label": None,
    }
    assert payload["model"]["ship"] == model.ship
    assert len(payload["objects"]) == 1
    result = payload["objects"][0]
    assert result["kind"] == "block"
    assert result["ship"] == impl_block.id
    assert result["current_edition_id"] == _edition_id(impl_block)
    assert result["current_label"] == "770.Impl.Req"
    assert result["line_count"] == 1
    assert result["standing"]["unasserted"] > 0
    assert result["standing"]["unreviewed_lines"] == 1
    assert all(
        unrelated_legacy_block.id not in finding["path"]
        for finding in payload["findings"]
    )


def test_project_set_main_model_cli_associates_an_existing_model(
    tmp_path: Path, capsys
) -> None:
    config = tmp_path / "diagram.json"
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Shared Tarav")
    DiagramConfiguration.load(config, create=True).mount(namespace, default=True)
    project = _project(tmp_path / "tarav-md")

    assert (
        main(
            [
                "diagram",
                "project",
                "set-main-model",
                "--project",
                str(project),
                "--model-ship",
                model.ship,
                "--diagram-config",
                str(config),
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    marker = json.loads((project / ".tarav" / "project.json").read_text())
    assert payload["main_model"] == model.ship
    assert payload["namespace_id"] == namespace.id
    assert marker["diagram"] == {"main_model": model.ship}


def test_capture_context_returns_model_and_manifest_ready_turn_references(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    config = tmp_path / "diagram.json"
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Shared Tarav")
    DiagramConfiguration.load(config, create=True).mount(namespace, default=True)
    project = _project(tmp_path / "tarav-md")
    Diagram((namespace,), namespace.id).set_project_main_model(project, model.ship)
    identity = "a" * 64
    normal_model = _normal_model(
        identity, ("user", "Approve this line."), ("agent", "Settled capture.")
    )
    monkeypatch.setattr(
        diagram_commands, "provide_normal_model", lambda **_: normal_model
    )

    assert (
        main(
            [
                "diagram",
                "capture",
                "context",
                "--project",
                str(project),
                "--session-id",
                "session-one",
                "--diagram-config",
                str(config),
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["model"]["ship"] == model.ship
    block_types = payload["model"]["object_types"]["block_types"]
    design = next(item for item in block_types if item["id"] == "Design.Block")
    impl_req = next(item for item in block_types if item["id"] == "Impl.Req.Block")
    issue = next(item for item in block_types if item["id"] == "Issue.Block")
    generic = next(item for item in block_types if item["id"] == "Diagram.Block")
    assert generic["definition_block_ship"] == ("7b2bb6ef-37b8-47e0-8c6b-2ff5ccbdd82d")
    assert generic["line_types"][0]["definition_block_ship"] == (
        "7b2bb6ef-37b8-47e0-8c6b-2ff5ccbdd82d"
    )
    assert design["definition_block_ship"] == ("aa26bfa3-49f6-406d-b74f-f071ec3d11fa")
    assert [item["id"] for item in design["line_types"]] == [
        "Design.Line.Definition",
        "Design.Line.Decision",
        "Design.Line.Constraint",
        "Design.Line.Rejection",
        "Design.Line.Principle",
        "Design.Line.Freedom",
        "Design.Line.Example",
    ]
    assert impl_req["class"] == "ImplReqBlock"
    assert impl_req["definition_block_ship"] == ("f6dfcbcb-6eb5-468c-a3f8-7f7034334b94")
    assert impl_req["line_types"] == design["line_types"]
    assert issue["class"] == "IssueBlock"
    assert issue["definition_block_ship"] == ("4864c2cc-9542-49ea-8295-a566eea29164")
    assert issue["line_types"][:-1] == design["line_types"]
    assert issue["line_types"][-1] == {
        "id": "Issue.Line.Resolve",
        "short_code": "RESOLVE",
        "edition_class": "IssueLineResolve",
        "ship_class": "IssueResolveLineShip",
        "definition_block_ship": "3753a425-04e7-4d62-9d44-01f42af5b5e4",
    }
    assert {
        item["id"]: item["definition_block_ship"] for item in design["line_types"]
    } == {
        "Design.Line.Definition": "00a33f68-90a7-4a92-87c4-c3862e879bc5",
        "Design.Line.Decision": "7cf2af24-e6d9-46b7-a09a-c43db69ccd68",
        "Design.Line.Constraint": "9b0bea0f-1408-483e-85cf-504e2009ad25",
        "Design.Line.Rejection": "2d3dd161-b4c2-4810-9e2b-4fda1a6c8743",
        "Design.Line.Principle": "6c43fce3-dd2d-40d3-b676-4e58df8195ee",
        "Design.Line.Freedom": "1894d99c-ddca-491d-a586-1a7a53e9c4b0",
        "Design.Line.Example": "1366fc61-a9fe-4ef5-91dc-6f13f0447e30",
    }
    assert len(payload["model"]["object_types"]["findings"]) == 15
    assert {item["code"] for item in payload["model"]["object_types"]["findings"]} == {
        "object-type-definition-block-unresolved"
    }
    assert [item["side"] for item in payload["chat"]["turns"]] == ["user", "agent"]
    assert payload["chat"]["turns"][0]["text"] == "Approve this line."
    assert payload["chat"]["turns"][0]["reference"]["session_identity"] == identity


def test_model_create_and_list_cli_support_shared_model_selection(
    tmp_path: Path, capsys
) -> None:
    config = tmp_path / "diagram.json"
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    DiagramConfiguration.load(config, create=True).mount(namespace, default=True)

    assert (
        main(
            [
                "diagram",
                "model",
                "create",
                "--label",
                "Tarav",
                "--diagram-config",
                str(config),
                "--json",
            ]
        )
        == 0
    )
    created = json.loads(capsys.readouterr().out)["model"]
    assert (
        main(
            [
                "diagram",
                "model",
                "list",
                "--diagram-config",
                str(config),
                "--json",
            ]
        )
        == 0
    )
    listed = json.loads(capsys.readouterr().out)["models"]

    assert [item["ship"] for item in listed] == [created["ship"]]
    assert listed[0]["namespace_id"] == namespace.id


def test_support_must_precede_the_producer_turn() -> None:
    identity = "a" * 64
    normal_model = _normal_model(
        identity,
        ("agent", "Settled capture."),
        ("user", "This arrived too late."),
    )
    evidence = ChatlasEvidence(model_loader=lambda _: normal_model)
    producer = ChatlasTurnReferenceInterface(
        session_identity=identity, turn_address="1" * 64, turn_hash="2" * 64
    )
    late_support = ChatlasTurnReferenceInterface(
        session_identity=identity, turn_address="5" * 64, turn_hash="6" * 64
    )

    assert evidence.was_available(producer, late_support) is False


def test_gate_only_annotation_reviews_an_existing_line_without_rebinding_it(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    line = _line(model.ship)
    namespace.apply(CaptureManifest.create(model.ship, (line,)))
    original = namespace.edition(_edition_id(line)).to_record()
    identity = "d" * 64
    normal_model = _normal_model(
        identity,
        (
            "agent",
            "Capture concerns only the present Model.\n\n"
            "Approve with ::approve review:gate-one",
        ),
        ("user", "::approve review:gate-one"),
    )
    gate = VerbatimGate(
        "review:gate-one",
        ChatlasTurnReferenceInterface(
            session_identity=identity, turn_address="1" * 64, turn_hash="2" * 64
        ),
        ChatlasTurnReferenceInterface(
            session_identity=identity, turn_address="5" * 64, turn_hash="6" * 64
        ),
    )
    gate_draft = AnnotationDraftInterface.from_record(
        str(uuid4()),
        {
            "type": LINE_GATE_ANNOTATION_TYPE,
            "target_edition": _edition_id(line),
            "gates": [gate.to_dict()],
        },
    )
    evidence = ChatlasEvidence(model_loader=lambda _: normal_model)
    other_model = namespace.create_model(label="Other")

    mismatch = CaptureManifest.create(
        other_model.ship, annotations=(gate_draft,)
    ).check(namespace, evidence=evidence)
    mismatch_finding = next(
        item for item in mismatch if item.code == "capture-model-mismatch"
    )
    assert mismatch_finding.path == "annotations[0].target_edition"

    receipt = namespace.apply(
        CaptureManifest.create(model.ship, annotations=(gate_draft,)), evidence=evidence
    )
    typed = namespace.annotation(gate_draft.id).specialize()
    review = namespace.line_review(
        namespace.edition(_edition_id(line)).specialize().location.line_ship,
        evidence=evidence,
    )

    assert isinstance(typed, LineGateAnnotation)
    assert typed.target.id == _edition_id(line)
    assert namespace.edition(_edition_id(line)).to_record() == original
    assert review.standing == "Reviewed"
    assert review.assessments[0].standing == "Passed"
    assert set(review.assessments[0].scores.values()) == {True}
    assert not {
        "verbatim-gate-token-mismatch",
        "verbatim-gate-order-mismatch",
        "verbatim-gate-content-mismatch",
    } & {item.code for item in receipt.findings}


def test_assertion_engine_recomputes_gate_scores_without_mutating_the_record(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    line = _line(model.ship)
    namespace.apply(CaptureManifest.create(model.ship, (line,)))
    identity = "d" * 64
    token = "review:central-engine"
    normal_model = _normal_model(
        identity,
        (
            "agent",
            f"Capture concerns only the present Model.\n\n::approve {token}",
        ),
        ("user", f"::approve {token}"),
    )
    gate = AnnotationDraftInterface.from_record(
        str(uuid4()),
        {
            "type": LINE_GATE_ANNOTATION_TYPE,
            "target_edition": _edition_id(line),
            "gates": [
                VerbatimGate(
                    token,
                    ChatlasTurnReferenceInterface(
                        session_identity=identity,
                        turn_address="1" * 64,
                        turn_hash="2" * 64,
                    ),
                    ChatlasTurnReferenceInterface(
                        session_identity=identity,
                        turn_address="5" * 64,
                        turn_hash="6" * 64,
                    ),
                ).to_dict()
            ],
        },
    )
    namespace.apply(CaptureManifest.create(model.ship, annotations=(gate,)))
    annotation = namespace.annotation(gate.id)
    retained_before = annotation.to_record()

    assessment = AssertionEngine(
        evidence=ChatlasEvidence(model_loader=lambda _: normal_model)
    ).assess(annotation)

    assert assessment.standing == "UnAsserted"
    assert all(
        assessment.assertion_state(assertion_type) == "Passed"
        for assertion_type in assessment.assertion_types
        if assertion_type.startswith("Verbatim.Gate.")
    )
    assert (
        assessment.assertion_state("Semantic.Record.Representation.Assertion")
        == "NotEvaluated"
    )
    assert annotation.score_vector() == {}
    assert namespace.annotation(gate.id).to_record() == retained_before


def test_assertion_engine_distinguishes_unassessable_from_not_evaluated(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    line = _line(model.ship)
    _edition(line)["gates"] = [
        VerbatimGate(
            "review:no-evidence",
            ChatlasTurnReferenceInterface(
                session_identity="d" * 64, turn_address="1" * 64, turn_hash="2" * 64
            ),
            ChatlasTurnReferenceInterface(
                session_identity="d" * 64, turn_address="5" * 64, turn_hash="6" * 64
            ),
        ).to_dict()
    ]
    namespace.apply(CaptureManifest.create(model.ship, (line,)))

    assessment = AssertionEngine().assess(namespace.edition(_edition_id(line)))

    assert assessment.assertion_state("Verbatim.Gate.Token.Assertion") == "Unassessable"
    assert assessment.assertion_state("Line.Continuity.Assertion") == "NotEvaluated"
    assert assessment.score_vector["Verbatim.Gate.Token.Assertion"] is None
    assert "Line.Continuity.Assertion" not in assessment.score_vector


def test_assertion_engine_accepts_registered_evaluators(tmp_path: Path) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    line = _line(model.ship)
    namespace.apply(CaptureManifest.create(model.ship, (line,)))

    class ContinuityEvaluator:
        name = "Test.Line.Continuity.Evaluator"
        assertion_types = ("Line.Continuity.Assertion",)

        def evaluate(self, annotation, *, evidence, path):
            del annotation, evidence, path
            return AssertionEvaluation(self.name, {"Line.Continuity.Assertion": True})

    assessment = AssertionEngine(evaluators=(ContinuityEvaluator(),)).assess(
        namespace.edition(_edition_id(line))
    )

    assert assessment.assertion_state("Line.Continuity.Assertion") == "Passed"
    assert assessment.assertion_state("Block.Context.Assertion") == "NotEvaluated"


def test_embedded_gate_reviews_a_new_line_and_bad_wording_remains_a_poi(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    identity = "d" * 64
    normal_model = _normal_model(
        identity,
        ("agent", "Different wording. review:gate-two"),
        ("user", "::approve review:gate-two"),
    )
    gate = VerbatimGate(
        "review:gate-two",
        ChatlasTurnReferenceInterface(
            session_identity=identity, turn_address="1" * 64, turn_hash="2" * 64
        ),
        ChatlasTurnReferenceInterface(
            session_identity=identity, turn_address="5" * 64, turn_hash="6" * 64
        ),
    )
    line = _line(model.ship)
    _edition(line)["gates"] = [gate.to_dict()]
    evidence = ChatlasEvidence(model_loader=lambda _: normal_model)

    receipt = namespace.apply(
        CaptureManifest.create(model.ship, (line,)), evidence=evidence
    )
    typed = namespace.edition(_edition_id(line)).specialize()
    review = namespace.line_review(typed.location.line_ship, evidence=evidence)

    assert isinstance(typed, LineEditionRecord)
    assert typed.gates == (gate,)
    assert review.standing == "Unreviewed"
    assert "verbatim-gate-content-mismatch" in {item.code for item in receipt.findings}


@pytest.mark.parametrize(
    ("turns", "proposal_address", "approval_address", "expected_code"),
    (
        (
            (
                ("agent", "Capture concerns only the present Model. review:bad"),
                ("user", "::approve another-token"),
            ),
            "1",
            "5",
            "verbatim-gate-token-mismatch",
        ),
        (
            (
                ("user", "::approve review:bad"),
                ("agent", "Capture concerns only the present Model. review:bad"),
            ),
            "5",
            "1",
            "verbatim-gate-order-mismatch",
        ),
        (
            (
                ("user", "Capture concerns only the present Model. review:bad"),
                ("agent", "::approve review:bad"),
            ),
            "1",
            "5",
            "verbatim-gate-proposal-not-agent",
        ),
    ),
)
def test_verbatim_gate_surfaces_protocol_failures(
    tmp_path: Path,
    turns: tuple[tuple[str, str], ...],
    proposal_address: str,
    approval_address: str,
    expected_code: str,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    line = _line(model.ship)
    namespace.apply(CaptureManifest.create(model.ship, (line,)))
    typed = namespace.edition(_edition_id(line)).specialize()
    identity = "d" * 64
    normal_model = _normal_model(identity, *turns)
    hashes = {"1": "2", "5": "6"}
    gate = VerbatimGate(
        "review:bad",
        ChatlasTurnReferenceInterface(
            session_identity=identity,
            turn_address=proposal_address * 64,
            turn_hash=hashes[proposal_address] * 64,
        ),
        ChatlasTurnReferenceInterface(
            session_identity=identity,
            turn_address=approval_address * 64,
            turn_hash=hashes[approval_address] * 64,
        ),
    )

    gate_annotation = AnnotationDraftInterface.from_record(
        str(uuid4()),
        {
            "type": LINE_GATE_ANNOTATION_TYPE,
            "target_edition": typed.id,
            "gates": [gate.to_dict()],
        },
    )
    namespace.apply(CaptureManifest.create(model.ship, annotations=(gate_annotation,)))
    assessment = (
        AssertionEngine(evidence=ChatlasEvidence(model_loader=lambda _: normal_model))
        .assess(namespace.annotation(gate_annotation.id))
        .gate_assessments[0]
    )

    assert assessment.standing == "Failed"
    assert expected_code in {item.code for item in assessment.findings}


def _normal_model(identity: str, *turn_values: tuple[str, str]) -> dict[str, object]:
    events = []
    messages = []
    turns = []
    digits = iter("123456789abcdef")
    for side, text in turn_values:
        turn_address = next(digits) * 64
        turn_hash = next(digits) * 64
        message_address = next(digits) * 64
        message_hash = next(digits) * 64
        message_ref = {
            "message_address": message_address,
            "message_hash": message_hash,
        }
        event_ref = {
            "event_address": turn_address,
            "event_hash": turn_hash,
        }
        events.append(
            {
                "type": "User.Event" if side == "user" else "Agent.Event",
                **event_ref,
                "started_at": "2026-09-20T00:00:00Z",
                "origin": side,
                "observations": [
                    {
                        "observed_at": "2026-09-20T00:00:00Z",
                        "source_ref": {
                            "source_id": "source-one",
                            "record_index": len(events) + 1,
                            "line": len(events) + 1,
                        },
                    }
                ],
                "opaque_payload_hash": "0" * 64,
                "content": {"text": text},
            }
        )
        messages.append(
            {
                "type": "Chat.Message",
                **message_ref,
                "side": side,
                "text": text,
                "event_refs": [event_ref],
            }
        )
        turns.append(
            {
                "type": "Chat.Turn",
                "turn_address": turn_address,
                "turn_hash": turn_hash,
                "side": side,
                "message_refs": [message_ref],
                "event_refs": [event_ref],
            }
        )
    return {
        "session": {"identity_hash": identity, "session_id": "session-one"},
        "events": events,
        "messages": messages,
        "turns": turns,
    }
