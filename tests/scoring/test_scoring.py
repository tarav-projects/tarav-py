from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from tarav._core.project import initialize_project_layout
from tarav.cli.cli import main
from tarav.diagram import (
    BLOCK_SHIP_TYPE,
    DESIGN_BLOCK_OBJECT_TYPE,
    DESIGN_LINE_PRINCIPLE_TYPE,
    LINE_SHIP_TYPE,
    CaptureManifest,
    ChatlasEvidence,
    DiagramConfiguration,
    DiagramNamespace,
    ShipDraft,
)
from tarav.scoring import (
    GROUNDING_TASK_TYPE,
    RESULT_TYPE,
    RUN_TYPE,
    ScoringError,
    ScoringRepository,
    builtin_score_definition,
    compute_win_rate_score,
    create_grounding_task,
    create_pool,
    create_result,
    create_run,
    render_task,
)
from tarav.scoring.tasks import create_line_grounding_task
from tarav.scoring.runner import execute_run, prepare_run


def _candidate(candidate_id: str, claim: str) -> dict[str, object]:
    return {
        "id": candidate_id,
        "assertion": {
            "type": "Index.Line.Grounding.Assertion",
            "subject": {"line_edition_id": candidate_id},
        },
        "presentation": f"Line claim:\n{claim}\n\nDeclared Support.Set:\nEvidence.",
        "appendix": [],
    }


def _task():
    first, second = str(uuid4()), str(uuid4())
    pool = create_pool("line-grounding")
    task = create_grounding_task(
        pool=pool,
        candidates=(_candidate(first, "First claim."), _candidate(second, "Second claim.")),
    )
    return pool, task, first, second


def test_repository_retains_typed_records_in_git_and_resolves_prefixes(tmp_path: Path) -> None:
    repository = ScoringRepository.initialize(tmp_path / "scoring")
    pool = repository.create(create_pool("grounding"))

    assert repository.resolve(pool["id"][:12]) == pool
    assert repository.path_for(pool).parent.name == "pools"
    assert repository.head()
    assert int(
        __import__("subprocess").run(
            ("git", "-C", str(repository.root), "rev-list", "--count", "HEAD"),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    ) == 2

    rebound = {**pool, "type": RUN_TYPE}
    with pytest.raises(ScoringError):
        repository.save(rebound)


def test_task_rendering_uses_opaque_labels_and_run_retains_exact_prompt() -> None:
    _, task, first, second = _task()
    rendered = render_task(task, {"A": second, "B": first})

    assert "## Candidate A" in rendered
    assert "Second claim." in rendered
    assert first not in rendered
    assert second not in rendered

    run = create_run(
        task=task,
        runner={"type": "Preview.Ranking.Task.Runner"},
        repository_root="/tmp/scoring records",
        seed="repeatable",
        status="Preview",
    )
    assert run["type"] == RUN_TYPE
    assert run["rendered_prompt_sha256"]
    assert "tarav scoring submit" in run["rendered_prompt"]
    assert "--root '/tmp/scoring records'" in run["rendered_prompt"]


def test_structured_results_map_labels_and_scores_retain_exact_inputs() -> None:
    pool, task, first, second = _task()
    run_one = create_run(
        task=task,
        runner={"type": "Preview.Ranking.Task.Runner"},
        repository_root="/tmp/scoring",
        seed="one",
    )
    labels_one = {candidate: label for label, candidate in run_one["labels"].items()}
    result_one = create_result(
        run=run_one,
        tiers=((labels_one[first],), (labels_one[second],)),
        rationale="The first is grounded more completely.",
    )
    run_two = create_run(
        task=task,
        runner={"type": "Preview.Ranking.Task.Runner"},
        repository_root="/tmp/scoring",
        seed="two",
    )
    result_two = create_result(
        run=run_two,
        tiers=(tuple(run_two["labels"]),),
        rationale="Equivalent support.",
    )
    definition = builtin_score_definition()
    score = compute_win_rate_score(
        pool=pool,
        definition=definition,
        results=(result_one, result_two),
    )

    assert result_one["type"] == RESULT_TYPE
    assert result_one["tiers"] == [[first], [second]]
    assert score["result_ids"] == [result_one["id"], result_two["id"]]
    standings = {item["candidate_id"]: item for item in score["standings"]}
    assert standings[first]["value"] == pytest.approx(0.75)
    assert standings[second]["value"] == pytest.approx(0.25)

    with pytest.raises(ScoringError, match="every presented label"):
        create_result(run=run_one, tiers=((labels_one[first],),))
    with pytest.raises(ScoringError, match="no longer accepts"):
        create_result(
            run={**run_one, "status": "Exited.Without.Result"},
            tiers=(tuple(run_one["labels"]),),
        )


def test_cli_preview_submit_score_and_debug_surfaces(tmp_path: Path, capsys) -> None:
    root = tmp_path / "scoring"
    assert main(["scoring", "init", "--root", str(root)]) == 0
    repository = ScoringRepository(root).open()
    pool, task, _, _ = _task()
    repository.create(pool)
    repository.create(task)

    assert main(["scoring", "render", task["id"][:10], "--root", str(root)]) == 0
    assert "# Ranking Task" in capsys.readouterr().out
    assert (
        main(
            [
                "scoring",
                "run",
                task["id"],
                "--root",
                str(root),
                "--preview",
                "--seed",
                "cli-test",
            ]
        )
        == 0
    )
    preview = capsys.readouterr().out
    run_id = preview.splitlines()[0].split(": ", 1)[1]
    run = repository.resolve(run_id)
    labels = list(run["labels"])
    assert main(
        [
            "scoring",
            "submit",
            run_id,
            "--root",
            str(root),
            "--tier",
            labels[0],
            "--tier",
            labels[1],
            "--rationale",
            "First is stronger.",
        ]
    ) == 0
    capsys.readouterr()
    assert main(["scoring", "score", pool["id"], "--root", str(root)]) == 0
    assert "results: 1" in capsys.readouterr().out
    assert main(["scoring", "show", run_id[:10], "--root", str(root)]) == 0
    assert '"rendered_prompt"' in capsys.readouterr().out


def test_runtime_exposes_scoring_and_retires_tournament() -> None:
    from tarav.cli.cli import build_parser

    command_action = next(
        action
        for action in build_parser()._actions
        if getattr(action, "dest", None) == "command"
    )
    assert "scoring" in command_action.choices
    assert "tournament" not in command_action.choices


def test_agent_runner_retains_resolved_provenance_and_submitted_result(
    tmp_path: Path, monkeypatch
) -> None:
    from tarav.agent.run_runtime import AgentRunResult

    repository = ScoringRepository.initialize(tmp_path / "scoring")
    pool, task, _, _ = _task()
    repository.create(pool)
    repository.create(task)
    run = prepare_run(
        repository=repository,
        task=task,
        provider="fake",
        profile=None,
        home=tmp_path / "agent-home",
        model="judge-v1",
        account="judge-account",
        cwd=tmp_path,
        seed="runner-test",
        preview=False,
    )

    class FakeAgent:
        provider = "fake"
        profile_id = None
        home = tmp_path / "agent-home"
        default_model = "default-judge"
        account = None

        def run(self, command_config, run_config):
            assert command_config.prompt == run["rendered_prompt"]
            assert command_config.interaction_mode == "non_interactive"
            assert run_config.process_mode == "capture"
            repository.create(
                create_result(run=run, tiers=tuple((label,) for label in run["labels"]))
            )
            return AgentRunResult(exit_code=0, stdout="submitted", stderr="")

    monkeypatch.setattr("tarav.scoring.runner.resolve_agent", lambda **_: FakeAgent())

    completed, result = execute_run(
        repository=repository,
        run=run,
        timeout_sec=10,
    )

    assert completed["status"] == "Completed"
    assert completed["runner"]["resolved_provider"] == "fake"
    assert completed["runner"]["resolved_model"] == "judge-v1"
    assert completed["execution"]["result_id"] == result["id"]


def test_grounding_task_resolves_diagram_line_editions_and_support(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    initialize_project_layout(project_root)
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "diagram")
    model = namespace.create_model(label="Tarav")
    config = DiagramConfiguration.load(tmp_path / "diagram.json", create=True).mount(
        namespace, default=True
    )
    config.diagram().set_project_main_model(project_root, model.ship)
    block_ship = str(uuid4())
    user_ref = {
        "session_identity": "a" * 64,
        "turn_address": "1" * 64,
        "turn_hash": "2" * 64,
    }
    agent_ref = {
        "session_identity": "a" * 64,
        "turn_address": "5" * 64,
        "turn_hash": "6" * 64,
    }
    block = ShipDraft(
        block_ship,
        {
            "type": BLOCK_SHIP_TYPE,
            "model_ship": model.ship,
            "editions": [
                {
                    "id": str(uuid4()),
                    "block_type": DESIGN_BLOCK_OBJECT_TYPE,
                    "data": {"label": "Scoring"},
                }
            ],
        },
    )
    lines = []
    line_ids = []
    for text in ("Results are evidence.", "Scores interpret Results."):
        line_ship = str(uuid4())
        line_ids.append(line_ship)
        lines.append(
            ShipDraft(
                line_ship,
                {
                    "type": LINE_SHIP_TYPE,
                    "model_ship": model.ship,
                    "block_ship": block_ship,
                    "editions": [
                        {
                            "id": str(uuid4()),
                            "line_type": DESIGN_LINE_PRINCIPLE_TYPE,
                            "producer": agent_ref,
                            "support": [{"root": user_ref, "neighborhood": []}],
                            "data": {"text": text},
                        }
                    ],
                },
            )
        )
    namespace.apply(CaptureManifest(model.ship, (block, *lines)), commit=False)
    normal_model = {
        "session": {"identity_hash": "a" * 64, "session_id": "session"},
        "events": [],
        "messages": [
            {
                "message_address": "3" * 64,
                "message_hash": "4" * 64,
                "side": "user",
                "text": "Keep ranking evidence separate from scores.",
            }
        ],
        "turns": [
            {
                **user_ref,
                "side": "user",
                "message_refs": [
                    {"message_address": "3" * 64, "message_hash": "4" * 64}
                ],
                "event_refs": [],
            }
        ],
    }
    task = create_line_grounding_task(
        pool=create_pool("grounding"),
        project_path=project_root,
        line_ships=line_ids,
        diagram_config=config.path,
        evidence=ChatlasEvidence(model_loader=lambda _: normal_model),
    )

    assert task["type"] == GROUNDING_TASK_TYPE
    assert "Block: Scoring" in task["candidates"][0]["presentation"]
    assert "Keep ranking evidence separate from scores." in task["candidates"][0]["presentation"]
    assert task["candidates"][0]["assertion"]["subject"]["line_ship"] == line_ids[0]
