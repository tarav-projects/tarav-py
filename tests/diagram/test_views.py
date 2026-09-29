from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from tarav.l3.cli.cli import main
from tarav.l2.unsorted.constants import BLOCK_SHIP_TYPE, DESIGN_BLOCK_OBJECT_TYPE, DESIGN_LINE_PRINCIPLE_TYPE, LINE_SHIP_TYPE
from tarav.l2.unsorted.capture import CaptureManifest
from tarav.l2.unsorted.evidence import ChatlasEvidence
from tarav.l2.unsorted.storage import Diagram, DiagramConfiguration, DiagramNamespace
from tarav.l2.unsorted.contracts import ShipDraftInterface
from tarav.l2.unsorted import view_commands
from tarav.l2.unsorted import views
from tarav.l2.unsorted.views import (
    DIAGRAM_VIEW_TYPE,
    PROJECT_DIAGRAM_VIEW_TYPE,
    SESSION_DIAGRAM_VIEW_TYPE,
    DiagramView,
    DiagramViewConfiguration,
    DiagramViewError,
    DiagramViewRepository,
    ProjectDiagramView,
    SessionDiagramView,
)


REF = {
    "session_identity": "a" * 64,
    "turn_address": "b" * 64,
    "turn_hash": "c" * 64,
}
AGENT_REF = {
    "session_identity": "a" * 64,
    "turn_address": "d" * 64,
    "turn_hash": "e" * 64,
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


def _line(
    model_ship: str, block_ship: str, line_ship: str, text: str
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
                    "support": [{"root": REF, "neighborhood": []}],
                    "data": {"text": text},
                }
            ],
        },
    )


def _diagram(tmp_path: Path):
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    context_block = str(uuid4())
    provider_block = str(uuid4())
    first_line = str(uuid4())
    second_line = str(uuid4())
    drafts = (
        _block(model.ship, context_block, "Context.Provider"),
        _block(model.ship, provider_block, "Diagram.View"),
        _line(
            model.ship,
            provider_block,
            first_line,
            "Diagram.View is operated through Context.Provider mechanics.",
        ),
        _line(
            model.ship,
            provider_block,
            second_line,
            "Agents select the context they need.",
        ),
    )
    namespace.apply(CaptureManifest.create(model.ship, drafts))
    return (
        Diagram((namespace,), namespace.id),
        model,
        context_block,
        provider_block,
        first_line,
        second_line,
    )


def test_view_repository_materializes_agent_readable_context(tmp_path: Path) -> None:
    diagram, model, context_block, provider_block, _, _ = _diagram(tmp_path)
    repository = DiagramViewRepository.create(tmp_path / "views")

    mutation = repository.create_view(
        diagram,
        model_ships=(model.ship,),
        about={"workflow": "ground", "session_id": "session-one"},
        configuration=DiagramViewConfiguration.create(bootstrap_visible_lines=1),
    )

    view = mutation.view
    assert (repository.root / ".git").is_dir()
    assert {path.name for path in view.root.iterdir()} == {
        "manifest.json",
        "about.json",
        "config.json",
        "view.json",
    }
    assert view.manifest["type"] == "Diagram.View.Manifest"
    assert view.manifest["view_type"] == DIAGRAM_VIEW_TYPE
    assert isinstance(view, DiagramView)
    assert type(view) is DiagramView
    assert view.about == {"workflow": "ground", "session_id": "session-one"}
    state = view.state
    assert state["scope"] == [
        {
            "type": "Diagram.Model",
            "namespace_id": model.namespace.id,
            "model_ship": model.ship,
        }
    ]
    blocks = {item["block_ship"]: item for item in state["blocks"]}
    assert blocks[context_block]["label"] == "Context.Provider"
    provider = blocks[provider_block]
    assert provider["label"] == "Diagram.View"
    assert provider["stats"]["line_count"] == 2
    assert len(provider["disclosure"]["lines"]) == 1
    assert set(provider["disclosure"]["lines"][0]["editions"][0]) == {
        "edition_id",
        "text",
    }
    assert provider["dependencies"] == [
        {
            "label": "Context.Provider",
            "status": "resolved",
            "targets": [
                {
                    "namespace_id": model.namespace.id,
                    "block_ship": context_block,
                }
            ],
        }
    ]
    assert view.check(diagram) == ()


def test_view_manifest_type_selects_runtime_view_class(tmp_path: Path) -> None:
    diagram, model, _, _, _, _ = _diagram(tmp_path)
    repository = DiagramViewRepository.create(tmp_path / "views")

    session = repository.create_view(
        diagram,
        model_ships=(model.ship,),
        view_type=SESSION_DIAGRAM_VIEW_TYPE,
        about={"chatlas_session_identity": REF["session_identity"]},
    ).view
    project = repository.create_view(
        diagram,
        model_ships=(model.ship,),
        view_type=PROJECT_DIAGRAM_VIEW_TYPE,
    ).view

    assert isinstance(session, SessionDiagramView)
    assert session.session_identity == REF["session_identity"]
    assert isinstance(project, ProjectDiagramView)
    assert isinstance(repository.view(session.ship), SessionDiagramView)
    assert isinstance(repository.view(project.ship), ProjectDiagramView)


def test_a_repository_of_another_schema_version_is_refused(tmp_path: Path) -> None:
    repository = DiagramViewRepository.create(tmp_path / "views")
    record_path = repository.root / "repository.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["schema_version"] = record["schema_version"] + 1
    record_path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(DiagramViewError, match="Unsupported Diagram.View repository"):
        DiagramViewRepository.open(repository.root)


def test_session_view_peer_hints_expose_related_selections(tmp_path: Path) -> None:
    diagram, model, _, provider_block, _, _ = _diagram(tmp_path)
    repository = DiagramViewRepository.create(tmp_path / "views")
    first = repository.create_view(
        diagram,
        model_ships=(model.ship,),
        view_type=SESSION_DIAGRAM_VIEW_TYPE,
        about={"chatlas_session_identity": "session-one"},
    ).view
    second = repository.create_view(
        diagram,
        model_ships=(model.ship,),
        view_type=SESSION_DIAGRAM_VIEW_TYPE,
        about={"chatlas_session_identity": "session-two"},
    ).view

    hints = repository.session_peer_hints(first.ship)

    assert len(hints) == 1
    assert hints[0]["view_ship"] == second.ship
    assert hints[0]["shared_models"] == [model.ship]
    assert any(
        block["block_ship"] == provider_block for block in hints[0]["selected_blocks"]
    )


def test_session_view_mentions_surface_blocks_outside_the_view(tmp_path: Path) -> None:
    diagram, _, context_block, provider_block, _, _ = _diagram(tmp_path)
    repository = DiagramViewRepository.create(tmp_path / "views")
    normal_model = _normal_model()
    normal_model["messages"][0]["text"] = (
        "Diagram.View depends on Context.Provider for this session."
    )
    evidence = ChatlasEvidence(model_loader=lambda _: normal_model)
    view = repository.create_view(
        diagram,
        block_ships=(provider_block,),
        view_type=SESSION_DIAGRAM_VIEW_TYPE,
        about={"chatlas_session_identity": REF["session_identity"]},
        evidence=evidence,
    ).view
    assert isinstance(view, SessionDiagramView)

    mentions = view.mentions(diagram, evidence)
    by_ship = {mention["block_ship"]: mention for mention in mentions}

    assert by_ship[provider_block]["present_in_view"] is True
    assert by_ship[context_block]["present_in_view"] is False
    assert any(
        finding.code == "diagram-view-mentioned-block-absent"
        and context_block in finding.path
        for finding in view.check(diagram, evidence=evidence)
    )


def test_view_disclosure_and_line_selection_are_cli_managed(tmp_path: Path) -> None:
    diagram, model, _, provider_block, first_line, second_line = _diagram(tmp_path)
    repository = DiagramViewRepository.create(tmp_path / "views")
    view = repository.create_view(
        diagram,
        block_ships=(provider_block,),
        configuration=DiagramViewConfiguration.create(bootstrap_visible_lines=1),
    ).view

    included = repository.select_line(
        view.ship,
        diagram,
        block_ship=provider_block[:12],
        line_ship=second_line[:12],
        selected=True,
    )
    block = included.view.state["blocks"][0]
    assert set(block["selected_line_ships"]) == {first_line, second_line}
    assert len(block["disclosure"]["lines"]) == 2

    collapsed = repository.disclose(
        view.ship, diagram, block_ship=provider_block[:12], steps=-1000
    )
    block = collapsed.view.state["blocks"][0]
    assert block["disclosure_name"] == "collapsed"
    assert block["disclosure"]["lines"] == []
    assert block["label"] == "Diagram.View"
    assert block["dependencies"]

    expanded = repository.disclose(
        view.ship, diagram, block_ship=provider_block[:12], steps=2
    )
    line = expanded.view.state["blocks"][0]["disclosure"]["lines"][0]
    assert expanded.view.state["blocks"][0]["disclosure_name"] == "support"
    assert line["stats"]["support_root_count"] == 1
    assert line["stats"]["support_turn_count"] == 1
    assert "support" not in line

    rendered = expanded.view.render()
    assert f"`{provider_block[:12]}`" in rendered
    assert f"`{first_line[:12]}`" in rendered
    assert provider_block not in rendered
    assert first_line not in rendered
    assert expanded.view.ship not in rendered
    assert (
        "[PR] Diagram.View is operated through Context.Provider mechanics." in rendered
    )
    assert "1 support root" in rendered
    assert "session_identity" not in rendered


def test_view_deep_support_renders_content_without_raw_reference_json(
    tmp_path: Path,
) -> None:
    diagram, _, _, provider_block, _, _ = _diagram(tmp_path)
    repository = DiagramViewRepository.create(tmp_path / "views")
    evidence = ChatlasEvidence(model_loader=lambda _: _normal_model())
    view = repository.create_view(
        diagram,
        block_ships=(provider_block,),
        configuration=DiagramViewConfiguration.create(bootstrap_visible_lines=1),
        evidence=evidence,
    ).view

    expanded = repository.disclose(
        view.ship,
        diagram,
        block_ship=provider_block,
        steps=1000,
        full=True,
        evidence=evidence,
    )
    rendered = expanded.view.render()
    retained = json.dumps(expanded.view.state["blocks"][0]["disclosure"])

    assert rendered.count("Please keep context selection Agent-operated.") == 1
    assert "    - **User (root):**\n      `````text\n" in rendered
    assert "\n      `````" in rendered
    assert "Support.Content" not in rendered
    assert "session_identity" not in rendered
    assert REF["session_identity"] not in rendered
    assert REF["turn_address"] not in rendered
    assert REF["session_identity"][:12] in rendered
    assert "session_identity" not in retained
    assert "turn_address" not in retained
    assert "turn_hash" not in retained
    assert REF["session_identity"] not in retained


def test_view_verbatim_fence_is_collision_free() -> None:
    assert views._fenced_verbatim_lines("plain", indent="  ") == [
        "  `````text",
        "  plain",
        "  `````",
    ]
    assert views._fenced_verbatim_lines("before\n`````\nafter", indent="  ") == [
        "  ``````text",
        "  before",
        "  `````",
        "  after",
        "  ``````",
    ]


def _normal_model() -> dict[str, object]:
    user_event_ref = {
        "event_address": REF["turn_address"],
        "event_hash": REF["turn_hash"],
    }
    agent_event_ref = {
        "event_address": AGENT_REF["turn_address"],
        "event_hash": AGENT_REF["turn_hash"],
    }
    return {
        "session": {"identity_hash": REF["session_identity"]},
        "events": [
            _event_record("user", user_event_ref, "Please keep context selection Agent-operated."),
            _event_record("agent", agent_event_ref, "Settled compact View context."),
        ],
        "messages": [
            {
                "type": "Chat.Message",
                "message_address": "f" * 64,
                "message_hash": "0" * 64,
                "side": "user",
                "text": "Please keep context selection Agent-operated.",
                "event_refs": [user_event_ref],
            },
            {
                "type": "Chat.Message",
                "message_address": "1" * 64,
                "message_hash": "2" * 64,
                "side": "agent",
                "text": "Settled compact View context.",
                "event_refs": [agent_event_ref],
            },
        ],
        "turns": [
            {
                "type": "Chat.Turn",
                "turn_address": REF["turn_address"],
                "turn_hash": REF["turn_hash"],
                "side": "user",
                "message_refs": [
                    {"message_address": "f" * 64, "message_hash": "0" * 64}
                ],
                "event_refs": [user_event_ref],
            },
            {
                "type": "Chat.Turn",
                "turn_address": AGENT_REF["turn_address"],
                "turn_hash": AGENT_REF["turn_hash"],
                "side": "agent",
                "message_refs": [
                    {"message_address": "1" * 64, "message_hash": "2" * 64}
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


def test_view_full_expansion_is_an_idempotent_no_op(tmp_path: Path) -> None:
    diagram, _, _, provider_block, first_line, second_line = _diagram(tmp_path)
    repository = DiagramViewRepository.create(tmp_path / "views")
    view = repository.create_view(
        diagram,
        block_ships=(provider_block,),
        configuration=DiagramViewConfiguration.create(bootstrap_visible_lines=1),
    ).view

    expanded = repository.disclose(
        view.ship,
        diagram,
        block_ship=provider_block,
        steps=1000,
        full=True,
    )
    assert set(expanded.view.state["blocks"][0]["selected_line_ships"]) == {
        first_line,
        second_line,
    }
    commit = expanded.commit

    repeated = repository.disclose(
        view.ship,
        diagram,
        block_ship=provider_block,
        steps=1000,
        full=True,
    )

    assert repeated.changes == ()
    assert repeated.commit == commit
    assert repeated.view.edition()["commit"] == commit


def test_view_commit_reuses_head_when_target_paths_are_unchanged(
    tmp_path: Path,
) -> None:
    repository = DiagramViewRepository.create(tmp_path / "views")
    commit = views._git(repository.root, "rev-parse", "HEAD")

    repeated = views._commit(
        repository.root,
        (Path("repository.json"),),
        "diagram(view): unchanged repository",
    )

    assert repeated == commit
    assert views._git(repository.root, "rev-list", "--count", "HEAD") == "1"


def test_view_check_surfaces_stale_source_until_sync(tmp_path: Path) -> None:
    diagram, model, _, provider_block, _, _ = _diagram(tmp_path)
    repository = DiagramViewRepository.create(tmp_path / "views")
    view = repository.create_view(diagram, model_ships=(model.ship,)).view
    model.namespace.append((_block(model.ship, str(uuid4()), "New.Block"),))

    assert {item.code for item in view.check(diagram)} == {"diagram-view-source-stale"}

    synced = repository.synchronize(view.ship, diagram)
    assert synced.changes
    assert synced.view.check(diagram) == ()
    assert any(
        item["block_ship"] == provider_block for item in synced.view.state["blocks"]
    )


def test_view_cli_creates_and_renders_a_retained_view(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    diagram, model, _, _, _, _ = _diagram(tmp_path)
    config = DiagramConfiguration.load(tmp_path / "diagram.json", create=True).mount(
        model.namespace, default=True
    )
    views_root = tmp_path / "views"
    monkeypatch.setattr(view_commands, "_evidence", lambda _: None)

    assert (
        main(
            [
                "diagram",
                "view",
                "create",
                "--model-ship",
                model.ship,
                "--diagram-config",
                str(config.path),
                "--views-root",
                str(views_root),
                "--view-type",
                SESSION_DIAGRAM_VIEW_TYPE,
                "--about-field",
                "workflow=tarav-hugentics.ground",
                "--about-field",
                "chatlas_session_identity=session-one",
                "--json",
            ]
        )
        == 0
    )
    created = json.loads(capsys.readouterr().out)
    view_ship = created["view_ship"]
    loaded = DiagramViewRepository.open(views_root).view(view_ship)
    assert isinstance(loaded, SessionDiagramView)
    assert loaded.about == {
        "workflow": "tarav-hugentics.ground",
        "chatlas_session_identity": "session-one",
    }

    assert (
        main(
            [
                "diagram",
                "view",
                "render",
                "--view",
                view_ship[:12],
                "--views-root",
                str(views_root),
            ]
        )
        == 0
    )
    rendered = capsys.readouterr().out
    assert "# Diagram.View" in rendered
    assert "## Diagram.View" in rendered


def test_view_cli_mutation_renders_the_complete_affected_block(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    diagram, model, _, provider_block, _, _ = _diagram(tmp_path)
    config = DiagramConfiguration.load(tmp_path / "diagram.json", create=True).mount(
        model.namespace, default=True
    )
    repository = DiagramViewRepository.create(tmp_path / "views")
    view = repository.create_view(
        diagram,
        model_ships=(model.ship,),
        configuration=DiagramViewConfiguration.create(bootstrap_visible_lines=1),
    ).view
    monkeypatch.setattr(view_commands, "_evidence", lambda _: None)

    assert (
        main(
            [
                "diagram",
                "view",
                "expand",
                "--view",
                view.ship[:12],
                "--block-ship",
                provider_block[:12],
                "--diagram-config",
                str(config.path),
                "--views-root",
                str(repository.root),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "## Diagram.View" in output
    assert "## Context.Provider" not in output
    assert "Diagram.View is operated through Context.Provider mechanics." in output
    assert "support · 2 lines" in output


def test_view_list_filters_open_about_metadata_and_reports_exact_edition(
    tmp_path: Path, capsys
) -> None:
    diagram, model, _, _, _, _ = _diagram(tmp_path)
    repository = DiagramViewRepository.create(tmp_path / "views")
    selected = repository.create_view(
        diagram,
        model_ships=(model.ship,),
        about={
            "workflow": "tarav-hugentics.ground",
            "chatlas_session_identity": "session-one",
        },
    ).view
    repository.create_view(
        diagram,
        model_ships=(model.ship,),
        about={
            "workflow": "tarav-hugentics.ground",
            "chatlas_session_identity": "session-two",
        },
    )

    assert (
        main(
            [
                "diagram",
                "view",
                "list",
                "--views-root",
                str(repository.root),
                "--about",
                "workflow=tarav-hugentics.ground",
                "--about",
                "chatlas_session_identity=session-one",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert [item["view_ship"] for item in payload["views"]] == [selected.ship]
    assert payload["views"][0]["manifest_id"] == selected.manifest_id
    assert "annotation_id" not in payload["views"][0]
    assert payload["views"][0]["about"]["chatlas_session_identity"] == "session-one"
    assert payload["views"][0]["edition"] == selected.edition()


def test_session_view_cli_reports_peers_and_mentions(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    diagram, model, _, provider_block, _, _ = _diagram(tmp_path)
    config = DiagramConfiguration.load(tmp_path / "diagram.json", create=True).mount(
        model.namespace, default=True
    )
    repository = DiagramViewRepository.create(tmp_path / "views")
    first = repository.create_view(
        diagram,
        block_ships=(provider_block,),
        view_type=SESSION_DIAGRAM_VIEW_TYPE,
        about={"chatlas_session_identity": REF["session_identity"]},
    ).view
    second = repository.create_view(
        diagram,
        model_ships=(model.ship,),
        view_type=SESSION_DIAGRAM_VIEW_TYPE,
        about={"chatlas_session_identity": "session-two"},
    ).view
    normal_model = _normal_model()
    normal_model["messages"][0]["text"] = "Diagram.View uses Context.Provider."
    monkeypatch.setattr(
        view_commands,
        "_evidence",
        lambda _: ChatlasEvidence(model_loader=lambda __: normal_model),
    )

    assert (
        main(
            [
                "diagram",
                "view",
                "peers",
                "--view",
                first.ship[:12],
                "--views-root",
                str(repository.root),
                "--json",
            ]
        )
        == 0
    )
    peers = json.loads(capsys.readouterr().out)
    assert [item["view_ship"] for item in peers["peers"]] == [second.ship]

    assert (
        main(
            [
                "diagram",
                "view",
                "mentions",
                "--view",
                first.ship[:12],
                "--views-root",
                str(repository.root),
                "--diagram-config",
                str(config.path),
                "--json",
            ]
        )
        == 0
    )
    mentions = json.loads(capsys.readouterr().out)["mentions"]
    assert {item["label"] for item in mentions} == {
        "Context.Provider",
        "Diagram.View",
    }
