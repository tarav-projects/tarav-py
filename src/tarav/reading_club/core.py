"""Thin logistical model for Tarav.Reading.Club."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
from typing import Any

from tarav.l0._core.data_root import default_tarav_data_root


READING_PROJECT_CLASS = "Tarav.Reading.Project"
READING_PROJECT_SCHEMA_VERSION = 1


class ReadingClubError(Exception):
    """Raised when a Reading Club surface cannot be read safely."""


def default_reading_club_root() -> Path:
    return default_tarav_data_root() / "reading-club"


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReadingClubError(f"{field} must be a non-empty string")
    return value


def _relative_path(value: object, *, field: str) -> Path:
    text = _text(value, field=field)
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts:
        raise ReadingClubError(f"{field} must stay inside its Reading Project")
    return Path(*path.parts)


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReadingClubError(f"cannot read Reading Project manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReadingClubError(f"Reading Project manifest must be an object: {path}")
    return value


@dataclass(frozen=True, slots=True)
class ReadingProject:
    root: Path
    slug: str
    title: str
    status: str
    tags: tuple[str, ...]
    transcript_name: Path
    notes_name: Path | None = None
    source: str | None = None

    @classmethod
    def read(cls, root: Path) -> ReadingProject:
        resolved = root.expanduser().resolve()
        manifest_path = resolved / "project.json"
        data = _read_manifest(manifest_path)
        if (
            data.get("class") != READING_PROJECT_CLASS
            or data.get("schema_version") != READING_PROJECT_SCHEMA_VERSION
        ):
            raise ReadingClubError(f"unsupported Reading Project manifest: {manifest_path}")

        slug = _text(data.get("slug"), field="slug")
        if slug != resolved.name:
            raise ReadingClubError(
                f"Reading Project slug must match its directory: {slug} != {resolved.name}"
            )
        raw_tags = data.get("tags", [])
        if not isinstance(raw_tags, list):
            raise ReadingClubError("tags must be an array")
        tags = tuple(_text(item, field="tags[]") for item in raw_tags)
        transcript_name = _relative_path(data.get("transcript"), field="transcript")
        notes_value = data.get("notes")
        notes_name = (
            _relative_path(notes_value, field="notes")
            if notes_value is not None
            else None
        )
        source_value = data.get("source")
        source = _text(source_value, field="source") if source_value is not None else None
        project = cls(
            root=resolved,
            slug=slug,
            title=_text(data.get("title"), field="title"),
            status=_text(data.get("status"), field="status"),
            tags=tags,
            transcript_name=transcript_name,
            notes_name=notes_name,
            source=source,
        )
        if not project.transcript.is_file():
            raise ReadingClubError(f"Reading Project transcript is missing: {project.transcript}")
        if project.notes is not None and not project.notes.is_file():
            raise ReadingClubError(f"Reading Project notes are missing: {project.notes}")
        return project

    @property
    def transcript(self) -> Path:
        return self.root / self.transcript_name

    @property
    def notes(self) -> Path | None:
        return self.root / self.notes_name if self.notes_name is not None else None

    def matches(self, query: str) -> bool:
        needle = query.casefold()
        values = (self.slug, self.title, self.status, *self.tags)
        if self.source is not None:
            values += (self.source,)
        return any(needle in value.casefold() for value in values)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "slug": self.slug,
            "title": self.title,
            "status": self.status,
            "tags": list(self.tags),
            "root": str(self.root),
            "transcript": str(self.transcript),
            "notes": str(self.notes) if self.notes is not None else None,
        }
        if self.source is not None:
            payload["source"] = self.source
        return payload


@dataclass(frozen=True, slots=True)
class ReadingClub:
    root: Path

    @classmethod
    def open(cls, root: Path | None = None) -> ReadingClub:
        resolved = (root or default_reading_club_root()).expanduser().resolve()
        if not (resolved / "projects").is_dir():
            raise ReadingClubError(f"Reading Club is not initialized: {resolved}")
        return cls(resolved)

    def projects(self, *, include_inactive: bool = False) -> tuple[ReadingProject, ...]:
        projects = tuple(
            ReadingProject.read(path)
            for path in sorted((self.root / "projects").iterdir())
            if path.is_dir() and (path / "project.json").is_file()
        )
        if include_inactive:
            return projects
        return tuple(item for item in projects if item.status.casefold() == "active")

    def find(
        self, query: str, *, include_inactive: bool = False
    ) -> tuple[ReadingProject, ...]:
        needle = _text(query, field="query")
        return tuple(
            item
            for item in self.projects(include_inactive=include_inactive)
            if item.matches(needle)
        )

    def project(self, slug: str) -> ReadingProject:
        selector = _text(slug, field="project")
        if Path(selector).name != selector:
            raise ReadingClubError("project must be an exact Reading Project slug")
        path = self.root / "projects" / selector
        if not (path / "project.json").is_file():
            raise ReadingClubError(f"Reading Project does not exist: {selector}")
        return ReadingProject.read(path)
