from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.project import require_agentos_project_root
from agentos.utils.skills import query_skills

from .core import (
    create_mission,
    get_help,
    help_has_children,
    help_summary,
    list_missions,
    load_mission,
    mission_last_activity,
    most_recent_active_mission_name,
    resolve_mission_name,
    save_mission,
    set_help_entry,
    touch_mission,
    todo_progress,
)


def _project_root(args: argparse.Namespace) -> "Path":
    return require_agentos_project_root(
        project=args.project,
        include_init_hint=True,
    )


# ── mission new ──────────────────────────────────────────────────────

def _cmd_new(args: argparse.Namespace) -> int:
    root = _project_root(args)
    mission = create_mission(root, args.name, args.goal, args.validation)
    if args.json:
        print(json.dumps(mission, indent=2))
    else:
        print(f"created mission: {mission['name']}")
    return 0


# ── mission activate ─────────────────────────────────────────────────

def _cmd_activate(args: argparse.Namespace) -> int:
    root = _project_root(args)
    mission = load_mission(root, args.name)
    mission["status"] = "active"
    mission["finished"] = None
    touch_mission(mission)
    save_mission(root, mission)
    if args.json:
        print(json.dumps(mission, indent=2))
    else:
        print(f"mission activated: {args.name}")
    return 0


# ── mission status ───────────────────────────────────────────────────

def _format_status(mission: dict) -> str:
    lines = []
    lines.append(f"mission: {mission['name']} [{mission['status']}]")
    lines.append(f"goal:    {mission['goal']}")
    lines.append(f"check:   {mission['validation']}")
    last_activity = mission_last_activity(mission)
    if last_activity:
        lines.append(f"last:    {last_activity}")

    todos = mission.get("todos", [])
    if todos:
        lines.append("")
        lines.append("todos:")
        for i, t in enumerate(todos, 1):
            mark = "x" if t.get("done") else " "
            lines.append(f"  {i}. [{mark}] {t['text']}")

    notes = mission.get("notes", [])
    if notes:
        lines.append("")
        lines.append("notes:")
        for n in notes:
            lines.append(f"  - {n}")

    return "\n".join(lines)


def _cmd_status(args: argparse.Namespace) -> int:
    root = _project_root(args)
    name = resolve_mission_name(root, args.name)
    mission = load_mission(root, name)
    if args.json:
        print(json.dumps(mission, indent=2))
    else:
        print(_format_status(mission))
    return 0


# ── mission done ─────────────────────────────────────────────────────

def _cmd_done(args: argparse.Namespace) -> int:
    root = _project_root(args)
    name = resolve_mission_name(root, args.name)
    mission = load_mission(root, name)
    mission["status"] = "done"
    mission["finished"] = touch_mission(mission)
    save_mission(root, mission)

    if args.json:
        print(json.dumps(mission, indent=2))
    else:
        print(f"mission done: {name}")
    return 0


# ── mission park ─────────────────────────────────────────────────────

def _cmd_park(args: argparse.Namespace) -> int:
    root = _project_root(args)
    name = resolve_mission_name(root, args.name)
    mission = load_mission(root, name)
    mission["status"] = "parked"
    touch_mission(mission)
    save_mission(root, mission)

    if args.json:
        print(json.dumps(mission, indent=2))
    else:
        print(f"mission parked: {name}")
    return 0


# ── mission list ─────────────────────────────────────────────────────

def _format_list(missions: list[dict], default_name: str | None) -> str:
    if not missions:
        return "no missions"

    grouped: dict[str, list[dict]] = {"active": [], "parked": [], "done": []}
    for m in missions:
        status = m.get("status", "active")
        grouped.setdefault(status, []).append(m)

    lines = []
    for status in ("active", "parked", "done"):
        group = grouped.get(status, [])
        if not group:
            continue
        if lines:
            lines.append("")
        heading = status if status != "active" else "active (most recent first)"
        lines.append(f"{heading}:")
        for m in group:
            name = m["name"]
            goal = m.get("goal", "")
            if len(goal) > 50:
                goal = goal[:47] + "..."
            done_count, total = todo_progress(m)
            marker = "  (default)" if name == default_name and status == "active" else ""
            last_activity = mission_last_activity(m)
            last_label = f"  [last {last_activity}]" if last_activity and status != "done" else ""
            if status == "done":
                finished = m.get("finished", "")
                lines.append(f"  {name}{marker}  {goal}  [done {finished}]")
            else:
                lines.append(
                    f"  {name}{marker}  {goal}  [{done_count}/{total} todos]{last_label}"
                )

    return "\n".join(lines)


def _cmd_list(args: argparse.Namespace) -> int:
    root = _project_root(args)
    missions = list_missions(root)
    default_name = most_recent_active_mission_name(root)
    if args.json:
        print(json.dumps({"default": default_name, "missions": missions}, indent=2))
    else:
        print(_format_list(missions, default_name))
    return 0


# ── mission todo add ─────────────────────────────────────────────────

def _cmd_todo_add(args: argparse.Namespace) -> int:
    root = _project_root(args)
    name = resolve_mission_name(root, args.mission)
    mission = load_mission(root, name)
    mission.setdefault("todos", []).append({"text": args.text, "done": False})
    touch_mission(mission)
    save_mission(root, mission)
    idx = len(mission["todos"])
    if args.json:
        print(json.dumps({"mission": name, "index": idx, "text": args.text}))
    else:
        print(f"added todo #{idx} to {name}")
    return 0


# ── mission todo done ────────────────────────────────────────────────

def _cmd_todo_done(args: argparse.Namespace) -> int:
    root = _project_root(args)
    name = resolve_mission_name(root, args.mission)
    mission = load_mission(root, name)
    todos = mission.get("todos", [])
    idx = args.index
    if idx < 1 or idx > len(todos):
        raise CliError(f"todo index {idx} out of range (1-{len(todos)})")
    todos[idx - 1]["done"] = True
    touch_mission(mission)
    save_mission(root, mission)
    if args.json:
        print(json.dumps({"mission": name, "index": idx, "done": True}))
    else:
        print(f"todo #{idx} done: {todos[idx - 1]['text']}")
    return 0


# ── mission note ─────────────────────────────────────────────────────

def _cmd_note(args: argparse.Namespace) -> int:
    root = _project_root(args)
    name = resolve_mission_name(root, args.mission)
    mission = load_mission(root, name)
    mission.setdefault("notes", []).append(args.text)
    touch_mission(mission)
    save_mission(root, mission)
    if args.json:
        print(json.dumps({"mission": name, "note": args.text}))
    else:
        print(f"noted on {name}")
    return 0


# ── mission fork ─────────────────────────────────────────────────────

def _cmd_fork(args: argparse.Namespace) -> int:
    root = _project_root(args)
    name = resolve_mission_name(root, args.mission)
    mission = load_mission(root, name)

    if args.as_mission:
        new_mission = create_mission(root, args.as_mission, args.text, "")
        mission.setdefault("notes", []).append(
            f"FORK: {args.text} → spawned mission '{args.as_mission}'"
        )
        touch_mission(mission)
        save_mission(root, mission)
        if args.json:
            print(json.dumps({
                "mission": name,
                "forked_as": args.as_mission,
                "new_mission": new_mission,
            }, indent=2))
        else:
            print(f"forked from {name} → new mission: {args.as_mission}")
    else:
        mission.setdefault("notes", []).append(f"FORK: {args.text}")
        touch_mission(mission)
        save_mission(root, mission)
        if args.json:
            print(json.dumps({"mission": name, "fork": args.text}))
        else:
            print(f"fork noted on {name}")

    return 0


# ── mission help ─────────────────────────────────────────────────────

def _format_help_overview(mission: dict) -> str:
    help_obj = get_help(mission)
    if not help_obj:
        return f"mission: {mission['name']}\nno help entries"
    lines = [f"mission: {mission['name']}", ""]
    for field, entry in help_obj.items():
        summary = help_summary(entry)
        marker = "  [+]" if help_has_children(entry) else ""
        lines.append(f"{field}: {summary}{marker}")
    return "\n".join(lines)


def _format_help_detail(mission: dict, field: str) -> str:
    help_obj = get_help(mission)
    entry = help_obj.get(field)
    if entry is None:
        return f"no help entry for: {field}"
    if isinstance(entry, str):
        return f"{field}: {entry}"
    if isinstance(entry, dict):
        lines = [f"{field}: {help_summary(entry)}"]
        for k, v in entry.items():
            if k == "help":
                continue
            if isinstance(v, str):
                lines.append(f"  {k}: {v}")
            elif isinstance(v, dict):
                lines.append(f"  {k}: {help_summary(v)}  [+]")
            else:
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)
    return f"{field}: {entry}"


def _cmd_help(args: argparse.Namespace) -> int:
    root = _project_root(args)
    name = resolve_mission_name(root, args.name)
    mission = load_mission(root, name)

    if args.json:
        help_obj = get_help(mission)
        if args.field:
            entry = help_obj.get(args.field)
            print(json.dumps({"mission": name, "field": args.field, "help": entry}, indent=2))
        else:
            print(json.dumps({"mission": name, "help": help_obj}, indent=2))
        return 0

    if args.field:
        print(_format_help_detail(mission, args.field))
    else:
        print(_format_help_overview(mission))
    return 0


def _cmd_help_set(args: argparse.Namespace) -> int:
    root = _project_root(args)
    name = resolve_mission_name(root, args.mission)
    mission = load_mission(root, name)
    set_help_entry(mission, args.field, args.text)
    touch_mission(mission)
    save_mission(root, mission)
    if args.json:
        print(json.dumps({"mission": name, "field": args.field, "help": args.text}))
    else:
        print(f"help set for {args.field} on {name}")
    return 0


# ── mission templates ────────────────────────────────────────────────

def _cmd_templates(args: argparse.Namespace) -> int:
    results = query_skills(
        Path.cwd(),
        filters={"type": "mission.template"},
    )

    if args.json:
        print(json.dumps(
            [
                {
                    "name": skill.name,
                    "source_kind": skill.source_kind,
                    "path": str(skill.path),
                    "frontmatter": fm,
                }
                for skill, fm in results
            ],
            indent=2,
        ))
        return 0

    if not results:
        print("no mission templates found")
        return 0

    for skill, fm in results:
        desc = fm.get("description", "")
        print(f"  {skill.name}  {desc}")
    return 0


# ── registration ─────────────────────────────────────────────────────

def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Output as JSON.")


def _add_mission_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--mission", default=None,
        help="Target mission name (default: most recently active mission).",
    )


def _add_project_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        nargs="?",
        type=Path,
        const=Path("."),
        default=None,
        help="Project target override. Bare --project targets current pwd.",
    )


def register_mission_commands(subparsers: argparse._SubParsersAction) -> None:
    mission_parser = subparsers.add_parser(
        "mission",
        help="Mission control — coordinate named blocks of work.",
    )
    mission_subs = mission_parser.add_subparsers(dest="mission_command")

    # new
    p = mission_subs.add_parser("new", help="Create a new mission.")
    p.add_argument("name", help="Mission name (kebab-case).")
    p.add_argument("--goal", required=True, help="What this mission achieves.")
    p.add_argument("--validation", required=True, help="How we know it's done.")
    _add_project_argument(p)
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_new)

    # activate
    p = mission_subs.add_parser("activate", help="Mark a mission as recently active and resume it.")
    p.add_argument("name", help="Mission name to activate.")
    _add_project_argument(p)
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_activate)

    # status
    p = mission_subs.add_parser("status", help="Show mission status.")
    p.add_argument("name", nargs="?", default=None, help="Mission name (default: most recently active).")
    _add_project_argument(p)
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_status)

    # done
    p = mission_subs.add_parser("done", help="Mark a mission as done.")
    p.add_argument("name", nargs="?", default=None, help="Mission name (default: most recently active).")
    _add_project_argument(p)
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_done)

    # park
    p = mission_subs.add_parser("park", help="Park a mission for later.")
    p.add_argument("name", nargs="?", default=None, help="Mission name (default: most recently active).")
    _add_project_argument(p)
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_park)

    # list
    p = mission_subs.add_parser("list", help="List all missions.")
    _add_project_argument(p)
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_list)

    # help show
    p = mission_subs.add_parser("help", help="Show help entries for a mission.")
    p.add_argument("name", nargs="?", default=None, help="Mission name (default: most recently active).")
    p.add_argument("field", nargs="?", default=None, help="Drill into a specific field.")
    _add_project_argument(p)
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_help)

    # help set (as separate top-level subcommand)
    p = mission_subs.add_parser("help-set", help="Set a help entry for a mission field.")
    p.add_argument("field", help="Field name to document.")
    p.add_argument("text", help="Help text for the field.")
    _add_project_argument(p)
    _add_mission_flag(p)
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_help_set)

    # templates
    p = mission_subs.add_parser("templates", help="List mission template skills.")
    p.add_argument("--list", action="store_true", dest="list_templates", help="List available mission templates.")
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_templates)

    # todo (nested subcommands)
    todo_parser = mission_subs.add_parser("todo", help="Manage mission todos.")
    todo_subs = todo_parser.add_subparsers(dest="todo_command")

    p = todo_subs.add_parser("add", help="Add a todo to a mission.")
    p.add_argument("text", help="Todo text.")
    _add_project_argument(p)
    _add_mission_flag(p)
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_todo_add)

    p = todo_subs.add_parser("done", help="Mark a todo as done.")
    p.add_argument("index", type=int, help="1-based todo index.")
    _add_project_argument(p)
    _add_mission_flag(p)
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_todo_done)

    # note
    p = mission_subs.add_parser("note", help="Add a note to a mission.")
    p.add_argument("text", help="Note text.")
    _add_project_argument(p)
    _add_mission_flag(p)
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_note)

    # fork
    p = mission_subs.add_parser("fork", help="Log a fork idea on a mission.")
    p.add_argument("text", help="Fork description.")
    p.add_argument("--as-mission", default=None, help="Also create as a new mission.")
    _add_project_argument(p)
    _add_mission_flag(p)
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_fork)
