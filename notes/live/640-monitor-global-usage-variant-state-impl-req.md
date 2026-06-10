# Monitor Global Usage Variant State - impl-req

## Impl.Abstract

- **scope:** replace per-row usage display toggles with one global monitor display state for the Weekly `%` / `Burst` usage type.
- **status:** implemented.
- **source:** follow-up from Weekly Burst pressure monitor work and the key-toggle discussion. The current implementation makes `r` toggle each visible row's local `variant_index`; the accepted design is simpler: one global state variable flips, and every eligible usage row renders from that mode.
- **goal:** make `%` / `Burst` usage-type selection a monitor-level display mode, not row-local animation state.
- **strong constraint:** eliminate automatic usage-type switching. Draw-tick animation remains only for overflow/marquee text; pressing `r` is the only usage-type toggle path.

## Impl.Index

### Current.State

- `src/agentos/agent/monitor/clock.py` defines `MONITOR_USAGE_VARIANT_TOGGLE_ALARM = "io.usage-variant-toggle"`.
- `src/agentos/agent/commands.py` has an interactive monitor input thread:
  - Enter sets `MONITOR_ENTER_ALARM`
  - `r` sets `MONITOR_USAGE_VARIANT_TOGGLE_ALARM`
- `src/agentos/agent/monitor/loop.py` currently handles the display alarm by calling:

```python
self.visible_frame.toggle_usage_time_variants()
```

- `src/agentos/agent/monitor/models.py` currently stores usage-type selection in each `MonitorUsageTimeRow`:
  - `variants: tuple[MonitorColumnVariant, ...]`
  - `variant_index: int`
  - `toggle_variant()`
  - `MonitorFrame.toggle_usage_time_variants()`
  - animation-state inheritance copies row `variant_index`
- This produces global-looking behavior for visible rows, but the state is scattered across row objects and must be copied into refreshed frames.

### Accepted.Design

- Add one monitor-global display state under `MonitorState.data`.
- Use a stable nested key, for example:

```python
state.data["monitor_display"] = {
    "usage_variant": "used",
}
```

- Supported usage variants:
  - `"used"` -> render `%` used pace, label `usage/time [used]`
  - `"left"` -> render remaining Burst pressure, label `time/usage [left]`
- Pressing `r` flips the global state:

```text
used -> left -> used
```

- All eligible `MonitorUsageTimeRow` rows render from the same global mode.
- Newly refreshed workflow frames automatically use the current global mode because rendering reads monitor state, not row-local copied state.
- The `r` toggle remains display-only:
  - it must not refresh account status
  - it must not wake monitor workflows
  - it must not reset adaptive `limits-tracking` alarms

### Render Boundary

- Prefer passing display mode through render context rather than mutating rows on keypress.
- `MonitorRenderContext` can carry `usage_variant: Literal["used", "left"]`.
- `format_monitor_frame(...)`, `rich_monitor_frame(...)`, and renderer paths should render rows with the display mode from monitor state.
- If a caller has only a `MonitorFrame`, default mode should be `"used"` so existing plain rendering remains deterministic.
- JSON/debug row summary should continue to expose semantic variants and current display mode if useful, but must not require parsing rendered text.

### Row Model

- Keep paired `MonitorColumnVariant` objects; they are the right representation for row-owned alternate displays.
- Remove row-local selection state:
  - remove `MonitorUsageTimeRow.variant_index`
  - remove `MonitorUsageTimeRow.toggle_variant()`
  - remove `MonitorFrame.toggle_usage_time_variants()`
  - remove variant-index inheritance from `_inherit_row_animation_state(...)`
- `MonitorUsageTimeRow.render_frame(context)` should select the active variant from `context.usage_variant`.
- If the requested variant is unavailable for a row, render the base row or the first variant. Keep the fallback simple and deterministic.

### Input And Loop Behavior

- Keep `MONITOR_USAGE_VARIANT_TOGGLE_ALARM`.
- Keep `r` key binding in `commands.py`.
- Change `MonitorLoop._apply_display_alarms(...)` so it flips `MonitorState.data["monitor_display"]["usage_variant"]`.
- Keep `_workflow_alarm_names(...)` filtering so display-only alarms do not reach workflows.
- Ensure `MonitorLoop._prepare_visible_frame_for_render()` or renderer calls can see the current display mode.

### No.Legacy.Allowed

- Do not keep per-row `variant_index`.
- Do not keep frame-level row mutation for usage-type toggling.
- Do not reintroduce automatic 5-tick usage-type rotation.
- Do not make `r` trigger account refresh.
- Do not add compatibility aliases for old JSON fields.

## Execution.Plan

### Slice 1 - Add Global Display State

Status: complete.

- Add helper functions or methods in `MonitorLoop` for:
  - reading current usage variant
  - toggling current usage variant
  - initializing default `"used"` state
- Store state under `state.data["monitor_display"]["usage_variant"]`.
- Check:
  - default mode is `"used"`
  - toggling flips to `"left"` and back
  - state appears in JSON/debug monitor state

### Slice 2 - Move Variant Selection Into Render Context

Status: complete.

- Extend `MonitorRenderContext` with a usage-variant field.
- Update render paths to pass the current global usage variant.
- Update `MonitorUsageTimeRow.render_frame(...)` to select variants by context rather than row-local `variant_index`.
- Remove row/frame toggle methods and variant-index inheritance.
- Check:
  - `frame.step_animations()` does not change usage type
  - rendering the same frame with different contexts changes all eligible rows consistently

### Slice 3 - Keep `r` As Display-Only Toggle

Status: complete.

- Update `MonitorLoop._apply_display_alarms(...)` to toggle global state.
- Preserve `_workflow_alarm_names(...)` filtering.
- Preserve Enter refresh behavior in `commands.py`.
- Check:
  - `r` toggles global display state
  - `r` does not queue workflow snapshots
  - Enter still queues the refresh path

### Slice 4 - Tests And Validation

Status: complete.

- Update monitor tests to assert global state behavior:
  - default JSON/render mode is `usage/time [used]`
  - toggling state changes render to `time/usage [left]`
  - toggling twice returns to `usage/time [used]`
  - refreshed rows use the global state without inheriting row-local indices
  - display alarm remains workflow-filtered
- Run:

```sh
uv run pytest tests/test_agent_monitor_auto_prime.py -q
uv run pytest tests/test_agent_account_registry.py tests/test_agent_monitor_auto_prime.py -q
uv run ruff check src/agentos/agent/monitor src/agentos/agent/commands.py tests/test_agent_monitor_auto_prime.py
```

- Smoke:

```sh
agentos agent accounts monitor --once --json | rg -n 'monitor_display|usage_variant|variants|usage/time \[used\]|time/usage \[left\]'
```

## Impl.Log

- Created from the monitor display-mode discussion. The target is to simplify the current row-local toggle implementation into one global monitor display variable flipped by `r`.
- 2026-06-09: Executed as designed. No deviations recorded. Validation commands listed in Slice 4 passed.
