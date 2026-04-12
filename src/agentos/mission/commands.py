from __future__ import annotations

import argparse
import json

from agentos._core.errors import CliError
from agentos._core.clock import utc_now_iso
from agentos._core.project import require_agentos_project_root

from .core import (
    create_mission,
    list_missions,
    load_active,
    load_mission,
    resolve_mission_name,
    save_active,
    save_mission,
    todo_progress,
)


def _project_root() -> "Path":
    return require_agentos_project_root()


# ── mission new ──────────────────────────────────────────────────────

def _cmd_new(args: argparse.Namespace) -> int:
    root = _project_root()
    mission = create_mission(root, args.name, args.goal, args.validation)
    if args.json:
        print(json.dumps(mission, indent=2))
    else:
        print(f"created mission: {mission['name']}")
    return 0


# ── mission activate ─────────────────────────────────────────────────

def _cmd_activate(args: argparse.Namespace) -> int:
    root = _project_root()
    load_mission(root, args.name)  # ensure it exists
    save_active(root, args.name)
    if args.json:
        print(json.dumps({"active": args.name}))
    else:
        print(f"active mission: {args.name}")
    return 0


# ── mission status ───────────────────────────────────────────────────

def _format_status(mission: dict) -> str:
    lines = []
    lines.append(f"mission: {mission['name']} [{mission['status']}]")
    lines.append(f"goal:    {mission['goal']}")
    lines.append(f"check:   {mission['validation']}")

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
    root = _project_root()
    name = resolve_mission_name(root, args.name)
    mission = load_mission(root, name)
    if args.json:
        print(json.dumps(mission, indent=2))
    else:
        print(_format_status(mission))
    return 0


# ── mission done ─────────────────────────────────────────────────────

def _cmd_done(args: argparse.Namespace) -> int:
    root = _project_root()
    name = resolve_mission_name(root, args.name)
    mission = load_mission(root, name)
    mission["status"] = "done"
    mission["finished"] = utc_now_iso()
    save_mission(root, mission)

    active = load_active(root)
    if active == name:
        save_active(root, None)

    if args.json:
        print(json.dumps(mission, indent=2))
    else:
        print(f"mission done: {name}")
    return 0


# ── mission park ─────────────────────────────────────────────────────

def _cmd_park(args: argparse.Namespace) -> int:
    root = _project_root()
    name = resolve_mission_name(root, args.name)
    mission = load_mission(root, name)
    mission["status"] = "parked"
    save_mission(root, mission)

    active = load_active(root)
    if active == name:
        save_active(root, None)

    if args.json:
        print(json.dumps(mission, indent=2))
    else:
        print(f"mission parked: {name}")
    return 0


# ── mission list ─────────────────────────────────────────────────────

def _format_list(missions: list[dict], active_name: str | None) -> str:
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
        lines.append(f"{status}:")
        for m in group:
            name = m["name"]
            goal = m.get("goal", "")
            if len(goal) > 50:
                goal = goal[:47] + "..."
            done_count, total = todo_progress(m)
            marker = " *" if name == active_name else ""
            if status == "done":
                finished = m.get("finished", "")
                if finished:
                    finished = finished[:10]
                lines.append(f"  {name}{marker}  {goal}  [done {finished}]")
            else:
                lines.append(f"  {name}{marker}  {goal}  [{done_count}/{total} todos]")

    return "\n".join(lines)


def _cmd_list(args: argparse.Namespace) -> int:
    root = _project_root()
    missions = list_missions(root)
    active_name = load_active(root)
    if args.json:
        print(json.dumps({"active": active_name, "missions": missions}, indent=2))
    else:
        print(_format_list(missions, active_name))
    return 0


# ── mission todo add ─────────────────────────────────────────────────

def _cmd_todo_add(args: argparse.Namespace) -> int:
    root = _project_root()
    name = resolve_mission_name(root, args.mission)
    mission = load_mission(root, name)
    mission.setdefault("todos", []).append({"text": args.text, "done": False})
    save_mission(root, mission)
    idx = len(mission["todos"])
    if args.json:
        print(json.dumps({"mission": name, "index": idx, "text": args.text}))
    else:
        print(f"added todo #{idx} to {name}")
    return 0


# ── mission todo done ────────────────────────────────────────────────

def _cmd_todo_done(args: argparse.Namespace) -> int:
    root = _project_root()
    name = resolve_mission_name(root, args.mission)
    mission = load_mission(root, name)
    todos = mission.get("todos", [])
    idx = args.index
    if idx < 1 or idx > len(todos):
        raise CliError(f"todo index {idx} out of range (1-{len(todos)})")
    todos[idx - 1]["done"] = True
    save_mission(root, mission)
    if args.json:
        print(json.dumps({"mission": name, "index": idx, "done": True}))
    else:
        print(f"todo #{idx} done: {todos[idx - 1]['text']}")
    return 0


# ── mission note ─────────────────────────────────────────────────────

def _cmd_note(args: argparse.Namespace) -> int:
    root = _project_root()
    name = resolve_mission_name(root, args.mission)
    mission = load_mission(root, name)
    mission.setdefault("notes", []).append(args.text)
    save_mission(root, mission)
    if args.json:
        print(json.dumps({"mission": name, "note": args.text}))
    else:
        print(f"noted on {name}")
    return 0


# ── mission fork ─────────────────────────────────────────────────────

def _cmd_fork(args: argparse.Namespace) -> int:
    root = _project_root()
    name = resolve_mission_name(root, args.mission)
    mission = load_mission(root, name)

    if args.as_mission:
        new_mission = create_mission(root, args.as_mission, args.text, "")
        mission.setdefault("notes", []).append(
            f"FORK: {args.text} → spawned mission '{args.as_mission}'"
        )
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
        save_mission(root, mission)
        if args.json:
            print(json.dumps({"mission": name, "fork": args.text}))
        else:
            print(f"fork noted on {name}")

    return 0


# ── registration ─────────────────────────────────────────────────────

def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Output as JSON.")


def _add_mission_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--mission", default=None,
        help="Target mission name (default: active mission).",
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
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_new)

    # activate
    p = mission_subs.add_parser("activate", help="Set the active mission.")
    p.add_argument("name", help="Mission name to activate.")
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_activate)

    # status
    p = mission_subs.add_parser("status", help="Show mission status.")
    p.add_argument("name", nargs="?", default=None, help="Mission name (default: active).")
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_status)

    # done
    p = mission_subs.add_parser("done", help="Mark a mission as done.")
    p.add_argument("name", nargs="?", default=None, help="Mission name (default: active).")
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_done)

    # park
    p = mission_subs.add_parser("park", help="Park a mission for later.")
    p.add_argument("name", nargs="?", default=None, help="Mission name (default: active).")
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_park)

    # list
    p = mission_subs.add_parser("list", help="List all missions.")
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_list)

    # todo (nested subcommands)
    todo_parser = mission_subs.add_parser("todo", help="Manage mission todos.")
    todo_subs = todo_parser.add_subparsers(dest="todo_command")

    p = todo_subs.add_parser("add", help="Add a todo to a mission.")
    p.add_argument("text", help="Todo text.")
    _add_mission_flag(p)
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_todo_add)

    p = todo_subs.add_parser("done", help="Mark a todo as done.")
    p.add_argument("index", type=int, help="1-based todo index.")
    _add_mission_flag(p)
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_todo_done)

    # note
    p = mission_subs.add_parser("note", help="Add a note to a mission.")
    p.add_argument("text", help="Note text.")
    _add_mission_flag(p)
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_note)

    # fork
    p = mission_subs.add_parser("fork", help="Log a fork idea on a mission.")
    p.add_argument("text", help="Fork description.")
    p.add_argument("--as-mission", default=None, help="Also create as a new mission.")
    _add_mission_flag(p)
    _add_json_flag(p)
    p.set_defaults(handler=_cmd_fork)
