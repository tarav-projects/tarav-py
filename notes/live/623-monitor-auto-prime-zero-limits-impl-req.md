# Monitor Auto-Prime Zero Limits - impl-req

## Impl.Abstract

- **scope:** add a separate account-monitor workflow that pings configured provider accounts when selected account limits are observed at `0%`.
- **status:** implemented.
- **source:** user request during monitor workflow design: when a provider limit resets, the account may not be usable until a new message is sent; the monitor should automatically send a light ping to prime accounts whose selected limits are at `0%`.
- **target project:** `agentos-py`.
- **primary surfaces:**
  - `src/agentos/agent/monitor/workflows.py`
  - `src/agentos/agent/monitor/loop.py`
  - `src/agentos/agent/monitor/clock.py`
  - `src/agentos/agent/monitor/config.py`
  - `src/agentos/agent/account_status.py`
  - `src/agentos/agent/providers.py`
  - `src/agentos/agent/run_runtime.py`
  - `tests/test_agent_account_registry_commands.py`
- **precondition already completed in current worktree:** `AccountLimit` has a required `limit_id`; Codex and Claude Code emit semantic ids `burst` and `weekly`.

## Impl.Index

### Intent

The monitor should automatically prime accounts with selected limits at `0%` by sending one light ping per account/limit-period.

The ping is account-level, not limit-level. If an account has multiple eligible zero limits in the same scan, run one ping and mark all eligible period keys as satisfied when the ping succeeds.

### Workflow.Boundary

Do not overload `limits-tracking`.

Add a separate workflow, likely named `auto-prime-zero-limits`, that consumes monitor state published by `limits-tracking`.

`limits-tracking` remains responsible for:

- fetching/parsing provider account usage
- publishing target states under `state.data["limits-tracking"]`
- rendering usage and reset rows

`auto-prime-zero-limits` is responsible for:

- reading `state.data["limits-tracking"]`
- deciding whether selected limits need a prime ping
- running a light configured ping
- recording success/failure/cooldown in its own state
- rendering only small status/error feedback

### Dependency.Model

No hard dependency framework is needed.

`auto-prime-zero-limits` may consume previous-tick `limits-tracking` state. It does not require `limits-tracking` to run in the same tick and does not require strict workflow ordering beyond the normal configured workflow order.

The workflow should be eventually consistent:

- if `limits-tracking` data is present, inspect it
- if absent or malformed, skip or render a compact expected-state message
- do not crash the monitor because a dependency state is absent

### Trigger.Model

`auto-prime-zero-limits` should own its own alarm and cadence.

Add a clock alarm constant such as:

```python
AUTO_PRIME_ZERO_LIMITS_PERIODIC_ALARM = "auto-prime-zero-limits.periodic"
```

The monitor loop currently has special adaptive scheduling for `limits-tracking`. Do not generalize the alarm framework unless needed. A minimal implementation may add a fixed periodic alarm for this workflow using a workflow attribute analogous to `periodic_alarm_name` and `refresh_interval_sec`.

Defaults:

- `interval_sec`: 60 seconds
- `retry_cooldown_sec`: 600 seconds

Setup behavior:

- initialize own workflow state
- do not ping during setup
- optionally write an empty/small frame block

Loop behavior:

- act only when its own periodic alarm fires
- ignore unrelated monitor alarms

### Limit.Selection

`auto-prime-zero-limits` is provider-aware, like `limits-tracking`.

Limit selection must use stable `AccountLimit.limit_id`, not duration fields such as `period_duration_mins`.

Default target ids:

- `codex`: `burst`
- `claude-code`: `burst`

No fallback ids. If config names an unsupported provider or limit id for this workflow, fail clearly during config loading or workflow construction.

Config shape may follow local monitor config style. A compact acceptable shape:

```json
{
  "workflow": "auto-prime-zero-limits",
  "interval_sec": 60,
  "retry_cooldown_sec": 600,
  "target_limits": {
    "codex": ["burst"],
    "claude-code": ["burst"]
  }
}
```

If `target_limits` is omitted, use provider defaults.

### Eligibility.Rule

For each target in `state.data["limits-tracking"]["targets"]`, inspect:

- target provider/account/home
- target status
- `account_status.limits[]`
- each limit's `limit_id`
- `usage_over_time.used_percent`
- `usage_over_time.period_started_at`
- `usage_over_time.period_ends_at`
- `usage_over_time.resets_at`

A limit is eligible when:

- target status is `ok`
- limit `limit_id` is configured for the target provider
- limit has `usage_over_time`
- `used_percent == 0`
- its current period has not expired according to `period_ends_at` or `resets_at`
- the exact account/limit-period key has not already had a successful prime
- the account is not under failure cooldown

If period dates cannot be parsed, skip the limit and optionally record a compact state reason. Do not ping based on an unbounded period key.

### Period.Key

The state key should be stable for one account and one observed limit period.

Use a structured key derived from:

- provider
- account
- home
- limit_id
- period_started_at
- period_ends_at or resets_at

Do not use display label text for period keys.

### Ping.Semantics

Use the existing agent run machinery, not a shell call to `agentos agent ping`.

Build the account agent with:

```python
build_registered_account_agent(provider=..., account=..., home=...)
```

Then run the selected agent's configured ping with `AgentCommandConfig` and `AgentRunConfig`.

The ping should be light:

- process mode should be capture, not terminal UI
- use existing configured `agent.ping`
- validate the same success conditions as `agentos agent ping` where practical
- do not print provider output into the monitor by default

If `agent.ping.enabled` is false, treat it as an expected prime failure for that account and apply cooldown.

### State.Shape

Store workflow state under:

```python
state.data["auto-prime-zero-limits"]
```

Suggested shape:

```python
{
    "targets": {
        "provider/account@home": {
            "last_attempt_tick": 10,
            "last_success_tick": 10,
            "retry_after_monotonic": 123.45,
            "primed_periods": {
                "<period-key>": {
                    "limit_id": "burst",
                    "status": "ok",
                    "attempt_count": 1,
                    "last_attempt_tick": 10,
                    "last_success_tick": 10
                }
            },
            "last_error": {
                "message": "...",
                "error_type": "...",
                "last_attempt_tick": 12
            }
        }
    }
}
```

Use monotonic time for cooldown calculations. Tick fields are useful for JSON/debugging.

### Rendering

Keep footprint small.

Acceptable rendering:

- no per-target success rows by default
- a compact row when pings actually happened, e.g. `auto-prime | pinged 1`
- a compact row for failures, e.g. `auto-prime | codex/br failed: ...`

It is acceptable for `auto-prime-zero-limits` to append a small block after `limits-tracking`. Do not redesign monitor rendering.

If appending into the existing `limits-tracking` frame block is simpler and consistent with workflow order, it is allowed, but the workflow must not mutate `limits-tracking` state semantics.

### No.Legacy.Allowed

- Do not add compatibility paths for pre-`limit_id` account limit summaries.
- Do not select limits by `period_duration_mins`.
- Do not shell out to the `agentos` CLI for pings.
- Do not make `limits-tracking` run pings.
- Do not add a generalized workflow dependency framework.
- Do not introduce provider-specific ping command branches outside provider-aware selection and existing agent config.

## Execution.Plan

### Slice 1 - Confirm AccountLimit `limit_id` Baseline

Status: completed.

- Verify `AccountLimit.limit_id` is required and serialized.
- Verify Codex and Claude Code emit `burst` / `weekly`.
- Verify tests cover Codex semantic id behavior.

Checks:

```sh
uv run pytest tests/test_agent_account_registry_commands.py -q
```

### Slice 2 - Add Auto-Prime Config Model

Status: completed.

- Extend monitor config parsing to accept `workflow: "auto-prime-zero-limits"`.
- Add workflow config fields for:
  - `interval_sec`
  - `retry_cooldown_sec`
  - optional `target_limits`
- Validate target limit ids against supported provider defaults.
- Keep `limits-tracking` config behavior unchanged.

Checks:

- config with omitted `target_limits` uses Codex/Claude `burst`
- config with unsupported provider/limit id fails clearly
- existing unknown workflow tests remain meaningful

### Slice 3 - Add Alarm Scheduling

Status: completed.

- Add `AUTO_PRIME_ZERO_LIMITS_PERIODIC_ALARM`.
- Teach `MonitorLoop` to arm a periodic alarm for the new workflow without disturbing `limits-tracking` adaptive scheduling.
- Keep `auto-prime` fixed-period for now.

Checks:

- auto-prime alarm fires on its configured cadence
- unrelated alarms do not cause auto-prime pings
- limits-tracking adaptive alarm tests still pass

### Slice 4 - Implement Workflow Scan And State

Status: completed.

- Add `AutoPrimeZeroLimitsWorkflow`.
- `setup(...)` initializes/writes minimal state only.
- `loop(...)` reads `state.data["limits-tracking"]`, scans target account statuses, and computes eligible period keys.
- Store success/error/cooldown state under `state.data["auto-prime-zero-limits"]`.
- Skip absent/malformed dependency state without crashing.

Checks:

- no `limits-tracking` state means no ping
- non-zero limits do not ping
- zero configured limit creates an eligible account action
- expired periods do not ping
- already successful period keys do not ping again

### Slice 5 - Run Light Account Ping

Status: completed.

- Implement an internal helper to run the configured ping for a registered account agent.
- Reuse `build_registered_account_agent(...)`.
- Reuse ping command config semantics from `_cmd_agent_ping(...)` without calling the CLI handler.
- Apply a 10-minute cooldown on failure by default.
- On success, mark all eligible period keys for that account as primed.

Checks:

- multiple eligible limits on one account produce one ping
- success marks every eligible period key
- failure records error and prevents retry during cooldown
- cooldown expiry allows retry
- ping-disabled agents record expected failure and cooldown

### Slice 6 - Minimal Rendering

Status: completed.

- Add compact frame output for the new workflow.
- Prefer no success noise except a small summary when a ping occurs.
- Always show compact failure rows.
- Do not change existing `limits-tracking` rows except where explicitly chosen for small appended feedback.

Checks:

- success does not spam per-target rows
- failure is visible in frame JSON and text rendering
- monitor `--once --json` remains stable enough for existing tests

### Slice 7 - Validation

Status: completed.

Run focused tests:

```sh
uv run pytest tests/test_agent_account_registry_commands.py -q
```

Run lint:

```sh
uv run ruff check src/agentos/agent/monitor src/agentos/agent/commands.py src/agentos/agent/account_status.py src/agentos/codex/account_status.py src/agentos/claude/account_status.py src/agentos/copilot/account_status.py tests/test_agent_account_registry_commands.py
```

If CLI/runtime files changed, refresh installed CLI:

```sh
uv tool install --reinstall --editable .
```

Manual smoke:

```sh
agentos agent accounts monitor --once
agentos agent accounts monitor --once --json
agentos agent accounts monitor --max-ticks 3 --interval-sec 1
```

### Acceptance Signals

- `auto-prime-zero-limits` exists as a separate monitor workflow.
- It consumes `limits-tracking` state without a hard dependency framework.
- It selects limits by `limit_id`.
- Defaults prime `burst` for Codex and Claude Code.
- It pings once per account per eligible observed period.
- It does not ping again after a successful prime for the same period key.
- Failures enter cooldown and render compact feedback.
- `limits-tracking` does not perform ping work.
- Existing monitor behavior remains intact when the new workflow is not configured.

## Impl.Log

- Created Impl.Req from the accepted design discussion. The requested implementation should add a separate, lightweight auto-prime workflow that reads `limits-tracking` state and pings accounts whose selected semantic limit ids are at `0%`.
- Implemented `auto-prime-zero-limits` as a separate monitor workflow. It parses its own config (`interval_sec`, `retry_cooldown_sec`, `target_limits`), reads `state.data["limits-tracking"]`, selects provider-aware `limit_id` targets, pings configured registered account agents through captured `AgentRunConfig`, records primed period keys and cooldown state under its own state key, and renders compact success/failure rows only when there is feedback to show.
- Added fixed periodic alarm support for `auto-prime-zero-limits` without changing the existing adaptive `limits-tracking` alarm policy.
- Added focused tests for config defaults and validation, fixed alarm cadence, unrelated alarm suppression, expired period suppression, one ping per account for multiple eligible limits, success period marking, failure cooldown, and compact failure rendering.
- Validation completed: `uv run pytest tests/test_agent_account_registry_commands.py -q` passed with `112 passed`; requested `uv run ruff check ...` passed; `uv tool install --reinstall --editable .` completed; manual monitor smoke commands completed against the local configured `limits-tracking` monitor.
