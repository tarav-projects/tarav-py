# $kw: ^inline-event-ref-selection --from Chatlas.View.Model --from Session.Event.Tape --note [CT] inline filters select canonical events by stable Event.Ref addresses ^c20260807-16u
from __future__ import annotations

from pathlib import Path

from agentos._core.errors import CliError
from agentos.chatlas.event_ref import event_ref_addresses
from agentos.chatlas.index_query import (
    select_materialization_row,
    select_one_chatlas_index_row,
)
from agentos.chatlas.normalization.session_model import (
    project_chatlas_session_model_view,
)
from agentos.chatlas.normalization.session_model.filters import apply_chatlas_filters
from agentos.chatlas.normalization.session_model._views import CHATLAS_VIEW_NAMES
from agentos.chatlas.paths import default_chatlas_root
from agentos.chatlas.session_cache import load_chatlas_session_model
from agentos.chatlas.time_interface import format_local_timestamp


def chatlas_views_get(
    *,
    uri: str | None = None,
    identity_hash: str | None = None,
    project: str | Path | None = None,
    project_base: str | None = None,
    providers: tuple[str, ...] | None = None,
    instances: tuple[str, ...] | None = None,
    provider_instance_fingerprint: str | None = None,
    session_id: str | None = None,
    display_name: str | None = None,
    extractable_only: bool = False,
    active_after: str | None = None,
    sort: str = "lexical",
    limit: int | None = None,
    view: str | None = None,
    range_spec: str | None = None,
    contains: str | None = None,
    role: str | None = None,
    around: str | None = None,
    radius: int | None = None,
    file_read: str | None = None,
    file_write: str | None = None,
    file_touched: str | None = None,
    tool_contains: str | None = None,
    tool_name: str | None = None,
    filters: tuple[str, ...] = (),
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    has_selection = any(
        value is not None
        for value in (
            contains,
            role,
            around,
            file_read,
            file_write,
            file_touched,
            tool_contains,
            tool_name,
        )
    )
    if view is None:
        view = "events" if has_selection else "full"
    elif view == "full" and has_selection:
        raise CliError(
            "chatlas views get selection flags require a projected view "
            "(e.g. --view events); --view full is the unprojected model"
        )
    session = select_one_chatlas_index_row(
        command="chatlas views get",
        uri=uri,
        identity_hash=identity_hash,
        project=project,
        project_base=project_base,
        providers=providers,
        instances=instances,
        provider_instance_fingerprint=provider_instance_fingerprint,
        session_id=session_id,
        display_name=display_name,
        extractable_only=extractable_only,
        active_after=active_after,
        sort=sort,
        limit=limit,
        chatlas_root=chatlas_root,
    )
    session = select_materialization_row(
        session,
        uri=uri,
        instances=instances,
        provider_instance_fingerprint=provider_instance_fingerprint,
    )
    session_model = load_chatlas_session_model(session, chatlas_root=chatlas_root)
    file_filters = (
        ([("read", file_read)] if file_read is not None else [])
        + ([("write", file_write)] if file_write is not None else [])
        + ([("touched", file_touched)] if file_touched is not None else [])
    )
    if file_filters or tool_contains is not None or tool_name is not None:
        from agentos.chatlas.normalization.session_model.file_touch import (
            file_touch_invocations,
            tool_contains_invocations,
        )

        touching_addresses: set[str] = set()
        for mode, path in file_filters:
            for invocation in file_touch_invocations(
                session_model, path=path, mode=mode
            ):
                touching_addresses.update(
                    event_ref_addresses(invocation.get("event_refs"))
                )
        if tool_contains is not None or tool_name is not None:
            for invocation in tool_contains_invocations(
                session_model, text=tool_contains or "", tool_name=tool_name
            ):
                touching_addresses.update(
                    event_ref_addresses(invocation.get("event_refs"))
                )
        session_model = dict(session_model)
        chat = dict(session_model.get("chat") or {})
        chat["events"] = [
            event
            for event in (chat.get("events") or [])
            if event.get("event_address") in touching_addresses
        ]
        session_model["chat"] = chat



    event_window_selection = any(
        value is not None for value in (contains, role, around)
    )
    pre_filtered = bool(filters) and event_window_selection
    if pre_filtered:
        session_model = apply_chatlas_filters(session_model, filters)
    projected = project_chatlas_session_model_view(
        session_model,
        view=view,
        range_spec=range_spec,
        contains=contains,
        role=role,
        around=around,
        radius=radius,
    )
    if pre_filtered:
        return projected
    return apply_chatlas_filters(projected, filters)


def chatlas_views_list(*, chatlas_root: Path | None = None) -> dict[str, object]:
    root = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    return {
        "status": "ok",
        "command": "chatlas views list",
        "chatlas_root": str(root),
        "views": [
            {
                "name": name,
                "output": "normal-model",
                "materialized": False,
            }
            for name in CHATLAS_VIEW_NAMES
        ],
    }


def format_chatlas_view_text(payload: dict[str, object]) -> str:
    """Render the turn-shaped views as a conversation.

    `transcript`, `user`, and `zip-transcript` carry an ordered exchange and
    read badly as generic key/value output. The model-shaped views (`full`,
    `events`, `replay`) have no useful fixed layout, so they keep the generic
    renderer -- `--json` is the honest path for those.
    """
    from agentos.chatlas.output import render_payload_text

    turns = _view_turns(payload)
    if turns is None:
        return render_payload_text(payload)
    lines = [header] if (header := _view_header(payload)) else []
    for role, text, stamp in turns:
        label = (
            f"{role}:"
            if stamp is None
            else f"{role}  [{format_local_timestamp(stamp)}]:"
        )
        lines.append(label)
        lines.extend(f"  {line}" for line in (text or "").splitlines() or [""])
        lines.append("")
    return "\n".join(lines).rstrip("\n")


def _view_header(payload: dict[str, object]) -> str:
    session = payload.get("session")
    if not isinstance(session, dict):
        return ""
    parts = [
        str(session[key])
        for key in ("provider", "session_id")
        if isinstance(session.get(key), str)
    ]
    view = payload.get("view")
    if isinstance(view, str):
        parts.append(f"view={view}")
    return ("# " + "  ".join(parts) + "\n") if parts else ""


def _view_turns(
    payload: dict[str, object],
) -> list[tuple[str, str, str | None]] | None:
    turns = payload.get("turns")
    if isinstance(turns, list):
        return [
            (
                str(turn.get("role") or "?"),
                str(turn.get("text") or ""),
                None,
            )
            for turn in turns
            if isinstance(turn, dict)
        ]
    chat = payload.get("chat")
    if not isinstance(chat, dict):
        return None
    messages = chat.get("messages")
    if not isinstance(messages, list):
        return None
    return [
        (
            str(message.get("role") or "?"),
            _message_text(message.get("content")),
            message.get("timestamp") if isinstance(message.get("timestamp"), str) else None,
        )
        for message in messages
        if isinstance(message, dict)
    ]


def _message_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    blocks: list[str] = []
    for block in content:
        if isinstance(block, str):
            blocks.append(block)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            blocks.append(block["text"])
    return "\n".join(blocks)


__all__ = ["chatlas_views_get", "chatlas_views_list", "format_chatlas_view_text"]
