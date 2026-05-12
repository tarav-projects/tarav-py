from __future__ import annotations

from pathlib import Path

from agentos._core.errors import CliError


def chatlas_export_session_model(
    *,
    query: str,
    providers: tuple[str, ...] | None = None,
    output_format: str = "json",
    view: str = "full",
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    _ = query
    _ = providers
    _ = output_format
    _ = view
    _ = chatlas_root
    raise CliError("chatlas export is under reimplementation")


__all__ = ["chatlas_export_session_model"]
