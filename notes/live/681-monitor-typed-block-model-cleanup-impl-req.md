# 681 — monitor: typed block model + auto-prime period-parse dedup

## Impl.Abstract

- **Scope:** cleanup pass on the monitor subsystem (invoked via
  `agentos-hugentics-codebase-cleaner`, autonomous). Three themes:
  1. Replace the untyped block dicts in `monitor/models.py` with a
     `MonitorBlock` dataclass. Remove the legacy `lines` string mirror, the
     repeated `MonitorRow`-union isinstance validation
     (`monitor_block_rows` / `monitor_block_heading_rows`), and the
     `title` + `heading_rows` double bookkeeping in `monitor/loop.py`.
  2. Extract the duplicated limit/period parsing shared by
     `_eligible_limit_period` and `_uninitialized_trigger_reasons` in
     `monitor/workflows/auto_prime.py`.
  3. Fold the `MonitorTextRow` / `MonitorMarqueeRow` render/summary
     duplication where theme 1 makes it natural.
- **Status:** COMPLETE.
- **Source context:** follow-up to `680-monitor-frame-row-model-unification-impl-req.md`,
  which deliberately deferred the block-container question ("retained block
  `title` as metadata"). The dict shape is now the last untyped surface in the
  frame model.
- **Constraints carried from cleanup:** stay narrow, module-local helpers, no
  new frameworks, replace obsolete shapes rather than wrap them, no
  backward-compat aliases (`agentos-py` policy).
- **Out of scope:** workflow logic, rendering visuals, payload keys other than
  the block shape, the `workflows/` package layout (just split in `f20c08b`).

## Impl.Index

### Block: blocks are the last untyped container in the frame model
- Evidence:
  - `monitor/models.py` `monitor_block(...)` builds `dict[str, object]` with
    keys `lines`, `heading_rows`, `rows`, optional `title`, `data`.
  - `monitor_block_rows(...)` and `monitor_block_heading_rows(...)` re-validate
    the full `MonitorRow` union with `isinstance` on every access; the union is
    spelled out three times in the module (also `monitor_row_payload`).
  - `monitor/loop.py` `_apply_clock_feedback_to_visible_frame` writes both
    `block["title"]` and `block["heading_rows"]` for the same fact, twice.
  - No caller passes `lines=` or `heading_rows=` to `MonitorFrame.add_block`;
    heading rows are always derived from `title` (verified by grep across
    `src/`, `tests/`, and `agentos-cli`).
  - The payload `lines` field has no consumer in tests or the CLI.
- Decision: introduce `@dataclass MonitorBlock` with fields `title: str | None`,
  `rows: list[MonitorRow]`, `data: dict[str, object] | None`. Heading rows are
  **derived**: a `heading_rows` property returning
  `[MonitorTextRow(title, indent=False)]` when `title` is set, else `[]`.
  Deriving (not storing) removes the loop's double bookkeeping outright — the
  loop sets only `block.title`. This is safe because `MonitorTextRow` has no
  animation state, so recomputing the row per access loses nothing.
  Delete `monitor_block`, `monitor_block_rows`, `monitor_block_heading_rows`,
  and the `lines` mirror (model, payload, and `add_block(lines=...)` support).
  `monitor_block_payload` becomes a `MonitorBlock.payload()` method emitting
  `title`, `heading_rows`, `rows`, `data` (no `lines`).

### Block: consumers of the block dict shape
- Evidence (all must migrate to attribute access):
  - `monitor/loop.py:198-217` — `block.get("data")`, title/heading writes.
  - `monitor/render.py:94,199-213` — payload build and render walk.
  - `monitor/models.py` `_frame_rows` — animation flattening.
  - workflows: `frame.add_block(name, rows=..., data=...)` call sites in
    `limits_tracking.py`, `auto_prime.py`, `account_rotation.py` (signature
    keeps `title`, `rows`, `data`; drops `lines`, `heading_rows`).
  - tests: `tests/test_agent_monitor_auto_prime.py` (`blocks[0]["title"]`,
    payload assertions), `tests/test_agent_account_rotation_monitor.py` and
    `tests/test_agent_non_aligned_homes_monitor.py` (`b.get("title")`,
    `monitor_block_rows(block)`).
- Decision: replace dict indexing with `block.title` / `block.rows` /
  `block.data` everywhere, including tests. No compatibility shim.

### Block: auto-prime parses the same period twice
- Evidence: `monitor/workflows/auto_prime.py` — `_eligible_limit_period` and
  `_uninitialized_trigger_reasons` duplicate ~35 lines: extract `limit_id`,
  `used_percent`, `period_started_at`/`period_ends_at`/`resets_at`, validate
  `period_end > now`, extract provider/account/home, build
  `normal_period_key`, and call `_auto_prime_trigger_reasons`.
- Decision: extract a module-local parsed-context helper (e.g.
  `_parse_limit_period(source_target_state, limit, *, now)` returning a small
  frozen dataclass or `None`) plus a shared reasons call. Both callers consume
  it; behavior identical, including the observation-recording differences that
  stay in `_eligible_limit_period`.

### Block: marquee row duplicates text row mechanics
- Evidence: `MonitorMarqueeRow.render_frame`/`summary` are near-copies of
  `MonitorTextRow`'s (only the `indent` default and payload-emission condition
  differ — and the differing `indent` conditions in `summary` mean both emit
  `indent` only when it deviates from their default).
- Decision: extract module-local `_text_row_render(text, indent, context)` and
  `_text_row_summary(kind, text, indent, default_indent)` helpers used by both
  row types. No inheritance games; dataclass fields stay as they are.

## Execution.Plan

Ordering: slice 1 (block model) is the wide one and gates the test updates;
slices 2 and 3 are local and independent.

### Slice 1 — `MonitorBlock` dataclass replaces block dicts
- Changes: add `MonitorBlock` to `models.py`; rewrite `MonitorFrame.add_block`
  (drop `lines`/`heading_rows` params), `_frame_rows`, payload building;
  delete `monitor_block`, `monitor_block_rows`, `monitor_block_heading_rows`,
  `monitor_block_payload` (folded into the dataclass); update `loop.py` clock
  feedback to set `block.title` only; update `render.py` walk; update the
  three monitor test files and `monitor/__init__.py` exports.
- Path: workflow `add_block` → frame model → loop clock feedback → renderer →
  JSON payload.
- Observable result: no `dict[str, object]` blocks anywhere; payload blocks
  carry `title`, `heading_rows`, `rows`, `data` and no `lines`.
- Check (RED→GREEN): adjust payload test to assert `"lines" not in block`
  (RED before the change); full monitor suite green after.

### Slice 2 — auto-prime period-parse helper
- Changes: add `_parse_limit_period` (module-local) in `auto_prime.py`;
  `_eligible_limit_period` and `_uninitialized_trigger_reasons` consume it.
- Observable result: single parsing path; both functions shrink to their
  distinct logic (eligibility bookkeeping vs. uninitialized filtering).
- Check: existing auto-prime trigger/verification tests stay green (they cover
  both callers: eligibility, retry-block, verification transitions).

### Slice 3 — shared text-row helpers
- Changes: module-local render/summary helpers in `models.py` used by
  `MonitorTextRow` and `MonitorMarqueeRow`.
- Observable result: one implementation of text-row rendering/serialization.
- Check: marquee/text row payload + render tests stay green.

### Risks / deviation triggers
- Payload shape: dropping `lines` changes `monitor_result_payload`. Grep found
  no consumer; if one surfaces during execution, stop and surface (cleanup
  never broadens scope).
- Derived heading rows: if some path needs animated or multi-row headings,
  the property approach breaks — that would be a design reshape; abort and
  surface rather than storing rows again.

### Acceptance signals
- `uv run pytest tests/ -q` green (252 tests at plan time).
- `uv run ruff check src tests` clean.
- No `monitor_block*` dict helpers remain; `grep -rn '"lines"' src/agentos/agent/monitor` empty.

## Impl.Log

- 2026-07-04: Impl.Req created autonomously from the codebase-cleaner scan;
  boundary confirmation skipped per `--AUTO`.
- 2026-07-04: Executed slices 1-3 (executer, autonomous). Checkpoint commit:
  `845534d`. Open-space decisions:
  - `monitor_row_payload` deleted outright (not simplified): with typed
    `MonitorBlock.rows` and typed `top_rows`, payload building is plain
    `row.summary()` calls — no union re-validation anywhere.
  - `_LimitPeriod` carries `uninitialized_period_key` so
    `_eligible_limit_period` no longer rebuilds the provider/account/home
    join inline.
  - `MonitorBlock` added to `monitor/__init__` exports.
- Observation (out of scope): `agentos-cli` test suite has 27 pre-existing
  failures (argparse-level, `agent accounts` subcommands) — reproduced with
  this change stashed at the checkpoint; unrelated to the monitor cleanup.
- Verification: `uv run pytest tests/ -q` → 252 passed; `uv run ruff check
  src tests` → clean; `grep -rn '"lines"' src/agentos/agent/monitor` → empty.
