# $kw: --from Mission.Env
"""Mission.Env resolution — turn the optional mission.json env field into a launch prefix.

The launch prefix is the argv head used to start the in-env turn runner
(`iterante2._runner`). The harness always runs inside the resolved env as a
subprocess; there is no in-process mode.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _declared_env(mission_dir: Path) -> str | None:
    """Read the optional `env` field from mission.json, if present."""
    manifest = mission_dir / "mission.json"
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(f"invalid mission.json: {e}") from e
    env = data.get("env")
    if env is not None and not isinstance(env, str):
        raise SystemExit("mission.json 'env' must be a string path")
    return env


def resolve_launch_prefix(mission_dir: Path) -> list[str]:
    """Resolve the argv prefix that launches the runner inside the Mission.Env.

    - no env declared -> the CLI's own interpreter (the default Mission.Env)
    - a path to a python executable -> that interpreter directly
    - a path to a uv-project directory (holds pyproject.toml) -> `uv run --project <dir> python`

    Relative env paths resolve against the mission directory.
    """
    env = _declared_env(mission_dir)
    if env is None:
        return [sys.executable]

    ref = Path(env)
    if not ref.is_absolute():
        ref = (mission_dir / ref).resolve()

    if ref.is_dir():
        if (ref / "pyproject.toml").is_file():
            return ["uv", "run", "--project", str(ref), "python"]
        raise SystemExit(f"mission env dir is not a uv project (no pyproject.toml): {ref}")
    if ref.is_file():
        return [str(ref)]
    raise SystemExit(f"mission env not found: {env} (resolved: {ref})")


def ensure_iterante_importable(mission_dir: Path) -> None:
    """Fail fast if the resolved Mission.Env cannot import `iterante2`.

    `iterante2` is the env's only mandatory dependency. Surfaces a clear,
    actionable error naming the env instead of a raw ModuleNotFoundError later.
    """
    prefix = resolve_launch_prefix(mission_dir)
    proc = subprocess.run([*prefix, "-c", "import agentos.iterante2"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(
            f"mission env cannot import 'iterante2' (its only required dependency): "
            f"{' '.join(prefix)}\n  install iterante2 into that env to run this mission"
        )
