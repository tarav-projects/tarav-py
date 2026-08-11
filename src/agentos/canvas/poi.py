# $kw: ^canvas-poi-adapter --from POI.System --from POI.Linter --note [DF] Canvas legacy rule codes map once to valid package-owned POI class addresses ^c20260729-49u
from __future__ import annotations

from pathlib import Path

from agentos.index.wayfinder import create_index_wayfinder
from agentos.poi import POIInstance, POILinterReport, POILocation, build_poi_report
from agentos.wayfinder import poi_class_reference

from agentos.canvas.core import RenderAction, RenderError


CANVAS_RENDER_POI_CLASSES = {
    "model.missing": "Canvas.Linter/Model.Missing",
    "model.card.type_mismatch": "Canvas.Linter/Model.Card.TypeMismatch",
    "model.rel.adjacent": "Canvas.Linter/Model.Rel.Adjacent",
    "model.rel.contains": "Canvas.Linter/Model.Rel.Contains",
    "canvas.edge.label_not_tid": "Canvas.Linter/Canvas.Edge.LabelNotTid",
}


def build_canvas_linter_report(
    errors: list[RenderError],
    *,
    canvas_path: Path,
    actions: list[RenderAction],
) -> POILinterReport:
    instances = tuple(
        POIInstance.create(
            class_reference=poi_class_reference(
                "agentos-canvas-pkg", CANVAS_RENDER_POI_CLASSES[error.rule]
            ),
            target=POILocation(path=str(canvas_path)),
            severity="error",
            situation=error.message,
            evidence={
                "rule": error.rule,
                "message": error.message,
                "ordinal": ordinal,
            },
        )
        for ordinal, error in enumerate(errors)
    )
    return POILinterReport(
        poi_report=build_poi_report(
            instances,
            wayfinder=create_index_wayfinder(),
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
