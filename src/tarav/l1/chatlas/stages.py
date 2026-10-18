"""The Chatlas pipeline as stages a consumer runs: capture, cache, index.

native provider folders --capture--> raw --cache--> JSON Normal Models
--index--> ``index/normal-models.sqlite``

Each stage records the version of its input, so its standing is a comparison;
nothing runs unless asked. A consumer selects sessions by Session Index facts,
reads their standing, and updates any stages with a policy: ``missing``,
``stale`` (missing or stale, the default) or ``all``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tarav.l1.chatlas.core import chatlas_update
from tarav.l1.chatlas.index_store import load_chatlas_session_index_rows
from tarav.l1.chatlas.index_time import (
    chatlas_index_timestamp_sort_value,
    parse_chatlas_index_timestamp,
)
from tarav.l0._core.errors import CliError
from tarav.l1.chatlas.normal_model_cache import CachedPart, NormalModelCache
from tarav.l1.chatlas.normal_models_index import (
    INDEXED_PARTS,
    IndexedPart,
    IndexUpdate,
    NormalModelsIndex,
    POLICIES,
)
from tarav.l1.chatlas.paths import default_chatlas_root

JsonObject = dict[str, Any]
STAGES = ("capture", "cache", "index")
NORMALIZED_PROVIDERS = ("codex", "claude-code")
CACHE_PARTS = ("main", *INDEXED_PARTS)


@dataclass(frozen=True, slots=True)
class SessionStanding:
    """Where one session stands in the derived stages."""

    identity: str
    cache: dict[str, CachedPart]
    index: dict[str, IndexedPart]


@dataclass(frozen=True, slots=True)
class CacheUpdate:
    done: tuple[str, ...]
    failed: tuple[tuple[str, str], ...]


# tarav.breadcrumb 0b0e395b70ff
# tarav.breadcrumb 1261a9070131
class ChatlasStages:
    """Select sessions, read their standing, and run the stages they need."""

    def __init__(self, *, chatlas_root: Path | None = None) -> None:
        self.chatlas_root = (chatlas_root or default_chatlas_root()).expanduser().resolve()
        self.index = NormalModelsIndex(chatlas_root=self.chatlas_root)

    def select(
        self,
        *,
        provider: str | None = None,
        project: str | None = None,
        since: str | None = None,
        until: str | None = None,
        identities: Iterable[str] = (),
    ) -> list[JsonObject]:
        """Session Index rows of normalized providers, newest activity first."""
        wanted = set(identities)
        for name, value in (("since", since), ("until", until)):
            if value is not None and parse_chatlas_index_timestamp(value) is None:
                raise ValueError(f"{name} must be an ISO timestamp")
        index = load_chatlas_session_index_rows(
            chatlas_root=self.chatlas_root,
            providers=(provider,) if provider is not None else None,
        )
        rows = [
            row for row in index.rows
            if row.get("provider") in NORMALIZED_PROVIDERS
            and (not wanted or row.get("identity_hash") in wanted)
            and (project is None or _within(row.get("project_path"), project))
            and (since is None or _activity(row) >= chatlas_index_timestamp_sort_value(since))
            and (until is None or _activity(row) <= chatlas_index_timestamp_sort_value(until))
        ]
        return sorted(rows, key=_activity, reverse=True)

    def standing(self, rows: Iterable[JsonObject]) -> dict[str, SessionStanding]:
        rows = list(rows)
        indexed = self.index.standing(rows)
        result = {}
        for row in rows:
            identity = str(row["identity_hash"])
            parts = NormalModelCache(row, chatlas_root=self.chatlas_root).parts()
            result[identity] = SessionStanding(
                identity, {name: parts[name] for name in CACHE_PARTS}, indexed[identity])
        return result

    def capture(
        self,
        *,
        provider: str | None = None,
        identities: Iterable[str] = (),
        since: str | None = None,
    ) -> dict[str, object]:
        """Capture from the native provider folders, narrowed where capture can be."""
        identities = tuple(identities)
        session_ids = tuple(str(row["session_id"]) for row in self.select(identities=identities)) \
            if identities else ()
        window = None
        if since is not None:
            start = parse_chatlas_index_timestamp(since)
            if start is None:
                raise ValueError("since must be an ISO timestamp")
            window = max(0, int((datetime.now(timezone.utc) - start).total_seconds()))
        return chatlas_update(
            providers=(provider,) if provider is not None else None,
            session_ids=session_ids,
            window_seconds=window,
            chatlas_root=self.chatlas_root,
        )

    def update_cache(self, rows: Iterable[JsonObject], *, policy: str = "stale") -> CacheUpdate:
        """Build the JSON Normal Model of the sessions the policy selects."""
        _policy(policy)
        done, failed = [], []
        for row in rows:
            identity = str(row["identity_hash"])
            cache = NormalModelCache(row, chatlas_root=self.chatlas_root)
            parts = cache.parts()
            if policy == "missing" and all(parts[name].present for name in CACHE_PARTS):
                continue
            if policy == "stale" and cache.fresh(CACHE_PARTS):
                continue
            try:
                cache.build()
            except (CliError, OSError, ValueError) as exc:
                failed.append((identity, f"{type(exc).__name__}: {exc}"))
                continue
            done.append(identity)
        return CacheUpdate(tuple(done), tuple(failed))

    def update_index(self, rows: Iterable[JsonObject], *, policy: str = "stale") -> IndexUpdate:
        return self.index.update(rows, policy=policy)

    def run(
        self,
        *,
        stages: Iterable[str] = STAGES,
        policy: str = "stale",
        provider: str | None = None,
        project: str | None = None,
        since: str | None = None,
        until: str | None = None,
        identities: Iterable[str] = (),
    ) -> dict[str, object]:
        """Run the chosen stages in pipeline order over one selection."""
        chosen = tuple(stages)
        unknown = set(chosen) - set(STAGES)
        if unknown:
            raise ValueError(f"unknown Chatlas stage: {', '.join(sorted(unknown))}")
        _policy(policy)
        identities = tuple(identities)
        report: dict[str, object] = {}
        if "capture" in chosen:
            report["capture"] = self.capture(provider=provider, identities=identities, since=since)
        if not {"cache", "index"} & set(chosen):
            return report
        rows = self.select(provider=provider, project=project, since=since, until=until,
                           identities=identities)
        if "cache" in chosen:
            report["cache"] = self.update_cache(rows, policy=policy)
        if "index" in chosen:
            report["index"] = self.update_index(rows, policy=policy)
        return report


def _policy(policy: str) -> None:
    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {', '.join(POLICIES)}")


def _activity(row: JsonObject) -> float:
    return chatlas_index_timestamp_sort_value(row.get("last_activity_at"))


def _within(path: object, prefix: str) -> bool:
    if not isinstance(path, str):
        return False
    root = prefix.rstrip("/")
    return path == root or path.startswith(root + "/")


__all__ = ["CacheUpdate", "ChatlasStages", "STAGES", "SessionStanding"]
