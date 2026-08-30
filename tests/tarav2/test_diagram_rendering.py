from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from tarav.cli.cli import main
from tarav.tarav2.diagram import (
    BLOCK_ANNOTATION_TYPE,
    DESIGN_BLOCK_OBJECT_TYPE,
    DESIGN_LINE_PRINCIPLE_TYPE,
    LINE_ANNOTATION_TYPE,
    LINE_GATE_ANNOTATION_TYPE,
    AnnotationDraft,
    CaptureManifest,
    ChatlasEvidence,
    Diagram,
    DiagramBlockLocation,
    DiagramConfiguration,
    DiagramLocation,
    DiagramNamespace,
    VerbatimGate,
    ChatlasTurnReference,
)
from tarav.tarav2.diagram_rendering import (
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


def _diagram_with_line(tmp_path: Path):
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    block_ship = str(uuid4())
    line_ship = str(uuid4())
    block = AnnotationDraft(
        str(uuid4()),
        {
            "type": BLOCK_ANNOTATION_TYPE,
            "block_type": DESIGN_BLOCK_OBJECT_TYPE,
            "location": DiagramBlockLocation(model.ship, block_ship).to_dict(),
            "data": {"label": "Diagram.Rendering"},
        },
    )
    line = AnnotationDraft(
        str(uuid4()),
        {
            "type": LINE_ANNOTATION_TYPE,
            "line_type": DESIGN_LINE_PRINCIPLE_TYPE,
            "producer": AGENT_REF,
            "support": [{"root": USER_REF, "neighborhood": []}],
            "location": DiagramLocation(model.ship, block_ship, line_ship).to_dict(),
            "data": {"text": "Renderers are named read-only projections."},
        },
    )
    namespace.apply(CaptureManifest(model.ship, (block, line)))
    return Diagram((namespace,), namespace.id), model, block_ship, line_ship, line


def _normal_model() -> dict[str, object]:
    return {
        "session": {"identity_hash": IDENTITY, "session_id": "session-one"},
        "events": [],
        "messages": [
            {
                "message_address": "3" * 64,
                "message_hash": "4" * 64,
                "side": "user",
                "text": "Please make Diagram renderers named.",
            },
            {
                "message_address": "7" * 64,
                "message_hash": "8" * 64,
                "side": "agent",
                "text": "Settled rendering proposal.",
            },
        ],
        "turns": [
            {
                "turn_address": USER_REF["turn_address"],
                "turn_hash": USER_REF["turn_hash"],
                "side": "user",
                "message_refs": [
                    {
                        "message_address": "3" * 64,
                        "message_hash": "4" * 64,
                    }
                ],
                "event_refs": [],
            },
            {
                "turn_address": AGENT_REF["turn_address"],
                "turn_hash": AGENT_REF["turn_hash"],
                "side": "agent",
                "message_refs": [
                    {
                        "message_address": "7" * 64,
                        "message_hash": "8" * 64,
                    }
                ],
                "event_refs": [],
            },
        ],
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
    assert line.id in result.content
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


def test_ambiguous_line_renderer_surfaces_all_wording_variants(
    tmp_path: Path,
) -> None:
    diagram, model, block_ship, line_ship, _ = _diagram_with_line(tmp_path)
    second = AnnotationDraft(
        str(uuid4()),
        {
            "type": LINE_ANNOTATION_TYPE,
            "line_type": DESIGN_LINE_PRINCIPLE_TYPE,
            "producer": AGENT_REF,
            "support": [{"root": USER_REF, "neighborhood": []}],
            "location": DiagramLocation(model.ship, block_ship, line_ship).to_dict(),
            "data": {"text": "A second possible wording."},
        },
    )
    model.namespace.apply(CaptureManifest(model.ship, (second,)))

    result = renderer("Kernel.Writing.Line").render(
        line_render_target(diagram, line_ship)
    )

    assert result.content.count("\n\n- ") == 1
    assert "Renderers are named read-only projections." in result.content
    assert "A second possible wording." in result.content
    assert [item.code for item in result.findings] == [
        "line-rendering-selection-ambiguous",
        "line-unreviewed",
    ]


def test_block_renderer_projects_passing_gate_only_annotations(tmp_path: Path) -> None:
    diagram, model, block_ship, line_ship, line = _diagram_with_line(tmp_path)
    token = "review:rendering"
    proposal_ref = ChatlasTurnReference(IDENTITY, "9" * 64, "a" * 64)
    approval_ref = ChatlasTurnReference(IDENTITY, "d" * 64, "e" * 64)
    gate = AnnotationDraft(
        str(uuid4()),
        {
            "type": LINE_GATE_ANNOTATION_TYPE,
            "target_annotation": line.id,
            "gates": [VerbatimGate(token, proposal_ref, approval_ref).to_dict()],
        },
    )
    model.namespace.apply(CaptureManifest(model.ship, (gate,)))
    normal_model = _normal_model()
    normal_model["messages"].extend(
        [
            {
                "message_address": "b" * 64,
                "message_hash": "c" * 64,
                "side": "agent",
                "text": (
                    "Renderers are named read-only projections.\n"
                    f"Approve with ::approve {token}"
                ),
            },
            {
                "message_address": "f" * 64,
                "message_hash": "0" * 64,
                "side": "user",
                "text": f"::approve {token}",
            },
        ]
    )
    normal_model["turns"].extend(
        [
            {
                **proposal_ref.to_dict(),
                "side": "agent",
                "message_refs": [
                    {
                        "message_address": "b" * 64,
                        "message_hash": "c" * 64,
                    }
                ],
                "event_refs": [],
            },
            {
                **approval_ref.to_dict(),
                "side": "user",
                "message_refs": [
                    {
                        "message_address": "f" * 64,
                        "message_hash": "0" * 64,
                    }
                ],
                "event_refs": [],
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

    assert (
        main(["tarav2", "diagram", "renderer", "list", "--target", "line", "--json"])
        == 0
    )
    listed = json.loads(capsys.readouterr().out)
    assert {item["name"] for item in listed["renderers"]} == {
        "Kernel.Writing.Line",
        "Kernel.Writing.Line.WithSupport",
        "Diagram.Debug.Line",
    }

    assert (
        main(
            [
                "tarav2",
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
        "Kernel.Writing.Line",
        "Kernel.Writing.Line.WithSupport",
        "Kernel.Writing.Block",
        "Kernel.Writing.Block.WithSupport",
        "Kernel.Writing.Model",
        "Diagram.Debug.Annotation",
        "Diagram.Debug.Line",
    }
