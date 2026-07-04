# 680 — monitor: unify all rendered output under the frame row model

## Impl.Abstract

- **Scope:** remove the monitor's split rendering model so every visible line is
  owned by the frame model and rendered through the same row primitives.
  - Move the hardcoded top header (`Agent accounts monitor`, `Tick: ...`) out of
    the renderer and into frame-owned rows.
  - Replace `MonitorFrame.status_lines` with frame-owned rows; transient status
    such as `workflow: fetching account data` and `waiting for workflow frame`
    should use the same row pipeline as everything else.
  - Stop treating block titles as renderer-only strings; printed block headings
    should also be model-owned rows.
  - Add a dedicated marquee/help row type for the one-line shortcut strip
    beneath `Tick:`. It must use the existing circular right-to-left viewport
    behavior and loop on one line rather than wrapping.
  - Extend animation stepping + animation-state inheritance to include the new
    top/header rows so the marquee does not reset on every frame publish.
- **Status:** COMPLETE.
- **Source context:** current discussion plus the current monitor code. Hard
  evidence from the implementation:
  - the top header is hardcoded in `monitor/render.py` (`_monitor_render_rows`)
  - `MonitorFrame.status_lines` is a parallel string-only surface in
    `monitor/models.py`
  - the loop repopulates `status_lines` in `monitor/loop.py`
  - animation exists already, but only for row objects reachable through frame
    blocks (`MonitorFrame.step_animations`, `inherit_animation_state_from`,
    `_render_cell`, `_circular_cell_viewport`)
  - input shortcuts are currently `Enter`, `r`, and `m` from
    `agent/commands.py`; the new marquee line will surface those bindings.
- **Out of scope:**
  - changing shortcut behavior
  - redesigning usage/reset bar visuals
  - changing workflow logic unrelated to presentation composition
  - broader monitor block/workflow feature additions beyond the top info line

## Impl.Index

### Block: the monitor currently has three separate printed-surface systems
- Evidence:
  - renderer literals print `Agent accounts monitor` and `Tick: ...` directly in
    `agentos/agent/monitor/render.py`
  - `MonitorFrame.status_lines: list[str]` is maintained separately in
    `agentos/agent/monitor/models.py`
  - block bodies already use typed row primitives (`MonitorTextRow`,
    `MonitorInfoRow`, `MonitorUsageTimeRow`, `MonitorResetRow`, ...)
  - block titles are another renderer special case (`title` string on block
    dicts, rendered separately in `render.py`)
- Decision: collapse printed content to one model-driven rendering path. The
  frame should own top/header rows explicitly; blocks should expose heading/body
  rows explicitly. The renderer should walk row objects, not invent text.

### Block: animation already solves the marquee problem, but only inside rows
- Evidence:
  - `_render_cell(value, width, animation_tick)` scrolls oversized content by
    delegating to `_circular_cell_viewport(...)`
  - `MonitorFrame.step_animations()` currently advances only rows inside blocks
  - `MonitorFrame.inherit_animation_state_from(...)` only pairs rows returned by
    `_frame_rows(frame)`, which currently flattens block rows only
- Decision: reuse the existing cell viewport animation rather than inventing a
  new header-specific ticker path. The new shortcut strip should be a row type
  that renders through the same width-aware cell machinery and participates in
  the normal animation lifecycle.

### Block: a dedicated marquee/help row is clearer than overloading `MonitorInfoRow`
- Evidence:
  - `MonitorInfoRow` is column-oriented (`label | value | suffix`) and is good
    for structured facts, not a single long looping sentence
  - the desired shortcut strip is one full-width help sentence such as
    `Enter refresh | r toggle used/left | m materialize`
- Decision: add a new row type for full-width animated/help text rather than
  forcing a one-cell marquee into the three-column row family. Keep the
  existing column rows unchanged; add the minimal new primitive the design
  actually needs.

### Block: prefer a clean-cut model change over keeping legacy parallel fields
- Evidence:
  - current JSON payload includes `frame.status_lines` only because the model
    has that legacy field; tests assert monitor row payloads and rendered text,
    but no tests depend on `status_lines`
  - local `agentos-py/AGENTS.md` explicitly says not to add backward-compat
    aliases unless requested
- Decision: remove the parallel `status_lines` surface instead of preserving it
  as a redundant alias. The payload should expose the new frame-owned row data
  directly. If any compatibility issue appears during implementation, treat it
  as a deviation and decide explicitly rather than silently carrying both.

## Execution.Plan

Ordering: first establish the unified frame/block row model, then switch the
renderer to consume it, then migrate the loop/workflows to populate the new
surfaces and add the shortcut marquee. This keeps the first slice about model
boundaries, the second about rendering, and the third about composition.

### Slice 1 — introduce frame-owned top rows and typed block headings
- Changes:
  - extend `MonitorFrame` with a typed top-level row surface (for example
    `top_rows`)
  - replace `status_lines` with top rows
  - replace block `title: str` rendering dependence with typed heading rows in
    the block model
  - update `step_animations()` and `inherit_animation_state_from()` so top rows
    and heading rows participate alongside body rows
  - add the new marquee/help row type to the row union + payload helpers
- Path: `MonitorFrame` / block model → row flattening → animation state carryover.
- Observable result: a frame can fully describe its top printed content and
  block headings without renderer literals or string-only `status_lines`; two
  successive frames with identical marquee text preserve animation position.
- Check (RED→GREEN): add model/render tests that build two frames with the same
  animated top row, step/publish between them, and assert the animation tick is
  inherited instead of resetting. Assert top rows and heading rows serialize in
  `monitor_result_payload(...)`.

### Slice 2 — make the renderer consume only model-owned rows
- Changes:
  - rewrite `_monitor_render_rows(...)` so it renders frame-owned top rows,
    then errors/warnings as rows, then block heading/body rows
  - remove the hardcoded `Agent accounts monitor` / `Tick:` literals from the
    renderer
  - remove the `Status: ...` string expansion path
  - ensure the new marquee/help row renders as one width-aware animated line
    using the existing circular viewport behavior
- Path: frame model → render row dispatch → final text/Rich output.
- Observable result: `format_monitor_frame(...)` and Rich rendering produce the
  same monitor display as before for title/tick/status/headings, but now all of
  it comes from row objects; long help text loops horizontally instead of
  wrapping onto extra lines.
- Check (RED→GREEN): update/extend renderer tests to assert the rendered header
  text now comes from model-owned rows, and that a narrow-width marquee row
  renders a cropped single-line viewport rather than emitting multiple lines.

### Slice 3 — migrate loop/workflow composition and add the shortcut marquee
- Changes:
  - have `MonitorLoop` populate frame top rows instead of `status_lines`
  - emit the stable top rows in this order: monitor title, tick row, shortcut
    marquee/help row, transient workflow/waiting rows when applicable
  - migrate block title composition in workflows to the new heading-row shape
  - define the initial shortcut text from the actual bindings in
    `agent/commands.py`: `Enter`, `r`, `m`
- Path: loop/workflow state → frame composition → renderer.
- Observable result: interactive monitor top area becomes:
  - `Agent accounts monitor`
  - `Tick: N`
  - animated one-line shortcut help
  - transient workflow/waiting messages when needed
  while the rest of the monitor remains unchanged.
- Check (RED→GREEN): add/extend loop tests to assert the visible frame contains
  the new top rows during startup, steady-state, and workflow-active states.
  Assert the shortcut strip text is present and that animation survives frame
  swaps across loop ticks.

### Risks / deviation triggers
- **Payload drift:** `monitor_result_payload(...)` shape will change when
  `status_lines` disappears. If any consumer or test outside the monitor suite
  depends on that field, stop and decide whether to migrate or to stage the
  change explicitly.
- **Over-refactor risk:** do not turn this into a full monitor architecture
  rewrite. The goal is unified printed-row ownership, not redesigning every
  internal container unless needed to support that.
- **Animation regressions:** any path that forgets to include top rows or
  heading rows in `step_animations()` / `inherit_animation_state_from()` will
  cause the marquee to jitter or reset. Treat that as a blocking regression.
- **Width semantics:** the marquee row must remain a single visual line. If the
  chosen row type can wrap under Rich, tighten the row rendering contract until
  it cannot.

### Acceptance signals
- `monitor/render.py` no longer hardcodes printed header/status text.
- `MonitorFrame` owns the top rendered lines through typed rows; block headings
  are also row-owned.
- The shortcut help line exists beneath `Tick:` and loops horizontally on one
  line using the shared animation machinery.
- Animation state persists across published frames for the marquee row.
- Full monitor suite green (`uv run pytest tests/test_agent_monitor_auto_prime.py -q`
  plus any new focused monitor tests), and lint clean (`uv run ruff check src/ tests/`).

## Impl.Log

- 2026-07-04: `Impl.Req` created from direct user request after design alignment.
  Chosen direction: clean-cut row-model unification, not a compatibility bridge.
- 2026-07-04: Slices 1-3 completed in one pass. The monitor now renders its top
  area from `MonitorFrame.top_rows`, block headings from `heading_rows`, and the
  shortcut strip from a new `MonitorMarqueeRow`. The renderer no longer hardcodes
  the title/tick/status display path.
- Decision in open space: retained block `title` as metadata for workflow identity
  and existing tests/consumers, while moving the printed heading itself to
  `heading_rows`. This preserves non-render metadata without keeping the old
  renderer special case.
- Verification completed: `uv run pytest tests/test_agent_monitor_auto_prime.py
  tests/test_agent_account_rotation_monitor.py tests/test_agent_non_aligned_homes_monitor.py -q`
  -> `43 passed`; `uv run ruff check src/agentos/agent/monitor
  tests/test_agent_monitor_auto_prime.py tests/test_agent_account_rotation_monitor.py
  tests/test_agent_non_aligned_homes_monitor.py` -> clean.
- 2026-07-04 follow-up: moved the `m` materialize action out of display-only
  handling and into `AccountRotationWorkflow`. `MONITOR_MATERIALIZE_ALARM` now
  reaches the workflow thread, where the rotation workflow materializes and then
  rewrites its rotation / non-aligned homes blocks. Limits tracking still ignores
  this alarm for live fetch purposes; `Enter` remains the usage/account-status
  refresh shortcut. Verification updated: focused monitor suite now `45 passed`,
  ruff clean.
