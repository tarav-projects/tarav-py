# Monitor Adaptive Limits Tracking Alarm - impl-req

## Impl.Abstract

- **scope:** change the `limits-tracking` monitor workflow alarm policy from a fixed periodic interval to an adaptive interval.
- **status:** implemented.
- **source:** follow-up from monitor clock/alarm work and Claude usage-status cost review. Current live Claude statusline refresh uses Haiku but still consumes about 23k cached input tokens per live run, so unattended monitor refresh frequency should back off over time.
- **goal:** if the user does not interact, `limits-tracking` should refresh less often over time. If the user manually triggers the monitor with Enter, the cadence should reset to the baseline 60 seconds.
- **strong constraint:** this is workflow/alarm policy only. Do not put this behavior in the renderer. Do not preserve a second fixed-period scheduling path.

## Impl.Index

### Current.State

- `MonitorLoop` owns a `MonitorClock`.
- `MonitorClock` supports one-shot and periodic alarms.
- `MonitorLoop._configure_initial_alarms()` currently configures `LIMITS_TRACKING_PERIODIC_ALARM` from workflow `refresh_interval_sec`.
- `LimitsTrackingWorkflow.loop(...)` receives `MonitorClockSnapshot` and refreshes targets when any of these alarms fire:
  - `startup`
  - `io.enter`
  - `limits-tracking.periodic`
- Manual Enter is already modeled as an alarm through `MONITOR_ENTER_ALARM`.
- The renderer only displays current frame/block data and clock countdown feedback. It must remain uninvolved in scheduling decisions.

### Accepted.Behavior

- Baseline `limits-tracking` refresh period is 60 seconds unless config already provides another `refresh_interval_sec`.
- On automatic periodic fire:
  - run `limits-tracking`
  - increase the next automatic period by 1 second
- On direct user interruption / Enter fire:
  - run `limits-tracking`
  - reset the next automatic period to baseline
- Startup remains a live workflow activation, but it should not by itself increase the adaptive period.
- The period increase applies only after automatic periodic refreshes, not after manual refreshes.
- If multiple alarms fire in the same clock snapshot and `io.enter` is present, manual reset wins over automatic backoff.

### Alarm.Policy

- Adaptive cadence belongs to the monitor workflow/alarm control path.
- The clock remains the mechanism that fires alarms.
- The main loop remains the synchronizer of clock ticks.
- Workflows should not maintain independent wall clocks.
- The simplest acceptable implementation is to let `MonitorLoop` manage the adaptive period for the `LIMITS_TRACKING_PERIODIC_ALARM`, because `MonitorLoop` already owns clock configuration and receives fired alarm snapshots before workflow execution.

### Period.Units

- User-facing configuration remains seconds.
- `MonitorClock` periods remain ticks.
- Convert seconds to ticks through the monitor interval cadence logic.
- If `interval_sec` is `0`, keep the current convention of treating cadence as `1.0` second for period conversion.
- The adaptive increment is one second, converted through the same seconds-to-ticks path.

### Data.Visibility

- The visible countdown in the `limits-tracking | next in N ticks` title should reflect the adaptive next period because it reads the clock alarm snapshot.
- Optional state data may expose current adaptive period seconds for JSON/debugging, but this is not required for the renderer.
- Do not add in-app explanatory text about adaptive backoff.

### No.Legacy.Allowed

- Delete or replace fixed-period rearming behavior for `limits-tracking`.
- Do not add a parallel scheduler for the old behavior.
- Do not add provider-specific cadence hacks for Claude in this change.
- Do not special-case the renderer.

## Execution.Plan

### Slice 1 - Model Adaptive Period State In MonitorLoop

Status: implemented.

- Add monitor-loop-owned state for `limits-tracking` adaptive baseline/current period seconds.
- Initialize baseline from the merged `LimitsTrackingWorkflow.refresh_interval_sec`.
- Preserve existing period conversion behavior for ticks.
- Check:
  - startup still arms `LIMITS_TRACKING_PERIODIC_ALARM`
  - default baseline remains 60 seconds
  - configured `refresh_interval_sec` remains the baseline when explicitly set

### Slice 2 - Re-arm Periodic Alarm After Fired Snapshots

Status: implemented.

- When `LIMITS_TRACKING_PERIODIC_ALARM` fires without `MONITOR_ENTER_ALARM`, increase current period seconds by 1 and re-arm the periodic alarm using the new period.
- When `MONITOR_ENTER_ALARM` fires, reset current period seconds to baseline and re-arm the periodic alarm at baseline.
- If both periodic and Enter fire in the same snapshot, apply the manual reset.
- Keep startup separate: it should activate workflow execution but should not increment the adaptive period.
- Check:
  - automatic sequence starts `60s -> 61s -> 62s ...`
  - manual Enter resets the next automatic period to baseline
  - the workflow still receives the same fired alarm snapshot semantics

### Slice 3 - Preserve Workflow And Renderer Boundaries

Status: implemented.

- Keep `LimitsTrackingWorkflow.loop(...)` focused on target refresh and frame writing.
- Do not move scheduling decisions into `RichMonitorRenderer` or row rendering.
- Ensure countdown feedback continues to come from clock alarm snapshots.
- Check:
  - no renderer files need changes for scheduling
  - frame/block title shows the updated clock countdown naturally

### Slice 4 - Tests

Status: implemented.

- Add focused monitor-clock/loop tests for adaptive cadence:
  - automatic periodic fire increases next period by one second
  - manual Enter resets period to baseline
  - simultaneous Enter + periodic uses manual reset
  - startup does not increase period
- Update existing period tests that assume a fixed `limits-tracking` period.
- Check:
  - tests use shared alarm constants
  - tests assert clock/alarm behavior, not renderer implementation details

### Slice 5 - Validation

Status: implemented.

- Run focused tests:

```sh
uv run pytest tests/test_agent_account_registry_commands.py -q
```

- Run lint:

```sh
uv run ruff check src/agentos/agent/monitor src/agentos/agent/commands.py tests/test_agent_account_registry_commands.py
```

- Refresh installed CLI if runtime files changed:

```sh
uv tool install --reinstall --editable .
```

- Manual smoke:

```sh
agentos agent accounts monitor --once
agentos agent accounts monitor --max-ticks 3 --interval-sec 1
```

- Acceptance signals:
  - adaptive automatic cadence is `baseline, baseline + 1s, baseline + 2s...`
  - Enter/manual trigger resets cadence to baseline
  - renderer remains scheduling-neutral
  - no fixed-period duplicate path remains for `limits-tracking`

## Impl.Log

- Created to implement adaptive `limits-tracking` alarm cadence. The design keeps scheduling in the monitor clock/alarm control path and leaves rendering unchanged.
- Implemented adaptive alarm state in `MonitorLoop`: baseline/current seconds are derived from the merged `limits-tracking` workflow config, then converted to clock ticks through the existing monitor interval cadence rule.
- Replaced fixed `limits-tracking` re-arming with loop-owned policy: automatic periodic fires increase the next period by one second, Enter resets the period to baseline, and Enter wins when both alarms fire in the same snapshot. Startup remains a workflow activation without increasing the adaptive period.
- Preserved workflow and renderer boundaries. `LimitsTrackingWorkflow.loop(...)` still consumes fired alarm snapshots and writes frame data; renderer code was not changed for scheduling.
- Added focused tests for automatic backoff, manual reset, simultaneous Enter/periodic behavior, and startup non-increment behavior.
- Validation completed:
  - `uv run pytest tests/test_agent_account_registry_commands.py -q` -> 92 passed.
  - `uv run ruff check src/agentos/agent/monitor src/agentos/agent/commands.py tests/test_agent_account_registry_commands.py` -> passed.
  - `uv tool install --reinstall --editable .` -> installed refreshed `agentos`.
  - `agentos agent accounts monitor --once` -> passed.
  - `agentos agent accounts monitor --max-ticks 3 --interval-sec 1` -> passed.
