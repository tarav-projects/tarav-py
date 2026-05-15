# Monitor Column Rows - impl-req

## Impl.Abstract

- **scope:** evolve the account monitor frame/renderer row model so account title rows, usage rows, and reset rows carry semantic column pieces; renderers compute aligned columns instead of workflows manually embedding padded text.
- **status:** implemented.
- **source:** follow-up from monitor TUI design after checking `_DEPRECATED/agent-accounts-stats`; the useful deprecated pattern is renderer-owned row geometry, not the old text-parsing approach.
- **goal:** make freshness metadata fit on the account row cleanly, align `|` columns across account/usage/reset rows, and preserve the existing Rich colored bar behavior without parsing display text back into structure.

## Impl.Index

### Current.State.Evidence

- Active monitor frame rows are defined in `src/agentos/agent/monitor/models.py`.
- `LimitsTrackingWorkflow` in `src/agentos/agent/monitor/workflows.py` currently builds display-ready strings such as:
  - account row: `  ⬢ codex/br:`
  - freshness row: `    refreshed | now`
  - usage row: `    usage/time | ...`
  - reset row: `        resets | ...`
- `format_monitor_frame(...)` and `RichMonitorRenderer` in `src/agentos/agent/monitor/render.py` render rows from their `text` fields.
- Current row classes already carry some semantic values:
  - `MonitorUsageTimeRow` carries `used_percent`, `elapsed_percent`, `ratio`, `label`.
  - `MonitorResetRow` carries `elapsed_percent` and `marker_percent`.
- The recent freshness addition spends a full row per account for `refreshed | now`, which the user wants folded into the account row.

### Deprecated.Reference

- `_DEPRECATED/agent-accounts-stats/agent/account_commands.py` had a useful renderer-side geometry model:
  - `_InlineBarGroupGeometry(prefix_width, main_width, suffix_width)`
  - `_InlineBarRow(prefix_text, main_text, suffix_text, bar)`
  - `_inline_bar_group_geometries(...)` computes max cell widths with Rich `cell_len`.
  - `_render_inline_bar_row(...)` pads with Rich `set_cell_size`.
- Do not port the old parser design. The deprecated implementation parsed plain text lines to recover structure. The active monitor should keep structure native in `MonitorFrame` rows.

### Target.Model

- The workflow owns semantic monitor data.
- The renderer owns visual geometry.
- No workflow code should manually pad strings to align `|`.
- No renderer code should parse `usage/time` strings to recover usage/reset values.
- Row text can remain available for JSON/debug compatibility, but it should be derived from row pieces rather than treated as the source of truth.

### Row.Model

- Extend or replace current row classes with column-aware row pieces. Concrete shape may vary, but the model should support:

```python
MonitorAccountRow(
    label="⬢ codex/br:",
    value="now" | "Fri 05-15 15:03",
    suffix=None | "12m ago",
)

MonitorUsageTimeRow(
    label="usage/time",
    value=" 1% /  0% = n/a",
    suffix="Burst",
    used_percent=1,
    elapsed_percent=0,
    ratio=None,
)

MonitorResetRow(
    label="resets",
    value="Fri 05-15 21:35",
    suffix="4h 59m",
    elapsed_percent=...,
    marker_percent=...,
)
```

- Account rows with no freshness metadata should render as the current plain account title shape.
- Account rows with fresh metadata should render conceptually as:

```txt
    ⬢ codex/br: | now
```

- Account rows with registry fallback metadata should render conceptually as:

```txt
    ⬢ codex/br: | Fri 05-15 15:03 | 12m ago
```

- Usage and reset lines should keep their current content, only with the separator alignment owned by the renderer.

### Rendering.Model

- Plain output and Rich output should use the same row geometry rules.
- Geometry should be computed per monitor block, or per natural row group inside a block, using display-cell width where Rich is available.
- `|` separators should align for:
  - account rows with freshness metadata
  - usage/time rows
  - reset rows
- Rich bar rendering should continue to apply colored backgrounds to usage/reset rows.
- Rich bar width should be based on the computed main column width, not ad hoc full-line string length.
- Do not add a JSON renderer. `--json` remains a raw state/frame dump.

### Desired.Output.Shape

- Example fresh row:

```txt
    ⬢ codex/br: | now
      usage/time |  1% /  0% = n/a | Burst
          resets | Fri 05-15 21:35 | 4h 59m
```

- Example fallback row:

```txt
    ⬢ codex/br: | Fri 05-15 15:03 | 12m ago
      usage/time |  1% /  0% = n/a | Burst
          resets | Fri 05-15 21:35 | 4h 59m
```

- Exact spacing is owned by implementation, but the first `|` column should be visually aligned across the account/usage/reset rows in a block.

### Compatibility.Policy

- No legacy slop.
- Do not keep a second text-parsing renderer path.
- Do not introduce compatibility aliases for old row classes if the new row classes replace them.
- Update tests to assert the new expected output and JSON row payloads.

## Execution.Plan

### Slice 1 - Add Column-Aware Row Model

Status: completed.

- Update `src/agentos/agent/monitor/models.py` with native row fields for column rendering.
- Add an account/title row kind that can carry freshness metadata.
- Update row summaries so `--json` exposes the structured pieces.
- Keep the frame API simple and local to monitor models.
- Validate with focused unit tests around row summary payloads.

### Slice 2 - Emit Structured Rows From LimitsTrackingWorkflow

Status: completed.

- Update `src/agentos/agent/monitor/workflows.py` so account titles are emitted as account rows.
- Fold `raw["usage_record"]` freshness metadata into the account row instead of emitting a separate `refreshed` text row.
- Update usage/reset row construction to pass label/value/suffix fields instead of preformatted full text where appropriate.
- Preserve usage/time math and reset time calculations.
- Validate with monitor `--once` plain-output tests.

### Slice 3 - Render Columns In Plain And Rich Renderers

Status: completed.

- Update `src/agentos/agent/monitor/render.py` to compute column geometry from row pieces.
- Render plain text with aligned separators using the same geometry model.
- Render Rich usage/reset bars from structured row pieces and preserve colored bar behavior.
- Avoid parsing `row.text` for semantics.
- Validate with tests covering plain output and JSON row payloads.

### Slice 4 - Remove Stale Text-Only Assumptions

Status: completed.

- Remove monitor code that treats the old full `text` string as authoritative for structured rows.
- Keep genuinely plain `MonitorTextRow` for blank lines, errors, and simple status text.
- Ensure no workflow-side manual padding was added.
- Run `rg` checks for stale `refreshed |`, old line-shape assertions, or parser-like usage/time matching in the monitor renderer.

### Slice 5 - Validation

Status: completed.

- Run focused tests:

```sh
uv run pytest tests/test_agent_account_registry_commands.py -q
```

- Run full suite:

```sh
uv run pytest -q
```

- Run lint on touched files:

```sh
uv run ruff check src/agentos/agent/monitor tests/test_agent_account_registry_commands.py
```

- Run diff whitespace check:

```sh
git diff --check
```

- Refresh installed CLI if monitor CLI behavior changed:

```sh
uv tool install --reinstall --editable .
```

- Manual smoke:

```sh
agentos agent accounts monitor --once
```

## Impl.Log

- 2026-05-15: Drafted from user alignment. Key implementation decision: borrow the deprecated renderer-owned geometry idea, but not the deprecated text-parsing design. The active monitor should carry semantic row pieces in `MonitorFrame` and let renderers compute aligned columns.
- 2026-05-15: Implemented. Added `MonitorAccountRow`; changed usage/reset rows to carry label/value/suffix pieces; moved freshness metadata onto the account row; updated renderer-owned geometry for plain and Rich output; removed active monitor `refreshed |` row output; validated with focused tests, full suite, lint, diff check, CLI reinstall, smoke run, and stale-string search.
