from __future__ import annotations

from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.chatlas.provider_home_adapter import (
    ChatlasProviderInstance,
    ProviderHomeAdapter,
)
from agentos.chatlas.instance_selection import selected_provider_instances


def chatlas_provider_query(
    *,
    provider: str,
    instances: tuple[str, ...] | None = None,
    session_ids: tuple[str, ...] = (),
    start_path: Path | str = ".",
) -> dict[str, object]:
    if not provider:
        raise CliError("chatlas provider query requires --provider")
    if not session_ids:
        raise CliError(
            "chatlas provider query is point-lookup only; provide at least one --session-id"
        )

    selected = selected_provider_instances(providers=(provider,), start_path=start_path)
    if instances is not None:
        wanted = set(instances)
        selected = tuple(
            inst for inst in selected
            if inst.agent.profile_id in wanted or inst.instance in wanted
        )
    if not selected:
        raise CliError(
            f"no configured instances match provider={provider!r}"
            + (f" instances={list(instances)}" if instances else "")
        )

    rows: list[dict[str, object]] = []
    for session_id in session_ids:
        for instance in selected:
            row = _query_one(instance, session_id)
            if row is not None:
                rows.append(row)
                break
        else:
            rows.append({
                "session_id": session_id,
                "provider": provider,
                "found": False,
            })

    return {
        "status": "ok",
        "command": "chatlas provider query",
        "provider": provider,
        "instances": [_instance_summary(inst) for inst in selected],
        "session_ids": list(session_ids),
        "row_count": len(rows),
        "rows": rows,
    }


def _query_one(instance: ChatlasProviderInstance, session_id: str) -> dict[str, object] | None:
    session_ref = ProviderHomeAdapter(instance).find_session_ref(session_id)
    if session_ref is None:
        return None
    session = session_ref.to_session() if hasattr(session_ref, "to_session") else None
    sources = session.sources() if session is not None and hasattr(session, "sources") else ()
    source_paths = [str(src.path) for src in sources]
    primary = source_paths[0] if source_paths else None
    primary_mtime = None
    if primary is not None:
        try:
            primary_mtime = Path(primary).stat().st_mtime
        except OSError:
            primary_mtime = None
    row: dict[str, object] = {
        "session_id": session_id,
        "provider": instance.provider,
        "instance": instance.instance,
        "found": True,
        "source_paths": source_paths,
        "primary_source_path": primary,
        "primary_source_mtime": primary_mtime,
    }
    project_path = _safe_attr(session_ref, "project_path") or _safe_attr(session, "project_path")
    if project_path:
        row["project_path"] = project_path
    display_name = None
    if hasattr(session_ref, "display_name"):
        display_name = session_ref.display_name()
    if display_name:
        row["display_name"] = display_name
    return row


def _safe_attr(obj: object, name: str) -> Any:
    if obj is None:
        return None
    return getattr(obj, name, None)


def _instance_summary(instance: ChatlasProviderInstance) -> dict[str, object]:
    return {
        "provider": instance.provider,
        "instance": instance.instance,
        "fingerprint": instance.fingerprint,
    }


__all__ = ["chatlas_provider_query"]
