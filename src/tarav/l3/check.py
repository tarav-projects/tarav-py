"""Project checks CLI: run a Project's checks namespace in its harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l1.checks import CheckResult
from tarav.l1.poi.rendering import (
    DEFAULT_POI_RENDERER, POISelection, renderer, renderers,
)


# tarav.breadcrumb a671fcec806bcecf6adccaf70a7f2c991f04b2685ea24f7056aa3cf53f820f8e
# tarav.breadcrumb 31d6a87727d93d79dc92f3804e9916b37f4a8d7639862d3ef2fe9144dc778ee1
def report_project_checks(
    project, *, json_output: bool = False, by: str = "type", sort: str = "run",
    limit: int = 20, offset: int = 0, poi_type: str | None = None,
    check: str | None = None, renderer_name: str = DEFAULT_POI_RENDERER,
    level: str = "line", actions: str = "write",
) -> int:
    """Run a Project's suite and show a bounded grouped report."""
    def progress(result: CheckResult) -> None:
        if sys.stderr.isatty():
            print(f"{type(result.check).__name__}: {result.status}", file=sys.stderr,
                  flush=True)

    try:
        run = _retained(project, project.checks.run(on_result=progress))
        # tarav.breadcrumb ad61e17278a7f87bdbe6bba00b7195dd5389a8f9423618314b32ae8fa446c9e2
    except NotImplementedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    acted = _acted(project, run) if actions == "write" else None
    settled = _poi_actions()
    report = run.report(by=by, sort=sort, limit=limit, offset=offset, type=poi_type,
                        check=check, detail=level == "record", actions=settled)
    if json_output:
        print(json.dumps({**report, "actions": acted}, indent=2, default=str))
    else:
        print(renderer(renderer_name).render(POISelection.from_check_report(report), level=level))
        if acted is not None:
            print(_actions_text(acted))
    return 0 if run.clean(actions=settled) else 1


def _code(args: argparse.Namespace) -> str:
    options = {
        "json_output": args.json, "by": args.by, "sort": args.sort,
        "limit": args.limit, "offset": args.offset, "poi_type": args.poi_type,
        "check": args.check_type, "renderer_name": args.renderer, "level": args.level,
        "actions": args.actions,
    }
    return (
        "from tarav.l3.check import report_project_checks\n"
        f"raise SystemExit(report_project_checks(project, **{options!r}))\n"
    )


# tarav.breadcrumb 1778a37c1707becb0bed583cc5d2ee8f8a4b3047975fb3b90d1c61a0a8065481
def _check(args: argparse.Namespace) -> int:
    if args.project is None:
        raise CliError("tarav check needs --project [PATH]")
    from tarav.l3.project.harness import run

    return run(path=args.project, code=_code(args))


def register_check_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "check",
        help="Run a Project's checks (its checks() method) in its harness.",
        epilog=(
            "examples:\n"
            "  tarav check --project\n"
            "  tarav check --project /path/to/project --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--project",
        type=Path,
        nargs="?",
        const=Path("."),
        help="Search this directory and parents for a Project; optionally start at PATH.",
    )
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    parser.add_argument("--by", choices=("type", "check", "identity"),
                        default="type", help="Group POIs by this field (default: type).")
    parser.add_argument("--sort", choices=("run", "count"), default="run",
                        help="Sort groups by first occurrence or descending count.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum groups to show.")
    parser.add_argument("--offset", type=int, default=0, help="First group to show.")
    # tarav.breadcrumb 1c56bfc2a3f025dba4e39391246e2c9ff6b82badb41849082dabe55687cf7e92
    parser.add_argument("--type", dest="poi_type", help="Show this POI Type and its subtypes.")
    parser.add_argument("--check", dest="check_type", help="Filter by exact Check Type name.")
    parser.add_argument("--renderer", choices=tuple(item.name for item in renderers()),
                        default=DEFAULT_POI_RENDERER, help="Named POI renderer.")
    parser.add_argument("--level", choices=("line", "record", "context"), default="line",
                        help="POI detail level for rendered output.")
    parser.add_argument("--actions", choices=("write", "skip"), default="write",
                        help="Resolve each Project's actions from this run of its suite: "
                             "open the action of each new POI and close those no longer "
                             "produced, or leave the actions untouched.")
    parser.set_defaults(handler=_check)


def _retained(project, run):
    """Keep the reported POIs so `tarav context --id` can open them afterwards."""
    from tarav.l1.poi.reporting import ReportedPOIStore

    try:
        identity = {"id": str(project.id), "name": project.name, "root": str(project.root)}
    except Exception:
        return run
    ReportedPOIStore().retain(run.pois(), project=identity)
    return run


def _poi_actions():
    """The Actions workflow as a reader of blessings. None when it cannot be read."""
    try:
        from tarav.l1.actions.pois import POIActions

        return POIActions()
    except Exception:
        return None


# tarav.breadcrumb 34c9e2e74fe85182ac56b7d7c1f9d8c1c2ec324bd808ac782fe4a82d6c6e4478
# tarav.breadcrumb a5d57389a476154c5cd14d1c4942ff6d44660890e394ffada41543e0dfe9ce22
# tarav.breadcrumb ed537ee28f417d13c7f74cb132e59c85d763dd12e9fb52fc5b6e835e0250b24e
def _acted(project, run) -> dict[str, object] | None:
    """Resolve the Projects' actions from this run; a failure there never fails the check.

    The checks only produced POIs. The run knows which Project's suite each
    result came from, and each Project's actions are resolved from its own
    results.
    """
    try:
        from tarav.l1.actions.pois import POIActions

        result = POIActions().resolve(run)
        return {**{key: value for key, value in result.items() if key != "signals"},
                "closed": [signal.as_dict(detail=True) for signal in result["signals"]]}
    except Exception as exc:
        print(f"POI actions were not updated: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None


def _actions_text(acted: dict[str, object]) -> str:
    lines = [f"POI actions: {acted['actions']} raised now in {len(acted['projects'])} "
             f"Project(s); {acted['opened']} opened, "
             f"{acted['reopened']} reopened, {acted['gone']} closed as gone. "
             "List them with `tarav action list --project`."]
    lines.extend(f"  gone: {signal['message']}" for signal in acted["closed"])
    return "\n".join(lines)


__all__ = ["register_check_command", "report_project_checks"]
