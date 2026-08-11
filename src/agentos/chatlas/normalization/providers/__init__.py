"""Per-provider `Raw.Normalizer`s for `Normalization.Pipeline::Chatlas.Session.Model`.

`{claude,codex}_events` — the per-record-type event normalizers (pure + in-place) and the
assembler-owned event loop; `{claude,codex}_records` — the tool_invocations / model_runs
normalizers. Each provider implements only what its native rollout/transcript requires.
"""
