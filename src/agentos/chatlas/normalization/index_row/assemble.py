"""Index-row metadata via `Raw.Normalizer`s — the raw→index-metadata path.

claude-code + codex produce the index row's raw-derived fields (`native`,
`project_path`, `display_name`/`display_name_field`, `created_at`, `last_activity_at`)
from the discovered session's raw artifacts, replacing the agentos-py `session_ref`
extraction. `index_metadata` runs the per-provider normalizers and merges; returns
``None`` for providers without index-row normalizers (the caller falls back to the
`session_ref` path).
"""

from __future__ import annotations

from agentos.agent.session_refs import BackingArtifact

from . import _raw
from .claude import CLAUDE_NORMALIZERS
from .codex import CODEX_NORMALIZERS
from .context import NormalizerContext
from .fragment import CREATED_AT_CANDIDATES_KEY, LAST_ACTIVITY_AT_CANDIDATES_KEY, merge_fragments

_PROVIDER_NORMALIZERS = {
    "claude-code": CLAUDE_NORMALIZERS,
    "codex": CODEX_NORMALIZERS,
}


def index_metadata(
    provider: str, artifacts: tuple[BackingArtifact, ...]
) -> dict[str, object] | None:
    """The index row's raw-derived metadata fields, or ``None`` if the provider has no
    index-row normalizers (caller falls back to the `session_ref` path)."""
    normalizers = _PROVIDER_NORMALIZERS.get(provider)
    if normalizers is None:
        return None
    ctx = NormalizerContext(provider=provider, artifacts=artifacts)
    merged = merge_fragments([normalizer(ctx) for normalizer in normalizers])
    created_candidates = merged.pop(CREATED_AT_CANDIDATES_KEY, None)
    activity_candidates = merged.pop(LAST_ACTIVITY_AT_CANDIDATES_KEY, None)
    created_at = (
        _raw.format_stats_timestamp(min(created_candidates))
        if isinstance(created_candidates, list) and created_candidates
        else None
    )
    last_activity_at = (
        _raw.format_stats_timestamp(max(activity_candidates))
        if isinstance(activity_candidates, list) and activity_candidates
        else None
    )
    return {
        "native": merged.get("native", {}),
        "project_path": merged.get("project_path"),
        "display_name": merged.get("display_name"),
        "display_name_field": merged.get("display_name_field"),
        "created_at": created_at,
        "last_activity_at": last_activity_at,
    }
