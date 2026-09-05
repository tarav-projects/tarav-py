# Measured Burst Ratio and Provided Burst Window — Impl.Req

## Impl.Abstract

- **scope:** replace the hardcoded per-provider weekly-burst constant with a value
  measured from the two real provider windows, and remove the codex 5h burst
  estimation so codex renders only the provider-supplied 300-min window.
- **status:** implemented
- **source:** account-monitor session 2026-09-05; User decisions captured in the
  `781.Impl.Req` Collection.
- **current state:** OpenAI resumed publishing the codex 5h window on
  `2026-08-30T00:45Z`. Every codex usage record since then carries
  `rateLimits.primary.windowDurationMins == 300` and
  `secondary.windowDurationMins == 10080` across all four accounts, with no
  exceptions. `_synthesize_estimated_burst_limit` is therefore already gated off
  by `_has_burst_limit`, so the rendered Burst row is real provider data. The
  estimation machinery nevertheless still runs on every refresh alarm: a
  full-registry scan plus histogram fit measured at ~18s, and its output has
  degraded to 2.13 weekly-percent-per-burst against an empirical ~15.7. That
  degraded value is the live input to the codex Weekly burst-unit variant.
- **out of scope:** registry/persistence format, provider account-status parsing,
  auto-prime trigger semantics, monitor loop/clock/rotation code, the
  `dev/burst-detection` testground at the repository root.

## Impl.Req.Diagram

- **namespace:** User.Touched.Chatlas.Index / `1c99092c-ba46-4006-adc3-9ada50c00abd`
- **model:** Tarav / `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- **collection:** 781.Impl.Req / `016e7a4a-3de7-4c7e-b68c-66476f4525d7`
- **collection type:** Impl.Req.Collection
- **draft:** `8cb99243-0f5a-43db-ae0a-2cc097325d7e` /
  `~/Documents/tarav/diagram/drafts/8cb99243-0f5a-43db-ae0a-2cc097325d7e.json`
- **semantic block:** Account.Usage.Burst.Measurement / `fb675ad7-3cb7-407e-8ca0-50fdbb457ca8`
- **authorization gate:** `f7865bb8-4eaf-45d2-b9a8-77685822c6b9`

The Collection hosts the supported User-Touched constraints and decisions for
this request. Inspect the Draft and Diagram; do not duplicate those Lines here.

## Execution.Plan

### Slice 1 — Burst-ratio measurement module

- add `src/tarav/agent/monitor/burst_ratio.py` measuring weekly-percent-per-full-burst
  from usage-registry records that carry both provider windows.
- provider window adapters: codex reads `rateLimits.primary`/`secondary` matched by
  `windowDurationMins` 300 and 10080; claude-code reads `rate_limits.five_hour`
  and `rate_limits.seven_day`. A provider publishing only one window yields no
  samples and therefore no ratio.
- bounded scan: walk registry files newest-first and stop once the measurement
  window (default 14 days) is covered. Measured at 0.55s against the live
  registry, against ~18s for the estimator being removed.
- run splitting: start a new run whenever either window's reset identity changes
  or either used-percent decreases. Within a run take telescoped endpoint deltas
  (`last - first`), never per-observation deltas, so integer-percent truncation
  stays bounded at one unit per run instead of accumulating.
- keep a run when `delta_burst > 0` and `delta_weekly >= 0`.
- per account: `ratio = 100 * sum(delta_weekly) / sum(delta_burst)`.
- per provider: the median across per-account ratios, never a pooled sum over raw
  totals.
- observable: measuring the live registry returns codex within 15.3–15.9 and
  claude-code within 9.4–9.7, with per-account sample counts.
- check: `uv run pytest` over new module tests covering reset splitting,
  decrease splitting, telescoping across a quantized series, per-provider median
  selection, and insufficient data returning no ratio; `uv run ruff check` on the
  new file.
- status: complete

### Slice 2 — Wire the measured ratio into the Weekly burst-unit variant

- `LimitsWorkflowState.burst_ratios` replaces `codex_estimated_burst`, retaining
  per-account values, the per-provider median, sample counts, and `computed_at`
  for observability.
- refresh at workflow setup and whenever the retained measurement is older than
  the staleness TTL; the ratio is a slowly-moving calibration value, not a
  per-refresh measurement.
- `_weekly_burst_percent` resolves the account's own measured ratio first, then
  the provider median, and returns `None` when neither exists — an unmeasured
  target loses the Burst-unit variant rather than receiving a fabricated value.
- thread `account` from the target through `_account_limit_rows` and
  `_weekly_burst_unit_summary` to reach that lookup; `target_key` cannot identify
  the registry account.
- delete `_WEEKLY_BURST_PERCENT_BY_PROVIDER`.
- observable: codex and claude-code Weekly rows keep the Burst-unit variant
  driven by measured values; copilot-cli, which publishes no window pair, has no
  variant.
- check: `uv run pytest tests/test_agent_monitor_limits_tracking.py tests/test_agent_monitor_loop_render.py`
- status: complete

### Slice 3 — Remove the estimation path

- delete `src/tarav/agent/monitor/burst_estimation.py`.
- delete `_refresh_codex_estimated_burst_state`, `_synthesize_estimated_burst_limit`,
  `_has_burst_limit`, `_utc_iso`, and the burst-estimation imports from
  `limits_tracking.py`, plus both call sites in `setup` and `loop`.
- remove `AccountLimit.estimated` and its `summary()` branch from
  `src/tarav/agent/account_status.py`; remove the `~` prefix from `_limit_label`.
- relabel the `dev_test.py` candidate rows from `~Burst` to `Burst` and drop the
  docstring's estimated-burst reference.
- delete the estimation tests in `tests/test_agent_monitor_limits_tracking.py`
  and the `estimated` flag test in `tests/test_agent_account_status_report.py`.
- observable: codex Burst rows originate only in the provider payload; no `~`
  prefix and no `estimated` key remain anywhere.
- check: `uv run pytest tests/ -k "monitor or account_status" -q`
- status: complete

### Slice 4 — Verification

- full `uv run pytest` suite and `uv run ruff check` on touched files.
- confirm no limits-tracking refresh path performs a full-registry scan.
- status: complete

## Risks and Deviation Triggers

- stop if removing `AccountLimit.estimated` reaches a consumer outside the
  monitor and account-status surfaces.
- stop if the measured codex or claude ratio at execution time falls outside the
  ranges recorded in Slice 1; report the measurement rather than accepting it
  silently.
- a target whose provider publishes only one window is an expected no-variant
  case, not a failure.
- auto-prime consumes limits-tracking target states directly
  (`workflows/auto_prime.py:147`) and its configured `target_limits` for codex is
  `["burst"]`. Removing synthesis means it evaluates only provider-supplied burst
  limits. Do not reintroduce any in-memory limit synthesis without revisiting
  that coupling.

## Acceptance.Signals

- `_WEEKLY_BURST_PERCENT_BY_PROVIDER` and `burst_estimation.py` no longer exist.
- the Weekly Burst-unit variant is driven by measured registry values for both
  codex and claude-code.
- no `estimated` key in any `AccountLimit` summary and no `~` label prefix.
- limits-tracking refresh performs no full-registry scan.
- monitor and account-status suites and ruff pass.

## Impl.Log

- 2026-09-05: Impl.Req created from the account-monitor design session. Provider
  recovery, estimator cost, and estimator degradation were measured against the
  live usage registry before writing the plan.
- 2026-09-05: Open design decision recorded — run splitting keys on reset
  identity rather than used-percent decrease alone. A decrease-only rule was
  tested and produced 56.4 for codex `br` against 15.75 under reset-keyed
  splitting, because it merges across windows that reset from zero to zero.
- 2026-09-05: Open design decision recorded — per-provider aggregation takes the
  median of per-account ratios. Pooling raw totals was tested and produced 48.5
  for codex, because one account carried roughly sixteen times the burst volume
  of the others and dominated the sum.
- 2026-09-05: Observation deferred, not blocking — codex `br` produces 214 reset
  runs against 40–80 for the other accounts at comparable observation counts.
  Its reset identity churns far more. Possibly auto-prime activity; unconfirmed.
- 2026-09-05: Slice 1 — the bounded scan reuses `usage_registry._iter_lines_reverse`
  through a new public `iter_usage_records_since`, rather than re-reading whole
  files inside the monitor. Registry reading stays owned by `usage_registry`;
  `burst_ratio` stays pure measurement. Measured cost is 0.12s, below the 0.55s
  the plan budgeted.
- 2026-09-05: Slice 1 deviation (minor drift, resolved without User input) — over
  the 14-day measurement window codex `br` measures 15.07, marginally below the
  15.3–15.9 band the plan recorded from a 6-day sample. Every other account and
  both provider medians land inside their bands (codex 15.41, claude-code 9.76).
  The shift tracks the longer window, not a design fault, so execution continued.
- 2026-09-05: Slices 2 and 3 landed together, deviating from the planned slice
  order. Dropping the burst-estimation imports in Slice 2 left the synthesis
  helpers referencing undefined names, so the module had no coherent
  intermediate state in which Slice 2's check could pass.
- 2026-09-05: Open-space decision — `_account_limit_rows` keeps `target_key`
  alongside the new `account` parameter. `target_key` still addresses the
  weekly-baseline delta-marker feature, which is out of scope here; only the
  burst-ratio lookup moved to `account`.
- 2026-09-05: Verification — full suite 1288 passed, ruff clean across the
  project, and no `burst_estimation`, `codex_estimated`, `estimated`,
  `_WEEKLY_BURST_PERCENT_BY_PROVIDER`, or `~Burst` reference remains in `src/`
  or `tests/`. A live `tarav agent accounts monitor --once` measured
  codex 15.07–15.45 and claude-code 9.67–9.87, and every rendered Burst-unit
  row's `usage_burst_units_left` equals `(100 - used) / weekly_burst_percent`
  against its own account's measured ratio. `claude-code/om` has no usable runs
  and correctly falls back to the claude-code median; `copilot-cli/jp`
  publishes no window pair and renders no variant.
- 2026-09-05: Observation, out of scope — `codex/jp` reports two weekly windows
  in its provider payload, so it renders two Weekly rows. Pre-existing
  provider-parsing behavior; both rows take the same measured account ratio.
