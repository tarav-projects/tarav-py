# $kw: --from Agentos.Project
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tarav.l0._core.project import (
    tarav_home_dir,
    load_project_marker,
    project_marker_path,
    require_agentos_project_root,
)

FORUM_ROOT_ENV = "TARAV_FORUM_ROOT"
FORUM_CURSOR_ENV = "TARAV_FORUM_CURSOR"
DEFAULT_FORUM_ROOT = Path("~/Documents/tarav/forum")
POST_HEADING_RE = re.compile(r"^## (?P<time>\d{2}:\d{2}:\d{2})Z — (?P<title>.+)$")


@dataclass(frozen=True)
class PostRef:
    path: Path
    timestamp: str
    title: str


@dataclass(frozen=True)
class Post:
    path: Path
    timestamp: str
    title: str
    body: str
    source: str


class ForumDepot:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = forum_root() if root is None else Path(root).expanduser()

    @property
    def posts_dir(self) -> Path:
        return self.root / "posts"

    def post(self, title: str, body: str, source: str) -> PostRef:
        title = _clean_title(title)
        body = body.rstrip()
        source = str(source).strip() or "unknown"
        now = _utc_now()
        timestamp = _format_timestamp(now)
        path = self.posts_dir / f"{now:%Y-%m-%d}.md"
        section = _format_section(now, title=title, body=body, source=source)
        path.parent.mkdir(parents=True, exist_ok=True)
        _append_text(path, section)
        return PostRef(path=path, timestamp=timestamp, title=title)

    def read_all(self) -> list[Post]:
        return _read_posts_from_files(sorted(self.posts_dir.glob("*.md")))

    def read_date(self, date: str) -> list[Post]:
        _parse_date(date)
        return _read_posts_from_files([self.posts_dir / f"{date}.md"])

    def posts_since(self, timestamp: str | None) -> list[Post]:
        cutoff = _parse_timestamp(timestamp) if timestamp else None
        paths = sorted(self.posts_dir.glob("*.md"))
        if cutoff is not None:
            cutoff_date = cutoff.date()
            filtered_paths = []
            for path in paths:
                path_date = _safe_date_from_path(path)
                if path_date is not None and path_date >= cutoff_date:
                    filtered_paths.append(path)
            paths = filtered_paths
        posts = _read_posts_from_files(paths)
        if cutoff is None:
            return posts
        return [post for post in posts if _parse_timestamp(post.timestamp) > cutoff]


def forum_root() -> Path:
    configured = os.environ.get(FORUM_ROOT_ENV)
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_FORUM_ROOT.expanduser()


def cursor_path() -> Path:
    configured = os.environ.get(FORUM_CURSOR_ENV)
    if configured:
        return Path(configured).expanduser()
    return tarav_home_dir() / "forum-cursor.json"


def read_cursor() -> dict[str, str]:
    path = cursor_path()
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        key: value
        for key in ("last_read", "last_banner")
        if isinstance((value := payload.get(key)), str)
    }


def write_cursor(cursor: dict[str, str]) -> None:
    path = cursor_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cursor, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def mark_read(posts: list[Post]) -> None:
    if not posts:
        return
    cursor = read_cursor()
    cursor["last_read"] = max(post.timestamp for post in posts)
    write_cursor(cursor)


def forum_banner_line() -> str | None:
    try:
        cursor = read_cursor()
        unread = ForumDepot().posts_since(cursor.get("last_read"))
        if not unread:
            return None
        now = _utc_now()
        last_banner = _parse_timestamp(cursor.get("last_banner")) if cursor.get("last_banner") else None
        if last_banner is not None and now - last_banner < timedelta(hours=24):
            return None
        cursor["last_banner"] = _format_timestamp(now)
        write_cursor(cursor)
        count = len(unread)
        return f"tarav forum: {count} unread post(s) — run 'tarav forum check'"
    except Exception:
        return None


def current_post_source(start_path: Path | str = ".", *, override: str | None = None) -> str:
    if override:
        return override
    try:
        project_root = require_agentos_project_root(start_path)
        marker = load_project_marker(project_marker_path(project_root))
        name = str(marker.get("name") or "").strip()
        return name or str(project_root)
    except Exception:
        return str(Path(start_path).resolve())


def _format_section(now: datetime, *, title: str, body: str, source: str) -> str:
    lines = [f"## {now:%H:%M:%S}Z — {title}"]
    if body:
        lines.extend(["", body])
    lines.extend(["", f"- from: {source}", ""])
    return "\n".join(lines) + "\n"


def _append_text(path: Path, text: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    fd = os.open(path, flags, 0o644)
    try:
        handle = os.fdopen(fd, "a", encoding="utf-8")
    except Exception:
        os.close(fd)
        raise
    with handle:
        if path.stat().st_size > 0:
            handle.write("\n")
        handle.write(text)


def _read_posts_from_files(paths: list[Path]) -> list[Post]:
    posts: list[Post] = []
    for path in paths:
        if not path.is_file() or _safe_date_from_path(path) is None:
            continue
        try:
            posts.extend(_parse_posts_file(path, path.read_text(encoding="utf-8")))
        except OSError:
            continue
    return sorted(posts, key=lambda post: post.timestamp)


def _parse_posts_file(path: Path, text: str) -> list[Post]:
    file_date = _safe_date_from_path(path)
    if file_date is None:
        return []
    sections: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current:
                sections.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        sections.append(current)

    posts: list[Post] = []
    for section in sections:
        match = POST_HEADING_RE.match(section[0])
        if match is None:
            continue
        source = ""
        body_lines = section[1:]
        while body_lines and not body_lines[-1].strip():
            body_lines.pop()
        if body_lines and body_lines[-1].startswith("- from: "):
            source = body_lines[-1][8:].strip()
            body_lines = body_lines[:-1]
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)
        while body_lines and not body_lines[-1].strip():
            body_lines.pop()
        try:
            timestamp = f"{file_date.isoformat()}T{match.group('time')}Z"
            _parse_timestamp(timestamp)
        except ValueError:
            continue
        posts.append(
            Post(
                path=path,
                timestamp=timestamp,
                title=match.group("title").strip(),
                body="\n".join(body_lines),
                source=source,
            )
        )
    return posts


def _clean_title(title: str) -> str:
    clean = " ".join(str(title).split())
    if not clean:
        raise ValueError("forum post title must not be empty")
    return clean


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str | None) -> datetime:
    if not value:
        raise ValueError("timestamp is required")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _parse_date(value: str) -> datetime.date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _safe_date_from_path(path: Path):
    try:
        return _parse_date(path.stem)
    except ValueError:
        return None


__all__ = [
    "DEFAULT_FORUM_ROOT",
    "FORUM_CURSOR_ENV",
    "FORUM_ROOT_ENV",
    "ForumDepot",
    "Post",
    "PostRef",
    "current_post_source",
    "cursor_path",
    "forum_banner_line",
    "forum_root",
    "mark_read",
    "read_cursor",
    "write_cursor",
]
