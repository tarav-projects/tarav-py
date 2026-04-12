from __future__ import annotations

import json
from pathlib import Path

from agentos._core.clock import utc_now_iso
from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos._core.project import project_agentos_dir

MISSION_SCHEMA_VERSION = 1
MISSION_CLASS = "agentos.mission"
ACTIVE_CLASS = "agentos.mission.active"
VALID_STATUSES = ("active", "done", "parked")
MISSION_SUFFIX = ".mission.json"
ACTIVE_FILENAME = "_active.json"


def missions_dir(project_root: Path) -> Path:
    d = project_agentos_dir(project_root) / "missions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def mission_path(project_root: Path, name: str) -> Path:
    return missions_dir(project_root) / f"{name}{MISSION_SUFFIX}"


def active_path(project_root: Path) -> Path:
    return missions_dir(project_root) / ACTIVE_FILENAME


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON in {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CliError(f"{path.name} must be a JSON object")
    return payload


def load_active(project_root: Path) -> str | None:
    p = active_path(project_root)
    if not p.exists():
        return None
    data = _read_json(p)
    value = data.get("active")
    if value is None or value == "":
        return None
    return str(value)


def save_active(project_root: Path, name: str | None) -> None:
    _write_json(active_path(project_root), {
        "class": ACTIVE_CLASS,
        "active": name,
    })


def load_mission(project_root: Path, name: str) -> dict:
    p = mission_path(project_root, name)
    if not p.exists():
        raise CliError(f"mission not found: {name}")
    data = _read_json(p)
    if data.get("class") != MISSION_CLASS:
        raise CliError(f"invalid mission file: {p.name}")
    return data


def save_mission(project_root: Path, mission: dict) -> None:
    name = mission["name"]
    _write_json(mission_path(project_root, name), mission)


def list_missions(project_root: Path) -> list[dict]:
    d = missions_dir(project_root)
    results = []
    for p in sorted(d.iterdir()):
        if p.name.endswith(MISSION_SUFFIX) and p.is_file():
            try:
                results.append(_read_json(p))
            except CliError:
                continue
    return results


def create_mission(
    project_root: Path,
    name: str,
    goal: str,
    validation: str,
) -> dict:
    validated_name = validate_string_for_path(name, field_name="mission name")
    if mission_path(project_root, validated_name).exists():
        raise CliError(f"mission already exists: {validated_name}")

    mission = {
        "class": MISSION_CLASS,
        "schema_version": MISSION_SCHEMA_VERSION,
        "name": validated_name,
        "goal": goal.strip(),
        "validation": validation.strip(),
        "status": "active",
        "created": utc_now_iso(),
        "finished": None,
        "todos": [],
        "notes": [],
    }
    save_mission(project_root, mission)
    return mission


def resolve_mission_name(project_root: Path, name: str | None) -> str:
    if name is not None:
        return name
    active = load_active(project_root)
    if active is None:
        raise CliError("no mission specified and no active mission set")
    return active


def todo_progress(mission: dict) -> tuple[int, int]:
    todos = mission.get("todos", [])
    done = sum(1 for t in todos if t.get("done"))
    return done, len(todos)
