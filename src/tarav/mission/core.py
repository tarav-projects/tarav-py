# $kw: --from Iterante.Mission
from __future__ import annotations

import json
from pathlib import Path

from tarav._core.clock import utc_now_iso
from tarav._core.errors import CliError
from tarav._core.path_validation import validate_string_for_path
from tarav._core.project import project_agentos_dir

MISSION_SCHEMA_VERSION = 1
MISSION_CLASS = "agentos.mission"
VALID_STATUSES = ("active", "done", "parked")
MISSION_SUFFIX = ".mission.json"


def missions_dir(project_root: Path) -> Path:
    d = project_agentos_dir(project_root) / "missions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def mission_path(project_root: Path, name: str) -> Path:
    return missions_dir(project_root) / f"{name}{MISSION_SUFFIX}"


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


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def mission_last_activity(mission: dict) -> str | None:
    return (
        _string_or_none(mission.get("last_activity"))
        or _string_or_none(mission.get("finished"))
        or _string_or_none(mission.get("created"))
    )


def _normalize_mission(mission: dict, *, source_name: str) -> dict:
    if mission.get("class") != MISSION_CLASS:
        raise CliError(f"invalid mission file: {source_name}")

    status = mission.get("status", "active")
    if status not in VALID_STATUSES:
        raise CliError(
            f"invalid mission status in {source_name}: {status!r} "
            f"(expected one of: {', '.join(VALID_STATUSES)})"
        )

    normalized = dict(mission)
    normalized["status"] = status
    normalized.setdefault("todos", [])
    normalized.setdefault("notes", [])

    last_activity = mission_last_activity(normalized)
    if last_activity is not None:
        normalized["last_activity"] = last_activity
    return normalized


def load_mission(project_root: Path, name: str) -> dict:
    p = mission_path(project_root, name)
    if not p.exists():
        raise CliError(f"mission not found: {name}")
    return _normalize_mission(_read_json(p), source_name=p.name)


def save_mission(project_root: Path, mission: dict) -> None:
    name = mission["name"]
    _write_json(mission_path(project_root, name), mission)


def list_missions(project_root: Path) -> list[dict]:
    d = missions_dir(project_root)
    results = []
    for p in sorted(d.iterdir()):
        if p.name.endswith(MISSION_SUFFIX) and p.is_file():
            try:
                results.append(_normalize_mission(_read_json(p), source_name=p.name))
            except CliError:
                continue
    results.sort(
        key=lambda mission: (
            mission_last_activity(mission) or "",
            _string_or_none(mission.get("created")) or "",
            mission.get("name", ""),
        ),
        reverse=True,
    )
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

    created = utc_now_iso()
    mission = {
        "class": MISSION_CLASS,
        "schema_version": MISSION_SCHEMA_VERSION,
        "name": validated_name,
        "goal": goal.strip(),
        "validation": validation.strip(),
        "status": "active",
        "created": created,
        "last_activity": created,
        "finished": None,
        "todos": [],
        "notes": [],
    }
    save_mission(project_root, mission)
    return mission


def touch_mission(mission: dict, *, timestamp: str | None = None) -> str:
    touched_at = timestamp or utc_now_iso()
    mission["last_activity"] = touched_at
    return touched_at


def most_recent_active_mission_name(project_root: Path) -> str | None:
    for mission in list_missions(project_root):
        if mission.get("status", "active") == "active":
            return mission["name"]
    return None


def resolve_mission_name(project_root: Path, name: str | None) -> str:
    if name is not None:
        return name
    recent = most_recent_active_mission_name(project_root)
    if recent is None:
        raise CliError("no mission specified and no recent active mission found")
    return recent


def todo_progress(mission: dict) -> tuple[int, int]:
    todos = mission.get("todos", [])
    done = sum(1 for t in todos if t.get("done"))
    return done, len(todos)





def get_help(mission: dict) -> dict:
    return mission.get("help", {})


def set_help_entry(mission: dict, field: str, value: str | dict) -> None:
    mission.setdefault("help", {})[field] = value


def help_summary(entry: str | dict) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return str(entry.get("help", ""))
    return str(entry)


def help_has_children(entry: object) -> bool:
    return isinstance(entry, dict)
