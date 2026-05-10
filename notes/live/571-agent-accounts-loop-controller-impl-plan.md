# Agent Accounts Loop Controller - impl-plan

## Plan State

This plan is ready for implementation and targets the remaining controller-boundary weakness after the first loop redesign.

## User Intent

Finish the loop redesign by making the controller own the loop behavior, not just refresh worker lifecycle.

The concern being addressed is:

- `AccountStatsLoopController` currently exists, but it is still thin.
- Most loop policy still lives in `src/agentos/agent/account_commands.py`.
- The command file should become terminal I/O wiring, while `account_loop.py` should decide what the loop does next.

## Design Target

The final shape should be:

```text
account_commands.py
  terminal input/output adapter
  renderer wiring
  command flag wiring

account_loop.py
  state machine
  scheduling policy
  manual refresh policy
  refresh worker lifecycle
  stale event filtering
  immutable snapshots for rendering

accounts.py
  account data collection
  unchanged except for future cancellation hooks if needed
```

## Non-Goals

- Do not redesign account data collection.
- Do not change account stats JSON or usage output schemas.
- Do not add compatibility aliases.
- Do not reintroduce interval creep or legacy progressive/countdown helpers.
- Do not expand Rich styling beyond what is needed to render controller snapshots.
- Do not solve true provider cancellation in this plan unless a small hook is needed to preserve the controller boundary.

## Implementation Slices

### Slice 1. Introduce Explicit Controller State

Add explicit loop state types in `src/agentos/agent/account_loop.py`.

Suggested model:

```text
idle
refreshing
refresh_queued
stopping
```

Add a controller-owned immutable snapshot dataclass. It should contain only renderable state, not terminal or Rich objects.

Suggested fields:

- `state`
- `refresh_id`
- `started_at_monotonic`
- `finished_at_monotonic`
- `next_refresh_at_monotonic`
- `refresh_queued`
- `body`
- `error`
- `status_text`

Observable check:

- Unit tests can construct a controller and assert snapshot transitions without importing Rich or invoking CLI command code.

### Slice 2. Move Scheduling Policy Into The Controller

Move fixed-delay scheduling out of `account_commands.py`.

The controller should own:

- when the first refresh starts
- when the next refresh deadline is set
- what `tick(now)` does when idle and the deadline has passed
- how the 60 second fixed-delay policy is applied after refresh completion
- how errors affect the next refresh deadline

Observable check:

- A controller test proves refresh completion at time `T` creates a next deadline of `T + interval`.
- Repeated unattended refreshes keep the configured interval.

### Slice 3. Move Manual Refresh Policy Into The Controller

Move Enter behavior into a controller method, for example:

```python
controller.request_refresh(now)
```

Expected policy:

- If idle, start a refresh immediately.
- If refreshing, queue exactly one follow-up refresh.
- Repeated Enter presses during the same refresh keep one queued follow-up, not an unbounded queue.

Observable check:

- A test proves Enter while idle emits or performs a refresh start.
- A test proves Enter while refreshing sets queued state.
- A test proves done-with-queued starts the next refresh immediately.

### Slice 4. Move Worker Event Handling Into The Controller

Move refresh event routing and stale event filtering into `account_loop.py`.

The command should no longer contain logic like:

```python
if event.refresh_id != worker.refresh_id:
    continue
```

The controller should consume:

- started events
- payload events
- error events
- done events

It should decide:

- whether an event is stale
- whether body/error state changes
- whether the refresh is finished
- whether a queued refresh starts now
- whether the loop returns to idle with a next deadline

Observable check:

- A stale event from an old refresh cannot change snapshot body, error, queued state, or active refresh state.

### Slice 5. Convert Controller Decisions Into Effects

Keep terminal and Rich details outside the controller by returning explicit effects or exposing narrow methods.

Recommended effect shape:

```text
StartRefresh
StopRefresh
RenderSnapshot
```

The controller may still own the worker factory, but `account_commands.py` should not own loop policy.

Acceptable simpler shape:

- controller owns worker start/stop internally
- command only calls `controller.tick`, `controller.request_refresh`, `controller.drain_worker_events`, and `controller.shutdown`
- command paints whenever controller reports the snapshot changed

Decision point:

- Prefer the simpler shape if it keeps tests clean and avoids a speculative effect framework.
- Use explicit effects only if direct ownership makes worker creation hard to fake in tests.

Observable check:

- TTY loop code becomes small enough to review as I/O wiring.

### Slice 6. Shrink The TTY Command Loop

Refactor `_loop_chat_accounts_stats_tty` in `src/agentos/agent/account_commands.py` so it only handles:

- creating config/controller/renderer
- polling Enter/Ctrl-C
- passing input into the controller
- draining controller/worker events through the controller API
- painting controller snapshots
- stopping renderer on exit

It should not directly mutate loop frame state or decide refresh transitions.

Observable check:

- There is no command-level special case for queued refresh, stale refresh IDs, or next refresh deadline calculation.

### Slice 7. Rebalance Tests

Move behavioral tests from command-level TTY tests into controller tests.

Controller tests should cover:

- fixed-delay scheduling
- immediate manual refresh while idle
- queued manual refresh while refreshing
- repeated Enter collapse into one queued refresh
- stale event ignored
- payload event updates snapshot
- error event updates snapshot and still exits refresh state
- done event schedules next refresh
- done event with queued refresh starts next refresh immediately
- shutdown requests worker shutdown

CLI tests should become narrower:

- Enter is forwarded to controller.
- Renderer receives snapshots.
- Ctrl-C calls controller shutdown and stops renderer.
- Non-TTY loop follows the same scheduling policy or has an explicitly tested smaller path.

Observable check:

- `uv run pytest -q tests/test_agent_accounts_commands.py`
- `uv run pytest -q`

## Implementation Order

1. Add controller state and snapshot types in `account_loop.py`.
2. Add controller tests for state transitions before changing the command loop.
3. Move fixed-delay scheduling into the controller.
4. Move manual refresh queueing into the controller.
5. Move stale event filtering and refresh completion handling into the controller.
6. Simplify `_loop_chat_accounts_stats_tty`.
7. Rebalance command tests toward wiring-only coverage.
8. Run focused account command tests.
9. Run full Python test suite.
10. Update `569-agent-accounts-stats-loop-redesign-impl-req.md` end log only if implementation materially changes the completed redesign record.

## Acceptance Signals

- `account_commands.py` no longer owns loop state transitions.
- `AccountStatsLoopController` owns scheduling, manual refresh behavior, stale event handling, and refresh lifecycle transitions.
- Renderer receives immutable snapshots only.
- Enter behavior remains deterministic and truthful.
- Ctrl-C still performs explicit bounded shutdown.
- No legacy interval creep, progressive TTY helper, or countdown helper returns.
- Focused and full test suites pass.

## Main Risk

The main risk is over-abstracting the controller with a large effect framework. The pragmatic target is a testable state machine with narrow command wiring, not a generic loop engine.

If direct worker ownership inside the controller remains easy to fake in tests, keep it direct.

## Related Notes

- `notes/live/569-agent-accounts-stats-loop-redesign-impl-req.md`

## End Log

- 2026-05-10: Created as a follow-up implementation plan for moving the account stats loop state machine fully into `account_loop.py`.
- 2026-05-10: Implemented. Added controller-owned loop state/snapshots, moved fixed-delay scheduling, Enter queueing, stale event filtering, payload/error/done transitions, and shutdown state into `src/agentos/agent/account_loop.py`; simplified TTY command handling in `src/agentos/agent/account_commands.py`; rebalanced tests toward controller behavior; verified with focused account tests and the full Python test suite.
