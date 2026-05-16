# Monitor Row Render Animations - impl-req

## Impl.Abstract

- **scope:** evolve the account monitor frame/render model so rows own their rendered text through `row.render_frame(...)`, monitor columns use fixed widths, and overflowing cells animate with a draw-tick-driven marquee window.
- **status:** implemented.
- **source:** follow-up from monitor background-frame-swap and column-row work. The current renderer computes column width from content length, so a long value such as `claude usage API returned HTTP 429 [retry in 39m]` or a long account label such as `claude-code/browser-jp:` stretches the whole block.
- **goal:** keep workflow output semantic and stable while the drawing loop produces fixed-width, animated display text independent of workflow refresh cadence.

## Impl.Index

### Pre.Implementation.State.Evidence

- Monitor models were defined in `src/agentos/agent/monitor/models.py`.
- `MonitorFrame` had:
  - `tick`
  - `blocks`
  - `status_lines`
  - `warnings`
  - `errors`
- Row classes exposed a `text` property, but did not render from a draw context:
  - `MonitorTextRow`
  - `MonitorAccountRow`
  - `MonitorInfoRow`
  - `MonitorUsageTimeRow`
  - `MonitorResetRow`
- `MonitorLoop` in `src/agentos/agent/monitor/loop.py` already had two loops:
  - workflow thread builds `working_frame`
  - main/draw loop renders `visible_frame`
- `MonitorLoop` already double-buffered frames:
  - `visible_frame`
  - `working_frame`
- `render.py` computed `_MonitorColumnGeometry` from actual row content:
  - label width is `max(label length)`
  - value width is `max(value length where suffix exists)`
- That content-driven geometry causes long cells to widen the whole display instead of being clipped or animated inside fixed columns.

### Accepted.Design

- Workflows do not know about animation.
- Workflows keep writing full semantic content into `MonitorFrame` rows.
- The draw loop owns visual progression.
- Animation uses draw loop ticks, not wall-clock time.
- Rows own their rendered output:

```python
row.render_frame(context) -> str
```

- If a row has no animation, `render_frame(...)` returns the same string every draw tick.
- If a row has animated overflow, `render_frame(...)` returns a different fixed-width viewport as row animation state advances.
- The draw loop should call:

```python
renderer.render(frame, state)
frame.step_animations()
```

- `step_animations(frame)` should walk frame rows and let animated rows/cells advance by one draw tick.

### Frame.Animation.Model

- Add animation support to `MonitorFrame`.
- `MonitorFrame` should expose:

```python
def step_animations(self) -> None:
    ...
```

- `step_animations(...)` should traverse all blocks and rows.
- Rows that have animation state should advance it.
- Rows with no animation should no-op.
- Do not drive animation from workflow ticks.
- Do not drive animation from `time.monotonic()` or wall-clock time.
- Animation must continue while workflows are idle or slow, because it is driven by the draw loop over `visible_frame`.
- Frame `prepare(...)` must not accidentally destroy the visible frame's animation state during normal drawing. A workflow-created `working_frame` may start new row animation state for new semantic content.

### Row.Render.Model

- Add a render context shared by row render methods. Concrete names can vary, but it should carry fixed layout constraints:

```python
MonitorRenderContext(
    label_width=...,
    value_width=...,
    suffix_width=...,
)
```

- Row rendering should move from renderer-owned string assembly to row-owned render methods:

```python
MonitorTextRow.render_frame(context) -> str
MonitorAccountRow.render_frame(context) -> str
MonitorInfoRow.render_frame(context) -> str
MonitorUsageTimeRow.render_frame(context) -> str
MonitorResetRow.render_frame(context) -> str
```

- `render_frame(...)` returns the exact plain text that should be displayed for that draw tick.
- The renderer can still wrap usage/reset rows in Rich styling/bars, but the visible text should come from the row render method.
- The JSON/debug row summary should continue to expose semantic row data, not the animated transient string as source of truth.

### Fixed.Column.Policy

- Replace content-dependent monitor column geometry with fixed widths.
- First implementation can use constants in `render.py` or monitor model/render support code.
- Start with conservative defaults that fit the current TUI:

```txt
label_width = 24
value_width = 24
suffix_width = 12
```

- The exact constants can be tuned during implementation, but they must not be derived from the longest row content.
- Column rows should render conceptually as:

```txt
<label viewport> | <value viewport> | <suffix viewport>
```

- Rows without suffix should render:

```txt
<label viewport> | <value viewport>
```

- Rows without value should render just the label viewport.

### Overflow.Animation.Policy

- Any cell can animate if its content is wider than its fixed cell width.
- Overflow animation is a moving viewport, not truncation with hidden permanent text.
- Desired behavior for a long text cell over successive draw ticks:

```txt
claude usage API returned HTTP 42
laude usage API returned HTTP 429
aude usage API returned HTTP 429 
ude usage API returned HTTP 429 [
de usage API returned HTTP 429 [r
```

- A simple marquee algorithm is sufficient:
  - hold at the start for a few draw ticks
  - shift left one cell per draw tick
  - hold at the end for a few draw ticks
  - loop back to the beginning
- Animation should use display-cell width, not raw Python string length, so Rich/wide characters do not break alignment.
- If text fits inside the fixed width, render padded static text.
- If text does not fit, render a fixed-width window of the text.

### Rich.Rendering.Policy

- Keep Rich usage/reset bar behavior.
- Rich renderer should call row render methods for visible text, then apply the existing inline percent styling to usage/reset rows.
- The colored bar width should be based on rendered fixed-width text, not the full raw content.
- Do not add a separate JSON renderer.
- `--json` remains a raw state/frame dump; animation state may appear if the row model requires it, but semantic row fields remain authoritative.

### No.Legacy.Allowed

- Do not keep a second content-measured column path.
- Do not add text parsing to recover row semantics.
- Do not make workflows pre-truncate or pre-scroll text.
- Do not animate from wall-clock time.
- Do not introduce compatibility aliases for replaced row-render APIs unless explicitly required by failing public imports.
- Do not let long Claude/account/error strings stretch monitor columns.

## Execution.Plan

### Slice 1 - Add Render Context And Fixed Widths

Status: completed.

- Add a monitor render context/width model in `src/agentos/agent/monitor/models.py` or `render.py`.
- Define fixed label/value/suffix widths.
- Remove content-derived `_MonitorColumnGeometry` as the source of column widths.
- Keep width constants easy to tune.
- Check:
  - focused tests prove a long account label or long error value does not widen the rendered row.

### Slice 2 - Move Text Rendering Onto Rows

Status: completed.

- Add `render_frame(context)` methods to monitor row classes.
- Keep `summary()` semantic.
- Update `text` properties to delegate to `render_frame(default_context)` or preserve plain semantic text only where needed for compatibility inside the frame payload.
- Ensure `MonitorTextRow` still supports blank lines and simple text rows.
- Check:
  - row render tests for account/info/usage/reset rows.
  - `--json` row summaries still expose `label`, `value`, `suffix`, and usage/reset semantic fields.

### Slice 3 - Add Row/Frame Animation State

Status: completed.

- Add animation state to rows/cells that need overflow scrolling.
- Add `step_animation()` or equivalent no-op method for rows.
- Add `MonitorFrame.step_animations()` that walks all block rows and calls row animation stepping.
- Keep non-overflow rows stable across animation steps.
- Check:
  - long cell render changes after `frame.step_animations()`.
  - short cell render remains unchanged after repeated steps.

### Slice 4 - Wire Draw Loop Animation Step

Status: completed.

- Update `MonitorLoop.run(...)` so the main draw loop calls `visible_frame.step_animations()` after `on_tick(...)`.
- Preserve workflow-loop isolation: workflows should not call animation methods.
- Preserve `--once` semantics. It can render the first animation frame and exit without needing extra animation ticks.
- Preserve row animation ticks across republished workflow frames when row semantic content is unchanged, so fast workflow publications do not reset visual scrolling.
- Check:
  - a finite monitor loop with the same visible frame produces advancing rendered text across draw ticks.
  - workflow refresh count remains independent of animation steps.

### Slice 5 - Update Plain And Rich Renderers

Status: completed.

- Update `format_monitor_frame(...)` and `rich_monitor_frame(...)` to render rows through `row.render_frame(context)`.
- Preserve Rich usage/reset colored bars.
- Ensure fixed columns are used consistently for plain and Rich output.
- Check:
  - plain monitor output has stable `|` positions even with `claude-code/browser-jp:` and long fetch error text.
  - Rich rendering still identifies usage/reset rows for percent bars.

### Slice 6 - Validation And Smoke

Status: completed.

- Run focused monitor tests:

```sh
uv run pytest tests/test_agent_account_registry_commands.py -q
```

- Run lint on touched files:

```sh
uv run ruff check src/agentos/agent/monitor tests/test_agent_account_registry_commands.py
```

- Run full suite:

```sh
uv run pytest -q
```

- Run diff whitespace check:

```sh
git diff --check
```

- Refresh installed CLI:

```sh
uv tool install --reinstall --editable .
```

- Manual smoke:

```sh
agentos agent accounts monitor --max-ticks 3
```

- Acceptance signal:
  - long account/error strings no longer stretch columns
  - overflow text visibly advances between draw ticks
  - workflow refresh cadence remains independent of animation cadence

## Impl.Log

- 2026-05-15: Drafted from alignment with the user. Accepted model: animations belong to rows; workflows do not know about animation; draw loop calls `frame.step_animations()` after render; animation uses draw ticks, not wall-clock time; fixed columns replace content-measured geometry.
- 2026-05-15: Implemented fixed monitor render context in `src/agentos/agent/monitor/models.py` with `label_width=24`, `value_width=24`, and `suffix_width=12`. Removed the renderer-owned content-measured `_MonitorColumnGeometry` path.
- 2026-05-15: Moved monitor row display rendering onto row `render_frame(...)` methods while keeping row `summary()` and `text` as semantic frame/debug data.
- 2026-05-15: Added row/frame animation state, `MonitorFrame.step_animations()`, and draw-loop stepping after renderer callbacks in `MonitorLoop.run(...)`.
- 2026-05-15: Added animation-state inheritance for semantically identical republished rows so fast workflow cycles do not reset marquees every tick.
- 2026-05-15: Updated plain and Rich monitor rendering to use row-owned rendered text. Rich usage/reset bar styling remains attached to semantic usage/reset rows.
- 2026-05-15: Validation passed: `uv run pytest tests/test_agent_account_registry_commands.py -q` (`72 passed`), `uv run ruff check src/agentos/agent/monitor tests/test_agent_account_registry_commands.py`, `uv run pytest -q` (`350 passed`), `git diff --check`, and `uv tool install --reinstall --editable .`.
- 2026-05-15: Smoke passed: `agentos agent accounts monitor --max-ticks 3` exited cleanly; `agentos agent accounts monitor --once` showed fixed columns with clipped long Claude fetch error text; `agentos agent accounts monitor --max-ticks 10` showed the long fetch error viewport advanced to `ude usage API returned H`.
