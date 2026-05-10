# Agent Accounts Stats Loop Redesign - impl-req

## Impl-Req State

This request has been implemented for the loop runtime redesign; the full Python test suite passes.

## User Intent

Redesign the loop behavior behind:

```sh
agentos agent accounts stats --output=usage --refresh-usage --loop
```

The user specifically does not want the account data collection layer redesigned in this request. The focus is the interactive loop runtime: scheduling, refresh worker lifecycle, input handling, cancellation, and truthful rendering state.

## Why This Exists

The current loop is unreliable in practice. The user reports needing to reload it often.

Code inspection shows the loop mixes scheduling, Rich rendering, input polling, worker lifetime, and refresh state inside `agentos.agent.account_commands`. That makes manual refresh, Ctrl-C, slow provider calls, and redraw behavior interact in fragile ways.

## Current Situation

The relevant command is registered in `src/agentos/agent/commands.py` and handled by `src/agentos/agent/account_commands.py`.

Current loop issues observed from code review:

- The TTY loop starts an asynchronous refresh worker thread, but Ctrl-C stops only the renderer path. The worker is daemonized and not explicitly cancelled or joined.
- Pressing Enter while a refresh is already running only resets the displayed interval. It does not actually force an immediate refresh, cancel/restart the current refresh, or queue a refresh after the current one finishes.
- The loop schedules the next refresh after the previous refresh completes, so slow provider work stretches the effective cadence.
- The default interval silently increases after unattended refreshes, up to ten minutes, even though the CLI help says the loop refreshes every 60 seconds.
- Renderer state and loop control state are coupled, which makes the behavior hard to test without Rich rendering details.
- Slow live usage paths, especially Claude Code live usage, expose the lifecycle problem because refreshes can remain in flight for a long time.

The account data path itself is outside this request:

- `chat_account_stats`
- `iter_chat_account_stats_refresh_payloads`
- provider account collectors in `src/agentos/agent/accounts.py`

## Requested Change

Replace the current ad hoc loop with a small controller-oriented loop runtime.

The target design:

- A loop controller owns state transitions, scheduling, input events, and worker lifecycle.
- A refresh worker owns exactly one account stats refresh attempt and emits structured events.
- A renderer receives immutable view-state snapshots and only displays them.
- Manual refresh behavior is deterministic and truthful.
- Ctrl-C has a deterministic shutdown path that does not intentionally abandon refresh work.
- Existing account stats collection and output formatting behavior remain stable unless a loop contract requires a narrow adapter.

## Constraints And Invariants

- Do not redesign or rewrite provider account data collection in this request.
- Keep the user-facing command path and flags stable unless a small additive flag is needed.
- Preserve `--output=usage`, `--refresh-usage`, and `--loop` behavior at the command surface.
- Do not add compatibility aliases.
- Do not revert unrelated dirty worktree changes.
- Keep non-TTY loop behavior simple and compatible, but prefer sharing the same controller semantics where practical.
- Avoid daemon refresh work outliving the loop as a normal control path.
- Rendering must accurately describe what Enter and Ctrl-C do in the current state.

## Out Of Scope

- Changing provider usage parsing.
- Changing Claude, Codex, or Copilot account collector behavior except for cancellation hooks if the loop needs them.
- Changing account stats JSON or usage output schema.
- Changing account config fields.
- Redesigning history persistence.
- Reworking Rich visual styling beyond text required for accurate loop state.

## Acceptance Signals

- Enter while idle starts a refresh immediately.
- Enter while refreshing either queues a next refresh or cancels/restarts the current refresh; the implemented behavior is explicit in code and UI text.
- Ctrl-C stops the renderer and loop promptly and performs explicit worker shutdown.
- No refresh worker thread is intentionally abandoned as the normal Ctrl-C/reload path.
- The UI distinguishes at least these states clearly:
  - refreshing
  - next refresh countdown
  - refresh queued/requested
  - refresh error with last usable body preserved when available
- The loop cadence is predictable. If it is fixed-delay, the UI communicates that the next refresh is counted from completion. If it is fixed-rate, stale worker events cannot corrupt current state.
- The default loop does not silently back off from 60 seconds unless this behavior is made explicit and tested.
- Tests cover controller behavior without depending on Rich internals.
- Existing focused account command tests still pass after updates.

## Implementation Shape

Implement in vertical slices.

### Slice 1. Extract Loop State And Controller Skeleton

- Add a focused loop module, likely `src/agentos/agent/account_loop.py`, or an equivalent internal module if the codebase shape suggests a better name.
- Define small dataclasses for loop config, loop state, and view state.
- Move timing decisions out of Rich renderer code.
- Keep the first slice wired to existing refresh rendering/output functions so behavior can be compared quickly.

Observable check:

- Unit tests can instantiate the controller with fake time, fake input, and fake refresh worker callbacks.
- A single idle-to-refresh-to-idle path produces the expected view state transitions.

### Slice 2. Worker Event Contract

- Replace the current worker event queue shape with a refresh-id based event contract.
- Suggested events:
  - refresh started
  - refresh payload
  - refresh error
  - refresh finished
- Include `refresh_id` on events so late events from an old refresh can be ignored.
- Keep the worker calling `iter_chat_account_stats_refresh_payloads`; do not change that collector.

Observable check:

- A stale event from an old refresh does not overwrite the current body/error/progress state.

### Slice 3. Manual Refresh Semantics

- Make Enter deterministic:
  - If idle, start refresh now.
  - If refreshing, set a queued refresh flag or request cancellation/restart.
- Prefer queue-after-current as the first implementation if true cancellation would require invasive provider changes.
- Update status text so it does not promise immediate refresh while a refresh is already in flight unless immediate cancellation/restart is implemented.

Observable check:

- Tests prove Enter during refresh causes a second refresh after the current one finishes, or prove it cancels/restarts if that policy is chosen.

### Slice 4. Shutdown Lifecycle

- Remove normal reliance on daemon refresh abandonment.
- On Ctrl-C:
  - stop accepting input
  - stop or freeze renderer cleanly
  - request worker shutdown
  - join for a bounded time
  - let provider subprocess termination hooks run where available
- If cancellation is best-effort, document it in code and tests.

Observable check:

- A test with a blocked fake worker shows the loop returns promptly and calls the worker shutdown path.

### Slice 5. Cadence Policy

- Make cadence explicit.
- Recommended default: fixed-delay 60 seconds from refresh completion, because refreshes may be expensive and remote.
- Remove silent interval creep from the default path, or gate it behind an explicit backoff config/flag.
- Show refresh duration and next refresh countdown in the TTY view state.

Observable check:

- Tests prove unattended refreshes keep the configured interval unless explicit backoff is enabled.

### Slice 6. Renderer Adapter

- Keep `Rich` rendering as a renderer implementation, not the loop owner.
- Feed it a view state and preserve the existing usage text formatting, including inline usage/reset bar behavior.
- Update prompt/status text to match the new manual refresh and shutdown semantics.

Observable check:

- Existing rich text tests continue to cover inline usage/reset bar rendering.
- New tests cover only status text generated from view state.

## Relevant Files Or Surfaces

- `src/agentos/agent/commands.py`
- `src/agentos/agent/account_commands.py`
- `src/agentos/agent/accounts.py`
- `tests/test_agent_accounts_commands.py`
- Command surface: `agentos agent accounts stats --output=usage --refresh-usage --loop`

## Open Questions

- Should Enter during active refresh queue a follow-up refresh or cancel/restart immediately?
- Should the default cadence be fixed-delay from refresh completion or fixed-rate by wall clock?
- Should interval backoff remain as an explicit option, or be removed entirely?
- Should worker cancellation be introduced as a generic loop concept first, or should provider-specific subprocess cancellation hooks be added in the same pass?
- Should non-TTY loop use the same controller or remain a smaller synchronous path with matching scheduling semantics?

## Related Impl-Reqs

- None yet.

## End Log

- 2026-05-10: Created from code review and redesign discussion for unreliable `agent accounts stats --output=usage --refresh-usage --loop` behavior.
- 2026-05-10: Implemented the loop redesign. Added `src/agentos/agent/account_loop.py`, removed the old TTY progressive/countdown helper path and interval backoff behavior, made TTY refreshes use refresh IDs with started/payload/error/done events, queued manual refresh during active refresh, added bounded worker shutdown, updated loop status text, moved renderer calls to immutable view-state snapshots, and replaced legacy tests with fixed-delay, stale-event, queued-refresh, worker-event, and shutdown-oriented coverage. Verified with compileall plus the full Python test suite.
- 2026-05-10: Follow-up controller redesign implemented from `571-agent-accounts-loop-controller-impl-plan.md`. `AccountStatsLoopController` now owns explicit loop state, fixed-delay scheduling, manual refresh queueing, stale refresh event filtering, refresh completion transitions, bounded shutdown state, and immutable render snapshots. `_loop_chat_accounts_stats_tty` is now terminal I/O wiring around the controller API.
