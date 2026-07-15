# Codex Burst Baseline Rolling-Reset Fix - impl-req

## Impl.Abstract

- **scope:** fix the estimated codex `~Burst` baseline lookup so it stops keying the "weekly period" on the exact rolling `resetsAt`. The synthesized burst used% currently reads a frozen 0% whenever the current 5h window started before the last `resetsAt` change.
- **status:** implemented
- **source:** `agentos-hugentics-impl --dev` on the frozen-0% diagnosis (this session). Revises the `Baseline.Rule` established in `notes/live/690-codex-estimated-burst-limit-substitution-impl-req.md`.
- **current state:** `_synthesize_estimated_burst_limit` (`src/agentos/agent/monitor/workflows/limits_tracking.py`) filters registry records to `record["reset_at"] == period_key` (the account-status weekly `resetsAt`) before taking the nearest record at-or-before the fixed-local-5h `window_start`. Codex's weekly `resetsAt` is a rolling value that drifts every few minutes (observed: 4 distinct values in 24h; current one first appeared mid-window), so the exact-match `period_records` rarely reach back to the window start → `baseline is None` → `used_percent = 0`.
- **out of scope:** the overflow display work just shipped (uncommitted); the estimator math in `burst_estimation.py`; the `fixed_local_5h_window` convention; claude/copilot behavior; registry persistence; the monitor loop/clock/rotation.

## Impl.Index

### Baseline.Rolling.Reset.Defect

- codex's weekly `resetsAt` is not a stable weekly-period identity; it advances continuously as the rolling 7-day window slides (evidence: `tk` saw `resetsAt` values `07-19T20:02`, `07-22T05:25`, `05:28`, `05:32` within one day).
- keying `period_records` on exact `reset_at` equality collapses the eligible baseline set to "records since `resetsAt` last changed", which is typically after the current `window_start`.
- result: `nearest_record_at_or_before(period_records, window_start)` returns `None` and the estimate falls to the 0% branch — intermittently, whenever the window start precedes the last `resetsAt` change.

### Corrected.Baseline.Rule

- baseline = nearest registry record for the target at-or-before `window_start`, with **no weekly-period filter** and no proximity tolerance.
- the existing `max(0, weekly_now - baseline_used)` floor already absorbs a genuine weekly reset: usage drops across a reset → non-positive delta → 0% (safe), so the period filter was never load-bearing for reset safety.
- the temporal constraint is unchanged: no record at-or-before `window_start` still means no observed usage → 0% (preserves the existing "late record only" behavior).
- accepted limitation: after long monitor downtime that spans a real weekly reset, an old baseline from a prior week can overestimate; this only affects an already-`~`-flagged estimate, and the shipped overflow display renders >100% legibly. A future age-bound refinement is noted, not built.

### Hard.Evidence

- live simulation over the last 10 fixed-local-5h windows for `codex/tk`: OLD and NEW agree on every window where `resetsAt` was stable across the window start; they diverge only on the `2026-07-15T04:00` window where **OLD=0% (frozen), NEW=63%**. The `09:00` window legitimately reads 127% under both (real burst overflow), confirming the fix does not inflate normal windows.
- existing tests: `test_limits_tracking_synthesizes_estimated_burst_limit_for_codex` (same-period baseline → 50%) stays green; `test_limits_tracking_estimated_burst_zero_without_period_baseline` tests the *temporal* "record after window start" case (not period equality) → stays green. No existing test encodes the exact-`resetsAt` rejection being removed.

## Execution.Plan

### Slice 1 - Drift-resistant baseline (RED -> GREEN)

- RED: add `test_limits_tracking_estimated_burst_baseline_survives_rolling_reset` — one registry record at-or-before `window_start` carrying a **different** `reset_at` than the account-status weekly period, with a lower `used_percent`. On current code the exact-`reset_at` filter drops it → synthesized `used_percent == 0`; the test asserts a non-zero estimate, so it fails RED.
- GREEN: in `_synthesize_estimated_burst_limit`, remove the `period_records` exact-`reset_at` filter; call `nearest_record_at_or_before(target_records, target=window_start)`. Simplify `_weekly_usage_point` to yield just `weekly_now` if `period_key` becomes unused. Update the function docstring to state the corrected rule and the `max(0, delta)` reset-safety argument.
- keep the `max(0, ...)` floor and the uncapped value from impl-req 691.
- check: `cd agentos-py && uv run pytest tests/test_agent_monitor_limits_tracking.py`
- status: complete

### Slice 2 - Verification and rule sync

- rename/clarify `test_limits_tracking_estimated_burst_zero_without_period_baseline` if its name misleads post-fix (it asserts the temporal case); keep its assertion.
- note the revised `Baseline.Rule` against source surface: `notes/live/690-...-impl-req.md` and its agendix anchors (`Normalization.Pipeline::Account.Usage.Model-agendix.md`, `^20260715-3`). Update AGENTS.md only if it documents this rule (it documents logging only — verify).
- full monitor + account-status suite and ruff on touched files.
- check: `cd agentos-py && uv run pytest tests/ -k "monitor or account_status or limits" -q` and `uv run ruff check` on touched files.
- status: complete

## Acceptance.Signals

- the drifted-`resetsAt` RED test passes; a baseline at-or-before the window start is used regardless of its `reset_at`.
- `test_limits_tracking_synthesizes_estimated_burst_limit_for_codex` and `..._zero_without_period_baseline` remain green.
- no exact-`reset_at` period filter remains in `_synthesize_estimated_burst_limit`.
- full monitor/account-status/limits suite and ruff pass.
- manual live check: `agentos agent accounts monitor dev-test` unaffected; the codex `~Burst` row reflects weekly delta over the current 5h window rather than a frozen 0%.

## Deviation.Triggers

- stop if removing the filter makes an existing burst test assert a physically wrong value (would signal the delta semantics, not the filter, are wrong).
- stop if the fix requires touching `burst_estimation.py` estimator math or the registry (out of scope; would break the real-data-only invariant).
- stop if a bounded-baseline guard turns out to be required for correctness rather than a nice-to-have (escalate the design decision).

## Impl.Log

- 2026-07-15: Impl.Req created via `agentos-hugentics-impl --dev`. Baseline fix designed against live registry evidence; revises impl-req 690 `Baseline.Rule`.
- 2026-07-15: Executed via `agentos-hugentics-impl --exec --AUTO`. Git checkpoint deliberately **skipped**: the project's user-gated commit policy (higher priority than the execute module's mandatory-checkpoint step) forbids committing without explicit instruction, and the worktree already carries uncommitted overflow-display work; all changes left uncommitted for review.
- 2026-07-15: Slice 1 — RED `test_limits_tracking_estimated_burst_baseline_survives_rolling_reset` failed `0 == 50` on the exact-`reset_at` filter; removed the `period_records` filter so the baseline is the nearest record at-or-before `window_start` regardless of `reset_at`; GREEN. `_weekly_usage_point` left intact (still consumed by `_sync_weekly_usage_baselines`); `period_key` now unused in synthesis.
- 2026-07-15: Slice 2 — renamed `..._zero_without_period_baseline` → `..._zero_without_baseline_before_window` (it asserts the temporal case). AGENTS.md documents logging only; no doc update owed. Verification: full suite 361 passed (+1 new test); monitor/account-status/limits slice 87 passed; ruff clean on touched files. Live registry simulation confirmed the fix turns the frozen `04:00`-window `tk` estimate from 0% → 63% while agreeing with prior behavior on all stable-`resetsAt` windows.
