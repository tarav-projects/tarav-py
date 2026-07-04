# 684 — typed monitor workflow state

## Impl.Abstract

- **Scope:** item 3 of the user-approved cleanup list: replace the untyped
  `state.data` dict-of-dicts for the limits-tracking and auto-prime workflow
  state with typed dataclasses, removing the defensive `isinstance` reads.
  JSON payload boundary preserved via explicit `payload()` conversion.
- **Status:** PLANNED.
- **Out of scope:** loop-level `state.data` entries (`monitor_display`,
  `monitor_setup`, `monitor_config_warning`, `workflow_errors`) — flat dicts
  written/read locally, no isinstance noise worth removing; the
  account-rotation workflow (stateless); `account_status` payloads (external
  summary dicts by design).

## Impl.Index

### Block: typed state model
- New `monitor/workflows/state.py`:
  - `LimitsTargetState` — provider/account/home (str), profile/start_path
    (str|None), status, refresh_count, setup_message, `account_status:
    dict | None` (external payload stays dict), `error: dict | None`
    ({type,message}), last_refresh_tick, last_error_emit.
  - `LimitsWorkflowState` — `targets: dict[str, LimitsTargetState]` +
    bookkeeping (setup/last tick, run_count, refresh_interval_sec,
    fired_alarms).
  - `AutoPrimeTargetState` — provider/account/home, `observations` /
    `primed_periods` as `dict[str, dict]` **rows stay dicts** (pure JSON data
    records; typing the containers removes the isinstance guards, typing every
    row would double churn for no read-clarity gain), last_decisions,
    last_decision, retry_after_monotonic, last_error, attempt/success ticks.
  - `AutoPrimeWorkflowState` — targets + last_scan + config bookkeeping.
  - Each class `payload() -> dict[str, object]` mirroring the current stored
    key layout; `monitor_state_payload(state)` converts `state.data` for the
    JSON boundary (objects → payload(), plain dicts pass through).
- Payload-shape note (open-space decision): key presence becomes stable
  (fields always emitted once the state exists, `profile`/`start_path` only
  when set) instead of accreting keys as writes happen. Same values at every
  point a consumer reads today.

### Block: consumers to migrate
- `limits_tracking.py`: `_workflow_state`/`_target_state(s)` accessors become
  typed get-or-create; `_effective_target_state`, `_maybe_log_error`,
  `_error_signal`, `_refresh_target`, `_prime_target_from_usage_registry`,
  `_write_frame_block` (`_target_state_summary` → `payload()`).
- `auto_prime.py`: `_scan_and_prime` reads
  `LimitsWorkflowState.targets` typed; `_eligible_periods`, `_prime_target`,
  `_verify_existing_primes`, `_record_*` use attributes;
  `_parse_limit_period` / `_observation_time` / `_run_account_prime_ping`
  take `LimitsTargetState` (drops `_required_target_string`);
  `_auto_prime_target_state` / `_auto_prime_status_part` typed.
- `render.py`: `"state": monitor_state_payload(state)`.
- Tests: `_monitor_helpers`, auto-prime/limits/loop-render monitor tests,
  `test_agent_monitor_log.py` — construct typed states instead of dicts.

### Block: risk controls
- Thread boundary unchanged: same objects mutated under the existing
  trigger/ready handshake; no new sharing.
- Behavior oracle is the existing suite (255 tests, heavy on these paths).
  Any assertion change beyond dict→attribute construction is a deviation to
  log, not silently absorb.

## Execution.Plan

- Slice 1 — add `workflows/state.py` with the four dataclasses + payload().
- Slice 2 — migrate `limits_tracking.py` + render payload boundary.
- Slice 3 — migrate `auto_prime.py` (cross-reads typed).
- Slice 4 — migrate tests.
- Check after each slice: full suite; final: agentos-py + agentos-cli suites
  green, ruff clean.

## Impl.Log

- 2026-07-04: Impl.Req created (cleaner, autonomous, from user-approved list).
