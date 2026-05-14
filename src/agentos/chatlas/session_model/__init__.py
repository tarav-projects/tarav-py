from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "chatlas_export_session_model":
        from ._model import chatlas_export_session_model

        return chatlas_export_session_model
    if name == "build_chatlas_session_model_from_index_row":
        from ._model import build_chatlas_session_model_from_index_row

        return build_chatlas_session_model_from_index_row
    if name == "project_chatlas_session_model_view":
        from ._model import project_chatlas_session_model_view

        return project_chatlas_session_model_view
    raise AttributeError(name)

__all__ = [
    "build_chatlas_session_model_from_index_row",
    "chatlas_export_session_model",
    "project_chatlas_session_model_view",
]
