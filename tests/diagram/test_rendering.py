from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from tarav.l3.cli.cli import main
from tarav.l2.unsorted.constants import BLOCK_SHIP_TYPE, DESIGN_BLOCK_OBJECT_TYPE, DESIGN_LINE_PRINCIPLE_TYPE, ISSUE_BLOCK_OBJECT_TYPE, LINE_SHIP_TYPE, LINE_GATE_ANNOTATION_TYPE
from tarav.l2.unsorted.contracts import AnnotationDraftInterface, ShipDraftInterface, VerbatimGate, ChatlasTurnReferenceInterface
from tarav.l2.unsorted.capture import CaptureManifest
from tarav.l2.unsorted.evidence import ChatlasEvidence
from tarav.l2.unsorted.storage import Diagram, DiagramConfiguration, DiagramNamespace
from tarav.l2.lines.rendering import (
    block_render_target,
    line_render_target,
    model_render_target,
    renderer,
    renderers,
)


IDENTITY = "a" * 64
USER_REF = {
    "session_identity": IDENTITY,
    "turn_address": "1" * 64,
    "turn_hash": "2" * 64,
}
AGENT_REF = {
    "session_identity": IDENTITY,
    "turn_address": "5" * 64,
    "turn_hash": "6" * 64,
}


def _edition_id(ship: ShipDraftInterface) -> str:
    return str(ship.record["editions"][0]["id"])


def _block(
    model_ship: str,
    block_ship: str,
    label: str,
    block_type: str,
) -> ShipDraftInterface:
    return ShipDraftInterface.from_record(
        block_ship,
        {
            "type": BLOCK_SHIP_TYPE,
            "model_ship": model_ship,
            "editions": [
                {
                    "id": str(uuid4()),
                    "block_type": block_type,
                    "data": {"label": label},
                }
            ],
        },
    )


def _line(
    model_ship: str,
    block_ship: str,
    line_ship: str,
    text: str,
) -> ShipDraftInterface:
    return ShipDraftInterface.from_record(
        line_ship,
        {
            "type": LINE_SHIP_TYPE,
            "model_ship": model_ship,
            "block_ship": block_ship,
            "editions": [
                {
                    "id": str(uuid4()),
                    "line_type": DESIGN_LINE_PRINCIPLE_TYPE,
                    "producer": AGENT_REF,
                    "support": [{"root": USER_REF, "neighborhood": []}],
                    "data": {"text": text},
                }
            ],
        },
    )


def _diagram_with_line(tmp_path: Path):
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    block_ship = str(uuid4())
    line_ship = str(uuid4())
    block = _block(
        model.ship, block_ship, "Diagram.Rendering", DESIGN_BLOCK_OBJECT_TYPE
    )
    line = _line(
        model.ship,
        block_ship,
        line_ship,
        "Renderers are named read-only projections.",
    )
    namespace.apply(CaptureManifest.create(model.ship, (block, line)))
    return Diagram((namespace,), namespace.id), model, block_ship, line_ship, line


def _normal_model() -> dict[str, object]:
    user_event_ref = {
        "event_address": USER_REF["turn_address"],
        "event_hash": USER_REF["turn_hash"],
    }
    agent_event_ref = {
        "event_address": AGENT_REF["turn_address"],
        "event_hash": AGENT_REF["turn_hash"],
    }
    return {
        "session": {"identity_hash": IDENTITY, "session_id": "session-one"},
        "events": [
            _event_record("user", user_event_ref, "Please make Diagram renderers named."),
            _event_record("agent", agent_event_ref, "Settled rendering proposal."),
        ],
        "messages": [
            {
                "type": "Chat.Message",
                "message_address": "3" * 64,
                "message_hash": "4" * 64,
                "side": "user",
                "text": "Please make Diagram renderers named.",
                "event_refs": [user_event_ref],
            },
            {
                "type": "Chat.Message",
                "message_address": "7" * 64,
                "message_hash": "8" * 64,
                "side": "agent",
                "text": "Settled rendering proposal.",
                "event_refs": [agent_event_ref],
            },
        ],
        "turns": [
            {
                "type": "Chat.Turn",
                "turn_address": USER_REF["turn_address"],
                "turn_hash": USER_REF["turn_hash"],
                "side": "user",
                "message_refs": [
                    {
                        "message_address": "3" * 64,
                        "message_hash": "4" * 64,
                    }
                ],
                "event_refs": [user_event_ref],
            },
            {
                "type": "Chat.Turn",
                "turn_address": AGENT_REF["turn_address"],
                "turn_hash": AGENT_REF["turn_hash"],
                "side": "agent",
                "message_refs": [
                    {
                        "message_address": "7" * 64,
                        "message_hash": "8" * 64,
                    }
                ],
                "event_refs": [agent_event_ref],
            },
        ],
    }


def _event_record(
    side: str, event_ref: dict[str, str], text: str
) -> dict[str, object]:
    return {
        "type": "User.Event" if side == "user" else "Agent.Event",
        **event_ref,
        "started_at": "2026-09-20T00:00:00Z",
        "origin": side,
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
        "content": {"text": text},
    }


def test_named_line_renderer_includes_exact_rooted_support(tmp_path: Path) -> None:
    diagram, _, _, line_ship, line = _diagram_with_line(tmp_path)
    target = line_render_target(diagram, line_ship)
    evidence = ChatlasEvidence(model_loader=lambda _: _normal_model())

    result = renderer("Kernel.Writing.Line.WithSupport").render(
        target, evidence=evidence
    )

    assert "〔UnAsserted · Unreviewed〕" in result.content
    assert "Please make Diagram renderers named." in result.content
    assert "User.Touch.Root" in result.content
    assert _edition_id(line) in result.content
    assert "`Line.Continuity.Assertion` — unscored" in result.content
    assert [item.code for item in result.findings] == ["line-unreviewed"]


def test_block_and_model_renderers_project_the_flat_tape(tmp_path: Path) -> None:
    diagram, model, block_ship, _, _ = _diagram_with_line(tmp_path)

    block = renderer("Kernel.Writing.Block").render(
        block_render_target(diagram, block_ship)
    )
    rendered_model = renderer("Kernel.Writing.Model").render(model_render_target(model))

    assert block.content.startswith("## Diagram.Rendering")
    assert "[PR] Renderers are named read-only projections." in block.content
    assert rendered_model.content.startswith("# Tarav")
    assert "## Diagram.Rendering" in rendered_model.content
    assert "[PR] Renderers are named read-only projections." in rendered_model.content


def test_issue_block_renderer_exposes_open_state_and_poi(tmp_path: Path) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    block_ship = str(uuid4())
    line_ship = str(uuid4())
    block = _block(model.ship, block_ship, "Issue.Rendering", ISSUE_BLOCK_OBJECT_TYPE)
    line = _line(
        model.ship,
        block_ship,
        line_ship,
        "Open Issues surface attention without blocking work.",
    )
    namespace.apply(CaptureManifest.create(model.ship, (block, line)))
    diagram = Diagram((namespace,), namespace.id)

    result = renderer("Kernel.Writing.Block").render(
        block_render_target(diagram, block_ship)
    )

    assert result.content.startswith("## Issue.Rendering")
    assert "**Issue.State:** `Open`" in result.content
    assert "[PR] Open Issues surface attention without blocking work." in result.content
    assert "issue-open" in {item.code for item in result.findings}


def test_line_renderer_uses_current_edition_while_ship_retains_history(
    tmp_path: Path,
) -> None:
    diagram, model, block_ship, line_ship, _ = _diagram_with_line(tmp_path)
    second = _line(model.ship, block_ship, line_ship, "A second possible wording.")
    model.namespace.apply(CaptureManifest.create(model.ship, (second,)))

    result = renderer("Kernel.Writing.Line").render(
        line_render_target(diagram, line_ship)
    )

    assert result.content.count("\n\n- ") == 0
    assert "Renderers are named read-only projections." not in result.content
    assert "A second possible wording." in result.content
    assert len(model.namespace.ship(line_ship).record["editions"]) == 2
    assert [item.code for item in result.findings] == ["line-unreviewed"]


def test_block_renderer_uses_current_label_edition(tmp_path: Path) -> None:
    diagram, model, block_ship, _, _ = _diagram_with_line(tmp_path)
    replacement = _block(
        model.ship, block_ship, "Current.Rendering", DESIGN_BLOCK_OBJECT_TYPE
    )
    model.namespace.apply(CaptureManifest.create(model.ship, (replacement,)))

    result = renderer("Kernel.Writing.Block").render(
        block_render_target(diagram, block_ship)
    )

    assert result.content.startswith("## Current.Rendering")
    assert "block-label-selection-unresolved" not in {
        item.code for item in result.findings
    }


def test_block_renderer_projects_passing_gate_only_annotations(tmp_path: Path) -> None:
    diagram, model, block_ship, line_ship, line = _diagram_with_line(tmp_path)
    token = "review:rendering"
    proposal_ref = ChatlasTurnReferenceInterface(
        session_identity=IDENTITY, turn_address="9" * 64, turn_hash="a" * 64
    )
    approval_ref = ChatlasTurnReferenceInterface(
        session_identity=IDENTITY, turn_address="d" * 64, turn_hash="e" * 64
    )
    gate = AnnotationDraftInterface.from_record(
        str(uuid4()),
        {
            "type": LINE_GATE_ANNOTATION_TYPE,
            "target_edition": _edition_id(line),
            "gates": [VerbatimGate(token, proposal_ref, approval_ref).to_dict()],
        },
    )
    model.namespace.apply(CaptureManifest.create(model.ship, annotations=(gate,)))
    normal_model = _normal_model()
    proposal_event_ref = {
        "event_address": proposal_ref.turn_address,
        "event_hash": proposal_ref.turn_hash,
    }
    approval_event_ref = {
        "event_address": approval_ref.turn_address,
        "event_hash": approval_ref.turn_hash,
    }
    normal_model["events"].extend(
        [
            _event_record(
                "agent",
                proposal_event_ref,
                "Renderers are named read-only projections.",
            ),
            _event_record("user", approval_event_ref, f"::approve {token}"),
        ]
    )
    normal_model["messages"].extend(
        [
            {
                "type": "Chat.Message",
                "message_address": "b" * 64,
                "message_hash": "c" * 64,
                "side": "agent",
                "text": (
                    "Renderers are named read-only projections.\n"
                    f"Approve with ::approve {token}"
                ),
                "event_refs": [proposal_event_ref],
            },
            {
                "type": "Chat.Message",
                "message_address": "f" * 64,
                "message_hash": "0" * 64,
                "side": "user",
                "text": f"::approve {token}",
                "event_refs": [approval_event_ref],
            },
        ]
    )
    normal_model["turns"].extend(
        [
            {
                "type": "Chat.Turn",
                "turn_address": proposal_ref.turn_address,
                "turn_hash": proposal_ref.turn_hash,
                "side": "agent",
                "message_refs": [
                    {
                        "message_address": "b" * 64,
                        "message_hash": "c" * 64,
                    }
                ],
                "event_refs": [proposal_event_ref],
            },
            {
                "type": "Chat.Turn",
                "turn_address": approval_ref.turn_address,
                "turn_hash": approval_ref.turn_hash,
                "side": "user",
                "message_refs": [
                    {
                        "message_address": "f" * 64,
                        "message_hash": "0" * 64,
                    }
                ],
                "event_refs": [approval_event_ref],
            },
        ]
    )
    evidence = ChatlasEvidence(model_loader=lambda _: normal_model)

    result = renderer("Kernel.Writing.Block.WithSupport").render(
        block_render_target(diagram, block_ship), evidence=evidence
    )

    assert "〔UnAsserted · Reviewed〕" in result.content
    assert result.content.count("<summary>Support ·") == 1
    assert "line-unreviewed" not in {item.code for item in result.findings}
    assert diagram.line_review(line_ship, evidence=evidence).standing == "Reviewed"


def test_renderer_cli_discovers_and_runs_named_renderers(
    tmp_path: Path, capsys
) -> None:
    diagram, _, _, line_ship, _ = _diagram_with_line(tmp_path)
    config = DiagramConfiguration.load(tmp_path / "diagram.json", create=True).mount(
        diagram.namespaces[0], default=True
    )

    assert main(["diagram", "renderer", "list", "--target", "line", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert {item["name"] for item in listed["renderers"]} == {
        "Kernel.Writing.Line",
        "Kernel.Writing.Line.WithSupport",
        "Diagram.Debug.Line",
    }

    assert (
        main(
            [
                "diagram",
                "render",
                "--line-ship",
                line_ship,
                "--renderer",
                "Kernel.Writing.Line",
                "--diagram-config",
                str(config.path),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["renderer"] == "Kernel.Writing.Line"
    assert rendered["target"]["ship"] == line_ship
    assert rendered["media_type"] == "text/markdown"
    assert "Renderers are named read-only projections." in rendered["content"]


def test_renderer_registry_has_the_candidate_initial_surface() -> None:
    assert {item.name for item in renderers()} == {
        "Kernel.Writing.Line.Annotation",
        "Kernel.Writing.Line",
        "Kernel.Writing.Line.WithSupport",
        "Kernel.Writing.Block",
        "Kernel.Writing.Block.WithSupport",
        "Kernel.Writing.Collection",
        "Kernel.Writing.Model",
        "Diagram.Debug.Annotation",
        "Diagram.Debug.Line",
    }
