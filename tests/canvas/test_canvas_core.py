from __future__ import annotations

from tarav.canvas.core import CanvasModel, ModelCard, ModelRelationship, model_to_canvas, render_canvas


def test_render_reports_missing_model() -> None:
    result = render_canvas({"nodes": [], "edges": []})

    assert [error.rule for error in result.errors] == ["model.missing"]
    assert result.actions == []


def test_model_to_canvas_renders_model_layer() -> None:
    model = CanvasModel(
        cards=[
            ModelCard(id="auth", type="module"),
            ModelCard(id="db", type="module"),
        ],
        relationships=[
            ModelRelationship(
                from_card="auth",
                to_card="db",
                rel_type="edge",
                id="rel: queries",
            ),
        ],
    )

    canvas = model_to_canvas(model)
    result = render_canvas(canvas)

    assert result.errors == []
    assert canvas["_model"]["cards"] == [
        {"id": "auth", "type": "module"},
        {"id": "db", "type": "module"},
    ]
    assert canvas["edges"][0]["label"] == "rel: queries"
