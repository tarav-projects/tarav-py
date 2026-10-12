"""Project status CLI: what is open in a Project, and what the last run changed.

The Project does the work: it runs its checks and hands the results to its
actions. This module builds one result from that and presents it, readable by
default and in full with `--json`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

from tarav.l0.kernel import entity
from tarav.l1.checks import routine
from tarav.l1.poi.rendering import check_header

from .check import Progress, _retained, in_harness

LISTED = {"opened": "opened", "reopened": "reopened", "gone": "gone"}
COUNTED = (("opened", "opened"), ("reopened", "reopened"), ("gone", "closed as gone"))


def _short(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def _kinds(names: Counter) -> dict[str, int]:
    """Counts under the last part of each Type name, the full name where two would collide."""
    short = Counter(_short(name) for name in names)
    return {(_short(name) if short[_short(name)] == 1 else name): count
            for name, count in names.most_common()}


# tarav.context abd0372d:0c49207898a3b796
def status_result(status) -> dict:
    """One result for both presentations: the open actions, the changes, the checks."""
    from tarav.l1.actions import RUNNING
    from tarav.l1.actions.blessing import BLESSED
    from tarav.l1.actions.pois import POIActions

    suite = status.suite()
    acted = status.acted()
    standing = POIActions().standing
    projects = []
    for found in status.each():
        runs = found.project.actions.list()
        kinds = Counter(((run.data.get("event") or {}).get("poi") or {}).get("type")
                        or run.data["action"] for run in runs if run.state == RUNNING)
        projects.append({
            "name": found.project.name, "root": str(found.project.root),
            "open": sum(kinds.values()), "by_type": dict(kinds.most_common()),
            "blessed": sum(1 for run in runs if run.exit == BLESSED
                           and (run.data.get("situation") or {}).get("state") == "present"),
        })
    summary = suite.summary()
    # a suite that was left out is named with the Project it belongs to
    summary["not_run"] = [
        {**item, "project": found.project.name,
         "name": f"{item['name'] or _short(item['type'] or '?')} ({found.project.name})"}
        for found in status.each() for item in found.checks.summary()["not_run"]]
    return {
        "project": {"name": status.project.name, "root": str(status.project.root)},
        "open": sum(project["open"] for project in projects),
        "projects": projects,
        "changes": acted["changes"],
        "actions": {**{key: value for key, value in acted.items()
                       if key not in ("signals", "changes")},
                    "closed": [signal.as_dict(detail=True) for signal in acted["signals"]]},
        "checks": {**summary, "unfinished": [
            {"check": entity(type(result.check)).name, "status": result.status,
             "reason": result.reason} for result in suite.results
            if result.status != "completed"]},
        "report": suite.report(limit=10**6, label=standing),
        "settled": (all(result.status == "completed" for result in suite.results)
                    and all(standing(poi) == BLESSED for poi in suite.findings())),
    }


def _relative(root: str) -> str:
    try:
        path = os.path.relpath(root)
    except ValueError:
        return root
    return root if path.startswith("..") else path


# tarav.context abd0372d:0c49207898a3b796
def status_text(result: dict, *, limit: int = 20) -> str:
    """The readable form: what is open first, then what changed, then where to look."""
    projects = result["projects"]
    many = len(projects) > 1
    lines = [f"{result['project']['name']}: {result['open']} open actions"
             + (f" in {len(projects)} Projects" if many else "")]
    lines.extend(check_header(result["checks"], pois=False))
    lines.append("")
    counts = ", ".join(f"{result['actions'][key]} {words}" for key, words in COUNTED
                       if result["actions"][key])
    lines.append(f"Changed in this run: {counts or 'nothing'}")
    shown = result["changes"][:limit]
    width = max((len(change["project"]) for change in shown), default=0)
    for change in shown:
        where = f"{change['project']:<{width}}  " if many else ""
        lines.append(f"  {LISTED[change['change']]:<8}  {where}{_short(change['type'])}  "
                     f"{change['message'] or ''}  [{(change['poi'] or change['action'])[:12]}]")
    if len(result["changes"]) > limit:
        lines.append(f"  and {len(result['changes']) - limit} more; --json has them all.")
    lines.append("")
    if not result["open"] and not any(project["blessed"] for project in projects):
        lines.append("No open actions.")
        return "\n".join(lines)
    lines.append("Open actions")
    name_width = max(len(project["name"]) for project in projects)
    count_width = max(len(str(project["open"])) for project in projects)
    for project in sorted(projects, key=lambda item: -item["open"]):
        kinds = ", ".join(f"{name} {count}" for name, count in
                          _kinds(Counter(project["by_type"])).items())
        blessed = f"  ({project['blessed']} blessed)" if project["blessed"] else ""
        lines.append(f"  {project['name']:<{name_width}}  {project['open']:>{count_width}}"
                     f"  {kinds}{blessed}".rstrip())
    busiest = max(projects, key=lambda item: item["open"])
    lines.extend(("", f"List them:  tarav action list --project {_relative(busiest['root'])}",
                  "Open one:   tarav context --id <poi-id> --view poi-action"))
    return "\n".join(lines)


# tarav.context abd0372d:53a7beaeddd157ad
def report_project_status(project, *, json_output: bool = False, limit: int = 20,
                          everything: bool = False) -> int:
    """Run a Project's checks, hand the results to its actions, and say how it stands.

    Suites that are not routine are left out unless `everything` is set; their
    actions stay as they are. Exit 0 says every check that ran completed and
    every finding left is blessed.
    """
    progress = Progress()
    try:
        status = project.status(select=None if everything else routine, on_result=progress)
    except NotImplementedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        progress.done()
    _retained(project, status.suite())
    result = status_result(status)
    print(json.dumps(result, indent=2, default=str) if json_output
          else status_text(result, limit=limit))
    return 0 if result["settled"] else 1


def _status(args: argparse.Namespace) -> int:
    return in_harness(args, command="tarav status", module="tarav.l3.status",
                      function="report_project_status", options={
                          "json_output": args.json, "limit": args.limit,
                          "everything": args.all})


# tarav.context abd0372d:b3a1625d099be644
def register_status_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "status",
        help="Say what is open in a Project: run its checks, update its actions from the "
             "results, and show the open actions and what this run changed. Run it as "
             "often as needed; --all also runs the slow suites.",
        epilog=(
            "examples:\n"
            "  tarav status --project\n"
            "  tarav status --project --all\n"
            "  tarav status --project /path/to/project --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--project", type=Path, nargs="?", const=Path("."),
        help="Search this directory and parents for a Project; optionally start at PATH.",
    )
    parser.add_argument("--json", action="store_true",
                        help="Print the whole result as JSON, the check report included.")
    parser.add_argument("--limit", type=int, default=20,
                        help="Maximum changes to list (default: 20).")
    parser.add_argument("--all", action="store_true",
                        help="Run every suite. Without it, suites that are not part of the "
                             "routine run are left out, such as a Project's pytest tests.")
    parser.set_defaults(handler=_status)


__all__ = ["register_status_command", "report_project_status", "status_result", "status_text"]
