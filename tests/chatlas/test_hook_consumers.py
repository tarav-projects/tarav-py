from pathlib import Path

import pytest

from agentos.hooks import HookError, HookInvocation, HookRegistry

import agentos.chatlas.hook_consumers as hook_consumers


def test_turn_stop_refresh_is_registered_for_daemon_execution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    update_calls: list[dict[str, object]] = []
    selected_rows: list[dict[str, object]] = []
    warmed_rows: list[dict[str, object]] = []
    session = {"identity_hash": "chatlas-identity"}

    monkeypatch.setattr(
        hook_consumers,
        "chatlas_update",
        lambda **kwargs: update_calls.append(kwargs) or {"status": "ok"},
    )
    monkeypatch.setattr(
        hook_consumers,
        "select_one_chatlas_index_row",
        lambda **kwargs: selected_rows.append(kwargs) or session,
    )
    monkeypatch.setattr(
        hook_consumers,
        "load_chatlas_session_model",
        lambda row: warmed_rows.append(row) or {},
    )

    registry = HookRegistry()
    hook_consumers.register_chatlas_hook_callbacks(registry)
    invocation = HookInvocation(
        name="agent.turn.stop",
        ctx={"session_id": "session-123", "cwd": str(tmp_path)},
        ctx_type="codex",
    )

    registry.dispatch(invocation, execution="inline")
    assert update_calls == []

    registry.dispatch(invocation, execution="daemon")

    assert update_calls == [
        {
            "providers": ("codex",),
            "session_ids": ("session-123",),
            "start_path": tmp_path,
            "progress": None,
        }
    ]
    assert selected_rows == [
        {
            "command": "agent.turn.stop Chatlas refresh",
            "providers": ("codex",),
            "session_id": "session-123",
        }
    ]
    assert warmed_rows == [session]


def test_turn_stop_refresh_ignores_unsupported_context_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        hook_consumers,
        "chatlas_update",
        lambda **kwargs: update_calls.append(kwargs),
    )

    hook_consumers.refresh_chatlas_session_from_hook(
        HookInvocation(
            name="agent.turn.stop",
            ctx={"session_id": "session-123"},
            ctx_type="unknown-provider",
        )
    )

    assert update_calls == []


def test_turn_stop_refresh_requires_a_session_id() -> None:
    with pytest.raises(HookError, match="session_id"):
        hook_consumers.refresh_chatlas_session_from_hook(
            HookInvocation(
                name="agent.turn.stop",
                ctx={},
                ctx_type="codex",
            )
        )
