# Codex Estimated Burst Limit Substitution - impl-req

## Impl.Abstract

- **scope:** replace the parallel estimated-burst rendering path in the monitor limits-tracking workflow with a data-layer substitution: a synthesized, flagged `AccountLimit` flowing through the unchanged limit-rendering pipeline. Codex recovers the full limit view (Burst + Weekly) mirroring claude, with the burst row marked `~Burst` as estimation guidance.
- **status:** implemented
- **source:** design session 2026-07-15; decisions captured in `agentos-md/skills/agentos-pkg/agendix/Normalization.Pipeline::Account.Usage.Model-agendix.md` (anchors `^20260715-0…3`).
- **current state:** OpenAI stopped publishing the codex 5h burst window (live registry confirms: `primary` = weekly 10080-min window, `secondary` null). The uncommitted estimation work in `src/agentos/agent/monitor/workflows/limits_tracking.py` (+523 lines over `e25c861`) added the weekly-history estimator plus a second, conditionally-gated rendering path (`_codex_estimated_burst_rows`, `codex_estimated_burst_targets`, ±30min baseline tolerance) — when its gate fails, codex silently shows Weekly only.
- **out of scope:** registry/persistence changes (registry logs only real provider data — unchanged by construction); estimator math changes (kept as-is, iterated separately in `dev/burst-detection`); claude/copilot behavior; the committed weekly-baseline delta-marker feature (`e25c861`); monitor loop/clock/rotation code.

## Impl.Index

### Estimation.As.Data.Substitution

- the estimation substitutes only the missing provider burst window; every other limits-tracking service stays on (user decision ^20260715-0).
- substitution happens at the data layer: a synthesized `Usage.Limit` entering the target's limits list, rendered by the generic `_account_limit_rows` pipeline — never a parallel row builder (^20260715-1).
- synthesis is monitor-in-memory only; usage-registry records are written exclusively by the fetch paths, so estimated limits cannot reach disk by construction (^20260715-1).
- synthesis is skipped when the provider payload carries a real burst window (estimation is a fallback, not an override).

### Estimated.Limit.Flag

- `AccountLimit` gains `estimated: bool = False`; `summary()` emits `"estimated": true` only when set, so real-limit payloads are byte-identical to today (^20260715-2).
- display derives from the flag: `_limit_label` prefixes `~` (→ `~Burst`); no consumer may treat a flagged limit as provider data.

### Baseline.Rule

- burst window = fixed local 5h bucket (midnight-aligned) — a deliberate guidance convention (^20260715-2).
- baseline = nearest registry record at-or-before window start within the same weekly period; **no proximity tolerance** — a record gap means no monitored activity, so an older baseline stays valid (^20260715-3).
- no at-or-before record in the current weekly period → estimated burst shows 0% ("no activity, no usage"); records after window start may exist but do not serve as baseline (^20260715-2).
- estimated used% = round(max(0, weekly_now − weekly_at_baseline) / burst_weekly_percent × 100), clamped to [0, 100] for the gauge.

### Estimator.Module

- the weekly-history estimator (flat-range deltas → exponential-background/gaussian-excess fit → median across thresholds, fallback 15.8%) moves verbatim into `src/agentos/agent/monitor/burst_estimation.py` — statistics, registry scanning, and window math have no business inside the workflow class.
- module mirrors `dev/burst-detection/common` conceptually; improvements iterate there first (^20260715-1).
- the weekly row's burst-unit variant for codex keeps consuming the estimate (claude uses a static constant; codex uses the dynamic one).

## Execution.Plan

### Slice 1 - Estimator module extraction

- create `src/agentos/agent/monitor/burst_estimation.py`: move `_codex_usage_registry_records`, `_codex_weekly_limit_from_payload`, `_timestamp_period_key`, `_codex_estimated_burst_weekly_percent`, `_codex_flat_range_deltas`, `_codex_records_by_target`, `_codex_flat_ranges`, `_nearest_codex_record`, `_bisect_datetimes`, `_gaussian_estimate_from_excess`, `_ExponentialBackground`, `_fit_exponential_background`, `_fit_log_linear`, `_median`, `_mad`, the `_CODEX_ESTIMATED_BURST_*` constants, and `_fixed_local_5h_window` — public names for the module boundary (e.g. `estimated_burst_weekly_percent`, `codex_registry_records`, `fixed_local_5h_window`, `nearest_record_at_or_before`).
- `limits_tracking.py` imports from the module; behavior unchanged.
- check: `uv run pytest tests/test_agent_monitor_limits_tracking.py tests/test_agent_monitor_loop_render.py`
- status: complete

### Slice 2 - AccountLimit.estimated flag

- add `estimated: bool = False` to `AccountLimit` (`src/agentos/agent/account_status.py`); `summary()` includes `"estimated": True` only when set.
- RED: test that a flagged limit's summary carries `estimated: true` and an unflagged one omits the key.
- GREEN: implement; all existing account-status tests unchanged.
- check: `uv run pytest tests/test_agent_account_status.py` (or nearest account-status suite)
- status: complete

### Slice 3 - Synthesis replaces the parallel path

- in `limits_tracking.py`: on refresh (setup + loop), for each codex target whose account-status limits lack a 300-min window, synthesize an estimated burst limit dict (`limit_id="burst"`, `limit_label="Burst"`, `estimated=True`, `usage_over_time` from the fixed-local-5h bucket, used% per `Baseline.Rule`) and insert it before the weekly limit in the target's in-memory `account_status["limits"]`.
- `_limit_label` prefixes `~` when the limit dict carries `estimated`.
- keep `workflow_state.codex_estimated_burst` (weekly_percent + computed_at) as observability payload; delete `codex_estimated_burst_targets`, `_codex_estimated_burst_target_states`, `_codex_estimated_burst_rows`, `_codex_estimated_burst_row_data`, and the ±30min tolerance constant from `state.py`/`limits_tracking.py`.
- the weekly-row burst-unit variant keeps working off the estimate via `_weekly_burst_percent`.
- RED: codex target with weekly-only limits + registry baseline at-or-before window start → frame rows contain a `~Burst` usage/time row and its resets row via the standard pipeline; codex with no earlier record in the weekly period → `~Burst` row at 0%; provider payload with a real burst window → no synthesis, no `~` prefix.
- GREEN: implement; existing burst-unit variant tests stay green.
- check: `uv run pytest tests/test_agent_monitor_limits_tracking.py tests/test_agent_monitor_loop_render.py`
- status: complete

### Slice 4 - Verification and doc sync

- full monitor suite + ruff on touched files.
- update `AGENTS.md` if it documents limits-tracking behavior (it documents the monitor log only — verify).
- check: `uv run pytest tests/ -k "monitor or account_status" -q` and `uv run ruff check` on touched files
- status: complete

## Acceptance.Signals

- codex targets render Burst + Weekly rows through `_account_limit_rows` alone; no codex-specific row builder remains.
- the burst row label is `~Burst`; the limit dict carries `estimated: true`.
- missing baseline no longer suppresses the row — worst case is a 0% estimate.
- real provider payloads produce byte-identical summaries to today (no `estimated` key).
- registry files are never written by the synthesis path.
- monitor + account-status tests and ruff pass.

## Deviation.Triggers

- stop if the synthesis needs to mutate anything that gets persisted (violates registry-real-data invariant).
- stop if `MonitorUsageTimeRow`/render layer needs estimated-awareness beyond the label (would signal the substitution is leaking).

## Impl.Log

- 2026-07-15: Impl.Req created from the design session; executes on top of the uncommitted estimation work in the `agentos-py` worktree (baseline commit `e25c861`).
- 2026-07-15: Pre-execution checkpoint `ef39785` (worktree as found), per the execution workflow's mandatory checkpoint.
- 2026-07-15: Deviation (recorded, no action needed): the checkpointed worktree carried a broken test — `test_limits_tracking_weekly_usage_time_animates_burst_units` failed (`KeyError: 'variants'`) because the parallel path had removed the codex burst-unit variant when no estimate state existed. Fixed under this plan by seeding `codex_estimated_burst={"weekly_percent": 15.7}` in the test's workflow state; the variant path itself is unchanged.
- 2026-07-15: Open-space decision: the ±30min tolerance survives *inside* `burst_estimation.py` as `_FLAT_RANGE_START_TOLERANCE` — it is part of the estimator's flat-range delta sampling (estimator math, out of scope), not the rendering baseline. The rendering baseline uses `nearest_record_at_or_before` with no tolerance, per the design decision.
- 2026-07-15: Open-space decision: `codex_estimated_burst.source` now reports `"usage-registry"` or `"fallback"` so the observability payload distinguishes a fitted estimate from the fallback constant.
- 2026-07-15: AGENTS.md checked: it documents logging subsystems only; no section covers limits-tracking rendering, so no doc update owed.
- 2026-07-15: Executed in `Alignment.Mode:Autonomous`. Verification: `agentos-py` full suite 360 passed; `agentos-cli` `test_e2e_agent_accounts.py` 3 passed; ruff clean on all touched files. Implementation left uncommitted for user review.
