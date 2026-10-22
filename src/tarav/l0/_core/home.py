"""The Tarav home: `~/.tarav` (or `$TARAV_HOME`), its global config and storage.

The `.tarav` directory layout helpers here are shared with Project layout.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from tarav.l0._core.errors import CliError

TARAV_DIRNAME = ".tarav"
GLOBAL_CONFIG_FILENAME = "config.json"
GLOBAL_SCHEMA_VERSION = 1
GLOBAL_CONFIG_CLASS = "tarav.global.config"
# Homes initialized before the Agentos rename keep loading until their config is rewritten.
# tarav.context bbf9a2bc:52dc459d3a7ab9db
_READABLE_GLOBAL_CONFIG_CLASSES = frozenset({GLOBAL_CONFIG_CLASS, "agentos.global.config"})
GLOBAL_STORAGE_DIR_NAMES = ("indexes", "tmp", "cache")


def tarav_home_dir() -> Path:
    env_home = os.getenv("TARAV_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    return (Path.home() / TARAV_DIRNAME).resolve()


def home_path_str(home: Path | str | None) -> str | None:
    """Stringify a home path for logging — expanded, with a best-effort fallback."""
    if home is None:
        return None
    try:
        return str(Path(home).expanduser())
    except Exception:
        return str(home)


def global_config_path(home_dir: Path | None = None) -> Path:
    root = tarav_home_dir() if home_dir is None else home_dir
    return root / GLOBAL_CONFIG_FILENAME


def storage_dir_paths(base: Path, names: tuple[str, ...]) -> dict[str, Path]:
    return {name: base / name for name in names}


def global_storage_paths(home_dir: Path | None = None) -> dict[str, Path]:
    base = tarav_home_dir() if home_dir is None else home_dir
    return {
        "tarav_dir": base,
        "config": global_config_path(base),
        **storage_dir_paths(base, GLOBAL_STORAGE_DIR_NAMES),
    }


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
    if payload.get("class") not in _READABLE_GLOBAL_CONFIG_CLASSES:
        raise CliError(f"global config field class must be '{GLOBAL_CONFIG_CLASS}'")
    return payload


def ensure_json_file(path: Path, payload: dict[str, object]) -> bool:
    if path.exists():
        if not path.is_file():
            raise CliError(f"path exists but is not a file: {path}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return True


def ensure_named_dirs(base_dir: Path, names: tuple[str, ...]) -> dict[str, Path]:
    resolved: dict[str, Path] = {}
    for name in names:
        path = base_dir / name
        path.mkdir(parents=True, exist_ok=True)
        resolved[name] = path
    return resolved


def initialize_global_layout(
    *,
    ensure: bool = False,
    home_dir: Path | None = None,
) -> dict[str, object]:
    base = tarav_home_dir() if home_dir is None else home_dir.expanduser().resolve()
    paths = global_storage_paths(base)
    config_path = paths["config"]
    config_created = False

    config_payload: dict[str, object]
    if config_path.exists():
        config_payload = load_global_config(config_path)
        if not ensure:
            raise CliError(f"tarav global home already initialized: {base}")
    else:
        base.mkdir(parents=True, exist_ok=True)
        config_payload = {"class": GLOBAL_CONFIG_CLASS, "schema_version": GLOBAL_SCHEMA_VERSION}
        config_created = ensure_json_file(config_path, config_payload)

    dirs = ensure_named_dirs(base, GLOBAL_STORAGE_DIR_NAMES)

    return {
        "tarav_dir": base,
        "config_path": config_path,
        "config": config_payload,
        "config_created": config_created,
        "dirs": dirs,
    }
