# $kw: ^chatlas2-views --from Chatlas.Query.Surface --from Normalization.Pipeline::Chatlas.Session.Model --note [IMPL] Chatlas2 Views are disposable bounded read projections over canonical Normal Model content and own no normalization or cache policy --supp ^c20260816-23u ^c20260816-33u ^c20260816-36u
from __future__ import annotations

from copy import deepcopy
from collections.abc import Iterable
from typing import Literal

from tarav._core.errors import CliError

from .cache import NormalModelCacheReader
from .model import JsonObject


ViewName = Literal["full", "transcript", "user", "events"]
_VIEW_DEFINITIONS: tuple[JsonObject, ...] = (
    {"name": "full", "collection": "normal_model", "bounded": False},
    {"name": "transcript", "collection": "chat_messages", "bounded": True},
    {"name": "user", "collection": "chat_messages", "bounded": True},
    {"name": "events", "collection": "events", "bounded": True},
)


def list_views() -> JsonObject:
    return {
        "class": "tarav.chatlas2.views",
        "views": deepcopy(list(_VIEW_DEFINITIONS)),
    }


def view_names() -> tuple[str, ...]:
    return tuple(str(definition["name"]) for definition in _VIEW_DEFINITIONS)


def project_view(
    reader: NormalModelCacheReader,
    *,
    view: ViewName,
    limit: int | None = None,
) -> JsonObject:
    if view not in view_names():
        raise CliError(f"unknown Chatlas2 view: {view}")
    if limit is not None and limit < 0:
        raise CliError("Chatlas2 view limit must be non-negative")
    if view == "full":
        if limit is not None:
            raise CliError("--limit is unavailable for the full view")
        return reader.load_normal_model()

    model = reader.metadata.get("model")
    session = model.get("session") if isinstance(model, dict) else None
    if not isinstance(session, dict):
        raise CliError("Chatlas2 cache metadata has no session")

    if view in {"transcript", "user"}:
        records = list(
            reader.iter_chat_message_records(
                side="user" if view == "user" else None,
                limit=limit,
            )
        )
        return _collection_view(
            view=view,
            session=session,
            collection="messages",
            records=records,
        )

    events = _bounded(reader.iter_events(), limit=limit)
    return _collection_view(
        view=view,
        session=session,
        collection="events",
        records=events,
    )


def _bounded(records: Iterable[JsonObject], *, limit: int | None) -> list[JsonObject]:
    if limit == 0:
        return []
    selected: list[JsonObject] = []
    for record in records:
        selected.append(record)
        if limit is not None and len(selected) >= limit:
            break
    return selected


def _collection_view(
    *,
    view: str,
    session: JsonObject,
    collection: str,
    records: list[JsonObject],
) -> JsonObject:
    return {
        "class": "tarav.chatlas2.view",
        "view": view,
        "session": deepcopy(session),
        "count": len(records),
        collection: records,
    }


__all__ = ["ViewName", "list_views", "project_view", "view_names"]
