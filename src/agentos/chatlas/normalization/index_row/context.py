"""`Normalizer.Context` — a coordination surface for reusing loaded `Raw.Source` data.

It is an offered convenience, not a contract: a `Raw.Normalizer` may pull sources
through it (so overlapping normalizers over the same session pay each load once),
or read on its own and ignore it. It caches raw only — no model or fragment data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from agentos.agent.session_refs import BackingArtifact

from . import _raw


class NormalizerContext:
    """Lazy, per-run raw-source cache scoped to one provider's normalizers."""

    def __init__(self, *, provider: str, artifacts: tuple[BackingArtifact, ...]) -> None:
        self.provider = provider
        self.artifacts = artifacts
        self._first_jsonl: dict[Path, dict[str, Any] | None] = {}
        self._codex_meta: dict[Path, dict[str, Any] | None] = {}

    def artifacts_by_role(self, role: str) -> tuple[BackingArtifact, ...]:
        return tuple(artifact for artifact in self.artifacts if artifact.role == role)

    def primary_transcript(self) -> BackingArtifact | None:
        transcripts = self.artifacts_by_role("transcript")
        return transcripts[0] if transcripts else None

    def first_jsonl_object(self, path: Path) -> dict[str, Any] | None:
        return self._cached(self._first_jsonl, path, _raw.read_first_jsonl_object)

    def codex_session_meta(self, path: Path) -> dict[str, Any] | None:
        return self._cached(self._codex_meta, path, _raw.read_codex_session_meta)

    @staticmethod
    def _cached(
        cache: dict[Path, dict[str, Any] | None],
        path: Path,
        loader: Callable[[Path], dict[str, Any] | None],
    ) -> dict[str, Any] | None:
        if path not in cache:
            cache[path] = loader(path)
        return cache[path]
