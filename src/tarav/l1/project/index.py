"""Machine-local observations of portable Project identities and their locations."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock

from tarav.l0._core.errors import CliError
from tarav.l0._core.home import tarav_home_dir
from tarav.l0._core.persistence import atomic_write_json
from tarav.l0.project import load_project_marker, project_marker_name, project_marker_path

_LOG = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# tarav.breadcrumb 0e66eab5c87f
class ProjectIndex:
    """An observed-location index; Project markers remain the authority."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or tarav_home_dir() / "projects.json"

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {"schema_version": 1, "projects": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CliError(f"Cannot read global Project index {self.path}: {exc}") from exc
        if (not isinstance(data, dict) or data.get("schema_version") != 1
                or not isinstance(data.get("projects"), dict)):
            raise CliError(f"Invalid global Project index: {self.path}")
        return data

    def observe(self, root: Path | str) -> None:
        """Record an existing Project at its current path, preserving older paths."""
        project_root = Path(root).expanduser().resolve()
        marker = load_project_marker(project_marker_path(project_root))
        project_id = str(marker["project_id"])
        name = project_marker_name(marker) or project_root.name
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.path) + ".lock"):
            data = self._read()
            projects = data["projects"]
            assert isinstance(projects, dict)
            entry = projects.setdefault(project_id, {"name": name, "locations": {}})
            if not isinstance(entry, dict) or not isinstance(entry.get("locations"), dict):
                raise CliError(f"Invalid global Project index entry for {project_id}")
            entry["name"] = name
            entry["locations"][str(project_root)] = _now()
            atomic_write_json(self.path, data)

    def list(self) -> list[dict[str, object]]:
        """Return observed IDs and validate each remembered location now."""
        projects = self._read()["projects"]
        assert isinstance(projects, dict)
        rows = []
        for project_id, entry in sorted(projects.items()):
            if not isinstance(entry, dict) or not isinstance(entry.get("locations"), dict):
                raise CliError(f"Invalid global Project index entry for {project_id}")
            locations = []
            for path, seen_at in sorted(entry["locations"].items()):
                marker_path = project_marker_path(Path(path))
                if not marker_path.is_file():
                    status = "missing"
                else:
                    try:
                        actual = load_project_marker(marker_path)
                        status = "present" if str(actual["project_id"]) == project_id else "different-id"
                    except (OSError, ValueError, CliError):
                        status = "unreadable"
                locations.append({"path": path, "last_seen_at": seen_at, "status": status})
            present = sum(item["status"] == "present" for item in locations)
            rows.append({"project_id": project_id, "name": entry.get("name"),
                         "status": "ambiguous" if present > 1 else
                                   "present" if present == 1 else "unavailable",
                         "locations": locations})
        return rows


def observe_project(root: Path | str) -> None:
    """Best-effort CLI notification; never change the foreground operation."""
    try:
        ProjectIndex().observe(root)
    except Exception:
        _LOG.warning("Could not update global Project index", exc_info=True)


__all__ = ["ProjectIndex", "observe_project"]
