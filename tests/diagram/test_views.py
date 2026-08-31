from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from tarav.cli.cli import main
from tarav.diagram import (
    BLOCK_ANNOTATION_TYPE,
    DESIGN_BLOCK_OBJECT_TYPE,
    DESIGN_LINE_PRINCIPLE_TYPE,
    LINE_ANNOTATION_TYPE,
    AnnotationDraft,
    CaptureManifest,
    Diagram,
    DiagramBlockLocation,
    DiagramConfiguration,
    DiagramLocation,
    DiagramNamespace,
)
from tarav.diagram import view_commands
from tarav.diagram import views
from tarav.diagram.views import (
    DiagramViewConfiguration,
    DiagramViewRepository,
)


REF = {
    "session_identity": "a" * 64,
    "turn_address": "b" * 64,
    "turn_hash": "c" * 64,
}


def _diagram(tmp_path: Path):
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    context_block = str(uuid4())
    provider_block = str(uuid4())
    first_line = str(uuid4())
    second_line = str(uuid4())
    drafts = (
        AnnotationDraft(
            str(uuid4()),
            {
                "type": BLOCK_ANNOTATION_TYPE,
                "block_type": DESIGN_BLOCK_OBJECT_TYPE,
                "location": DiagramBlockLocation(model.ship, context_block).to_dict(),
                "data": {"label": "Context.Provider"},
            },
        ),
        AnnotationDraft(
            str(uuid4()),
            {
                "type": BLOCK_ANNOTATION_TYPE,
                "block_type": DESIGN_BLOCK_OBJECT_TYPE,
                "location": DiagramBlockLocation(model.ship, provider_block).to_dict(),
                "data": {"label": "Diagram.View"},
            },
        ),
        AnnotationDraft(
            str(uuid4()),
            {
                "type": LINE_ANNOTATION_TYPE,
                "line_type": DESIGN_LINE_PRINCIPLE_TYPE,
                "producer": REF,
                "support": [{"root": REF, "neighborhood": []}],
                "location": DiagramLocation(
                    model.ship, provider_block, first_line
                ).to_dict(),
                "data": {
                    "text": "Diagram.View is operated through Context.Provider mechanics."
                },
            },
        ),
        AnnotationDraft(
            str(uuid4()),
            {
                "type": LINE_ANNOTATION_TYPE,
                "line_type": DESIGN_LINE_PRINCIPLE_TYPE,
                "producer": REF,
                "support": [{"root": REF, "neighborhood": []}],
                "location": DiagramLocation(
                    model.ship, provider_block, second_line
                ).to_dict(),
                "data": {"text": "Agents select the context they need."},
            },
        ),
    )
    namespace.apply(CaptureManifest(model.ship, drafts))
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
        configuration=DiagramViewConfiguration(bootstrap_visible_lines=1),
    )

    view = mutation.view
    assert (repository.root / ".git").is_dir()
    assert {path.name for path in view.root.iterdir()} == {
        "manifest.json",
        "about.json",
        "config.json",
        "view.json",
    }
    assert view.manifest["type"] == "Diagram.View.Annotation"
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


def test_view_disclosure_and_line_selection_are_cli_managed(tmp_path: Path) -> None:
    diagram, model, _, provider_block, first_line, second_line = _diagram(tmp_path)
    repository = DiagramViewRepository.create(tmp_path / "views")
    view = repository.create_view(
        diagram,
        block_ships=(provider_block,),
        configuration=DiagramViewConfiguration(bootstrap_visible_lines=1),
    ).view

    included = repository.select_line(
        view.ship,
        diagram,
        block_ship=provider_block,
        line_ship=second_line,
        selected=True,
    )
    block = included.view.state["blocks"][0]
    assert set(block["selected_line_ships"]) == {first_line, second_line}
    assert len(block["disclosure"]["lines"]) == 2

    collapsed = repository.disclose(
        view.ship, diagram, block_ship=provider_block, steps=-1000
    )
    block = collapsed.view.state["blocks"][0]
    assert block["disclosure_name"] == "collapsed"
    assert block["disclosure"]["lines"] == []
    assert block["label"] == "Diagram.View"
    assert block["dependencies"]

    expanded = repository.disclose(
        view.ship, diagram, block_ship=provider_block, steps=2
    )
    line = expanded.view.state["blocks"][0]["disclosure"]["lines"][0]
    assert expanded.view.state["blocks"][0]["disclosure_name"] == "support"
    assert line["support"][0]["members"][0]["root"] == REF


def test_view_full_expansion_is_an_idempotent_no_op(tmp_path: Path) -> None:
    diagram, _, _, provider_block, first_line, second_line = _diagram(tmp_path)
    repository = DiagramViewRepository.create(tmp_path / "views")
    view = repository.create_view(
        diagram,
        block_ships=(provider_block,),
        configuration=DiagramViewConfiguration(bootstrap_visible_lines=1),
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
    model.namespace.append(
        (
            AnnotationDraft(
                str(uuid4()),
                {
                    "type": BLOCK_ANNOTATION_TYPE,
                    "block_type": DESIGN_BLOCK_OBJECT_TYPE,
                    "location": DiagramBlockLocation(
                        model.ship, str(uuid4())
                    ).to_dict(),
                    "data": {"label": "New.Block"},
                },
            ),
        )
    )

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
    assert DiagramViewRepository.open(views_root).view(view_ship).about == {
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
    assert payload["views"][0]["about"]["chatlas_session_identity"] == "session-one"
    assert payload["views"][0]["edition"] == selected.edition()
