# $kw: ^chatlas2-package --from Normalization.Pipeline::Chatlas.Session.Model --from Dependency.Profile.Split --note [CT] Chatlas2 is an isolated experimental namespace that may reuse current Chatlas without creating a reverse dependency --supp ^c20260814-12u ^c20260814-13u ^c20260814-14u
from __future__ import annotations

from .commands import register_chatlas2_commands
from .pipeline import build_normal_model, build_normal_model_from_row

__all__ = [
    "build_normal_model",
    "build_normal_model_from_row",
    "register_chatlas2_commands",
]
