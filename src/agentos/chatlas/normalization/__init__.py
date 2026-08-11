"""`Normalization.Pipeline::Chatlas.Session.Model` — provider sessions normalized into
the `Chatlas.Session.Model`.

The pipeline is the load-bearing producer of the model: `session_assembler` is the
`Normal.Assembler`; `providers/{claude,codex}_events` hold the per-record-type event
`Raw.Normalizer`s and `providers/{claude,codex}_records` the tool_invocations / model_runs
`Raw.Normalizer`s; the per-provider builders live under `session_model/`. Production
reaches it via `session_model.build_chatlas_session_model_from_index_row`.
"""

from __future__ import annotations

from .session_assembler import assemble_session_chat, assemble_session_model

__all__ = [
    "assemble_session_model",
    "assemble_session_chat",
]
