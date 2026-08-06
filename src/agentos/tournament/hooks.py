# $kw: ^tournament-hooks --from Tournament.Hook --from Tournament.Definition --note [DF] named consumer functions the engine calls at fixed points; every hook has a working default and none may perform effects ^<anchor-on-landing>
"""Consumer-owned tournament definitions, loaded as snapshotted Python.

A definition file exposes named functions. Each has a working default, so a file
declaring none still runs end to end. Hooks return values; the engine performs
every effect. The file is snapshotted at load and matches execute the snapshot,
so a definition edited mid-tournament cannot silently make later verdicts
incomparable with earlier ones.
"""

from __future__ import annotations

import hashlib
import importlib.util
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType, SimpleNamespace

from agentos.tournament import locking
from agentos.tournament.model import TournamentError

RENDER_MATCH = "render_match"
MATCH_IDENTITY = "match_identity"
VERDICT_SLOT = "verdict_slot"
SELECT_PAIRS = "select_pairs"

HOOK_NAMES = (RENDER_MATCH, MATCH_IDENTITY, VERDICT_SLOT, SELECT_PAIRS)

DEFAULT_QUESTION = "Which of the two candidates below is better?"


class HookError(TournamentError):
    pass


class HookLoadError(HookError):
    pass


class HookReturnError(HookError):
    """A hook returned something the engine cannot act on."""


class HookPurityError(HookError):
    """A hook performed an effect instead of returning a value."""


@dataclass(frozen=True)
class HookContext:
    """Read-only data handed to a hook. Carries data, nothing callable."""

    question: str
    players: tuple[str, ...]
    presented: tuple[str, ...]
    snapshot_path: str
    rendering: str | None = None
    verdicts: tuple[dict[str, object], ...] = ()
    pool: tuple[str, ...] = ()
    budget: int = 0


@dataclass
class TournamentDefinition:
    """One snapshotted consumer definition and its resolved hooks."""

    origin_path: Path
    snapshot_path: Path
    digest: str
    module: ModuleType
    guarded_paths: tuple[Path, ...] = field(default_factory=tuple)

    @property
    def question(self) -> str:
        value = getattr(self.module, "question", DEFAULT_QUESTION)
        return str(value)

    def render_match(
        self, *, players: tuple[str, ...], presented: tuple[str, ...]
    ) -> str:
        context = self._context(players=players, presented=presented)
        hook = getattr(self.module, RENDER_MATCH, None)
        if hook is None:
            return _default_render(context)
        value = self._call(RENDER_MATCH, hook, context)
        if not isinstance(value, str) or not value.strip():
            raise HookReturnError(
                f"{RENDER_MATCH} must return a non-empty string "
                f"(got {type(value).__name__})"
            )
        return value

    def match_identity(
        self,
        *,
        players: tuple[str, ...],
        presented: tuple[str, ...],
        rendering: str,
    ) -> str:
        context = self._context(
            players=players, presented=presented, rendering=rendering
        )
        hook = getattr(self.module, MATCH_IDENTITY, None)
        if hook is None:
            return _default_identity(rendering)
        value = self._call(MATCH_IDENTITY, hook, context)
        if not isinstance(value, str) or not value.strip():
            raise HookReturnError(
                f"{MATCH_IDENTITY} must return a non-empty string "
                f"(got {type(value).__name__})"
            )
        return value

    def verdict_slot(
        self,
        *,
        players: tuple[str, ...],
        presented: tuple[str, ...],
        rendering: str,
    ) -> dict[str, object]:
        context = self._context(
            players=players, presented=presented, rendering=rendering
        )
        hook = getattr(self.module, VERDICT_SLOT, None)
        if hook is None:
            return {}
        value = self._call(VERDICT_SLOT, hook, context)
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise HookReturnError(
                f"{VERDICT_SLOT} must return a JSON object or None "
                f"(got {type(value).__name__})"
            )
        return dict(value)

    def select_pairs(
        self,
        *,
        pool: tuple[str, ...],
        budget: int,
        verdicts: tuple[dict[str, object], ...],
    ) -> tuple[tuple[str, str], ...] | None:
        hook = getattr(self.module, SELECT_PAIRS, None)
        if hook is None:
            return None
        context = self._context(
            players=pool, presented=(), pool=pool, budget=budget, verdicts=verdicts
        )
        value = self._call(SELECT_PAIRS, hook, context)
        return _validated_pairs(value, pool)

    def _context(
        self,
        *,
        players: tuple[str, ...],
        presented: tuple[str, ...],
        rendering: str | None = None,
        pool: tuple[str, ...] = (),
        budget: int = 0,
        verdicts: tuple[dict[str, object], ...] = (),
    ) -> HookContext:
        return HookContext(
            question=self.question,
            players=tuple(players),
            presented=tuple(presented),
            snapshot_path=str(self.snapshot_path),
            rendering=rendering,
            pool=pool,
            budget=budget,
            verdicts=verdicts,
        )

    def _call(self, name: str, hook: object, context: HookContext) -> object:
        if not callable(hook):
            raise HookReturnError(f"{name} must be callable")
        value = hook(context)
        self._verify_purity(name)
        return value

    def _verify_purity(self, name: str) -> None:
        for guarded in (self.snapshot_path, *self.guarded_paths):
            try:
                locking.verify(guarded)
            except locking.LockViolation as error:
                raise HookPurityError(
                    f"{name} performed an effect: {error}. Hooks return values; "
                    "the engine performs every effect."
                ) from error


def load_definition(
    path: Path | str,
    *,
    snapshot_dir: Path | str,
    guarded_paths: tuple[Path, ...] | list[Path] = (),
) -> TournamentDefinition:
    """Snapshot a definition file and load the snapshot as the executed module."""
    origin = Path(path).expanduser().resolve()
    if not origin.is_file():
        raise HookLoadError(f"tournament definition does not exist: {origin}")

    snapshot_root = Path(snapshot_dir).expanduser().resolve()
    snapshot_root.mkdir(parents=True, exist_ok=True)
    snapshot = snapshot_root / "_definition-snap.py"
    shutil.copy2(origin, snapshot)
    locking.record(snapshot)

    guarded = tuple(Path(item).resolve() for item in guarded_paths)
    for item in guarded:
        locking.record(item)

    module = _load_module(snapshot)
    return TournamentDefinition(
        origin_path=origin,
        snapshot_path=snapshot,
        digest="sha256:" + locking.content_hash(snapshot),
        module=module,
        guarded_paths=guarded,
    )


def open_definition(
    snapshot_path: Path | str,
    *,
    origin_path: Path | str,
    guarded_paths: tuple[Path, ...] | list[Path] = (),
) -> TournamentDefinition:
    """Open an existing snapshot for a later run.

    Distinct from ``load_definition``: a tournament already froze its definition,
    so reopening verifies that snapshot rather than taking a new one. Re-recording
    here would re-authorize a tampered snapshot instead of catching it.
    """
    snapshot = Path(snapshot_path).expanduser().resolve()
    if not snapshot.is_file():
        raise HookLoadError(f"tournament definition snapshot is missing: {snapshot}")
    try:
        locking.verify(snapshot)
    except locking.LockViolation as error:
        raise HookPurityError(
            f"the tournament's definition snapshot changed outside the system: {error}"
        ) from error

    guarded = tuple(Path(item).resolve() for item in guarded_paths)
    return TournamentDefinition(
        origin_path=Path(origin_path),
        snapshot_path=snapshot,
        digest="sha256:" + locking.content_hash(snapshot),
        module=_load_module(snapshot),
        guarded_paths=guarded,
    )


def _load_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("tournament_definition", path)
    if spec is None or spec.loader is None:
        raise HookLoadError(f"cannot load tournament definition from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _default_render(context: HookContext) -> str:
    first, second = context.presented
    return (
        f"{context.question}\n\n"
        f"A:\n{first}\n\n"
        f"B:\n{second}\n\n"
        'Answer with exactly one JSON object: {"outcome": "A" | "B" | "no_contest", '
        '"attribution": "none" | "question" | "player" | "prompt", "reason": "..."}\n'
        'Use "no_contest" when the comparison cannot honestly be made, and attribute '
        "it to the question, to one player, or to this prompt. Use \"none\" only when "
        "you decided."
    )


def _default_identity(rendering: str) -> str:
    return "sha256:" + hashlib.sha256(rendering.encode("utf-8")).hexdigest()


def _validated_pairs(
    value: object, pool: tuple[str, ...]
) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, (list, tuple)):
        raise HookReturnError(
            f"{SELECT_PAIRS} must return a sequence of player pairs "
            f"(got {type(value).__name__})"
        )
    known = set(pool)
    pairs: list[tuple[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise HookReturnError(f"{SELECT_PAIRS} item {index} must be a pair")
        first, second = str(item[0]), str(item[1])
        if first == second:
            raise HookReturnError(f"{SELECT_PAIRS} item {index} pairs a player with itself")
        missing = sorted({first, second} - known)
        if missing:
            raise HookReturnError(
                f"{SELECT_PAIRS} item {index} names players outside the pool: "
                + ", ".join(missing)
            )
        pairs.append((first, second))
    return tuple(pairs)
