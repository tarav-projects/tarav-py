# Check-Selection CLI De-duplication — Implementation Request

## Impl.Abstract

- **Scope:** remove the duplicated check-selection **CLI surface** between the index linter and the skw linter by hoisting it into the shared `skwlint` core (which already owns the selection *logic*).
- **What:** the `--list-checks` render loop is byte-identical in `index/commands.py` and `skillware/commands.py`; the `--check`/`--skip`/`--list-checks` argparse block is near-identical. Extract a shared renderer and a shared arg-adder into `skwlint`; both CLIs call them.
- **Status:** IMPLEMENTED (cleanup run, `--AUTO`). Both slices done; full `agentos-py` suite 454 passed; live `--list-checks` on both CLIs renders from one code path; flags unchanged.
- **Source context:** cleanup scan; motivated by the user's "we must not duplicate the linter mechanics" observation after the selection core was shared but its CLI surface was left copied.
- **Out of scope:** converging the two linter *run-loops* (index gated `CHECKS` vs skw POI-kind stream) — a larger design question, not a cleanup; anything beyond the selection CLI surface.

## Impl.Index

- **Current state (cited):**
  - `src/agentos/index/commands.py` `_cmd_linter` — `--list-checks` prints via a 3-line loop (`state`/`tier`/`print`); argparse block adds `--check`/`--skip`/`--list-checks` to `linter_parser`.
  - `src/agentos/skillware/commands.py` `_cmd_skillware_check` — the same 3-line render loop; the same argparse block added inside the `check` subparser branch (help text says "POI kind" vs the index "check").
  - `src/agentos/skwlint.py` — already owns `check_selector`, `resolve_enabled_checks`, `check_registry`. Natural home for the selection CLI surface too.
- **Design decisions:**
  - the shared renderer is a **pure** function returning text lines (no printing) — testable, no I/O in the core.
  - the shared arg-adder takes the parser plus a `unit` label so each CLI keeps its own noun in help ("check" vs "POI kind"); `skwlint` importing `argparse` (stdlib) is acceptable since it already owns the selection system end to end.

## Execution.Plan

Test-first at boundaries. Loop: `pytest tests/test_skw_check_selection.py tests/test_index_linter.py`; completion runs full `pytest` + live `--list-checks` on both CLIs.

### Slice 1 — Shared `render_check_registry`
- **Do:** add `render_check_registry(rows) -> list[str]` to `skwlint` (rows = `check_registry(...)` output). One formatted line per row, identical to today's format. Replace the render loop in both `_cmd_linter` and `_cmd_skillware_check` with a call that prints the returned lines.
- **Observable:** the function returns the expected formatted lines; both CLIs' `--list-checks` output is unchanged.
- **RED/GREEN:** unit test on the formatter (on/off + structural/reportable + alignment); the existing `--list-checks` CLI tests (index + skw) still pass unchanged.

### Slice 2 — Shared `add_check_selection_args`
- **Do:** add `add_check_selection_args(parser, *, unit="check")` to `skwlint` adding `--check`/`--skip`/`--list-checks` with `unit`-parameterized help. Call it from the index `linter_parser` setup and the skw `check` subparser branch; delete the inline argparse blocks.
- **Observable:** both parsers still accept the three flags with the same behavior.
- **RED/GREEN:** existing include/exclude/list/unknown-selector CLI tests on both linters still pass; a focused test that `add_check_selection_args` wires all three onto a fresh parser.

## Slice Status

- Slice 1 — shared `render_check_registry` in `skwlint` — ✅ both `_cmd_linter` and `_cmd_skillware_check` render through it
- Slice 2 — shared `add_check_selection_args(parser, *, unit)` in `skwlint` — ✅ both argparse sites call it; inline blocks deleted

## Impl.Log

- Net: the byte-identical `--list-checks` render loop and the near-identical `--check`/`--skip`/`--list-checks` argparse block collapsed to one home each in `skwlint`; the two linter CLIs now consume the whole selection surface (logic + rendering + args) from the core. Run-loops remain distinct by design (out of scope).
