from __future__ import annotations

import fcntl
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from agentos._core.clock import utc_now_iso
from agentos._core.errors import CliError
from agentos._core.ids import normalize_or_generate_uuid, validate_uuid_string
from agentos._core.project import (
    agentos_home_dir,
    load_project_marker,
    project_marker_path,
    require_agentos_project_root,
)

FORUM_SCHEMA_VERSION = 1
FORUM_DIRNAME = "forum"
FORUM_PROJECTS_DIRNAME = "projects"
FORUM_PROJECT_CLASS = "agentos.forum.project"
FORUM_EVENT_CLASS = "agentos.forum.event"
FORUM_PROJECT_MANIFEST_FILENAME = "project.json"
FORUM_EVENTS_FILENAME = "events.jsonl"
VALID_FORUM_EVENT_TYPES = ("post", "reply", "reaction")
VALID_FORUM_REACTIONS = ("ack", "like", "watch", "concern")


@dataclass(frozen=True)
class LocatedForumEvent:
    source_file: Path
    line_no: int
    event: dict[str, object]


def forum_root() -> Path:
    return agentos_home_dir() / FORUM_DIRNAME


def forum_projects_dir() -> Path:
    return forum_root() / FORUM_PROJECTS_DIRNAME


def forum_project_dir(project_id: str) -> Path:
    normalized_project_id = validate_uuid_string(project_id, field_name="project id")
    return forum_projects_dir() / normalized_project_id


def forum_project_manifest_path(project_id: str) -> Path:
    return forum_project_dir(project_id) / FORUM_PROJECT_MANIFEST_FILENAME


def forum_project_events_path(project_id: str) -> Path:
    return forum_project_dir(project_id) / FORUM_EVENTS_FILENAME


def current_author_project(start_path: Path | str = ".") -> dict[str, object]:
    project_root = require_agentos_project_root(start_path, include_init_hint=True)
    marker = load_project_marker(project_marker_path(project_root))
    return {
        "project_id": str(marker["project_id"]),
        "project_root": project_root,
        "source_root": str(project_root),
        "display_name": project_root.name,
        "marker": marker,
    }


def load_or_register_forum_project(project_identity: dict[str, object]) -> dict[str, object]:
    normalized_identity = _normalize_project_identity(project_identity)
    manifest_path = forum_project_manifest_path(normalized_identity["project_id"])
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    now = utc_now_iso()
    if manifest_path.exists():
        manifest = _load_forum_project_manifest(manifest_path)
        manifest["display_name"] = normalized_identity["display_name"]
        manifest["source_root"] = normalized_identity["source_root"]
        manifest["last_seen_at"] = now
    else:
        manifest = {
            "class": FORUM_PROJECT_CLASS,
            "schema_version": FORUM_SCHEMA_VERSION,
            "project_id": normalized_identity["project_id"],
            "display_name": normalized_identity["display_name"],
            "source_root": normalized_identity["source_root"],
            "created_at": now,
            "last_seen_at": now,
        }

    _write_json(manifest_path, manifest)
    return dict(manifest)


def append_forum_event(author_project_id: str, event: dict[str, object]) -> dict[str, object]:
    normalized_author_project_id = validate_uuid_string(author_project_id, field_name="author project id")
    normalized_event = _normalize_forum_event(event)
    if normalized_event["author_project_id"] != normalized_author_project_id:
        raise CliError(
            "forum event author_project_id must match the target author project log"
        )

    events_path = forum_project_events_path(normalized_author_project_id)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    _append_jsonl_line(events_path, normalized_event)
    return dict(normalized_event)


def iter_all_forum_events() -> Iterator[LocatedForumEvent]:
    projects_dir = forum_projects_dir()
    if not projects_dir.exists():
        return
    if not projects_dir.is_dir():
        raise CliError(f"forum projects path is not a directory: {projects_dir}")

    for project_dir in sorted(child for child in projects_dir.iterdir() if child.is_dir()):
        author_project_id = project_dir.name
        validate_uuid_string(author_project_id, field_name="forum project directory")
        events_path = project_dir / FORUM_EVENTS_FILENAME
        if not events_path.exists():
            continue
        if not events_path.is_file():
            raise CliError(f"forum events path is not a file: {events_path}")

        with events_path.open("r", encoding="utf-8") as handle:
            for line_no, raw_line in enumerate(handle, start=1):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                payload = _parse_json_object_line(stripped, path=events_path, line_no=line_no)
                event = _normalize_forum_event(payload, source_name=f"{events_path.name}:{line_no}")
                if event["author_project_id"] != author_project_id:
                    raise CliError(
                        "forum event author_project_id does not match containing project log: "
                        f"{events_path}:{line_no}"
                    )
                yield LocatedForumEvent(
                    source_file=events_path,
                    line_no=line_no,
                    event=event,
                )


def load_forum_event(event_id: str) -> LocatedForumEvent:
    normalized_event_id = validate_uuid_string(event_id, field_name="event id")
    matched: LocatedForumEvent | None = None
    for located in iter_all_forum_events():
        if located.event["event_id"] != normalized_event_id:
            continue
        if matched is not None:
            raise CliError(f"duplicate forum event id found: {normalized_event_id}")
        matched = located
    if matched is None:
        raise CliError(f"forum event not found: {normalized_event_id}")
    return matched


def _normalize_project_identity(project_identity: dict[str, object]) -> dict[str, str]:
    if not isinstance(project_identity, dict):
        raise CliError("forum project identity must be a JSON object")

    project_id = validate_uuid_string(
        str(project_identity.get("project_id", "")).strip(),
        field_name="project id",
    )

    source_root_value = project_identity.get("source_root")
    if source_root_value is None:
        project_root_value = project_identity.get("project_root")
        if project_root_value is None:
            raise CliError("forum project identity source_root is required")
        source_root = str(Path(project_root_value).expanduser().resolve())
    else:
        source_root = str(Path(source_root_value).expanduser().resolve())

    display_name = str(project_identity.get("display_name", "")).strip()
    if not display_name:
        display_name = Path(source_root).name
    if not display_name:
        raise CliError("forum project identity display_name must not be empty")

    return {
        "project_id": project_id,
        "display_name": display_name,
        "source_root": source_root,
    }


def _load_forum_project_manifest(path: Path) -> dict[str, object]:
    payload = _read_json(path)
    if payload.get("class") != FORUM_PROJECT_CLASS:
        raise CliError(f"invalid forum project manifest: {path.name}")

    project_id = validate_uuid_string(
        str(payload.get("project_id", "")).strip(),
        field_name="forum project id",
    )
    display_name = str(payload.get("display_name", "")).strip()
    if not display_name:
        raise CliError(f"forum project manifest display_name is required: {path.name}")
    source_root = str(payload.get("source_root", "")).strip()
    if not source_root:
        raise CliError(f"forum project manifest source_root is required: {path.name}")
    created_at = _normalize_timestamp(
        payload.get("created_at"),
        field_name="forum project manifest created_at",
        default_now=False,
    )
    last_seen_at = _normalize_timestamp(
        payload.get("last_seen_at"),
        field_name="forum project manifest last_seen_at",
        default_now=False,
    )

    return {
        "class": FORUM_PROJECT_CLASS,
        "schema_version": FORUM_SCHEMA_VERSION,
        "project_id": project_id,
        "display_name": display_name,
        "source_root": str(Path(source_root).expanduser().resolve()),
        "created_at": created_at,
        "last_seen_at": last_seen_at,
    }


def _normalize_forum_event(
    event: dict[str, object],
    *,
    source_name: str = "forum event",
) -> dict[str, object]:
    if not isinstance(event, dict):
        raise CliError(f"{source_name} must be a JSON object")
    event_class = str(event.get("class", FORUM_EVENT_CLASS)).strip()
    if event_class != FORUM_EVENT_CLASS:
        raise CliError(f"{source_name} field class must be '{FORUM_EVENT_CLASS}'")

    event_id = normalize_or_generate_uuid(event.get("event_id"), field_name="event id")
    event_type = str(event.get("event_type", "")).strip()
    if event_type not in VALID_FORUM_EVENT_TYPES:
        raise CliError(
            f"{source_name} event_type must be one of: {', '.join(VALID_FORUM_EVENT_TYPES)}"
        )

    created_at = _normalize_timestamp(
        event.get("created_at"),
        field_name="created_at",
        default_now=source_name == "forum event",
    )
    author_project_id = validate_uuid_string(
        str(event.get("author_project_id", "")).strip(),
        field_name="author project id",
    )
    channel_project_id = validate_uuid_string(
        str(event.get("channel_project_id", "")).strip(),
        field_name="channel project id",
    )
    thread_root_post_id = validate_uuid_string(
        str(event.get("thread_root_post_id", "")).strip(),
        field_name="thread root post id",
    )
    parent_post_id = _normalize_optional_uuid(event.get("parent_post_id"), field_name="parent post id")
    target_post_id = _normalize_optional_uuid(event.get("target_post_id"), field_name="target post id")
    ref_post_ids = _normalize_uuid_list(event.get("ref_post_ids", []), field_name="ref_post_ids")
    refs = _normalize_refs(event.get("refs", []))
    reaction = _normalize_optional_string(event.get("reaction"))
    body = _normalize_body(event.get("body"))

    normalized = {
        "class": FORUM_EVENT_CLASS,
        "schema_version": FORUM_SCHEMA_VERSION,
        "event_id": event_id,
        "event_type": event_type,
        "created_at": created_at,
        "author_project_id": author_project_id,
        "channel_project_id": channel_project_id,
        "thread_root_post_id": thread_root_post_id,
        "parent_post_id": parent_post_id,
        "target_post_id": target_post_id,
        "ref_post_ids": ref_post_ids,
        "refs": refs,
        "reaction": reaction,
        "body": body,
    }
    _validate_event_type_fields(normalized, source_name=source_name)
    return normalized


def _validate_event_type_fields(event: dict[str, object], *, source_name: str) -> None:
    event_type = str(event["event_type"])
    event_id = str(event["event_id"])
    author_project_id = str(event["author_project_id"])
    channel_project_id = str(event["channel_project_id"])
    thread_root_post_id = str(event["thread_root_post_id"])
    parent_post_id = event.get("parent_post_id")
    target_post_id = event.get("target_post_id")
    reaction = event.get("reaction")
    body = event.get("body")

    if event_type == "post":
        if author_project_id != channel_project_id:
            raise CliError(
                f"{source_name} top-level posts must use the author's own main channel"
            )
        if thread_root_post_id != event_id:
            raise CliError(f"{source_name} post thread_root_post_id must equal event_id")
        if parent_post_id is not None:
            raise CliError(f"{source_name} post parent_post_id must be null")
        if target_post_id is not None:
            raise CliError(f"{source_name} post target_post_id must be null")
        if reaction is not None:
            raise CliError(f"{source_name} post reaction must be null")
        if body is None:
            raise CliError(f"{source_name} post body is required")
        return

    if event_type == "reply":
        if parent_post_id is None:
            raise CliError(f"{source_name} reply parent_post_id is required")
        if target_post_id is not None:
            raise CliError(f"{source_name} reply target_post_id must be null")
        if reaction is not None:
            raise CliError(f"{source_name} reply reaction must be null")
        if body is None:
            raise CliError(f"{source_name} reply body is required")
        return

    if target_post_id is None:
        raise CliError(f"{source_name} reaction target_post_id is required")
    if parent_post_id is not None:
        raise CliError(f"{source_name} reaction parent_post_id must be null")
    if reaction is None:
        raise CliError(f"{source_name} reaction name is required")
    if reaction not in VALID_FORUM_REACTIONS:
        raise CliError(
            f"{source_name} reaction must be one of: {', '.join(VALID_FORUM_REACTIONS)}"
        )
    if body is not None:
        raise CliError(f"{source_name} reaction body must be empty")


def _normalize_timestamp(value: object, *, field_name: str, default_now: bool) -> str:
    if value is None:
        if default_now:
            return utc_now_iso()
        raise CliError(f"{field_name} is required")
    normalized = str(value).strip()
    if not normalized:
        raise CliError(f"{field_name} is required")
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CliError(f"invalid {field_name}: {value}") from exc
    if parsed.tzinfo is None:
        raise CliError(f"invalid {field_name}: {value}")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_optional_uuid(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return validate_uuid_string(normalized, field_name=field_name)


def _normalize_uuid_list(value: object, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise CliError(f"{field_name} must be a JSON array")

    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value, start=1):
        item_uuid = validate_uuid_string(item, field_name=f"{field_name}[{index}]")
        if item_uuid in seen:
            continue
        normalized.append(item_uuid)
        seen.add(item_uuid)
    return normalized


def _normalize_refs(value: object) -> list[object]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise CliError("refs must be a JSON array")
    return list(value)


def _normalize_optional_string(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized


def _normalize_body(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized


def _append_jsonl_line(path: Path, payload: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(json.dumps(payload) + "\n")
            handle.flush()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise CliError(f"forum metadata does not exist: {path}")
    if not path.is_file():
        raise CliError(f"forum metadata path is not a file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON in {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CliError(f"{path.name} must be a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _parse_json_object_line(raw_line: str, *, path: Path, line_no: int) -> dict[str, object]:
    try:
        payload = json.loads(raw_line)
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON object in {path}:{line_no}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CliError(f"{path}:{line_no} must be a JSON object")
    return payload
