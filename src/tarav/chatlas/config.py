from __future__ import annotations

from pathlib import Path
from typing import Any

from tarav._core.errors import CliError
from tarav.agent.config import load_chat_config_documents

from tarav.chatlas._duration import parse_duration_seconds

DEFAULT_COLD_SESSION_CUTOFF = "30d"


def cold_session_cutoff_seconds_for_provider(
    provider: str,
    *,
    start_path: Path | str = ".",
) -> int:
    cutoff = DEFAULT_COLD_SESSION_CUTOFF
    for config in load_chat_config_documents(start_path=start_path):
        chatlas_config = config.get("chatlas")
        if not isinstance(chatlas_config, dict) or "cold_session_cache" not in chatlas_config:
            continue
        cutoff = _cold_session_cutoff_from_config(
            chatlas_config["cold_session_cache"],
            provider=provider,
            current_cutoff=cutoff,
        )
    return parse_duration_seconds(
        cutoff,
        field_name=f"chatlas.cold_session_cache cutoff for provider {provider}",
    )


def _cold_session_cutoff_from_config(
    value: object,
    *,
    provider: str,
    current_cutoff: str,
) -> str:
    if not isinstance(value, dict):
        raise CliError("config field chatlas.cold_session_cache must be a JSON object")
    cutoff = _optional_duration_text(
        value.get("cutoff"),
        field_name="chatlas.cold_session_cache.cutoff",
        default=current_cutoff,
    )
    providers = value.get("providers")
    if providers is None:
        return cutoff
    if not isinstance(providers, dict):
        raise CliError("config field chatlas.cold_session_cache.providers must be a JSON object")
    provider_config = providers.get(provider)
    if provider_config is None:
        return cutoff
    return _provider_cutoff(provider_config, provider=provider, default=cutoff)


def _provider_cutoff(value: object, *, provider: str, default: str) -> str:
    field_name = f"chatlas.cold_session_cache.providers.{provider}"
    if isinstance(value, str):
        return _optional_duration_text(value, field_name=field_name, default=default)
    if not isinstance(value, dict):
        raise CliError(f"config field {field_name} must be a duration string or JSON object")
    return _optional_duration_text(value.get("cutoff"), field_name=f"{field_name}.cutoff", default=default)


def _optional_duration_text(value: Any, *, field_name: str, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise CliError(f"config field {field_name} must be a duration string")
    parse_duration_seconds(value, field_name=field_name)
    return value


__all__ = [
    "DEFAULT_COLD_SESSION_CUTOFF",
    "cold_session_cutoff_seconds_for_provider",
]
