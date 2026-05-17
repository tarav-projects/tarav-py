# Monitor Manual Workflow Trigger - impl-req

## Impl.Abstract

- **scope:** add an interactive manual workflow trigger to `agentos agent accounts monitor` so pressing Enter requests a workflow-loop run immediately, with set-to-one trigger semantics and forced workflow refresh for that manual run.
- **status:** implemented.
- **source:** follow-up from monitor loop design discussion after the monitor gained separate render and workflow loops.
- **goal:** the monitor should keep rendering/animating continuously while workflow execution is independently request-driven. Startup runs one workflow cycle; pressing Enter in the interactive monitor requests exactly one pending forced workflow cycle, even if Enter is pressed repeatedly while a workflow is already running.

## Impl.Index

### Current.Monitor.Loop.Shape

- `src/agentos/agent/monitor/loop.py` owns:
  - `MonitorLoop.run(...)`
  - the main render/tick loop
  - the background workflow thread
  - frame swap through `visible_frame`, `working_frame`, pending workflow triggers, and `working_frame_ready`
- implemented behavior starts one forced startup workflow cycle; later workflow cycles are requested through `MonitorLoop.request_workflow_cycle(...)`.
- current frame ownership model is important:
  - workflow thread owns `working_frame` while executing workflows
  - main thread owns `visible_frame`
  - frames are swapped only after `working_frame_ready`
  - this avoids locks around frame mutation
- current CLI entry point is `_cmd_agent_accounts_monitor(...)` in `src/agentos/agent/commands.py`.
- current renderer path uses `RichMonitorRenderer` for non-JSON mode and direct JSON dumps for `--json`.

### Accepted.Trigger.Semantics

- Manual trigger is Enter in the interactive monitor.
- Enter must request workflow execution as soon as the workflow thread can take it.
- Enter must force workflow refresh for that workflow cycle.
- Repeated Enter presses must not build an unbounded backlog.
- Default trigger behavior should be **set**, not **add**:
  - if no pending workflow trigger exists, set one pending trigger.
  - if a pending workflow trigger already exists, replace/keep one pending trigger.
  - if a workflow is currently running, the active trigger has already been consumed; Enter sets one pending trigger for exactly one follow-up run.
- This is a reset-and-set event, not an incrementing queue.
- Future trigger producers should prefer the same set-to-one behavior unless a specific use case needs additive queueing.

### Loop.Control.State.Boundary

- Add a small loop-control state surface owned by `MonitorLoop`.
- The loop-control state is for inter-loop coordination between:
  - render/main loop
  - workflow loop
  - IO/input loop
- It is not workflow domain state.
- It is not `MonitorFrame`.
- It is not rendered directly.
- IO/input code must not mutate `MonitorState` or `MonitorFrame` directly.
- IO/input code should call a method such as:

```python
loop.request_workflow_cycle(reason="manual", force_refresh=True)
```

- The method owns synchronization and updates the loop-control trigger slot.

### Workflow.Trigger.Model

- Add a small immutable trigger object, for example:

```python
MonitorWorkflowTrigger(
    reason="startup" | "manual" | "scheduled",
    force_refresh=True | False,
)
```

- Workflow protocol should receive this trigger:

```python
workflow.run(state, frame, trigger)
```

- The trigger is consumed before workflow execution starts.
- If the workflow fails, the trigger remains consumed. Failure should be represented in state/frame through the existing workflow error handling, not by automatically retrying the same trigger forever.

### Limits.Tracking.Refresh.Semantics

- `LimitsTrackingWorkflow` currently throttles provider fetches using `refresh_interval_sec`.
- With manual trigger:
  - `trigger.force_refresh=True` should bypass `refresh_interval_sec`.
  - stale/interval-based refresh still works for non-forced triggers.
- Manual Enter is therefore a user-commanded refresh, not just a frame rebuild.

### CLI.Input.Semantics

- Enter listening should be enabled only for the interactive Rich monitor path.
- Do not read stdin for:
  - `--json`
  - `--once`
  - non-TTY execution
- The input loop should be a small daemon thread or equivalent minimal non-blocking mechanism.
- It should block on stdin line input and call `loop.request_workflow_cycle(reason="manual", force_refresh=True)` for each Enter.
- It should not print directly and should not mutate render/workflow data.
- Ctrl-C behavior should remain the existing clean shutdown path returning `130`.

### Out.Of.Scope

- Do not redesign monitor rendering.
- Do not add keyboard commands beyond Enter.
- Do not add a full terminal input framework.
- Do not add additive trigger queues in this slice.
- Do not change account registration, provider homes, or account status fetching beyond respecting `force_refresh` in the limits workflow.
- Do not change JSON output into an interactive mode.

## Execution.Plan

### Slice 1 - Add Workflow Trigger Model And Protocol

Status: completed.

- Add `MonitorWorkflowTrigger` to the monitor model/loop surface.
- Update `MonitorWorkflow` protocol to `run(state, frame, trigger)`.
- Update `LimitsTrackingWorkflow.run(...)` to accept the trigger.
- Check:
  - existing monitor tests still exercise workflow execution.
  - workflow error handling still records errors into state/frame.

### Slice 2 - Replace Auto-Rerun With Set-To-One Trigger Slot

Status: completed.

- Add loop-control synchronization inside `MonitorLoop`.
- Startup should set one pending trigger:
  - `reason="startup"`
  - `force_refresh=True`
- Workflow thread should wait for a pending trigger, consume it before workflow execution, then run workflows with that trigger.
- Publishing a frame should not automatically start the next workflow cycle.
- `request_workflow_cycle(...)` should set one pending trigger, replacing/coalescing any pending trigger rather than incrementing a backlog.
- Check:
  - continuous draw ticks continue while no workflow is pending.
  - initial startup workflow still runs.
  - repeated manual requests while a workflow is running result in one follow-up run.

### Slice 3 - Force Refresh In LimitsTrackingWorkflow

Status: completed.

- Make `LimitsTrackingWorkflow` bypass `refresh_interval_sec` when `trigger.force_refresh` is true.
- Keep existing interval throttling for non-forced triggers.
- Check:
  - forced manual trigger refreshes even when `last_refresh_at_monotonic` is recent.
  - non-forced trigger still respects `refresh_interval_sec`.

### Slice 4 - Wire Enter Input In Interactive CLI

Status: completed.

- In `_cmd_agent_accounts_monitor(...)`, enable Enter listening only for interactive Rich mode:
  - not `--json`
  - not `--once`
  - stdin is a TTY
- Add a minimal input thread that blocks on stdin and calls:

```python
loop.request_workflow_cycle(reason="manual", force_refresh=True)
```

- Ensure shutdown does not hang on the input thread.
- Check:
  - `--json` behavior remains deterministic and non-interactive.
  - `--once` still waits for the first frame and exits.
  - interactive monitor continues rendering between workflow runs.

### Slice 5 - Validation

Status: completed.

- Run focused tests:

```sh
uv run pytest tests/test_agent_account_registry_commands.py -q
```

- Run lint on touched files:

```sh
uv run ruff check src/agentos/agent/monitor src/agentos/agent/commands.py tests/test_agent_account_registry_commands.py
```

- Refresh installed CLI after runtime/CLI changes:

```sh
uv tool install --reinstall --editable .
```

- Manual smoke:

```sh
agentos agent accounts monitor
```

- Acceptance signals:
  - monitor starts and shows initial data.
  - pressing Enter triggers a forced workflow refresh.
  - repeated Enter presses while a refresh is active produce at most one pending follow-up refresh.
  - render animation continues independently of workflow execution.
  - `agentos agent accounts monitor --once --json` still exits with one JSON payload.

## Impl.Log

- Created to capture the accepted manual workflow trigger design: Enter uses set-to-one pending trigger semantics and forces workflow refresh, while IO/render/workflow communication stays inside `MonitorLoop` loop-control state.
- Implemented `MonitorWorkflowTrigger`, updated workflow protocol calls, replaced automatic workflow reruns with a set-to-one pending trigger slot, and kept frame ownership transfer between workflow and render loops.
- Wired startup as a forced workflow trigger and added `MonitorLoop.request_workflow_cycle(...)` for manual and future scheduled trigger producers.
- Updated `LimitsTrackingWorkflow` so forced triggers bypass `refresh_interval_sec`, while non-forced scheduled triggers keep the existing interval throttle.
- Added interactive Rich monitor Enter listening through a daemon stdin thread; `--json`, `--once`, and non-TTY monitor runs remain non-interactive.
- Added tests for explicit republish triggers, coalescing repeated manual requests while a workflow is active, forced refresh bypassing the limits interval, and non-forced triggers respecting the interval.
- Validation passed:
  - `uv run pytest tests/test_agent_account_registry_commands.py -q`
  - `uv run ruff check src/agentos/agent/monitor src/agentos/agent/commands.py tests/test_agent_account_registry_commands.py`
  - `uv tool install --reinstall --editable .`
  - `agentos agent accounts monitor --once`
  - `agentos agent accounts monitor --once --json`
