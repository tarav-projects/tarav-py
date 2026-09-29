from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from tarav.l3.cli.cli import main
from tarav.l2.unsorted.constants import BLOCK_SHIP_TYPE, DESIGN_BLOCK_OBJECT_TYPE, DESIGN_LINE_PRINCIPLE_TYPE, LINE_ANNOTATION_TYPE, LINE_SHIP_TYPE
from tarav.l2.unsorted.contracts import AnnotationDraftInterface, ShipDraftInterface
from tarav.l2.unsorted.capture import CaptureManifest
from tarav.l2.unsorted.storage import Diagram, DiagramConfiguration, DiagramNamespace
from tarav.l2.lines.references import DiagramArgumentReferenceInterface
from tarav.l2.unsorted.primitives import DiagramError
from tarav.l2.lines.records import LineAnnotationRecord
from tarav.l2.lines.rendering import annotation_render_target, renderer


REFERENCE = {
    "session_identity": "a" * 64,
    "turn_address": "b" * 64,
    "turn_hash": "c" * 64,
}


def _block(model_ship: str, block_ship: str, label: str) -> ShipDraftInterface:
    return ShipDraftInterface.from_record(
        block_ship,
        {
            "type": BLOCK_SHIP_TYPE,
            "model_ship": model_ship,
            "editions": [
                {
                    "id": str(uuid4()),
                    "block_type": DESIGN_BLOCK_OBJECT_TYPE,
                    "data": {"label": label},
                }
            ],
        },
    )


def _block_line(model_ship: str, block_ship: str, text: str) -> ShipDraftInterface:
    return ShipDraftInterface.from_record(
        str(uuid4()),
        {
            "type": LINE_SHIP_TYPE,
            "model_ship": model_ship,
            "block_ship": block_ship,
            "editions": [
                {
                    "id": str(uuid4()),
                    "line_type": DESIGN_LINE_PRINCIPLE_TYPE,
                    "producer": REFERENCE,
                    "support": [{"root": REFERENCE, "neighborhood": []}],
                    "data": {"text": text},
                }
            ],
        },
    )


def _line_annotation(
    namespace: DiagramNamespace,
    model_ship: str,
    annotation_id: str,
    edition_id: str,
    arguments: tuple[str, ...],
    text: str,
    *,
    supported: bool = True,
) -> AnnotationDraftInterface:
    edition: dict[str, object] = {
        "id": edition_id,
        "arguments": [
            DiagramArgumentReferenceInterface(
                namespace_id=namespace.id, kind="ship", id=identity
            ).model_dump(mode="json")
            for identity in arguments
        ],
        "data": {"text": text},
    }
    if supported:
        edition.update(
            {
                "producer": REFERENCE,
                "support": [{"root": REFERENCE, "neighborhood": []}],
            }
        )
    return AnnotationDraftInterface.from_record(
        annotation_id,
        {
            "type": LINE_ANNOTATION_TYPE,
            "model_ship": model_ship,
            "editions": [edition],
        },
    )


def test_line_annotation_is_a_free_standing_line_with_argument_context(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    block_x = str(uuid4())
    block_y = str(uuid4())
    claim = "Block Y is superseded by Block X."
    block_line = _block_line(model.ship, block_y, claim)
    namespace.apply(
        CaptureManifest.create(
            model.ship,
            ships=(
                _block(model.ship, block_x, "Block X"),
                _block(model.ship, block_y, "Block Y"),
                block_line,
            ),
        )
    )
    annotation_id = str(uuid4())
    edition_id = str(uuid4())
    draft = _line_annotation(
        namespace,
        model.ship,
        annotation_id,
        edition_id,
        (block_y, block_x),
        claim,
    )

    receipt = namespace.apply(CaptureManifest.create(model.ship, annotations=(draft,)))
    annotation = namespace.annotation(annotation_id)
    typed = annotation.specialize()
    diagram = Diagram((namespace,), namespace.id)

    assert receipt.created_annotations == (annotation_id,)
    assert receipt.created_editions == (edition_id,)
    assert isinstance(typed, LineAnnotationRecord)
    assert typed.current_edition_id == edition_id
    assert typed.text == claim
    assert [item.id for item in typed.arguments] == [block_y, block_x]
    assert typed.support
    assert [item.id for item in model.annotations()] == [annotation_id]
    assert annotation_id in {item.id for item in namespace.block_annotations(block_y)}
    assert [item.id for item in diagram.annotations_for_argument(block_x)] == [
        annotation_id
    ]
    assert [item.id for item in diagram.annotations_for_argument(block_y)] == [
        annotation_id
    ]
    assert model.project().line(block_line.id).current_edition.text == claim


def test_line_annotation_history_appends_editions_without_rebinding(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    subject = str(uuid4())
    namespace.apply(
        CaptureManifest.create(
            model.ship,
            ships=(_block(model.ship, subject, "Subject"),),
        )
    )
    annotation_id = str(uuid4())
    first_edition = str(uuid4())
    second_edition = str(uuid4())
    namespace.apply(
        CaptureManifest.create(
            model.ship,
            annotations=(
                _line_annotation(
                    namespace,
                    model.ship,
                    annotation_id,
                    first_edition,
                    (subject,),
                    "The subject has an earlier description.",
                    supported=False,
                ),
            ),
        )
    )

    receipt = namespace.apply(
        CaptureManifest.create(
            model.ship,
            annotations=(
                _line_annotation(
                    namespace,
                    model.ship,
                    annotation_id,
                    second_edition,
                    (subject,),
                    "The subject has a clearer description.",
                    supported=False,
                ),
            ),
        )
    )
    typed = namespace.annotation(annotation_id).specialize()

    assert isinstance(typed, LineAnnotationRecord)
    assert receipt.existing_annotations == (annotation_id,)
    assert receipt.created_editions == (second_edition,)
    assert [edition["id"] for edition in typed.editions] == [
        first_edition,
        second_edition,
    ]
    assert typed.text == "The subject has a clearer description."

    with pytest.raises(DiagramError, match="edition identity cannot be rebound"):
        namespace.apply(
            CaptureManifest.create(
                model.ship,
                annotations=(
                    _line_annotation(
                        namespace,
                        model.ship,
                        annotation_id,
                        second_edition,
                        (subject,),
                        "The same edition cannot acquire another meaning.",
                        supported=False,
                    ),
                ),
            )
        )


def test_line_annotation_unresolved_argument_is_a_writable_poi(tmp_path: Path) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    annotation_id = str(uuid4())
    draft = _line_annotation(
        namespace,
        model.ship,
        annotation_id,
        str(uuid4()),
        (str(uuid4()),),
        "This argument has not resolved yet.",
        supported=False,
    )

    receipt = namespace.apply(CaptureManifest.create(model.ship, annotations=(draft,)))

    assert "line-annotation-argument-unresolved" in {
        item.code for item in receipt.findings
    }
    assert namespace.annotation(annotation_id).type == LINE_ANNOTATION_TYPE


def test_line_annotation_is_discoverable_and_renderable_from_the_cli(
    tmp_path: Path, capsys
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    subject = str(uuid4())
    namespace.apply(
        CaptureManifest.create(
            model.ship,
            ships=(_block(model.ship, subject, "Subject"),),
        )
    )
    annotation_id = str(uuid4())
    edition_id = str(uuid4())
    namespace.apply(
        CaptureManifest.create(
            model.ship,
            annotations=(
                _line_annotation(
                    namespace,
                    model.ship,
                    annotation_id,
                    edition_id,
                    (subject,),
                    "The subject has a free-standing annotation.",
                    supported=False,
                ),
            ),
        )
    )
    config = DiagramConfiguration.load(tmp_path / "diagram.json", create=True).mount(
        namespace, default=True
    )

    assert (
        main(
            [
                "diagram",
                "annotation",
                "list",
                "--argument",
                subject,
                "--diagram-config",
                str(config.path),
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert [item["id"] for item in payload["annotations"]] == [annotation_id]
    assert payload["annotations"][0]["editions"][0]["id"] == edition_id

    diagram = Diagram((namespace,), namespace.id)
    result = renderer("Kernel.Writing.Line.Annotation").render(
        annotation_render_target(diagram, annotation_id)
    )
    assert "The subject has a free-standing annotation." in result.content
    assert f"**Line.Annotation:** `{annotation_id}`" in result.content
    assert f"**Edition:** `{edition_id}`" in result.content
    assert f":ship:{subject}`" in result.content
