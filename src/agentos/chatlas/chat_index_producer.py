from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.agent.primitives import RunCapable
from agentos.agent.providers import resolve_agent
from agentos.agent.run_runtime import AgentCommandConfig, AgentRunConfig
from agentos.hooks import AGENTOS_HOOKS_DISABLED_ENV

from agentos.chatlas.chat_index import (
    chatlas_chat_index_show,
    chatlas_chat_index_source,
)
from agentos.chatlas.chat_index_audit import chatlas_chat_index_audit
from agentos.chatlas.paths import default_chatlas_root
from agentos.chatlas.production_config import load_chatlas_run_produce_config


CAPTURE_PROMPT = "$agentos-chatlas-pkg --capture --session {identity_hash}"


def maintain_chat_index_with_agent(
    *,
    identity_hash: str,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    """Bring one semantic Chat.Index through the source horizon observed now."""
    root = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    source = chatlas_chat_index_source(
        chatlas_root=root,
        identity_hash=identity_hash,
    )
    target_turn_id = _last_source_turn_id(source)
    if target_turn_id is None:
        return {
            "status": "ok",
            "identity_hash": identity_hash,
            "skipped": True,
            "reason": "source has no turns",
        }

    before = chatlas_chat_index_show(
        chatlas_root=root,
        identity_hash=identity_hash,
    )
    if _capture_reaches_target(before, source=source, target_turn_id=target_turn_id):
        audit = chatlas_chat_index_audit(
            chatlas_root=root,
            identity_hash=identity_hash,
        )
        if audit.get("ok") is True:
            return {
                "status": "ok",
                "identity_hash": identity_hash,
                "skipped": True,
                "reason": "current",
                "target_turn_id": target_turn_id,
            }

    selection = load_chatlas_run_produce_config(chatlas_root=root)
    provider = _required_string(selection, "agent_provider")
    profile = _optional_string(selection, "profile")
    model = _optional_string(selection, "model")
    agent = resolve_agent(
        provider=provider,
        profile=profile,
        start_path=root,
    )
    if not isinstance(agent, RunCapable):
        raise CliError(
            f"Chat.Index production provider {agent.provider} does not support run"
        )
    # Internal retained-production agents must not recursively submit their own
    # lifecycle events to the daemon. This is process control, not hook context.
    agent = replace(
        agent,
        env=(*agent.env, (AGENTOS_HOOKS_DISABLED_ENV, "1")),
    )
    run = agent.run(
        AgentCommandConfig(
            prompt=CAPTURE_PROMPT.format(identity_hash=identity_hash),
            model=model,
            interaction_mode="non_interactive",
            credential_success_source="chatlas.chat-index.hook",
        ),
        AgentRunConfig(cwd=root, process_mode="capture"),
    )
    if run.exit_code != 0:
        raise CliError(f"Chat.Index capture agent exited {run.exit_code}")

    after = chatlas_chat_index_show(
        chatlas_root=root,
        identity_hash=identity_hash,
    )
    if not _capture_reaches_target(after, source=source, target_turn_id=target_turn_id):
        raise CliError(
            "Chat.Index capture agent exited successfully without materializing "
            f"the requested source horizon {target_turn_id}"
        )
    audit = chatlas_chat_index_audit(
        chatlas_root=root,
        identity_hash=identity_hash,
    )
    if audit.get("ok") is not True:
        raise CliError("Chat.Index capture agent produced a surface that failed audit")
    chat_index = after.get("chat_index")
    summary = chat_index if isinstance(chat_index, dict) else {}
    return {
        "status": "ok",
        "identity_hash": identity_hash,
        "skipped": False,
        "target_turn_id": target_turn_id,
        "delta_count": summary.get("delta_count"),
        "surface_path": summary.get("path"),
    }


def _last_source_turn_id(payload: dict[str, object]) -> str | None:
    source = payload.get("source")
    descriptor = source if isinstance(source, dict) else {}
    turn_refs = descriptor.get("turn_refs")
    if not isinstance(turn_refs, list) or not turn_refs:
        return None
    last = turn_refs[-1]
    coordinate = last if isinstance(last, dict) else {}
    turn_ref = coordinate.get("turn_ref")
    ref = turn_ref if isinstance(turn_ref, dict) else {}
    value = ref.get("turn_id")
    return value if isinstance(value, str) and value else None


def _capture_reaches_target(
    payload: dict[str, object],
    *,
    source: dict[str, object],
    target_turn_id: str,
) -> bool:
    capture = payload.get("capture")
    capture_payload = capture if isinstance(capture, dict) else {}
    head = capture_payload.get("head")
    head_payload = head if isinstance(head, dict) else {}
    horizon = head_payload.get("horizon")
    horizon_payload = horizon if isinstance(horizon, dict) else {}
    captured_turn_id = horizon_payload.get("turn_id")
    if not isinstance(captured_turn_id, str):
        return False

    source_payload = source.get("source")
    descriptor = source_payload if isinstance(source_payload, dict) else {}
    turn_refs = descriptor.get("turn_refs")
    if not isinstance(turn_refs, list):
        return False
    positions = {
        turn_id: index
        for index, entry in enumerate(turn_refs)
        if (turn_id := _turn_id(entry)) is not None
    }
    target_position = positions.get(target_turn_id)
    captured_position = positions.get(captured_turn_id)
    return (
        target_position is not None
        and captured_position is not None
        and captured_position >= target_position
    )


def _turn_id(value: object) -> str | None:
    entry = value if isinstance(value, dict) else {}
    turn_ref = entry.get("turn_ref")
    ref = turn_ref if isinstance(turn_ref, dict) else {}
    turn_id = ref.get("turn_id")
    return turn_id if isinstance(turn_id, str) and turn_id else None


def _required_string(payload: dict[str, object], key: str) -> str:
    value = _optional_string(payload, key)
    if value is None:
        raise CliError(
            "Chat.Index hook production requires "
            f"chatlas.run_produce.{key} in the Chatlas config"
        )
    return value


def _optional_string(payload: dict[str, object], key: str) -> str | None:
    value: Any = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise CliError(f"chatlas.run_produce.{key} must be a non-empty string")
    return value.strip()


__all__ = ["CAPTURE_PROMPT", "maintain_chat_index_with_agent"]
