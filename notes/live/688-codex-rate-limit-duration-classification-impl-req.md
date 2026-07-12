# 688 — codex rate-limit duration classification

## Impl.Abstract

- **Scope:** fix Codex account usage parsing so limit identity follows the reported window duration when Codex changes which window key carries weekly usage.
- **Status:** implemented.
- **Source:** `$agentos-hugentics-impl --dev`; user requested the parser bug fix and deferred broader discussion of the new Codex provider format.
- **Out of scope:** recovering a missing 300-minute Burst window when Codex does not return one, changing monitor layout, changing usage-registry retention, or redesigning Codex app-server integration.

## Impl.Index

### Bug.Codex.Primary.Window.Assumption

- Current Codex parser maps `primary` to `burst` and `secondary` to `weekly` unconditionally in `src/agentos/codex/account_status.py`.
- Current live Codex payloads may return `primary.windowDurationMins = 10080` with `secondary = null`.
- That makes the parsed limit id/label say Burst even though the duration is weekly.
- The monitor label derives from duration and shows Weekly, creating inconsistent state and summaries.

### Fix.Duration.First.Classification

- Codex limit identity should be classified from `windowDurationMins` when it is known: `300` is `burst`, `10080` is `weekly`.
- Window-key fallback should remain only for unknown or missing durations so older/partial payloads still parse.
- `provider_limit.window_key` should remain unchanged so raw-provider provenance is preserved.

## Execution.Plan

### Vertical.Slice 1 — Regression test for primary-weekly payload

- **Status:** complete.
- **Target:** `tests/test_codex_usage_records.py`.
- **Change:** add coverage for a Codex payload where `rateLimits.primary.windowDurationMins` is `10080` and `secondary` is `None`.
- **Check:** assert the parsed status summary and parsed limit identify Weekly, not Burst.
- **Acceptance:** test fails before parser change and passes after.

### Vertical.Slice 2 — Duration-first Codex classification

- **Status:** complete.
- **Target:** `src/agentos/codex/account_status.py`.
- **Change:** replace unconditional window-key identity with a small duration-first classifier used for `limit_id`, `limit_name`, and `limit_label`.
- **Check:** run `uv run pytest tests/test_codex_usage_records.py tests/test_agent_monitor_limits_tracking.py`.
- **Acceptance:** old `primary=300 secondary=10080` tests still pass; new `primary=10080 secondary=None` test passes.

### Vertical.Slice 3 — Verification

- **Status:** complete.
- **Checks:** targeted pytest, targeted ruff for changed files, `git diff --check`.
- **Acceptance:** no unrelated code changes; Impl.Req updated to implemented.

## Impl.Log

- **Decision:** skip the execution checkpoint commit because root AGENTS.md says commits are user-gated and the user did not explicitly authorize a commit.
- **RED:** `uv run pytest tests/test_codex_usage_records.py::test_agent_usage_classifies_codex_primary_weekly_by_duration` failed with `Burst 5%` instead of `Weekly 5%`.
- **Implemented:** Codex limit ids/labels now classify by `windowDurationMins` first (`300` -> `burst`, `10080` -> `weekly`) and fall back to `primary`/`secondary` only when duration is unknown.
- **Verified:** `uv run pytest tests/test_codex_usage_records.py::test_agent_usage_classifies_codex_primary_weekly_by_duration` — passed.
- **Verified:** `uv run pytest tests/test_codex_usage_records.py tests/test_agent_monitor_limits_tracking.py` — 9 passed.
- **Verified:** `uv run ruff check src/agentos/codex/account_status.py tests/test_codex_usage_records.py` — passed.
- **Verified:** `agentos agent accounts monitor --once --json` compact extraction shows current Codex `10080`-minute windows as `Weekly`.
- **Verified:** `git diff --check` — passed.
