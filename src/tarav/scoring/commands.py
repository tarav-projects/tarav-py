"""Compact public CLI for Ranking evidence and derived Assertion scores."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tarav._core.errors import CliError

from .model import (
    GROUNDING_ASSERTION_TYPE,
    GROUNDING_TASK_TYPE,
    POOL_TYPE,
    RESULT_TYPE,
    RUN_TYPE,
    SCORE_COMPUTATION_TYPE,
    SCORE_DEFINITION_TYPE,
    ScoringError,
    builtin_score_definition,
    compute_win_rate_score,
    create_pool,
    create_result,
    render_task,
)
from .repository import ScoringRepository, default_scoring_root
from .runner import execute_run, prepare_run
from .tasks import create_line_grounding_task


LIST_TYPES = {
    "pools": POOL_TYPE,
    "tasks": GROUNDING_TASK_TYPE,
    "runs": RUN_TYPE,
    "results": RESULT_TYPE,
    "definitions": SCORE_DEFINITION_TYPE,
    "scores": SCORE_COMPUTATION_TYPE,
}


def _root(args: argparse.Namespace) -> Path:
    return (
        Path(args.root).expanduser().resolve()
        if args.root is not None
        else default_scoring_root()
    )


def _repository(args: argparse.Namespace) -> ScoringRepository:
    return ScoringRepository(_root(args)).open()


def _emit(args: argparse.Namespace, payload: object, lines: list[str]) -> int:
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print("\n".join(lines))
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    try:
        repository = ScoringRepository.initialize(_root(args))
    except ScoringError as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {
            "status": "ok",
            "repository": str(repository.root),
            "git_head": repository.head(),
        },
        [f"scoring repository: {repository.root}", f"git: {repository.head()}"],
    )


def _cmd_pool(args: argparse.Namespace) -> int:
    try:
        repository = _repository(args)
        record = repository.create(create_pool(args.name, args.assertion_type))
    except ScoringError as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        record,
        [
            f"pool: {record['id']}",
            f"selector: {record['selector']['type']}",
            f"assertion: {record['selector']['assertion_type']}",
        ],
    )


def _cmd_task(args: argparse.Namespace) -> int:
    try:
        repository = _repository(args)
        pool = repository.resolve(args.pool, record_type=POOL_TYPE)
        task = create_line_grounding_task(
            pool=pool,
            project_path=Path(args.project),
            line_ships=args.line,
            diagram_config=Path(args.diagram_config).expanduser().resolve()
            if args.diagram_config
            else None,
            chatlas_root=Path(args.chatlas_root).expanduser().resolve()
            if args.chatlas_root
            else None,
            appendix=args.appendix,
        )
        repository.create(task)
    except (ScoringError, CliError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        task,
        [f"task: {task['id']}", f"candidates: {len(task['candidates'])}"],
    )


def _cmd_render(args: argparse.Namespace) -> int:
    try:
        record = _repository(args).resolve(args.record)
        if record["type"] == GROUNDING_TASK_TYPE:
            labels = {
                chr(ord("A") + index): candidate["id"]
                for index, candidate in enumerate(record["candidates"])
            }
            rendered = render_task(record, labels)
        elif record["type"] == RUN_TYPE:
            rendered = str(record["rendered_prompt"])
        else:
            raise ScoringError("render accepts a Ranking Task or Ranking Run")
    except ScoringError as exc:
        raise CliError(str(exc)) from exc
    if args.json:
        return _emit(args, {"record": record, "rendered": rendered}, [])
    print(rendered)
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        repository = _repository(args)
        task = repository.resolve(args.task, record_type=GROUNDING_TASK_TYPE)
        run = prepare_run(
            repository=repository,
            task=task,
            provider=args.provider,
            profile=args.profile,
            home=Path(args.home).expanduser().resolve() if args.home else None,
            model=args.model,
            account=args.account,
            cwd=Path(args.cwd).expanduser().resolve(),
            seed=args.seed,
            preview=args.preview,
        )
        if args.preview:
            if args.json:
                return _emit(args, run, [])
            print(f"run: {run['id']}\n")
            print(run["rendered_prompt"])
            return 0
        completed, result = execute_run(
            repository=repository,
            run=run,
            timeout_sec=args.timeout,
        )
    except (ScoringError, CliError) as exc:
        raise CliError(str(exc)) from exc
    payload = {"run": completed, "result": result}
    lines = [f"run: {completed['id']}", f"status: {completed['status']}"]
    if result is not None:
        lines.append(f"result: {result['id']}")
    _emit(args, payload, lines)
    return 0 if completed["status"] == "Completed" else 1


def _parse_tiers(values: list[str]) -> list[list[str]]:
    tiers = [
        [label.strip() for label in value.split(",") if label.strip()]
        for value in values
    ]
    if any(not tier for tier in tiers):
        raise ScoringError("--tier cannot be empty")
    return tiers


def _cmd_submit(args: argparse.Namespace) -> int:
    try:
        if args.abstain and not args.reason:
            raise ScoringError("--abstain requires --reason")
        if args.reason and not args.abstain:
            raise ScoringError("--reason requires --abstain")
        repository = _repository(args)
        run = repository.resolve(args.run, record_type=RUN_TYPE)
        if repository.result_for_run(str(run["id"])) is not None:
            raise ScoringError(f"Ranking Run already has a Result: {run['id']}")
        result = create_result(
            run=run,
            tiers=_parse_tiers(args.tier),
            rationale=args.rationale,
            abstain_reason=args.reason if args.abstain else None,
        )
        repository.create(result)
    except ScoringError as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        result,
        [f"result: {result['id']}", f"outcome: {result['outcome']}"],
    )


def _cmd_score(args: argparse.Namespace) -> int:
    try:
        repository = _repository(args)
        pool = repository.resolve(args.pool, record_type=POOL_TYPE)
        definitions = [
            item
            for item in repository.records(SCORE_DEFINITION_TYPE)
            if item.get("name") == args.name
        ]
        if len(definitions) > 1:
            raise ScoringError(f"Score Definition name is ambiguous: {args.name}")
        if definitions:
            definition = definitions[0]
        else:
            definition = builtin_score_definition()
            if definition["name"] != args.name:
                raise ScoringError(f"unknown Score Definition: {args.name}")
            repository.create(definition)
        score = compute_win_rate_score(
            definition=definition,
            observations=tuple(
                (
                    result,
                    repository.resolve_reference(result["run_ref"]),
                )
                for result in repository.results_for_pool(pool)
            ),
        )
        repository.create(score)
    except ScoringError as exc:
        raise CliError(str(exc)) from exc
    lines = [
        f"score: {score['id']}",
        f"definition: {definition['name']}",
        f"results: {score['result_count']} (+ {score['abstention_count']} abstentions)",
    ]
    lines.extend(
        f"{item['value']:.3f}\t{item['candidate_id']}\t{item['comparisons']} comparisons"
        for item in score["standings"]
        if item["value"] is not None
    )
    return _emit(args, score, lines)


def _cmd_list(args: argparse.Namespace) -> int:
    try:
        repository = _repository(args)
        records = repository.records(LIST_TYPES[args.kind])
    except ScoringError as exc:
        raise CliError(str(exc)) from exc
    lines = [
        "\t".join(
            (
                str(record["id"]),
                str(record["type"]),
                str(record.get("name") or record.get("status") or ""),
            )
        )
        for record in records
    ]
    return _emit(
        args,
        {"kind": args.kind, "count": len(records), "records": records},
        lines,
    )


def _cmd_show(args: argparse.Namespace) -> int:
    try:
        repository = _repository(args)
        record = repository.resolve(args.record)
        trace = repository.trace(record) if args.trace else None
    except ScoringError as exc:
        raise CliError(str(exc)) from exc
    payload = {
        "record": record,
        "path": str(repository.path_for(record)),
        "git_head": repository.head(),
    }
    if trace is not None:
        payload["trace"] = trace
    return _emit(
        args,
        payload,
        [
            json.dumps(
                trace if trace is not None else record,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
        ],
    )


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        help="Scoring repository; defaults to ~/Documents/tarav/scoring/.",
    )
    parser.add_argument("--json", action="store_true", help="Print structured JSON.")


def register_scoring_commands(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "scoring",
        help="Accumulate Ranking evidence and compute named Assertion scores.",
    )
    commands = parser.add_subparsers(dest="scoring_command", required=True)

    init = commands.add_parser(
        "init", help="Initialize the Git-backed Record repository."
    )
    _add_common(init)
    init.set_defaults(handler=_cmd_init)

    pool = commands.add_parser("pool", help="Create a typed Assertion selector Pool.")
    pool.add_argument("name")
    pool.add_argument("--assertion-type", default=GROUNDING_ASSERTION_TYPE)
    _add_common(pool)
    pool.set_defaults(handler=_cmd_pool)

    task = commands.add_parser(
        "task", help="Create an Index.Line grounding Ranking Task."
    )
    task.add_argument("--pool", required=True)
    task.add_argument("--project", default=".")
    task.add_argument(
        "--line",
        action="append",
        required=True,
        help="Line Ship UUID; repeat for candidates.",
    )
    task.add_argument("--appendix", action="append", default=[])
    task.add_argument("--diagram-config")
    task.add_argument("--chatlas-root")
    _add_common(task)
    task.set_defaults(handler=_cmd_task)

    render = commands.add_parser(
        "render", help="Render a Task or exact Run prompt for inspection."
    )
    render.add_argument("record", help="Task/Run UUID or unambiguous prefix.")
    _add_common(render)
    render.set_defaults(handler=_cmd_render)

    run = commands.add_parser(
        "run", help="Create a blinded Run and optionally execute its Agent runner."
    )
    run.add_argument("task")
    run.add_argument("--provider")
    run.add_argument("--profile")
    run.add_argument("--home")
    run.add_argument("--model")
    run.add_argument("--account")
    run.add_argument("--cwd", default=".")
    run.add_argument("--timeout", type=int)
    run.add_argument("--seed", help="Reproducible candidate-order seed.")
    run.add_argument(
        "--preview",
        action="store_true",
        help="Retain and print the exact Run without invoking an Agent.",
    )
    _add_common(run)
    run.set_defaults(handler=_cmd_run)

    submit = commands.add_parser(
        "submit", help="Submit one structured Result for a Run."
    )
    submit.add_argument("run")
    submit.add_argument(
        "--tier",
        action="append",
        default=[],
        help="One rank tier; use A,B for a tie. Repeat in best-first order.",
    )
    submit.add_argument("--rationale")
    submit.add_argument("--abstain", action="store_true")
    submit.add_argument("--reason")
    _add_common(submit)
    submit.set_defaults(handler=_cmd_submit)

    score = commands.add_parser(
        "score", help="Compute and retain a named score over one pool's Results."
    )
    score.add_argument("pool")
    score.add_argument("--name", default="Assertion.Ranking.WinRate.Score.v1")
    _add_common(score)
    score.set_defaults(handler=_cmd_score)

    listing = commands.add_parser("list", help="List one kind of scoring Record.")
    listing.add_argument("kind", choices=tuple(LIST_TYPES))
    _add_common(listing)
    listing.set_defaults(handler=_cmd_list)

    show = commands.add_parser(
        "show", help="Show a scoring Record and optionally trace its dependencies."
    )
    show.add_argument("record")
    show.add_argument(
        "--trace",
        action="store_true",
        help="Follow direct scoring Record references and expose external references.",
    )
    _add_common(show)
    show.set_defaults(handler=_cmd_show)


__all__ = ["register_scoring_commands"]
