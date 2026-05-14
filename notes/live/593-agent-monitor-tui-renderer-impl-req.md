# Agent Monitor TUI Renderer Impl Req

## Impl.Abstract

Status: implemented.

Source design: `notes/live/588-agent-account-registry-consolidated-design-session.md`.

Implement phase 2 of `agentos agent accounts monitor`: the monitor TUI mechanics. The monitor must remain loop-only. `--once` and `--max-ticks` only stop the same loop early. `--json` is raw diagnostic/test serialization of the loop data, not a renderer and not monitor UI.

This request intentionally does not implement real provider usage fetching, usage progress bars, account history, system-home setup, or rich usage-specific layout. It implements the corrected monitor mechanics:

- one `MonitorLoop` execution path.
- one persistent in-memory `MonitorState`.
- one persistent in-memory `MonitorFrame`.
- workflows mutate `MonitorState` and `MonitorFrame` in place.
- workflows own nice operational error placeholders.
- loop-level exception handling is last-resort only and must keep the monitor alive.
- normal monitor UI is rendered through a simple Rich renderer that consumes the same persistent `MonitorFrame`.

## Impl.Index

### Monitor.Loop.Only

`MonitorLoop` is the only monitor execution engine.

`--once` means `max_ticks = 1`. `--max-ticks N` means the same loop exits after `N` ticks. Unbounded monitor mode uses the same loop with no maximum tick count.

There must not be separate bounded and unbounded monitor engines in the command layer.

#### evidence

- Current design artifact: `notes/live/588-agent-account-registry-consolidated-design-session.md`.
- Pre-implementation code had command-level branching between `run_monitor` and `iter_monitor` in `src/agentos/agent/commands.py`.

#### meta

- status: implemented.

### Monitor.Frame.Persistent

`MonitorFrame` is persistent in memory. It is the shared display surface. The loop creates it once and keeps passing the same object to workflows and renderer across ticks.

The implementation must remove stale per-tick frame recreation. A workflow that wants to replace, clear, or update a display region should do that explicitly by mutating `MonitorFrame`.

#### evidence

- Pre-implementation code created `MonitorFrame(tick=tick)` inside `MonitorLoop.iter_frames()` in `src/agentos/agent/monitor.py`.
- Corrected design says `MonitorFrame` is the persistent canonical renderer model.

#### meta

- status: implemented.

### Monitor.Workflow.Error.Ownership

Workflows own operational error presentation.

A workflow should catch expected provider, refresh, parsing, account, and data errors; update `MonitorFrame` with a useful placeholder; optionally update `MonitorState`; and return.

`MonitorLoop` still keeps a last-resort boundary around workflow execution so an unexpected workflow crash does not kill the monitor. That boundary should record a generic unexpected-error entry and continue. It is not responsible for provider-specific nice error UI.

#### evidence

- Pre-implementation first-slice implementation caught workflow exceptions at loop level.
- Corrected design narrows that loop catch to last-resort safety.

#### meta

- status: implemented.

### Monitor.Renderer

The phase 2 renderer model is intentionally simple:

```text
RichMonitorRenderer
    consumes MonitorFrame and MonitorState
    renders a simple Rich terminal surface
```

Do not build a test renderer abstraction. Tests should use `--json` and direct loop data assertions.

Do not build progress bars or parse free-form text into bars in this phase. Usage-specific frame primitives and richer layout are later work.

#### evidence

- Old deprecated stats loop used Rich Live, Console, and Text.
- Current phase 2 target is mechanics, not real usage visualization.

#### meta

- status: implemented.

### Monitor.Json.Diagnostic

`--json` is not a renderer. It serializes raw monitor data for tests and debugging.

The diagnostic output must come from the same `MonitorLoop` state/frame mechanics as normal monitor UI. Tests should prefer bounded runs such as `--once --json` or `--max-ticks 3 --json`.

#### meta

- status: implemented.

## Execution.Plan

### Vertical.Slice 1 - Single Loop Core

Status: completed.

Change `src/agentos/agent/monitor.py` so `MonitorLoop` owns one `MonitorState` and one `MonitorFrame`.

Expected shape:

```text
MonitorLoop
    state = MonitorState()
    frame = MonitorFrame()

    while running:
        state.tick += 1
        frame.tick = state.tick
        for workflow in workflows:
            workflow.run(state, frame)
        render or yield raw data
        sleep to cadence
```

The exact API can differ, but the implementation must preserve these semantics:

- `MonitorFrame` is created once per loop instance.
- `MonitorState` is created once per loop instance.
- workflows receive the same frame object across ticks.
- workflow ordering remains config order.
- loop cadence remains approximately one tick per second by default.
- max tick handling is loop configuration, not command-level engine selection.

Validation:

- Add or update tests proving `MonitorFrame` object identity persists across multiple ticks.
- Add or update tests proving `MonitorState` persists across multiple ticks.
- Add or update tests proving `--once` and `--max-ticks` use the same loop path.

### Vertical.Slice 2 - Workflow Error Ownership Boundary

Status: completed.

Keep a last-resort loop boundary, but do not treat it as the normal workflow error UX.

Implementation requirements:

- unexpected workflow exceptions must not stop `MonitorLoop`.
- the loop records a generic unexpected-error entry in state/frame and continues.
- `LimitsTrackingWorkflow` placeholder path should be structured so future provider errors can be caught inside the workflow and written as a normal frame placeholder.
- tests should include a crashing workflow and a later successful workflow in the same tick.

Validation:

- A crashing workflow does not prevent a later workflow from mutating the persistent frame.
- The loop continues across ticks after an unexpected workflow exception.
- Existing monitor tests still pass.

### Vertical.Slice 3 - Simple Rich Monitor Renderer

Status: completed.

Add a simple Rich renderer for normal monitor UI.

Implementation requirements:

- Use Rich already present in project dependencies.
- Use `rich.live.Live` for continuous monitor mode.
- Render directly from `MonitorFrame` and `MonitorState`.
- Keep the UI plain:
  - monitor title.
  - tick/status metadata.
  - errors/warnings if present.
  - workflow blocks.
- No progress bars.
- No typed usage tables.
- No parsing rendered text back into UI semantics.

Validation:

- Running `agentos agent accounts monitor` refreshes one terminal surface instead of appending repeated text blocks.
- Ctrl-C stops Rich Live cleanly.
- `agentos agent accounts monitor --once` exits after one rendered tick.
- `agentos agent accounts monitor --max-ticks 2` exits after two rendered ticks.

### Vertical.Slice 4 - JSON Diagnostic Mode

Status: completed.

Keep `--json` as raw data output for tests and debugging.

Implementation requirements:

- `--json` must not use `RichMonitorRenderer`.
- `--json` must not be modeled as a renderer.
- `--json` output must reflect the same loop-owned `MonitorState` and persistent `MonitorFrame`.
- bounded JSON commands should remain deterministic for tests.

Validation:

- `agentos agent accounts monitor --once --json` prints raw state/frame data.
- `agentos agent accounts monitor --max-ticks 3 --interval-sec 0 --json` shows final tick count and workflow run counts.
- tests do not assert Rich terminal behavior when JSON data is enough.

### Vertical.Slice 5 - CLI Cleanup And No Legacy Paths

Status: completed.

Clean up command wiring so old first-slice helper paths do not preserve stale concepts.

Implementation requirements:

- remove or rewrite helper functions that imply separate bounded/unbounded engines.
- remove or rewrite tests that assert per-tick frame recreation.
- keep startup config errors as normal CLI errors before loop creation.
- keep workflow errors from killing the running loop.
- refresh the installed `agentos` executable after CLI changes.

Validation:

- `uv run ruff check src/agentos/agent/monitor.py src/agentos/agent/commands.py tests/test_agent_account_registry_commands.py`
- `uv run pytest tests/test_agent_account_registry_commands.py`
- `uv run pytest`
- `agentos agent accounts monitor --once`
- `agentos agent accounts monitor --once --json`
- `agentos agent accounts monitor --max-ticks 2`

## Impl.Log

- 2026-05-14: Created Impl.Req from corrected phase 2 monitor TUI design. The request explicitly removes stale per-tick `MonitorFrame` assumptions, keeps the monitor loop-only, keeps `--json` diagnostic-only, and scopes Rich rendering to simple mechanics.
- 2026-05-14: Implemented phase 2. `MonitorLoop` now owns one persistent `MonitorState` and one persistent `MonitorFrame`, bounded and unbounded modes use the same loop path, workflows mutate the shared frame in place, unexpected workflow exceptions are recorded without stopping later workflows, normal UI uses a simple Rich Live renderer, and `--json` remains raw diagnostic serialization. Validated with ruff, focused monitor tests, full pytest, installed CLI refresh, bounded monitor CLI runs, JSON CLI output, and Ctrl-C clean shutdown.
