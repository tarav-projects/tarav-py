# $kw: --from Agentos.Project
"""Project mechanics below the Project Type: marker, config, discovery, layout.

The Project namespace spans layers: this module is its lowest part, usable by
any workflow; `tarav.l1.project` holds the Project Type, `tarav.l2.project` its
integrations with other workflows, `tarav.l3.project` launch and bootstrap.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from tarav.l0._core.errors import CliError
from tarav.l0._core.clock import utc_now_iso as _utc_now_iso
from tarav.l0._core.home import (
    TARAV_DIRNAME,
    ensure_json_file,
    ensure_named_dirs,
    global_storage_paths,
    storage_dir_paths,
    tarav_home_dir,
)
from tarav.l0._core.ids import normalize_or_generate_uuid

PROJECT_MARKER_FILENAME = "project.json"
PROJECT_CONFIG_FILENAME = "config.json"
SCOPE_VALUES = ("project", "global", "auto")
PROJECT_STORAGE_DIR_NAMES = ("indexes", "tmp", "state")
TARAV_PROJECT_ID = "e308d11f-d709-4f23-b8c7-f214e28b3f11"


def project_agentos_dir(project_root: Path) -> Path:
    return project_root / TARAV_DIRNAME


def project_marker_path(project_root: Path) -> Path:
    return project_agentos_dir(project_root) / PROJECT_MARKER_FILENAME


def project_config_path(project_root: Path) -> Path:
    return project_agentos_dir(project_root) / PROJECT_CONFIG_FILENAME


# tarav.breadcrumb aed40d92e487
# tarav.breadcrumb 18fbfa2c450b
class ProjectHarnessConfig(BaseModel):
    """How a Project starts: the environment that runs it and its Type there.

    `environment` is a uv environment, relative to the Project's root; it may
    be another Project's. `type` is `module:Class`, imported from a package
    installed in that environment.
    """

    model_config = ConfigDict(strict=True, extra="forbid")
    environment: str
    type: str

    @field_validator("environment")
    @classmethod
    def _relative(cls, value: str) -> str:
        if not value or Path(value).is_absolute():
            raise ValueError("harness environment must be a path relative to the Project root")
        return value

    @field_validator("type")
    @classmethod
    def _import_path(cls, value: str) -> str:
        module, _, name = value.partition(":")
        if not module or not name or not all(
                part.isidentifier() for part in (*module.split("."), name)):
            raise ValueError("harness type must be module:Class")
        return value


class TaravProjectHandler:
    def __init__(self, root: Path | str):
        self.root = normalize_project_target(root)
        self._project_json: dict[str, object] | None = None

    @property
    def tarav_dir(self) -> Path:
        return project_agentos_dir(self.root)

    @property
    def marker_path(self) -> Path:
        return project_marker_path(self.root)

    @property
    def config_path(self) -> Path:
        return project_config_path(self.root)

    @property
    def project_json(self) -> dict[str, object]:
        if self._project_json is None:
            self._project_json = load_project_marker(self.marker_path)
        return self._project_json

    @property
    def project_id(self) -> str:
        return str(self.project_json["project_id"])

    @property
    def project_name(self) -> str:
        declared_name = project_marker_name(self.project_json)
        if declared_name is not None:
            return declared_name
        return self.root.name

    def require_marker(
        self,
        *,
        include_init_hint: bool = True,
        extra_hint: str | None = None,
    ) -> "TaravProjectHandler":
        if not self.marker_path.is_file():
            raise CliError(
                build_not_inside_project_message(
                    include_init_hint=include_init_hint,
                    extra_hint=extra_hint,
                )
            )
        return self

    def validate(self) -> "TaravProjectHandler":
        self._project_json = self.project_json
        return self


def find_agentos_project(start_path: Path | str = ".") -> TaravProjectHandler | None:
    current = Path(start_path).expanduser().resolve()
    if current.is_file():
        current = current.parent

    while True:
        if project_marker_path(current).is_file():
            return TaravProjectHandler(current)
        parent = current.parent
        if parent == current:
            return None
        current = parent


def find_agentos_project_root(start_path: Path | str = ".") -> Path | None:
    project = find_agentos_project(start_path)
    if project is None:
        return None
    return project.root


def find_agentos_project_roots_under(root: Path | str) -> list[Path]:
    search_root = Path(root).expanduser().resolve()
    if not search_root.exists():
        raise CliError(f"project discovery root does not exist: {search_root}")
    if not search_root.is_dir():
        raise CliError(f"project discovery root is not a directory: {search_root}")

    project_roots = {
        marker.parent.parent.resolve()
        for marker in search_root.rglob(PROJECT_MARKER_FILENAME)
        if marker.parent.name == TARAV_DIRNAME and marker.is_file()
    }
    return sorted(project_roots)


def find_agentos_project_roots_within(
    root: Path | str,
    *,
    max_depth: int,
) -> list[Path]:
    """Discover tarav project roots at or below ``root``, bounded by ``max_depth``.

    ``root`` itself is depth 0; a project at ``<root>/a/b`` is depth 2. ``max_depth``
    of 0 inspects only ``root``. Dotted and symlinked directories are not descended.
    """
    if max_depth < 0:
        raise CliError(f"project discovery max_depth must be non-negative: {max_depth}")

    search_root = Path(root).expanduser().resolve()
    if not search_root.exists():
        raise CliError(f"project discovery root does not exist: {search_root}")
    if not search_root.is_dir():
        raise CliError(f"project discovery root is not a directory: {search_root}")

    project_roots: set[Path] = set()
    frontier: list[tuple[Path, int]] = [(search_root, 0)]
    while frontier:
        directory, depth = frontier.pop()
        if project_marker_path(directory).is_file():
            project_roots.add(directory)
        if depth >= max_depth:
            continue
        for child in sorted(directory.iterdir(), key=lambda path: path.name):
            if child.name.startswith(".") or child.is_symlink() or not child.is_dir():
                continue
            frontier.append((child, depth + 1))

    return sorted(project_roots)


def normalize_project_target(project_path: Path | str = ".") -> Path:
    current = Path(project_path).expanduser().resolve()
    if current.is_file():
        return current.parent
    return current


def resolve_agentos_project(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
) -> TaravProjectHandler | None:
    if project is not None:
        return TaravProjectHandler(project)
    return find_agentos_project(start_path)


def require_explicit_project_target(
    project: Path | str | None,
    *,
    command_name: str,
) -> Path | str:
    if project is None:
        raise CliError(f"{command_name} requires --project")
    return project


def require_explicit_project_selector(
    project: Path | str | None,
    project_base: str | None,
    *,
    command_name: str,
) -> None:
    if project is None and project_base is None:
        raise CliError(f"{command_name} requires --project or --project-base")


def project_marker_name(marker: dict[str, object]) -> str | None:
    raw_name = marker.get("project_name")
    if isinstance(raw_name, str) and raw_name.strip():
        return raw_name.strip()
    return None


def assert_project_base(
    project: TaravProjectHandler,
    expected_base: str | None,
) -> None:
    if expected_base is None:
        return
    expected = str(expected_base).strip()
    if not expected:
        raise CliError("project base assertion must not be empty")

    actual = project.root.name
    if actual != expected:
        raise CliError(
            "project base assertion failed: "
            f"expected {expected!r}, resolved {actual!r} at {project.root}"
        )


def require_explicit_agentos_project(
    *,
    project: Path | str | None,
    command_name: str,
    project_base: str | None = None,
    include_init_hint: bool = True,
) -> TaravProjectHandler:
    require_explicit_project_selector(project, project_base, command_name=command_name)
    resolved_project = require_agentos_project(
        start_path=Path.cwd(),
        project=project,
        include_init_hint=include_init_hint,
    )
    assert_project_base(resolved_project, project_base)
    return resolved_project


def add_explicit_project_arguments(
    parser: argparse.ArgumentParser,
    *,
    project_help: str,
) -> None:
    parser.add_argument(
        "--project",
        nargs="?",
        type=Path,
        const=Path("."),
        default=None,
        help=project_help,
    )
    parser.add_argument(
        "--project-base",
        default=None,
        help="Assert the resolved project root basename after project discovery or --project resolution.",
    )


def resolve_project_target(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
) -> Path | None:
    resolved_project = resolve_agentos_project(start_path, project=project)
    if resolved_project is None:
        return None
    return resolved_project.root


def build_not_inside_project_message(
    *,
    include_init_hint: bool = False,
    extra_hint: str | None = None,
    git_style: bool = False,
) -> str:
    message = "not inside a tarav project (missing .tarav/project.json)"
    hints: list[str] = []
    if include_init_hint:
        hints.append("run `tarav project init`")
    if extra_hint is not None:
        hints.append(str(extra_hint))

    if hints:
        message = f"{message}; " + " or ".join(hints)
    if git_style:
        return f"fatal: {message}"
    return message


def require_agentos_project(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
    include_init_hint: bool = True,
    extra_hint: str | None = None,
) -> TaravProjectHandler:
    resolved_project = resolve_agentos_project(start_path, project=project)
    if resolved_project is None:
        raise CliError(
            build_not_inside_project_message(
                include_init_hint=include_init_hint,
                extra_hint=extra_hint,
            )
        )
    return resolved_project.require_marker(
        include_init_hint=include_init_hint,
        extra_hint=extra_hint,
    )


def require_agentos_project_root(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
    include_init_hint: bool = True,
    extra_hint: str | None = None,
) -> Path:
    return require_agentos_project(
        start_path,
        project=project,
        include_init_hint=include_init_hint,
        extra_hint=extra_hint,
    ).root


def resolve_scope_agentos_dir(
    scope: str,
    *,
    start_path: Path | str = ".",
) -> tuple[str, Path, Path | None]:
    normalized_scope = str(scope).strip().lower()
    if normalized_scope not in SCOPE_VALUES:
        raise CliError(f"unsupported scope '{scope}' (expected one of: {', '.join(SCOPE_VALUES)})")

    if normalized_scope == "global":
        return ("global", tarav_home_dir(), None)

    project_root = find_agentos_project_root(start_path)
    if normalized_scope == "project":
        if project_root is None:
            raise CliError(build_not_inside_project_message())
        return ("project", project_agentos_dir(project_root), project_root)

    if project_root is not None:
        return ("project", project_agentos_dir(project_root), project_root)
    return ("global", tarav_home_dir(), None)


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


def local_storage_paths(project_root: Path) -> dict[str, Path]:
    base = project_agentos_dir(project_root)
    return {
        "tarav_dir": base,
        "project_marker": project_marker_path(project_root),
        "config": project_config_path(project_root),
        **storage_dir_paths(base, PROJECT_STORAGE_DIR_NAMES),
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

    project_id = str(payload.get("project_id", "")).strip()
    if not project_id:
        raise CliError("project marker field project_id is required")
    try:
        UUID(project_id)
    except ValueError as exc:
        raise CliError(f"project marker project_id is not a valid UUID: {project_id}") from exc
    return payload


def project_id(project_root: Path | str) -> str:
    """The UUID that identifies the Project at ``project_root``, read from its marker.

    POI situations name a Project by it, never by its path, which changes when
    the folder moves.
    """
    return str(load_project_marker(project_marker_path(Path(project_root)))["project_id"])


def load_project_config(config_path: Path) -> dict[str, object]:
    if not config_path.exists():
        raise CliError(f"project config does not exist: {config_path}")
    if not config_path.is_file():
        raise CliError(f"project config path is not a file: {config_path}")
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid project config JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CliError("project config must be a JSON object")
    return payload


def _normalize_project_id(project_id: str | None) -> str:
    return normalize_or_generate_uuid(project_id, field_name="project id")


def initialize_project_layout(
    project_root: Path | str,
    *,
    ensure: bool = False,
    project_id: str | None = None,
    project_name: str | None = None,
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
        normalized_project_name = str(project_name).strip() if project_name is not None else None
        if normalized_project_name and project_marker_name(marker_payload) != normalized_project_name:
            raise CliError("project already initialized with a different project_name")
        if not ensure:
            raise CliError(f"tarav project already initialized: {marker_path}")
    else:
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_payload = {
            "project_id": _normalize_project_id(project_id),
            "created_at": _utc_now_iso(),
        }
        normalized_project_name = str(project_name).strip() if project_name is not None else None
        if normalized_project_name:
            marker_payload["project_name"] = normalized_project_name
        marker_path.write_text(json.dumps(marker_payload, indent=2) + "\n", encoding="utf-8")
        marker_created = True

    dirs = ensure_named_dirs(paths["tarav_dir"], PROJECT_STORAGE_DIR_NAMES)
    config_created = ensure_json_file(config_path, {})

    return {
        "project_root": root,
        "tarav_dir": paths["tarav_dir"],
        "marker_path": marker_path,
        "marker": marker_payload,
        "marker_created": marker_created,
        "config_path": config_path,
        "config_created": config_created,
        "dirs": dirs,
    }
