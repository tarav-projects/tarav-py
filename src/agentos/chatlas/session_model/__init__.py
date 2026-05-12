from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "chatlas_export_session_model":
        from ._model import chatlas_export_session_model

        return chatlas_export_session_model
    raise AttributeError(name)

__all__ = ["chatlas_export_session_model"]
