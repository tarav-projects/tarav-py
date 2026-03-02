from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import UUID

from agentos._core.errors import CliError
from agentos._core.clock import utc_now_iso as _utc_now_iso
from agentos._core.ids import normalize_or_generate_uuid
from agentos._core.path_validation import validate_string_for_path

AGENTOS_DIRNAME = ".agentos"
PROJECT_MARKER_FILENAME = "project.json"
PROJECT_CONFIG_FILENAME = "config.json"
GLOBAL_CONFIG_FILENAME = "config.json"
PROJECT_SCHEMA_VERSION = 1
GLOBAL_SCHEMA_VERSION = 1
SCOPE_VALUES = ("project", "global", "auto")
PROJECT_DIR_NAMES = ("tapes", "indexes", "tmp", "state")
GLOBAL_DIR_NAMES = ("tapes", "indexes", "tmp", "cache")


def agentos_home_dir() -> Path:
    env_home = os.getenv("AGENTOS_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    return (Path.home() / AGENTOS_DIRNAME).resolve()


def project_agentos_dir(project_root: Path) -> Path:
    return project_root / AGENTOS_DIRNAME


def project_marker_path(project_root: Path) -> Path:
    return project_agentos_dir(project_root) / PROJECT_MARKER_FILENAME


def project_config_path(project_root: Path) -> Path:
    return project_agentos_dir(project_root) / PROJECT_CONFIG_FILENAME


def global_config_path(home_dir: Path | None = None) -> Path:
    root = agentos_home_dir() if home_dir is None else home_dir
    return root / GLOBAL_CONFIG_FILENAME


def find_agentos_project_root(start_path: Path | str = ".") -> Path | None:
    current = Path(start_path).expanduser().resolve()
    if current.is_file():
        current = current.parent

    while True:
        if project_marker_path(current).is_file():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def build_not_inside_project_message(
    *,
    include_init_hint: bool = False,
    extra_hint: str | None = None,
    git_style: bool = False,
) -> str:
    message = "not inside an agentos project (missing .agentos/project.json)"
    hints: list[str] = []
    if include_init_hint:
        hints.append("run `agentos init`")
    if extra_hint is not None:
        hints.append(str(extra_hint))

    if hints:
        message = f"{message}; " + " or ".join(hints)
    if git_style:
        return f"fatal: {message}"
    return message


def require_agentos_project_root(start_path: Path | str = ".") -> Path:
    project_root = find_agentos_project_root(start_path)
    if project_root is None:
        raise CliError(build_not_inside_project_message())
    return project_root


def resolve_scope_agentos_dir(
    scope: str,
    *,
    start_path: Path | str = ".",
) -> tuple[str, Path, Path | None]:
    normalized_scope = str(scope).strip().lower()
    if normalized_scope not in SCOPE_VALUES:
        raise CliError(f"unsupported scope '{scope}' (expected one of: {', '.join(SCOPE_VALUES)})")

    if normalized_scope == "global":
        return ("global", agentos_home_dir(), None)

    project_root = find_agentos_project_root(start_path)
    if normalized_scope == "project":
        if project_root is None:
            raise CliError(build_not_inside_project_message())
        return ("project", project_agentos_dir(project_root), project_root)

    if project_root is not None:
        return ("project", project_agentos_dir(project_root), project_root)
    return ("global", agentos_home_dir(), None)


def resolve_scope_storage_paths(
    scope: str,
    *,
    start_path: Path | str = ".",
) -> tuple[str, dict[str, Path], Path | None]:
    effective_scope, effective_agentos_dir, effective_project_root = resolve_scope_agentos_dir(
        scope,
        start_path=start_path,
    )
    if effective_scope == "project":
        assert effective_project_root is not None
        return (
            effective_scope,
            local_storage_paths(effective_project_root),
            effective_project_root,
        )
    return (
        effective_scope,
        global_storage_paths(effective_agentos_dir),
        None,
    )


def resolve_project_tape_dir(
    tape_name: str,
    *,
    start_path: Path | str = ".",
) -> tuple[Path, Path, str]:
    normalized_tape_name = validate_string_for_path(tape_name, field_name="tape")
    project_root = find_agentos_project_root(start_path)
    if project_root is None:
        raise CliError(
            build_not_inside_project_message(
                include_init_hint=True,
                extra_hint="pass --root",
            )
        )
    return (project_agentos_dir(project_root) / "tapes" / normalized_tape_name, project_root, normalized_tape_name)


def local_storage_paths(project_root: Path) -> dict[str, Path]:
    base = project_agentos_dir(project_root)
    return {
        "agentos_dir": base,
        "project_marker": project_marker_path(project_root),
        "config": project_config_path(project_root),
        "tapes": base / "tapes",
        "indexes": base / "indexes",
        "tmp": base / "tmp",
        "state": base / "state",
    }


def global_storage_paths(home_dir: Path | None = None) -> dict[str, Path]:
    base = agentos_home_dir() if home_dir is None else home_dir
    return {
        "agentos_dir": base,
        "config": global_config_path(base),
        "tapes": base / "tapes",
        "indexes": base / "indexes",
        "tmp": base / "tmp",
        "cache": base / "cache",
    }


def load_project_marker(marker_path: Path) -> dict[str, object]:
    if not marker_path.exists():
        raise CliError(f"project marker does not exist: {marker_path}")
    if not marker_path.is_file():
        raise CliError(f"project marker path is not a file: {marker_path}")
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid project marker JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CliError("project marker must be a JSON object")
    if payload.get("class") != "agentos.project":
        raise CliError("project marker field class must be 'agentos.project'")

    project_id = str(payload.get("project_id", "")).strip()
    if not project_id:
        raise CliError("project marker field project_id is required")
    try:
        UUID(project_id)
    except ValueError as exc:
        raise CliError(f"project marker project_id is not a valid UUID: {project_id}") from exc
    return payload


def load_global_config(config_path: Path) -> dict[str, object]:
    if not config_path.exists():
        raise CliError(f"global config does not exist: {config_path}")
    if not config_path.is_file():
        raise CliError(f"global config path is not a file: {config_path}")
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid global config JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CliError("global config must be a JSON object")
    if payload.get("class") != "agentos.global.config":
        raise CliError("global config field class must be 'agentos.global.config'")
    return payload


def _normalize_project_id(project_id: str | None) -> str:
    return normalize_or_generate_uuid(project_id, field_name="project id")


def _ensure_json_file(path: Path, payload: dict[str, object]) -> bool:
    if path.exists():
        if not path.is_file():
            raise CliError(f"path exists but is not a file: {path}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return True


def _ensure_named_dirs(base_dir: Path, names: tuple[str, ...]) -> dict[str, Path]:
    resolved: dict[str, Path] = {}
    for name in names:
        path = base_dir / name
        path.mkdir(parents=True, exist_ok=True)
        resolved[name] = path
    return resolved


def initialize_project_layout(
    project_root: Path | str,
    *,
    ensure: bool = False,
    project_id: str | None = None,
) -> dict[str, object]:
    root = Path(project_root).expanduser().resolve()
    if not root.exists():
        raise CliError(f"project root does not exist: {root}")
    if not root.is_dir():
        raise CliError(f"project root is not a directory: {root}")

    paths = local_storage_paths(root)
    marker_path = paths["project_marker"]
    config_path = paths["config"]
    marker_created = False

    marker_payload: dict[str, object]
    if marker_path.exists():
        marker_payload = load_project_marker(marker_path)
        normalized_project_id = _normalize_project_id(project_id) if project_id is not None else None
        if normalized_project_id is not None and marker_payload.get("project_id") != normalized_project_id:
            raise CliError("project already initialized with a different project_id")
        if not ensure:
            raise CliError(f"agentos project already initialized: {marker_path}")
    else:
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_payload = {
            "class": "agentos.project",
            "schema_version": PROJECT_SCHEMA_VERSION,
            "project_id": _normalize_project_id(project_id),
            "created_at": _utc_now_iso(),
        }
        marker_path.write_text(json.dumps(marker_payload, indent=2) + "\n", encoding="utf-8")
        marker_created = True

    dirs = _ensure_named_dirs(paths["agentos_dir"], PROJECT_DIR_NAMES)
    config_created = _ensure_json_file(
        config_path,
        {"class": "agentos.project.config", "schema_version": PROJECT_SCHEMA_VERSION},
    )

    return {
        "project_root": root,
        "agentos_dir": paths["agentos_dir"],
        "marker_path": marker_path,
        "marker": marker_payload,
        "marker_created": marker_created,
        "config_path": config_path,
        "config_created": config_created,
        "dirs": dirs,
    }


def initialize_global_layout(
    *,
    ensure: bool = False,
    home_dir: Path | None = None,
) -> dict[str, object]:
    base = agentos_home_dir() if home_dir is None else home_dir.expanduser().resolve()
    paths = global_storage_paths(base)
    config_path = paths["config"]
    config_created = False

    config_payload: dict[str, object]
    if config_path.exists():
        config_payload = load_global_config(config_path)
        if not ensure:
            raise CliError(f"agentos global home already initialized: {base}")
    else:
        base.mkdir(parents=True, exist_ok=True)
        config_payload = {"class": "agentos.global.config", "schema_version": GLOBAL_SCHEMA_VERSION}
        config_created = _ensure_json_file(config_path, config_payload)

    dirs = _ensure_named_dirs(base, GLOBAL_DIR_NAMES)

    return {
        "agentos_dir": base,
        "config_path": config_path,
        "config": config_payload,
        "config_created": config_created,
        "dirs": dirs,
    }
