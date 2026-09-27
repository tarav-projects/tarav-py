from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from tarav.cli.cli import main
from tarav.unsorted.constants import BLOCK_SHIP_TYPE, CAPTURE_AUTHORIZATION_GATE_TYPE, COLLECTION_SHIP_TYPE, DESIGN_BLOCK_OBJECT_TYPE, DIAGRAM_COLLECTION_OBJECT_TYPE, IMPL_REQ_COLLECTION_OBJECT_TYPE, LINE_SHIP_TYPE
from tarav.unsorted.contracts import AnnotationDraftInterface, ShipDraftInterface
from tarav.unsorted.capture import CaptureManifest
from tarav.unsorted.evidence import ChatlasEvidence
from tarav.unsorted.storage import Diagram, DiagramConfiguration, DiagramNamespace
from tarav.unsorted.drafts import DiagramDraftError, DiagramDraftRepository
from tarav.lines.rendering import model_render_target, renderer


def _host(kind: str, identity: str) -> dict[str, str]:
    return {"kind": kind, "id": identity}


def _collection(
    model_ship: str,
    *,
    ship: str | None = None,
    edition: str | None = None,
    collection_type: str = DIAGRAM_COLLECTION_OBJECT_TYPE,
    label: str = "Working set",
    state: str | None = None,
    host: dict[str, str] | None = None,
    references: list[dict[str, str]] | None = None,
    **data: object,
) -> ShipDraftInterface:
    edition_data: dict[str, object] = {"label": label, **data}
    if state is not None:
        edition_data["state"] = state
    value: dict[str, object] = {
        "id": edition or str(uuid4()),
        "collection_type": collection_type,
        "data": edition_data,
    }
    if host is not None:
        value["host"] = host
    if references is not None:
        value["references"] = references
    return ShipDraftInterface.from_record(
        ship or str(uuid4()),
        {
            "type": COLLECTION_SHIP_TYPE,
            "model_ship": model_ship,
            "editions": [value],
        },
    )


def _block(model_ship: str, *, ship: str | None = None) -> ShipDraftInterface:
    return ShipDraftInterface.from_record(
        ship or str(uuid4()),
        {
            "type": BLOCK_SHIP_TYPE,
            "model_ship": model_ship,
            "editions": [
                {
                    "id": str(uuid4()),
                    "block_type": DESIGN_BLOCK_OBJECT_TYPE,
                    "data": {"label": "Dispatch"},
                }
            ],
        },
    )


def _line(
    model_ship: str,
    block_ship: str,
    *,
    ship: str | None = None,
    edition: str | None = None,
    text: str,
    host: dict[str, str] | None = None,
    authorization_gates: list[str] | None = None,
    recorded_at: str | None = None,
) -> ShipDraftInterface:
    ref = {
        "session_identity": "a" * 64,
        "turn_address": "b" * 64,
        "turn_hash": "c" * 64,
    }
    value: dict[str, object] = {
        "id": edition or str(uuid4()),
        "producer": ref,
        "support": [],
        "data": {"text": text},
    }
    if host is not None:
        value["host"] = host
    if authorization_gates is not None:
        value["authorization_gates"] = authorization_gates
    if recorded_at is not None:
        value["recorded_at"] = recorded_at
    return ShipDraftInterface.from_record(
        ship or str(uuid4()),
        {
            "type": LINE_SHIP_TYPE,
            "model_ship": model_ship,
            "block_ship": block_ship,
            "editions": [value],
        },
    )


def _authorization_gate(
    namespace_id: str, model_ship: str, gate_id: str
) -> AnnotationDraftInterface:
    return AnnotationDraftInterface.from_record(
        gate_id,
        {
            "type": CAPTURE_AUTHORIZATION_GATE_TYPE,
            "model_ship": model_ship,
            "token": "$tarav-hugentics --impl --dev",
            "workflow": "Impl.Develop",
            "permission_turn": {
                "session_identity": "a" * 64,
                "turn_address": "b" * 64,
                "turn_hash": "c" * 64,
            },
            "operations": ["Diagram.Draft.Apply"],
            "target_scope": [
                {"namespace_id": namespace_id, "kind": "ship", "id": model_ship}
            ],
        },
    )


def _evidence() -> ChatlasEvidence:
    event_ref = {"event_address": "b" * 64, "event_hash": "c" * 64}
    message = {
        "type": "Chat.Message",
        "message_address": "d" * 64,
        "message_hash": "e" * 64,
        "side": "user",
        "text": "$tarav-hugentics --impl --dev",
        "event_refs": [event_ref],
    }
    model = {
        "session": {"identity_hash": "a" * 64, "session_id": "session"},
        "events": [
            {
                "type": "User.Event",
                **event_ref,
                "started_at": "2026-09-20T00:00:00Z",
                "origin": "user",
                "observations": [
                    {
                        "observed_at": "2026-09-20T00:00:00Z",
                        "source_ref": {
                            "source_id": "source-one",
                            "record_index": 1,
                            "line": 1,
                        },
                    }
                ],
                "opaque_payload_hash": "0" * 64,
                "content": {"text": "$tarav-hugentics --impl --dev"},
            }
        ],
        "messages": [message],
        "turns": [
            {
                "type": "Chat.Turn",
                "turn_address": "b" * 64,
                "turn_hash": "c" * 64,
                "side": "user",
                "message_refs": [
                    {
                        "message_address": "d" * 64,
                        "message_hash": "e" * 64,
                    }
                ],
                "event_refs": [event_ref],
            }
        ],
    }
    return ChatlasEvidence(model_loader=lambda _identity: model)


def test_collection_hosts_editions_without_polluting_primary_model_load(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    block = _block(model.ship)
    collection = _collection(
        model.ship,
        collection_type=IMPL_REQ_COLLECTION_OBJECT_TYPE,
        label="771.Impl.Req",
        state="Open",
        references=[{"namespace_id": namespace.id, "kind": "ship", "id": block.id}],
    )
    line_ship = str(uuid4())
    primary = _line(model.ship, block.id, ship=line_ship, text="Primary wording.")
    collected = _line(
        model.ship,
        block.id,
        ship=line_ship,
        text="Implementation-specific wording.",
        host=_host("collection", collection.id),
    )
    child = _collection(
        model.ship,
        label="Nested slice",
        host=_host("collection", collection.id),
    )
    preflight = CaptureManifest.create(
        model.ship, (block, collection, primary, collected, child)
    ).check(namespace)
    assert "collection-reference-unresolved" not in {item.code for item in preflight}
    namespace.apply(
        CaptureManifest.create(
            model.ship, (block, collection, primary, collected, child)
        ),
        commit=False,
    )

    default = model.project()
    expanded = model.project(include_collection_content=True)
    projected_collection = default.collection(collection.id)

    assert default.line(line_ship).current_edition.text == "Primary wording."
    assert expanded.line(line_ship).current_edition.text == (
        "Implementation-specific wording."
    )
    assert {item.edition for item in projected_collection.hosted_editions} == {
        collected.record["editions"][0]["id"],
        child.record["editions"][0]["id"],
    }
    assert default.child_collections(collection.id)[0].ship == child.id
    assert {item.code for item in default.findings} >= {"model-staleness"}
    rendered = renderer("Kernel.Writing.Model").render(model_render_target(model))
    assert "## Collections" in rendered.content
    assert "771.Impl.Req" in rendered.content
    assert "Implementation-specific wording." not in rendered.content


def test_object_list_serializes_collection_host_interfaces(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "diagram.json"
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    parent = _collection(model.ship, label="Parent")
    child = _collection(
        model.ship,
        label="Child",
        host=_host("collection", parent.id),
    )
    namespace.apply(CaptureManifest.create(model.ship, (parent, child)))
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
                "collection",
                "--label",
                "Child",
                "--include-collection-content",
                "--diagram-config",
                str(config_path),
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["objects"][0]["host"] == {
        "kind": "collection",
        "id": parent.id,
    }


def test_impl_req_lifecycle_surfaces_closed_writes_and_invalid_reopening(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    block = _block(model.ship)
    collection = _collection(
        model.ship,
        collection_type=IMPL_REQ_COLLECTION_OBJECT_TYPE,
        state="Open",
    )
    namespace.apply(
        CaptureManifest.create(model.ship, (block, collection)), commit=False
    )
    closed = _collection(
        model.ship,
        ship=collection.id,
        collection_type=IMPL_REQ_COLLECTION_OBJECT_TYPE,
        state="Closed",
        closed_at="2026-01-02T00:00:00+00:00",
        reopen_until="2026-01-03T00:00:00+00:00",
    )
    namespace.apply(CaptureManifest.create(model.ship, (closed,)), commit=False)

    late = _line(
        model.ship,
        block.id,
        text="Late mutation.",
        host=_host("collection", collection.id),
        recorded_at="2026-01-04T00:00:00+00:00",
    )
    findings = CaptureManifest.create(model.ship, (late,)).check(namespace)
    assert "impl-req-closed-write" in {item.code for item in findings}

    invalid_reopen = _collection(
        model.ship,
        ship=collection.id,
        collection_type=IMPL_REQ_COLLECTION_OBJECT_TYPE,
        state="Open",
        reopened_at="2026-01-04T00:00:00+00:00",
    )
    findings = CaptureManifest.create(model.ship, (invalid_reopen,)).check(namespace)
    assert "impl-req-reopen-window-invalid" in {item.code for item in findings}


def test_new_impl_req_preserves_open_then_closed_order_inside_one_draft(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    collection_ship = str(uuid4())
    collection = ShipDraftInterface.from_record(
        collection_ship,
        {
            "type": COLLECTION_SHIP_TYPE,
            "model_ship": model.ship,
            "editions": [
                {
                    "id": "f0000000-0000-4000-8000-000000000001",
                    "collection_type": IMPL_REQ_COLLECTION_OBJECT_TYPE,
                    "data": {"label": "771.Impl.Req", "state": "Open"},
                },
                {
                    "id": "00000000-0000-4000-8000-000000000002",
                    "collection_type": IMPL_REQ_COLLECTION_OBJECT_TYPE,
                    "data": {
                        "label": "771.Impl.Req",
                        "state": "Closed",
                        "reopen_until": "2026-01-03T00:00:00+00:00",
                    },
                },
            ],
        },
    )

    findings = CaptureManifest.create(model.ship, (collection,)).check(namespace)
    assert "impl-req-reopen-window-invalid" not in {item.code for item in findings}


def test_authorization_gate_is_scored_and_receipt_retains_coverage(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    block = _block(model.ship)
    gate_id = str(uuid4())
    gate = _authorization_gate(namespace.id, model.ship, gate_id)
    line = _line(
        model.ship,
        block.id,
        text="Authorized automatic capture.",
        authorization_gates=[gate_id],
    )
    manifest = CaptureManifest.create(model.ship, (block, line), (gate,))

    findings = manifest.check(namespace, evidence=_evidence())
    assert not any(item.code.startswith("capture-authorization-") for item in findings)
    receipt = namespace.apply(manifest, evidence=_evidence(), commit=False)
    assert receipt.authorizations == (
        {
            "gate": gate_id,
            "objects": [
                {
                    "kind": "edition",
                    "id": line.record["editions"][0]["id"],
                    "ship": line.id,
                }
            ],
        },
    )

    missing_gate = _line(
        model.ship,
        block.id,
        text="Unresolved permission.",
        authorization_gates=[str(uuid4())],
    )
    assert "capture-authorization-gate-unresolved" in {
        item.code
        for item in CaptureManifest.create(model.ship, (missing_gate,)).check(namespace)
    }


def test_draft_reconciles_checks_applies_once_and_survives_reload(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    diagram = Diagram((namespace,), namespace.id)
    repository = DiagramDraftRepository.open(tmp_path / "drafts", create=True)
    draft = repository.create(model.ship)
    collection = _collection(
        model.ship,
        collection_type=IMPL_REQ_COLLECTION_OBJECT_TYPE,
        state="Open",
    )
    draft = repository.reconcile(draft, ships=(collection,))
    closed = _collection(
        model.ship,
        ship=collection.id,
        collection_type=IMPL_REQ_COLLECTION_OBJECT_TYPE,
        state="Closed",
        reopen_until="2026-01-03T00:00:00+00:00",
    )
    draft = repository.reconcile(draft, ships=(closed,))

    reloaded = DiagramDraftRepository.open(tmp_path / "drafts").draft(draft.id[:8])
    assert reloaded.to_record() == draft.to_record()
    assert len(reloaded.ship_drafts[0].record["editions"]) == 2
    assert reloaded.check(diagram)
    receipt = repository.apply(reloaded, diagram, commit=False)
    assert collection.id in receipt.created_ships
    assert repository.draft(draft.id).status == "Applied"
    with pytest.raises(DiagramDraftError, match="already been applied"):
        repository.apply(repository.draft(draft.id), diagram, commit=False)


def test_draft_cli_runs_create_update_check_apply_vertical_slice(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "diagram.json"
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    DiagramConfiguration.load(config_path, create=True).mount(namespace, default=True)
    drafts_root = tmp_path / "drafts"

    assert (
        main(
            [
                "diagram",
                "draft",
                "create",
                "--model-ship",
                model.ship,
                "--drafts-root",
                str(drafts_root),
                "--diagram-config",
                str(config_path),
                "--json",
            ]
        )
        == 0
    )
    draft_id = json.loads(capsys.readouterr().out)["draft"]["id"]
    collection = _collection(model.ship)
    delta = tmp_path / "delta.json"
    delta.write_text(
        json.dumps({"ships": [collection.model_dump(mode="json", exclude_unset=True)]}),
        encoding="utf-8",
    )

    base = ["--draft", draft_id, "--drafts-root", str(drafts_root)]
    assert (
        main(["diagram", "draft", "update", *base, "--input", str(delta), "--json"])
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "diagram",
                "draft",
                "check",
                *base,
                "--diagram-config",
                str(config_path),
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
                "draft",
                "apply",
                *base,
                "--diagram-config",
                str(config_path),
                "--no-commit",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["draft"]["status"] == "Applied"
    assert collection.id in payload["receipt"]["created_ships"]
