# 699 — skw parser: type the parse frame

## Impl.Abstract

- **Scope**: a single, module-local maintainability cleanup of the freshly-landed v2 parser (`agentos-py/src/agentos/skillware/model.py`, 698). Replace the untyped `frame` dict — a stringly-typed `dict[str, object]` with ~11 keys threaded through five nested closures — with a small typed `_Frame` dataclass. Behavior-preserving; no grammar, POI, or public-API change.
- **Origin**: `agentos-hugentics-codebase-cleaner --AUTO`. Cleanup theme = *maintainability / design clarity*: the dominant smell in the new parser is the stringly-typed frame, easy to mistype (`frame["verb"]`) and opaque to the type checker.
- **Constraints (carried from cleanup)**: stay narrow — one function's internal representation; module-local (`_Frame` is a private dataclass in `model.py`); no new framework; replace the dict outright rather than wrap it; the public `SkwSource`/`SkwRecipe`/`SkwConstruct`/`SkwDependency`/`SkwNote` surface is unchanged.
- **Verification**: the existing `tests/test_skillware.py` (76 tests) exercises every closure path (recipe, void dependency, note attach, router rows, nesting, force-close at heading/EOF); green before and after is the acceptance signal. Full agentos-py suite (408) as the outer guard.

## Impl.Index

- **[DC] the frame today** — a `dict` literal with keys `command`, `verb`, `heading`, `line`, `label`, `address`, `decl_span`, `body_start`, `froms`, `intent`, `notes`, `needs_end`, `children`. Created once in the main loop; read in `emit_frame`, mutated in the `--when`/`--then` parent-linkage (`parent["command"] = "router"`, `parent["needs_end"] = True`, `parent["children"].append(...)`), and popped in `close_top`/`force_close`/`peer_close_rows`.
- **[DF] `_Frame`** — a private, mutable `@dataclass` mirroring those fields with real types (`command: str`, `verb: str | None`, `children: list[str]`, `notes: list[SkwNote]`, spans as `tuple[int, int]`, …). Mutation sites (`.command`, `.needs_end`, `.children`) stay in-place, so a `frozen=True` is not used.
- **[CT] behavior parity** — the dataclass is a drop-in for attribute access; every `frame["x"]` becomes `frame.x`. No control-flow change, no new/renamed findings, identical `SkwSource` output.

## Execution.Plan

### Slice 1 — introduce `_Frame` and convert every access ✅
- **Change**: add the `_Frame` dataclass; build it in the main loop; convert all `frame["..."]`/`parent["..."]`/`stack[-1]["..."]` reads and writes to attribute form across `emit_frame`, `close_top`, `peer_close_rows`, `check_router_children`, `force_close`, and the main loop.
- **Check**: `uv run pytest tests/test_skillware.py -q` green (76); no behavior diff.
- **Observable**: `parse_skw_source` returns identical results; `stack: list[_Frame]`.

### Slice 2 — fold the trivial adjacent clarities ✅
- **Change**: `for note in frame.notes: notes.append(note)` → `notes.extend(frame.notes)`; keep `_has_content` as the single body-content predicate.
- **Check**: suite green.

### Acceptance signals
- `tests/test_skillware.py` 76/76 and the full agentos-py suite 408/408 pass unchanged; the parser carries a typed frame; no public surface moved.

## Impl.Log
- 2026-07-21 — created under the codebase-cleaner (`--AUTO`) as the scoped cleanup Impl.Req for the 698 parser; single theme (frame typing), design + exec autonomous.
