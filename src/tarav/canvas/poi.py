# $kw: ^canvas-poi-adapter --from POI.System --from POI.Linter --note [DF] Canvas legacy rule codes map once to valid package-owned POI class addresses ^c20260729-49u
from __future__ import annotations

from pathlib import Path

from tarav.skillware._build_core import find_project_root
from tarav.skillware.managed_blocks import create_tarav_wayfinder
from tarav.poi import (
    POIInstance,
    POILinterReport,
    POILocation,
    build_poi_report,
    tarav_poi_class_reference,
)

from tarav.canvas.core import RenderAction, RenderError


def _canvas_poi(
    error: RenderError, class_name: str, canvas_path: Path, ordinal: int
) -> POIInstance:
    return POIInstance.create(
        class_reference=tarav_poi_class_reference(class_name),
        target=POILocation(path=str(canvas_path)),
        severity="error",
        situation=error.message,
        evidence={"rule": error.rule, "message": error.message, "ordinal": ordinal},
    )


# $kw: Canvas.Linter/Model.Missing
# --note [DF] the Canvas renderer found no model cards or relationships in the file
# --note [CT] the producer finding code is `model.missing`
# --note [CT] the renderer produces no actions and does not write during a dry run
def _model_missing(error: RenderError, canvas_path: Path, ordinal: int) -> POIInstance:
    return _canvas_poi(error, "Canvas.Linter/Model.Missing", canvas_path, ordinal)


# $kw: Canvas.Linter/Model.Card.TypeMismatch
# --note [DF] a model card's expected `type: id` marker is absent from its Canvas text
# --note [CT] the producer finding code is `model.card.type_mismatch`
# --note [CT] the instance preserves the card identity and expected model type in its message
def _model_card_type_mismatch(
    error: RenderError, canvas_path: Path, ordinal: int
) -> POIInstance:
    return _canvas_poi(error, "Canvas.Linter/Model.Card.TypeMismatch", canvas_path, ordinal)


# $kw: Canvas.Linter/Model.Rel.Adjacent
# --note [DF] cards joined by an adjacency relationship do not touch within the renderer's existing tolerance
# --note [CT] the producer finding code is `model.rel.adjacent`
# --note [CT] the instance preserves the relationship and card identities in its message
def _model_rel_adjacent(
    error: RenderError, canvas_path: Path, ordinal: int
) -> POIInstance:
    return _canvas_poi(error, "Canvas.Linter/Model.Rel.Adjacent", canvas_path, ordinal)


# $kw: Canvas.Linter/Model.Rel.Contains
# --note [DF] a child card in a contains relationship is not geometrically inside its parent
# --note [CT] the producer finding code is `model.rel.contains`
# --note [CT] the instance preserves the relationship and card identities in its message
def _model_rel_contains(
    error: RenderError, canvas_path: Path, ordinal: int
) -> POIInstance:
    return _canvas_poi(error, "Canvas.Linter/Model.Rel.Contains", canvas_path, ordinal)


# $kw: Canvas.Linter/Canvas.Edge.LabelNotTid
# --note [DF] a nonempty Canvas edge label is not a valid `type: id` pair
# --note [CT] the producer finding code is `canvas.edge.label_not_tid`
# --note [CT] the instance preserves the endpoints and observed label in its message
def _canvas_edge_label_not_tid(
    error: RenderError, canvas_path: Path, ordinal: int
) -> POIInstance:
    return _canvas_poi(error, "Canvas.Linter/Canvas.Edge.LabelNotTid", canvas_path, ordinal)


#: One emitter per class, each carrying its class's managed block. The producer's rule code
#: is the key because that is what a `RenderError` reports; the class identity lives with the
#: definition rather than in a table beside it.
CANVAS_RENDER_POI_CLASSES = {
    "model.missing": _model_missing,
    "model.card.type_mismatch": _model_card_type_mismatch,
    "model.rel.adjacent": _model_rel_adjacent,
    "model.rel.contains": _model_rel_contains,
    "canvas.edge.label_not_tid": _canvas_edge_label_not_tid,
}


def build_canvas_linter_report(
    errors: list[RenderError],
    *,
    canvas_path: Path,
    actions: list[RenderAction],
) -> POILinterReport:
    instances = tuple(
        CANVAS_RENDER_POI_CLASSES[error.rule](error, canvas_path, ordinal)
        for ordinal, error in enumerate(errors)
    )
    return POILinterReport(
        poi_report=build_poi_report(
            instances,
            wayfinder=create_tarav_wayfinder(
                project_root=find_project_root(Path(__file__))
            ),
        ),
        summary={
            "poi_count": len(instances),
            "action_count": len(actions),
        },
        domain={
            "canvas": str(canvas_path),
            "actions": [
                {"action": action.action, "detail": action.detail} for action in actions
            ],
        },
    )


__all__ = ["CANVAS_RENDER_POI_CLASSES", "build_canvas_linter_report"]
