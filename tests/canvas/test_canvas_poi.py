from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from tarav.canvas.commands import _cmd_canvas_render
from tarav.canvas.core import RenderAction, RenderError
from tarav.canvas.poi import (
    CANVAS_RENDER_POI_CLASSES,
    build_canvas_linter_report,
)


def test_canvas_adapter_preserves_rules_messages_and_actions(tmp_path: Path) -> None:
    errors = [
        RenderError(rule=rule, message=f"message for {rule}")
        for rule in CANVAS_RENDER_POI_CLASSES
    ]
    actions = [RenderAction(action="created_node", detail="card")]

    report = build_canvas_linter_report(
        errors,
        canvas_path=tmp_path / "model.canvas",
        actions=actions,
    )

    assert [instance.evidence["rule"] for instance in report.instances] == list(
        CANVAS_RENDER_POI_CLASSES
    )
    assert [instance.situation for instance in report.instances] == [
        error.message for error in errors
    ]
    assert report.as_dict()["domain"]["actions"] == [
        {"action": "created_node", "detail": "card"}
    ]


def test_canvas_render_refusal_uses_common_poi_without_mutating_dry_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "missing-model.canvas"
    original = {"nodes": [], "edges": []}
    path.write_text(json.dumps(original), encoding="utf-8")

    exit_code = _cmd_canvas_render(argparse.Namespace(file=str(path), apply=False))

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Canvas.Linter/Model.Missing" in captured.err
    assert "[POI" not in captured.err
    assert json.loads(path.read_text(encoding="utf-8")) == original
