from __future__ import annotations

from pathlib import Path


def chatlas_export_session_model(
    *,
    query: str,
    providers: tuple[str, ...] | None = None,
    output_format: str = "json",
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    from ._model import chatlas_export_session_model as export_session_model

    return export_session_model(
        query=query,
        providers=providers,
        output_format=output_format,
        chatlas_root=chatlas_root,
    )

__all__ = ["chatlas_export_session_model"]
