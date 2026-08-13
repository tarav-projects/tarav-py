# $kw: ^tournament-hooks --from Tournament.Hook --from Tournament.Definition --from Tournament.Label --note [DC] the match-players and match-identity hooks are required and have no default; every other hook defaults --supp ^c20260806-21u ^<anchor-on-landing>
"""Consumer-owned tournament definitions, loaded as snapshotted Python.

A definition file exposes named functions. Two are required and have no default:
``match_players`` names the competitors of one match, and ``match_identity``
supplies that match's opaque identity. The engine computes neither — a generated
pool would not be the consumer's, and a generated identity would silently stop
accumulation.

``present_player`` and ``verdict_slot`` default, so a definition supplies only
what its domain forces. Hooks return values; the engine performs every effect.
The file is snapshotted at load and matches execute the snapshot, so a definition
edited mid-tournament cannot silently make later verdicts incomparable with
earlier ones.

``controls`` declares the calibration pool — players carrying an expected band —
and the module attribute ``control_rate`` says how often one is substituted in.
The hook returns the *pool*, never one control per call: which control lands in
which match is engine work.

``match_frame`` returns a ``Match.Frame`` — the definition's typed, composable
description of the whole prompt, with a ``Players()`` placeholder where the
candidates go. A definition that omits it renders exactly the bytes it rendered
before frames existed. With one, ``present_player`` may return a frame node
instead of a string, and a card may cite shared material the frame carries once
rather than copying it into every candidate.

``player_label`` and ``match_label`` attach opaque grouping tags the engine
records and never interprets. They are reader-side: a label never reaches the
judge, exactly like a control's declared band. A run may also supply consumer
``params``, which reach every hook through its context; the engine carries them
and never branches on them.

A hook may randomize *which* players meet — that is sampling strategy, and
`random` writes nothing that purity verification would catch. The engine
randomizes exactly two things: presentation order, because it decodes the judge's
answer through the order it ran, and control substitution.
"""

from __future__ import annotations

import importlib.util
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType, ModuleType

from agentos.tournament import locking
from agentos.tournament.contract import CONTROL_BANDS, MAX_ARITY, MIN_ARITY
from agentos.tournament.frame import Frame, Node, render_node
from agentos.tournament.model import TournamentError

MATCH_PLAYERS = "match_players"
MATCH_IDENTITY = "match_identity"
PRESENT_PLAYER = "present_player"
VERDICT_SLOT = "verdict_slot"
CONTROLS = "controls"
PLAYER_LABEL = "player_label"
MATCH_LABEL = "match_label"
MATCH_FRAME = "match_frame"

REQUIRED_HOOKS = (MATCH_PLAYERS, MATCH_IDENTITY)
DEFAULTED_HOOKS = (
    PRESENT_PLAYER,
    VERDICT_SLOT,
    CONTROLS,
    PLAYER_LABEL,
    MATCH_LABEL,
    MATCH_FRAME,
)
HOOK_NAMES = REQUIRED_HOOKS + DEFAULTED_HOOKS

DEFAULT_QUESTION = "Rank the candidates below from best to worst."

CONTROL_RATE_ATTR = "control_rate"



DEFAULT_CONTROL_RATE = 0.0


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
    """Read-only data handed to a hook. Carries data, nothing callable.

    It never carries the presented order. Identity that varied with the shuffle
    would make every repeat run a different match and stop accumulation.
    """

    question: str
    criteria: str | None = None
    player: str | None = None
    players: tuple[str, ...] = ()
    presentations: tuple[str, ...] = ()
    verdicts: tuple[dict[str, object], ...] = ()
    match_index: int = 0
    budget: int = 0
    snapshot_path: str = ""



    params: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))


@dataclass
class TournamentDefinition:
    """One snapshotted consumer definition and its resolved hooks."""

    origin_path: Path
    snapshot_path: Path
    digest: str
    module: ModuleType
    guarded_paths: tuple[Path, ...] = field(default_factory=tuple)


    params: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    @property
    def question(self) -> str:
        return str(getattr(self.module, "question", DEFAULT_QUESTION))

    @property
    def criteria(self) -> str | None:
        value = getattr(self.module, "criteria", None)
        return None if value is None else str(value)

    def match_players(
        self,
        *,
        verdicts: tuple[dict[str, object], ...],
        match_index: int,
        budget: int,
    ) -> tuple[str, ...] | None:
        context = self._context(
            verdicts=verdicts, match_index=match_index, budget=budget
        )
        value = self._call(MATCH_PLAYERS, getattr(self.module, MATCH_PLAYERS), context)
        if value is None:
            return None
        return _validated_players(value)

    @property
    def control_rate(self) -> float:
        """How often the engine substitutes a control, as a probability."""
        value = getattr(self.module, CONTROL_RATE_ATTR, DEFAULT_CONTROL_RATE)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise HookReturnError(
                f"{CONTROL_RATE_ATTR} must be a number between 0 and 1 "
                f"(got {type(value).__name__})"
            )
        if not 0.0 <= float(value) <= 1.0:
            raise HookReturnError(
                f"{CONTROL_RATE_ATTR} must be between 0 and 1 (got {value})"
            )
        return float(value)

    def controls(
        self,
        *,
        verdicts: tuple[dict[str, object], ...],
        match_index: int,
        budget: int,
    ) -> dict[str, str]:
        """The control pool, each player with its declared band.

        The pool and not one control per call: which control appears in a given
        match is engine work, and a one-per-call hook would hand that choice back
        to the consumer.
        """
        hook = getattr(self.module, CONTROLS, None)
        if hook is None:
            return {}
        context = self._context(
            verdicts=verdicts, match_index=match_index, budget=budget
        )
        value = self._call(CONTROLS, hook, context)
        if value is None:
            return {}
        return _validated_controls(value)

    def match_frame(
        self, *, players: tuple[str, ...], presentations: tuple[str, ...]
    ) -> Frame | None:
        """This match's composed prompt, or None to keep the legacy frame.

        A definition that supplies no frame renders exactly the bytes it rendered
        before frames existed. That equivalence is load-bearing, not courteous: a
        verbatim that cannot be rebuilt exactly cannot be checked against its
        recorded hash.
        """
        hook = getattr(self.module, MATCH_FRAME, None)
        if hook is None:
            return None
        context = self._context(players=players, presentations=presentations)
        value = self._call(MATCH_FRAME, hook, context)
        if value is None:
            return None
        if not isinstance(value, Frame):
            raise HookReturnError(
                f"{MATCH_FRAME} must return a Frame or None "
                f"(got {type(value).__name__})"
            )
        return value

    def present_player(self, player: str) -> str:
        return self.present_card(player)[0]

    def present_card(self, player: str) -> tuple[str, Node | None]:
        """The player's card, rendered, and the node it came from when it had one.

        A card may be a string or a frame node. The string path is the old one and
        stays; the node path is what lets a card cite shared material instead of
        carrying its own copy of it. The node travels back beside the text because
        the composition point — not this hook — is where a cite can be checked
        against the frame's tables, and an unresolvable one must not reach a spawn.
        """
        hook = getattr(self.module, PRESENT_PLAYER, None)
        if hook is None:
            return str(player), None
        context = self._context(player=str(player))
        value = self._call(PRESENT_PLAYER, hook, context)
        if isinstance(value, Node):
            rendered = render_node(value)
            if not rendered.strip():
                raise HookReturnError(
                    f"{PRESENT_PLAYER} returned a node that renders to nothing "
                    f"for player {player!r}"
                )
            return rendered, value
        if not isinstance(value, str) or not value.strip():
            raise HookReturnError(
                f"{PRESENT_PLAYER} must return a non-empty string or a frame node "
                f"(got {type(value).__name__})"
            )
        return value, None

    def player_label(self, player: str) -> str | None:
        """This player's grouping tag, or None when it carries none.

        Unlabeled is the default and reads as one undifferentiated population.
        The label is never compared against a previous match's: a label is free
        to vary across the matches a player appears in, which is what makes a
        fold group over label occurrences rather than over players.
        """
        return self._label(PLAYER_LABEL, self._context(player=str(player)))

    def match_label(
        self, *, players: tuple[str, ...], presentations: tuple[str, ...]
    ) -> str | None:
        """This match's grouping tag, or None when it carries none."""
        context = self._context(players=players, presentations=presentations)
        return self._label(MATCH_LABEL, context)

    def _label(self, name: str, context: HookContext) -> str | None:
        hook = getattr(self.module, name, None)
        if hook is None:
            return None
        value = self._call(name, hook, context)
        if value is None:
            return None


        if not isinstance(value, str) or not value.strip():
            raise HookReturnError(
                f"{name} must return a non-empty string or None "
                f"(got {type(value).__name__})"
            )
        return value

    def match_identity(
        self, *, players: tuple[str, ...], presentations: tuple[str, ...]
    ) -> str:
        context = self._context(players=players, presentations=presentations)
        value = self._call(
            MATCH_IDENTITY, getattr(self.module, MATCH_IDENTITY), context
        )
        if not isinstance(value, str) or not value.strip():
            raise HookReturnError(
                f"{MATCH_IDENTITY} must return a non-empty string "
                f"(got {type(value).__name__})"
            )
        return value

    def verdict_slot(
        self, *, players: tuple[str, ...], presentations: tuple[str, ...]
    ) -> dict[str, object]:
        hook = getattr(self.module, VERDICT_SLOT, None)
        if hook is None:
            return {}
        context = self._context(players=players, presentations=presentations)
        value = self._call(VERDICT_SLOT, hook, context)
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise HookReturnError(
                f"{VERDICT_SLOT} must return a JSON object or None "
                f"(got {type(value).__name__})"
            )
        return dict(value)

    def _context(
        self,
        *,
        player: str | None = None,
        players: tuple[str, ...] = (),
        presentations: tuple[str, ...] = (),
        verdicts: tuple[dict[str, object], ...] = (),
        match_index: int = 0,
        budget: int = 0,
    ) -> HookContext:
        return HookContext(
            question=self.question,
            criteria=self.criteria,
            player=player,
            players=tuple(players),
            presentations=tuple(presentations),
            verdicts=verdicts,
            match_index=match_index,
            budget=budget,
            snapshot_path=str(self.snapshot_path),
            params=self.params,
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
    params: Mapping[str, str] | None = None,
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
    _require_hooks(module, origin)
    return TournamentDefinition(
        origin_path=origin,
        snapshot_path=snapshot,
        digest="sha256:" + locking.content_hash(snapshot),
        module=module,
        guarded_paths=guarded,
        params=MappingProxyType(dict(params or {})),
    )


def open_definition(
    snapshot_path: Path | str,
    *,
    origin_path: Path | str,
    guarded_paths: tuple[Path, ...] | list[Path] = (),
    params: Mapping[str, str] | None = None,
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

    module = _load_module(snapshot)
    _require_hooks(module, Path(origin_path))
    return TournamentDefinition(
        origin_path=Path(origin_path),
        snapshot_path=snapshot,
        digest="sha256:" + locking.content_hash(snapshot),
        module=module,
        guarded_paths=tuple(Path(item).resolve() for item in guarded_paths),
        params=MappingProxyType(dict(params or {})),
    )


def _require_hooks(module: ModuleType, origin: Path) -> None:
    """Fail at load, naming every missing required hook.

    Failing here rather than mid-run is the point: a tournament that starts and
    then cannot name a match is a tournament that accumulates nothing.
    """
    missing = [name for name in REQUIRED_HOOKS if not callable(getattr(module, name, None))]
    if missing:
        raise HookLoadError(
            f"tournament definition {origin} must define "
            + " and ".join(f"{name}(ctx)" for name in missing)
            + "; the engine supplies no default for either"
        )


def _load_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("tournament_definition", path)
    if spec is None or spec.loader is None:
        raise HookLoadError(f"cannot load tournament definition from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validated_controls(value: object) -> dict[str, str]:
    """A mapping, because a control *is* a player plus a declared expectation.

    A sequence would let the same player be declared twice with two bands; a
    mapping cannot express that at all.
    """
    if not isinstance(value, dict):
        raise HookReturnError(
            f"{CONTROLS} must return a mapping of player to band or None "
            f"(got {type(value).__name__})"
        )
    pool: dict[str, str] = {}
    for player, band in value.items():
        if not isinstance(player, str) or not player.strip():
            raise HookReturnError(f"{CONTROLS} returned an empty control player")
        if band not in CONTROL_BANDS:
            raise HookReturnError(
                f"{CONTROLS} declared band {band!r} for {player!r}; a control is "
                f"expected {' or '.join(CONTROL_BANDS)}"
            )
        pool[player] = str(band)
    return pool


def _validated_players(value: object) -> tuple[str, ...]:
    """Arity is the definition's per-match choice; the engine only bounds it.

    The upper bound is label exhaustion, not a design position — twenty-six
    candidates in one prompt is far past where a judge can discriminate.
    """
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise HookReturnError(
            f"{MATCH_PLAYERS} must return the match's players or None "
            f"(got {type(value).__name__})"
        )
    if not MIN_ARITY <= len(value) <= MAX_ARITY:
        raise HookReturnError(
            f"{MATCH_PLAYERS} must return between {MIN_ARITY} and {MAX_ARITY} "
            f"players (got {len(value)})"
        )
    players = tuple(str(item) for item in value)
    for player in players:
        if not player.strip():
            raise HookReturnError(f"{MATCH_PLAYERS} returned an empty player")
    if len(set(players)) != len(players):
        raise HookReturnError(f"{MATCH_PLAYERS} returned the same player twice")
    return players
