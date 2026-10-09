"""Diagram POI identity, receipt round trips, and explicit Draft migration."""

from __future__ import annotations

# tarav.breadcrumb 4e11fb069eb91ffd415a438bd11e5f8d4da9df54a2d761736968bc3626305c14

import json
import argparse
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tarav.l0.kernel import entity
from tarav.l2.unsorted.capture import CaptureReceipt
from tarav.l2.unsorted.draft_migration import migrate_drafts
from tarav.l2.unsorted.drafts import DiagramDraft, DiagramDraftError
from tarav.l2.unsorted.pois import (
    CASE_TYPES,
    DiagramPOI,
    LineTypeMissing,
    ModelStaleness,
    poi_from_dict,
)
from tarav.l2.unsorted.poi_cli import render_pois
from tarav.l2.lines.rendering import DiagramRenderer, DiagramRenderTarget
from tarav.l2.unsorted import commands as diagram_commands


LEGACY_CODES = (
    "line-type-missing",
    "model-staleness",
    "impl-req-closed-write",
    "block-type-missing",
    "semantic-record-unasserted",
    "archive-grounding-unassessable",
    "producer-turn-unresolved",
    "capture-authorization-token-missing",
)


def _legacy_draft(path: Path, *, codes: tuple[str, ...] = LEGACY_CODES) -> None:
    record = DiagramDraft.create(path, str(uuid4()), str(uuid4()), "Applied",
                                 receipt={"findings": []}).records.to_record()
    record["schema_version"] = 1
    record["receipt"]["findings"] = [
        {"class": "Tarav.POI.Instance", "code": code,
         "path": f"subject.{index}", "message": f"message {index}"}
        for index, code in enumerate(codes)
    ]
    path.write_text(json.dumps(record))


def test_case_catalog_has_unique_atomic_identity_and_guidance() -> None:
    assert len(CASE_TYPES) == 81
    assert len({entity(cls).name for cls in CASE_TYPES}) == len(CASE_TYPES)
    assert len({str(entity(cls).id) for cls in CASE_TYPES}) == len(CASE_TYPES)
    with pytest.raises(TypeError, match="families cannot be raised"):
        DiagramPOI(path="p", message="m")
    for cls in CASE_TYPES:
        assert cls.__doc__
        assert cls.context_notes
        assert cls(path="p", message="m").summary()


def test_receipt_round_trip_rehydrates_concrete_types() -> None:
    first = LineTypeMissing(path="line.1", message="Missing Line.Type")
    second = ModelStaleness(path="model.1", message="Stale")
    receipt = CaptureReceipt.create("namespace", (), (), (first, second),
                                    False, "base", None)
    loaded = CaptureReceipt.records.from_record(receipt.records.to_record())
    assert [type(poi) for poi in loaded.pois] == [LineTypeMissing, ModelStaleness]
    assert [poi.to_dict() for poi in loaded.pois] == [first.to_dict(), second.to_dict()]
    assert "findings" not in receipt.records.to_record()
    assert first.identity != second.identity
    assert first.identity == LineTypeMissing(path="line.1", message="changed").identity
    with pytest.raises(ValueError, match="Unrecognized Diagram POI Type"):
        poi_from_dict({"type": "unknown", "path": "x", "message": "m"})


def test_diagram_uses_shared_poi_renderer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARAV_CHECK_REPORTS", str(tmp_path / "reports"))
    output = render_pois(
        argparse.Namespace(level="line"),
        (LineTypeMissing(path="line.1", message="Line Type is missing"),),
        title="Diagram POIs",
        root=tmp_path,
    )
    assert "Line Type is missing" in output
    assert "tarav context --id" in output


# tarav.breadcrumb f9d73a04c65058c13ecb61dd49bfdfe6e1d728b2d1dc2eca6fa3f5b212cc61f6
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
        level="context", json=False,
    )
    assert diagram_commands._cmd_diagram_render(args) == 0
    output = capsys.readouterr().out
    assert "Rendered model" in output
    assert f"tarav context --id {poi.identity}" in output

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


def test_draft_migration_preserves_all_eight_retained_case_shapes(tmp_path: Path) -> None:
    path = tmp_path / "draft.json"
    _legacy_draft(path)
    with pytest.raises(DiagramDraftError, match="draft migrate --to 2"):
        DiagramDraft.read(path)
    before = path.read_bytes()
    preview = migrate_drafts(tmp_path, dry_run=True)
    assert preview["row_count"] == len(LEGACY_CODES)
    assert preview["unmapped_count"] == 0
    assert path.read_bytes() == before
    done = migrate_drafts(tmp_path, dry_run=False)
    assert done["row_count"] == len(LEGACY_CODES)
    record = json.loads(path.read_text())
    assert record["schema_version"] == 2
    assert "findings" not in record["receipt"]
    assert len(record["receipt"]["pois"]) == len(LEGACY_CODES)
    assert all(set(row) == {"type", "path", "message"} for row in record["receipt"]["pois"])
    assert DiagramDraft.read(path).receipt == record["receipt"]
    assert migrate_drafts(tmp_path, dry_run=False)["drafts"][0]["status"] == "already-v2"


def test_unmapped_draft_stays_untouched_and_open_draft_only_bumps_version(tmp_path: Path) -> None:
    blocked = tmp_path / "blocked.json"
    _legacy_draft(blocked, codes=("unrecognized-case",))
    before = blocked.read_bytes()
    open_path = tmp_path / "open.json"
    record = DiagramDraft.create(open_path, str(uuid4()), str(uuid4()),
                                 "Open").records.to_record()
    record["schema_version"] = 1
    open_path.write_text(json.dumps(record))
    report = migrate_drafts(tmp_path, dry_run=False)
    assert report["unmapped_count"] == 1
    assert blocked.read_bytes() == before
    assert DiagramDraft.read(open_path).status == "Open"
