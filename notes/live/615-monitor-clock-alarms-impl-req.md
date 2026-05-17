# Monitor Clock Alarms - impl-req

## Impl.Abstract

- **scope:** replace monitor workflow triggering with a single `MonitorLoop`-owned clock that maintains named alarms. All workflow activation must be synchronized by the monitor main loop through this clock.
- **status:** implemented.
- **source:** follow-up from the monitor manual-trigger implementation after adding separate render/workflow loops and a visible workflow-fetching status line.
- **goal:** make automatic ticking public and inspectable, so render, IO, workflow scheduling, and future services share one global monitor tick. Workflows should be activated only when clock-owned alarms fire, and the monitor should expose countdown feedback such as `limits-tracking | next in N ticks`.
- **strong constraint:** delete the old trigger systems instead of layering alarms on top of them. No legacy trigger-slot path, no workflow-local activation clocks, and no hidden periodic timers should remain.

## Impl.Index

### Current.State

- `src/agentos/agent/monitor/loop.py` currently owns:
  - render/main loop tick increments
  - background workflow thread
  - `request_workflow_cycle(reason=..., force_refresh=...)`
  - `_pending_workflow_trigger`
  - `MonitorWorkflowTrigger`
  - `_workflow_active_count`
- `src/agentos/agent/monitor/workflows.py` currently lets `LimitsTrackingWorkflow` decide refresh timing with `time.monotonic()` and `refresh_interval_sec`.
- `src/agentos/agent/commands.py` currently lets the IO thread call `loop.request_workflow_cycle(reason="manual", force_refresh=True)` directly.
- The current model works, but it is the wrong abstraction for the next phase:
  - triggers are not modeled under a public clock
  - countdowns are not inspectable from a shared clock
  - workflow activation still depends on workflow-local timing
  - manual trigger and periodic trigger concepts are encoded as ad hoc trigger objects

### Accepted.Clock.Model

- Add a `MonitorClock` owned by `MonitorLoop`.
- The clock owns:
  - global `tick`
  - named alarms
  - alarm stepping
  - fired-alarm snapshots
- The monitor main loop is the only system that advances the clock.
- Other loops and services may set alarms, but they do not run workflows directly.
- Clock mutation must be synchronized with a small lock boundary:
  - lock while setting/resetting an alarm
  - lock while stepping alarms
  - lock while producing snapshots
  - do not hold the lock while rendering
  - do not hold the lock while running workflows

### Alarm.Model

- Each alarm has a stable issuer name. This gives each subsystem one isolated trigger slot and avoids semantic races between unrelated trigger sources.
- Initial alarm issuers:
  - `startup`
  - `io.enter`
  - `limits-tracking.periodic`
- Alarm behavior:
  - one-shot alarms fire once, then clear or disarm
  - periodic alarms fire, then reinitialize their countdown
- Alarm state must be inspectable for rendering:
  - current remaining ticks
  - period ticks for periodic alarms
  - whether it fired on the current tick
  - whether it is armed
- Default trigger behavior remains set/reset, not additive queueing.

### Main.Loop.Ownership

- The monitor main loop must be the only place that converts fired alarms into workflow execution.
- Main loop tick order should preserve this shape:
  - advance global clock tick
  - step alarms
  - take a fired-alarm snapshot
  - if any alarm fired, request exactly one workflow cycle with that snapshot
  - publish ready workflow frame if available
  - prepare/render visible frame with clock snapshot feedback
  - step row animations
- IO loop behavior changes:
  - Enter sets or resets the `io.enter` alarm
  - IO must not call workflow execution APIs directly
  - IO must not mutate `MonitorState` or `MonitorFrame`

### Workflow.Trigger.Snapshot

- Replace the old `MonitorWorkflowTrigger(reason, force_refresh)` model with a clock-derived snapshot.
- Workflow protocol should receive a trigger snapshot that tells it:
  - monitor tick when the snapshot was produced
  - which alarms fired
  - useful alarm metadata needed for workflow decisions
- Workflows should not receive the mutable clock.
- Workflows can inspect fired alarm names to decide what work to do.
- Manual Enter remains a force-refresh signal, but it is represented by the fired `io.enter` alarm, not a `force_refresh` flag.

### Limits.Tracking.Scheduling

- `LimitsTrackingWorkflow` should no longer use `time.monotonic()` to decide activation timing.
- The monitor clock should own the `limits-tracking.periodic` alarm.
- `refresh_interval_sec` may remain as user configuration for now, but implementation must convert it into monitor ticks using the monitor loop cadence.
- `limits-tracking` should run account-status refresh when:
  - `startup` fired
  - `io.enter` fired
  - `limits-tracking.periodic` fired
- `limits-tracking` should not fetch provider usage when no relevant alarm fired.
- The visible workflow title or block metadata should expose a countdown, for example:
  - `limits-tracking | next in 42 ticks`
  - while active, the existing workflow-fetching status line can still show that work is running.

### Delete.Old.Systems

The implementation must remove the old trigger mechanics, not keep compatibility paths:

- Delete `_pending_workflow_trigger`.
- Delete `MonitorWorkflowTrigger(reason, force_refresh)` or replace it fully with the new clock snapshot type.
- Delete `request_workflow_cycle(reason=..., force_refresh=...)` as the public trigger API.
- Delete direct IO-to-workflow triggering.
- Delete workflow-local `time.monotonic()` refresh throttling from `LimitsTrackingWorkflow`.
- Delete tests that preserve old trigger-slot behavior; rewrite them against clock alarms.
- Do not leave aliases, fallback helpers, compatibility wrappers, or stale docs for the old trigger model.

### Rendering.Feedback

- The clock snapshot should be available to visible-frame preparation.
- The monitor should render countdown feedback for `limits-tracking` without the workflow owning an internal clock.
- The existing active workflow status line should remain conditional:
  - show while workflow active count is non-zero
  - do not show when the active count is zero

## Execution.Plan

### Slice 1 - Introduce MonitorClock And Alarm Model

Status: completed.

- Add monitor clock/alarm model types in the monitor package.
- Support one-shot and periodic alarms.
- Add synchronized operations for setting/resetting alarms, stepping the clock, and producing immutable snapshots.
- Check:
  - unit tests cover one-shot firing and clearing
  - unit tests cover periodic firing and rearming
  - alarm snapshots expose remaining ticks for rendering

### Slice 2 - Make MonitorLoop Use Clock Tick

Status: completed.

- Move public tick ownership from `MonitorState.tick` mutation to `MonitorClock.tick`, with `MonitorState.tick` updated from the clock for compatibility with current payloads.
- Register startup and limits-tracking periodic alarms during monitor loop setup.
- Ensure the main loop is the only place that steps the clock and checks fired alarms.
- Check:
  - startup still causes the first workflow cycle
  - draw/render ticks continue when no alarm fires
  - visible frame tick matches clock tick

### Slice 3 - Replace Trigger Slot With Alarm Snapshot Workflow Execution

Status: completed.

- Replace `_pending_workflow_trigger` with one pending workflow snapshot produced by the main loop from fired alarms.
- Update workflow protocol to receive the new clock-derived trigger snapshot.
- Ensure repeated `io.enter` alarm sets coalesce through the alarm issuer slot, not an additive queue.
- Delete old `MonitorWorkflowTrigger(reason, force_refresh)` and old `request_workflow_cycle(...)` API.
- Check:
  - repeated Enter sets produce at most one pending manual workflow cycle
  - workflow errors remain captured in state/frame
  - frame ownership remains unchanged: workflow mutates only `working_frame`, render loop mutates only `visible_frame`

### Slice 4 - Wire IO Enter Through Clock Alarm

Status: completed.

- Change the monitor input thread so Enter sets/resets `io.enter` on the monitor clock.
- Keep Enter listening enabled only for interactive Rich monitor mode:
  - not `--json`
  - not `--once`
  - stdin is a TTY
- Check:
  - IO thread does not call workflow execution directly
  - Ctrl-C shutdown still returns `130`
  - non-interactive monitor modes do not read stdin

### Slice 5 - Move Limits Tracking To Clock-Owned Periodic Alarm

Status: completed.

- Convert `refresh_interval_sec` to a monitor-tick period for `limits-tracking.periodic`.
- Remove `time.monotonic()` activation throttling from `LimitsTrackingWorkflow`.
- Make `LimitsTrackingWorkflow` refresh only when relevant alarms fired:
  - `startup`
  - `io.enter`
  - `limits-tracking.periodic`
- Keep provider fetch/display behavior otherwise unchanged.
- Check:
  - periodic alarm triggers refresh at the configured period
  - manual Enter refreshes immediately through `io.enter`
  - no provider fetch happens on ordinary draw ticks where no relevant alarm fired

### Slice 6 - Render Countdown Feedback

Status: completed.

- Expose clock snapshot data to visible-frame preparation and/or frame block metadata.
- Add countdown feedback next to the `limits-tracking` block title or equivalent monitor row.
- Target display:
  - `limits-tracking | next in N ticks`
- Keep the active workflow status line conditional on active workflow count.
- Check:
  - countdown decreases on each monitor tick
  - countdown resets after the periodic alarm fires
  - fetching status line appears only while workflow active count is non-zero

### Slice 7 - Remove Legacy Tests And Add Clock Tests

Status: completed.

- Rewrite tests that assert old `request_workflow_cycle(...)` behavior.
- Add focused tests for:
  - one-shot alarms
  - periodic alarms
  - IO Enter alarm coalescing
  - workflow execution from fired alarm snapshot
  - limits-tracking countdown display
  - no provider fetch on non-fired draw ticks
- Check:
  - no tests import or assert old `MonitorWorkflowTrigger(reason, force_refresh)`
  - no tests call old `request_workflow_cycle(...)`

### Slice 8 - Validation

Status: completed.

- Run focused tests:

```sh
uv run pytest tests/test_agent_account_registry_commands.py -q
```

- Run lint on touched files:

```sh
uv run ruff check src/agentos/agent/monitor src/agentos/agent/commands.py tests/test_agent_account_registry_commands.py
```

- Refresh installed CLI:

```sh
uv tool install --reinstall --editable .
```

- Manual smoke:

```sh
agentos agent accounts monitor --once
agentos agent accounts monitor --once --json
agentos agent accounts monitor
```

- Acceptance signals:
  - monitor starts with startup alarm-driven data fetch
  - `limits-tracking` shows a countdown driven by the monitor clock
  - countdown approaches zero on draw ticks
  - periodic refresh happens only when the periodic alarm fires
  - Enter sets the `io.enter` alarm and forces one refresh
  - repeated Enter presses do not build an additive backlog
  - old trigger slot symbols and workflow-local scheduling code are gone

## Impl.Log

- Created to capture the clock-owned alarm design: all triggering belongs under `MonitorClock`, all alarm stepping is synchronized by the monitor main loop, and the old pending-trigger / workflow-local timing systems must be deleted rather than retained as compatibility paths.
- Implemented the clock alarm model in `src/agentos/agent/monitor/clock.py`, wired `MonitorLoop` to advance the clock and hand fired-alarm snapshots to workflows, and moved Enter handling to set the `io.enter` alarm instead of calling a workflow trigger API.
- Replaced `LimitsTrackingWorkflow` local `time.monotonic()` throttling with clock-owned alarm decisions. Startup, Enter, and `limits-tracking.periodic` fetch provider data; unrelated alarms can run the workflow frame path without fetching.
- Added countdown feedback by annotating the visible `limits-tracking` block title from the current clock snapshot, while keeping the active workflow-fetching status line conditional on the workflow active count.
- Removed old trigger symbols and tests: no `MonitorWorkflowTrigger`, no `request_workflow_cycle(...)`, no `force_refresh` flag, and no workflow-local refresh timestamp remain in the monitor implementation.
- Validation passed: `uv run pytest tests/test_agent_account_registry_commands.py -q`, `uv run ruff check src/agentos/agent/monitor src/agentos/agent/commands.py tests/test_agent_account_registry_commands.py`, `uv tool install --reinstall --editable .`, and `agentos agent accounts monitor --once`.
