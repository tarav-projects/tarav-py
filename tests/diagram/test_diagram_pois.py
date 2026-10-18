"""Diagram POI identity, receipt round trips, and explicit Draft migration."""

from __future__ import annotations

# tarav.breadcrumb 4e11fb069eb9

import json
import argparse
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tarav.l0.kernel import entity
from tarav.l2.unsorted.capture import CaptureReceipt
from tarav.l2.unsorted.drafts import DiagramDraft, DiagramDraftError
from tarav.l2.unsorted.pois import (
    CASE_TYPES,
    DiagramPOI,
    LineTypeMissing,
    ModelStaleness,
    load_poi,
)
from tarav.l2.unsorted.poi_cli import render_pois
from tarav.l2.lines.rendering import DiagramRenderer, DiagramRenderTarget
from tarav.l2.unsorted import commands as diagram_commands


def test_case_catalog_has_unique_atomic_identity_and_guidance() -> None:
    assert len(CASE_TYPES) == 81
    assert len({entity(cls).name for cls in CASE_TYPES}) == len(CASE_TYPES)
    assert len({str(entity(cls).id) for cls in CASE_TYPES}) == len(CASE_TYPES)
    with pytest.raises(TypeError, match="families cannot be raised"):
        DiagramPOI(path="p", message="m")
    for cls in CASE_TYPES:
        assert cls.__doc__
        assert cls(path="p", message="m").summary()


def test_receipt_round_trip_rehydrates_concrete_types() -> None:
    first = LineTypeMissing(path="line.1", message="Missing Line.Type")
    second = ModelStaleness(path="model.1", message="Stale")
    receipt = CaptureReceipt.create("namespace", (), (), (first, second),
                                    False, "base", None)
    loaded = CaptureReceipt.records.from_record(receipt.records.to_record())
    assert [type(poi) for poi in loaded.pois] == [LineTypeMissing, ModelStaleness]
    assert [poi.records.to_record() for poi in loaded.pois] == [
        first.records.to_record(), second.records.to_record()]
    record = first.records.to_record()
    assert set(record) == {"type", "class_id", "id", "message", "situation", "evidence"}
    assert record["situation"] == {"path": first.path} and not hasattr(first, "to_dict")
    assert "findings" not in receipt.records.to_record()
    assert first.identity != second.identity
    assert first.identity == LineTypeMissing(path="line.1", message="changed").identity
    with pytest.raises(ValueError, match="Unrecognized Diagram POI Type"):
        load_poi({"type": "unknown", "path": "x", "message": "m"})
    with pytest.raises(ValueError):  # the row shape that records replaced
        load_poi({"type": record["type"], "path": "x", "message": "m"})


def test_diagram_uses_shared_poi_renderer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARAV_CHECK_REPORTS", str(tmp_path / "reports"))
    output = render_pois(
        argparse.Namespace(level="line"),
        (LineTypeMissing(path="line.1", message="Line Type is missing"),),
        title="Diagram POIs",
        root=tmp_path,
    )
    assert "Line Type is missing" in output
    assert "tarav context" not in output  # a printed POI points at no stored context


# tarav.breadcrumb f9d73a04c650
def test_diagram_render_presents_and_retains_pois_in_text_and_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    monkeypatch.setenv("TARAV_CHECK_REPORTS", str(tmp_path / "reports"))
    namespace_id = str(uuid4())
    poi = LineTypeMissing(path="line.1", message="Line Type is missing")
    target = DiagramRenderTarget("model", str(uuid4()), namespace_id, object())
    content_renderer = DiagramRenderer(
        "Example.Renderer", "model", "text/plain", "test",
        lambda selected, context: ("Rendered model", (poi,)),
    )
    diagram = SimpleNamespace(
        model=lambda ship: object(),
        namespace=lambda selector: SimpleNamespace(root=tmp_path),
    )
    monkeypatch.setattr(diagram_commands, "_diagram_configuration",
                        lambda path: SimpleNamespace(diagram=lambda: diagram))
    monkeypatch.setattr(diagram_commands, "model_render_target", lambda model: target)
    monkeypatch.setattr(diagram_commands, "renderer", lambda name: content_renderer)
    monkeypatch.setattr(diagram_commands, "_diagram_evidence", lambda args: None)
    args = argparse.Namespace(
        annotation=None, line_ship=None, block_ship=None, collection_ship=None,
        model_ship=target.identity, project=None, namespace=None, diagram_config=None,
        chatlas_root=None, renderer="Example.Renderer", poi_renderer=None,
        level="line", json=False,
    )
    assert diagram_commands._cmd_diagram_render(args) == 0
    output = capsys.readouterr().out
    assert "Rendered model" in output
    assert poi.identity[:12] in output and "tarav context" not in output

    args.poi_renderer = "Tarav.POI.JsonLines.Renderer"
    args.level = "record"
    assert diagram_commands._cmd_diagram_render(args) == 0
    lines = capsys.readouterr().out.splitlines()
    assert json.loads(lines[1])["level"] == "record"
    assert json.loads(lines[2])["type"] == entity(LineTypeMissing).name

    args.json = True
    assert diagram_commands._cmd_diagram_render(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["pois"][0]["type"] == entity(LineTypeMissing).name
    assert payload["status"] == "poi"


def test_a_draft_of_another_schema_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "draft.json"
    record = DiagramDraft.create(path, str(uuid4()), str(uuid4()), "Open").records.to_record()
    record["schema_version"] = 1
    path.write_text(json.dumps(record))
    with pytest.raises(DiagramDraftError, match="Unsupported Diagram.Draft schema"):
        DiagramDraft.read(path)
