"""Compact public CLI for Ranking evidence and derived Assertion scores."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tarav._core.errors import CliError

from .model import (
    GROUNDING_POOL_CLASS,
    GROUNDING_TASK_TYPE,
    POOL_ENROLLMENT_TYPE,
    POOL_TYPE,
    RESULT_TYPE,
    RUN_TYPE,
    SCORING_EVENT_TYPE,
    SCORING_TRACE_TYPE,
    WIN_RATE_SCORE,
    ScoringError,
    compute_win_rate_scores,
    create_pool,
    create_result,
    create_scoring_event,
    create_scoring_trace,
    render_run,
    render_task,
)
from .rendering import (
    CURRENT_SCORE_RENDERER,
    RENDERERS,
    TRACE_EVOLUTION_RENDERER,
    TRACE_HISTORY_RENDERER,
    render_current_scores,
    render_trace_evolution,
    render_trace_history,
)
from .repository import ScoringRepository, default_scoring_root
from .runner import code_provenance, execute_run, prepare_agent_run, prepare_unknown_run
from .tasks import (
    create_line_grounding_enrollments,
    create_line_grounding_task,
    line_grounding_assertion_references,
)


LIST_TYPES = {
    "pools": POOL_TYPE,
    "enrollments": POOL_ENROLLMENT_TYPE,
    "tasks": GROUNDING_TASK_TYPE,
    "runs": RUN_TYPE,
    "results": RESULT_TYPE,
    "traces": SCORING_TRACE_TYPE,
    "events": SCORING_EVENT_TYPE,
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


def _cmd_pool_create(args: argparse.Namespace) -> int:
    try:
        repository = _repository(args)
        if any(item.get("name") == args.name for item in repository.records(POOL_TYPE)):
            raise ScoringError(f"Assertion Pool name already exists: {args.name}")
        record = repository.create(create_pool(args.name, args.pool_class))
    except ScoringError as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        record,
        [
            f"pool: {record['id']}",
            f"name: {record['name']}",
            f"class: {record['pool_class']}",
        ],
    )


def _cmd_pool_enroll(args: argparse.Namespace) -> int:
    try:
        repository = _repository(args)
        pool = repository.resolve(args.pool, record_type=POOL_TYPE)
        candidates = create_line_grounding_enrollments(
            pool=pool,
            project_path=Path(args.project),
            line_ships=args.line,
            diagram_config=Path(args.diagram_config).expanduser().resolve()
            if args.diagram_config
            else None,
        )
        assertion_keys = [
            json.dumps(item["assertion_ref"], sort_keys=True) for item in candidates
        ]
        if len(assertion_keys) != len(set(assertion_keys)):
            raise ScoringError("one enrollment request repeats an Assertion instance")
        for candidate in candidates:
            existing = repository.enrollment_for_assertion(
                pool=pool, assertion_ref=candidate["assertion_ref"]
            )
            if existing is not None:
                raise ScoringError(
                    f"Assertion is already enrolled in Pool: {existing['id']}"
                )
        enrollments = [repository.create(candidate) for candidate in candidates]
    except ScoringError as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {"pool": pool, "enrollments": enrollments},
        [f"pool: {pool['id']}"] + [f"enrollment: {item['id']}" for item in enrollments],
    )


def _cmd_pool_show(args: argparse.Namespace) -> int:
    try:
        repository = _repository(args)
        pool = repository.resolve(args.pool, record_type=POOL_TYPE)
        enrollments = repository.enrollments_for_pool(pool)
    except ScoringError as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {"pool": pool, "enrollments": enrollments},
        [
            f"pool: {pool['id']}",
            f"name: {pool['name']}",
            f"class: {pool['pool_class']}",
            f"enrollments: {len(enrollments)}",
        ],
    )


def _create_pool_task(
    args: argparse.Namespace,
    repository: ScoringRepository,
    pool: dict[str, object],
) -> dict[str, object]:
    enrollments = repository.enrollments_for_pool(pool)
    task = create_line_grounding_task(
        pool=pool,
        enrollments=enrollments,
        project_path=Path(args.project),
        diagram_config=Path(args.diagram_config).expanduser().resolve()
        if args.diagram_config
        else None,
        chatlas_root=Path(args.chatlas_root).expanduser().resolve()
        if args.chatlas_root
        else None,
        appendix=args.appendix,
    )
    return repository.create(task)


def _cmd_task(args: argparse.Namespace) -> int:
    try:
        repository = _repository(args)
        pool = repository.resolve(args.pool, record_type=POOL_TYPE)
        task = _create_pool_task(args, repository, pool)
        run, prompt = prepare_unknown_run(
            repository=repository,
            task=task,
            seed=args.seed,
        )
    except (ScoringError, CliError) as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        {"task": task, "run": run, "rendered_prompt": prompt},
        [
            f"task: {task['id']}",
            f"run: {run['id']}",
            f"candidates: {len(task['candidates'])}",
            "",
            prompt,
        ],
    )


def _cmd_pool_run(args: argparse.Namespace) -> int:
    """Create one exact Pool Task and pass it to the generic Runner."""

    try:
        repository = _repository(args)
        pool = repository.resolve(args.pool, record_type=POOL_TYPE)
        task = _create_pool_task(args, repository, pool)
        run, _ = prepare_agent_run(
            repository=repository,
            task=task,
            provider=args.provider,
            profile=args.profile,
            home=Path(args.home).expanduser().resolve() if args.home else None,
            model=args.model,
            account=args.account,
            cwd=Path(args.cwd).expanduser().resolve(),
            seed=args.seed,
        )
        completed, result = execute_run(
            repository=repository,
            run=run,
            timeout_sec=args.timeout,
        )
    except (ScoringError, CliError) as exc:
        raise CliError(str(exc)) from exc
    payload = {"pool": pool, "task": task, "run": completed, "result": result}
    lines = [
        f"pool: {pool['id']}",
        f"task: {task['id']}",
        f"run: {completed['id']}",
        f"status: {completed['status']}",
    ]
    if result is not None:
        lines.append(f"result: {result['id']}")
    _emit(args, payload, lines)
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    try:
        repository = _repository(args)
        record = repository.resolve(args.record)
        if record["type"] == GROUNDING_TASK_TYPE:
            labels = {
                chr(ord("A") + index): candidate["id"]
                for index, candidate in enumerate(record["candidates"])
            }
            rendered = render_task(record, labels)
        elif record["type"] == RUN_TYPE:
            task = repository.resolve_reference(record["task_ref"])
            rendered = render_run(
                task=task,
                run=record,
            )
        elif record["type"] == SCORING_TRACE_TYPE:
            renderer = args.renderer or TRACE_HISTORY_RENDERER
            events = repository.events_for_trace(record)
            if renderer == TRACE_HISTORY_RENDERER:
                rendered = render_trace_history(record, events)
            elif renderer == TRACE_EVOLUTION_RENDERER:
                rendered = render_trace_evolution(record, events)
            else:
                raise ScoringError(
                    f"renderer does not accept a scoring Trace: {renderer}"
                )
        else:
            raise ScoringError("render accepts a Ranking Task, Run, or scoring Trace")
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
        run, _ = prepare_agent_run(
            repository=repository,
            task=task,
            provider=args.provider,
            profile=args.profile,
            home=Path(args.home).expanduser().resolve() if args.home else None,
            model=args.model,
            account=args.account,
            cwd=Path(args.cwd).expanduser().resolve(),
            seed=args.seed,
        )
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
    return 0


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
        if args.method != WIN_RATE_SCORE:
            raise ScoringError(f"unknown Score method: {args.method}")
        pools = [
            repository.resolve(selector, record_type=POOL_TYPE)
            for selector in args.pool
        ]
        results = repository.results_for_pools(pools)
        results_commit = repository.head()
        scores = compute_win_rate_scores(
            observations=repository.ranking_observations(results),
        )
        if not scores:
            raise ScoringError("selected Pools have no scoreable Ranking Results")
        events = []
        traces = []
        if not args.no_record:
            provenance = code_provenance()
            for score in scores:
                assertion_ref = score["assertion_ref"]
                trace = repository.scoring_trace_for_assertion(assertion_ref)
                if trace is None:
                    trace = repository.create(create_scoring_trace(assertion_ref))
                event = repository.append_event(
                    create_scoring_event(
                        trace=trace,
                        score=score,
                        pool_ids=[str(pool["id"]) for pool in pools],
                        results_commit=results_commit,
                        code_provenance=provenance,
                    )
                )
                traces.append(trace)
                events.append(event)
    except ScoringError as exc:
        raise CliError(str(exc)) from exc
    rendered = render_current_scores(scores)
    payload = {
        "renderer": args.renderer,
        "method": args.method,
        "pool_ids": [pool["id"] for pool in pools],
        "results_commit": results_commit,
        "scores": scores,
        "recorded": not args.no_record,
        "traces": traces,
        "events": events,
    }
    return _emit(args, payload, rendered.splitlines())


def _cmd_assertion(args: argparse.Namespace) -> int:
    try:
        repository = _repository(args)
        references = line_grounding_assertion_references(
            project_path=Path(args.project),
            line_ships=[args.line],
            diagram_config=Path(args.diagram_config).expanduser().resolve()
            if args.diagram_config
            else None,
        )
        trace = repository.trace_reference(references[0])
    except ScoringError as exc:
        raise CliError(str(exc)) from exc
    return _emit(
        args,
        trace,
        [json.dumps(trace, indent=2, ensure_ascii=False, sort_keys=True)],
    )


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

    pool = commands.add_parser("pool", help="Manage explicit Assertion populations.")
    pool_commands = pool.add_subparsers(dest="pool_command", required=True)

    pool_create = pool_commands.add_parser("create", help="Create a named Pool.")
    pool_create.add_argument("name")
    pool_create.add_argument("--pool-class", default=GROUNDING_POOL_CLASS)
    _add_common(pool_create)
    pool_create.set_defaults(handler=_cmd_pool_create)

    pool_enroll = pool_commands.add_parser(
        "enroll", help="Explicitly enroll Assertion instances in a Pool."
    )
    pool_enroll.add_argument("pool")
    pool_enroll.add_argument("--project", default=".")
    pool_enroll.add_argument(
        "--line", action="append", required=True, help="Line Ship UUID; repeatable."
    )
    pool_enroll.add_argument("--diagram-config")
    _add_common(pool_enroll)
    pool_enroll.set_defaults(handler=_cmd_pool_enroll)

    pool_show = pool_commands.add_parser(
        "show", help="Show a Pool and its explicit enrollments."
    )
    pool_show.add_argument("pool")
    _add_common(pool_show)
    pool_show.set_defaults(handler=_cmd_pool_show)

    pool_run = pool_commands.add_parser(
        "run", help="Create a Task from enrolled Assertions and run it."
    )
    pool_run.add_argument("pool")
    pool_run.add_argument("--project", default=".")
    pool_run.add_argument("--appendix", action="append", default=[])
    pool_run.add_argument("--diagram-config")
    pool_run.add_argument("--chatlas-root")
    pool_run.add_argument("--provider")
    pool_run.add_argument("--profile")
    pool_run.add_argument("--home")
    pool_run.add_argument("--model")
    pool_run.add_argument("--account")
    pool_run.add_argument("--cwd", default=".")
    pool_run.add_argument("--timeout", type=int)
    pool_run.add_argument("--seed")
    _add_common(pool_run)
    pool_run.set_defaults(handler=_cmd_pool_run)

    task = commands.add_parser(
        "task", help="Create an Index.Line grounding Ranking Task."
    )
    task.add_argument("--pool", required=True)
    task.add_argument("--project", default=".")
    task.add_argument("--appendix", action="append", default=[])
    task.add_argument("--diagram-config")
    task.add_argument("--chatlas-root")
    task.add_argument("--seed", help="Reproducible candidate-order seed.")
    _add_common(task)
    task.set_defaults(handler=_cmd_task)

    render = commands.add_parser(
        "render", help="Render a Task, exact Run prompt, or scoring Trace."
    )
    render.add_argument("record", help="Task/Run UUID or unambiguous prefix.")
    render.add_argument("--renderer", choices=RENDERERS)
    _add_common(render)
    render.set_defaults(handler=_cmd_render)

    run = commands.add_parser(
        "run", help="Create a frozen blinded Run and execute its Agent runner."
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
        "score", help="Compute live Assertion Scores over selected Pool Results."
    )
    score.add_argument("--pool", action="append", required=True)
    score.add_argument("--method", default=WIN_RATE_SCORE)
    score.add_argument(
        "--renderer",
        choices=(CURRENT_SCORE_RENDERER,),
        default=CURRENT_SCORE_RENDERER,
    )
    score.add_argument(
        "--no-record",
        action="store_true",
        help="Compute read-only without appending scoring Trace events.",
    )
    _add_common(score)
    score.set_defaults(handler=_cmd_score)

    assertion = commands.add_parser(
        "assertion", help="Trace scoring data around one Line Assertion instance."
    )
    assertion.add_argument("--project", default=".")
    assertion.add_argument("--line", required=True)
    assertion.add_argument("--diagram-config")
    _add_common(assertion)
    assertion.set_defaults(handler=_cmd_assertion)

    listing = commands.add_parser("list", help="List one kind of scoring Record.")
    listing.add_argument("kind", choices=tuple(LIST_TYPES))
    _add_common(listing)
    listing.set_defaults(handler=_cmd_list)

    show = commands.add_parser(
        "show", help="Show a scoring Record and optionally trace its connected records."
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
