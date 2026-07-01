# 677 — reconnect monitor auto-prime, aligned to the new agent model

## Impl.Abstract

- **Scope:** re-enable automatic account pinging in `agentos agent accounts monitor`,
  and do it **the redesign-aligned way** — not a blind un-comment. Two coupled changes:
  1. **Reshape the prime consumer** to consume the structured `AgentPingResult` that
     `agent.ping()` returns (675), instead of the current result→exception→result
     round-trip.
  2. **Reconnect the workflow at the loop builder** so the (now-clean) auto-prime
     workflow is actually built into the running monitor.
- **Why now:** the auto-prime workflow is fully implemented and its config is generated
  by default, but it is **severed at one seam** — `build_monitor_workflows` drops it
  (`workflows.py:1232-1234` + `1250-1258`, "TEMPORARILY DISCONNECTED"). Meanwhile the
  prime consumer predates the capability redesign: it calls `agent.ping()` but then
  **re-raises** `result.failure` as `CliError` so the caller's `except Exception` can
  record it — throwing away everything `AgentPingResult` carries.
- **Design source:** this session's monitor exploration + the `Agent.Normal.Model` work
  (capabilities are methods returning structured results; consumers read them, a CLI
  maps to exceptions, the **monitor maps to structured state**). Prime is **ping-only**
  via the normal `agent.ping()` primitive — accepted.
- **Status:** COMPLETE.
- **Out of scope (do NOT touch):**
  - **Credential auto-capture on prime (Impl.Req 658)** — stays deferred. The reshape
    must leave a **clean seam** at the point after a successful ping where capture will
    later hook in (today's comment at `workflows.py:2356`).
  - **Gating prime on `profile_check`** — prime must ping **even when drifted** (probing
    regardless of fitness is its purpose), the same reason `run()`'s primitive stays
    ungated. No `profile_check` in the prime path.
  - **The other monitor workflows** (`LimitsTrackingWorkflow`, `AccountRotationWorkflow`)
    and the auto-prime eligibility/period/verification logic — unchanged; this Req only
    reshapes the *ping invocation + its result handling* and the *builder wiring*.
  - **The double-resolution** (limits-tracking resolves for `account_status`; auto-prime
    re-resolves the same target to ping) — inherent to workflow-state passing; leave it.

## Impl.Index

### Block A: the prime consumer is pre-redesign (`Hard.Evidence`)
- `_run_account_prime_ping` (`workflows.py:2337`) resolves the agent via
  `resolve_account_runtime_agent`, calls `agent.ping(cwd=…)`, then converts outcomes to
  exceptions: `AgentPingError → CliError` and `result.failure → raise CliError`. Returns
  `None`.
- `_prime_target` (`workflows.py:770`) wraps that call in `try/except Exception`,
  recording `last_error` from `str(exc)` and setting a retry cooldown on any failure; on
  success it records `primed_periods` + `AUTO_PRIME_EVENT_ATTEMPT_SUCCEEDED`
  (`workflows.py:~820`).
- Net: a ping that **ran and reported failure** and a ping that **could not be attempted**
  collapse into the same `except` path, and `AgentPingResult`'s `model` / `elapsed_ms` /
  `exit_code` / `output` are discarded.
- `_run_account_prime_ping` is exercised **directly** by tests
  (`test_agent_monitor_auto_prime.py:899/931/967`, monkeypatched at `:848`) — reshaping
  its signature updates those.

### Block B: the target shape (consumer reads the result)
- `_run_account_prime_ping(source_target_state) -> AgentPingResult`: resolve + `return
  agent.ping(cwd=…)`. **Exceptions are reserved for genuine "could not attempt"** —
  resolution failure and `AgentPingError` (ping disabled / not runnable) still propagate.
  A ping that ran is returned as an `AgentPingResult` (ok or not-ok).
- `_prime_target` branches on three outcomes:
  - **exception** (could-not-attempt) → `last_error` + retry (as today).
  - **`not result.ok`** (ran-but-failed) → `last_error` from `result.failure` + retry;
    same retry/error semantics as today, but sourced structurally (and `exit_code` /
    `output` are available if useful).
  - **`result.ok`** (success) → `primed_periods` + success event, **plus** the telemetry
    the result already carries (`model`, `elapsed_ms`) recorded on the success record /
    event payload. Minimal — record existing fields, invent no new measurement.

### Block C: the builder reconnect
- Restore the two commented blocks in `build_monitor_workflows` (`workflows.py:1232-1234`
  collection; `1250-1258` append via `_merge_auto_prime_configs`, which is intact at
  `:1299`). Delete the "TEMPORARILY DISCONNECTED" comments (`No.Legacy.Allowed`).
- The config is already produced by default (`config.py:79-119`: codex / claude-code,
  `burst`/`weekly`), and `LimitsTrackingWorkflow` (the state dependency) is active — so
  restoring the branch genuinely activates pinging.
- Nothing guards the disconnection today: add a builder test.

## Execution.Plan

Two vertical slices, test-first. **Order matters:** reshape the consumer first, then
reconnect — so the workflow that goes live is already the clean, structured-result
version, not reconnect-then-fix.

### Slice 1 — reshape the prime consumer to the structured result
- Changes: `_run_account_prime_ping -> AgentPingResult` (raise only on resolution /
  `AgentPingError`); `_prime_target` consumes the result with the three-way branch
  (Block B); record `model` + `elapsed_ms` on the success path.
- Path: auto-prime scan → `_prime_target` → `_run_account_prime_ping` → `agent.ping()` →
  structured branch. (Driven directly by tests, as the 26 existing auto-prime tests are —
  independent of the builder wiring.)
- Observable result: a successful prime records `primed_periods` **with** `model` /
  `elapsed_ms`; a ran-but-failed ping records `last_error` from `result.failure` (no
  exception round-trip); a could-not-attempt error still records `last_error` + retry.
- Check (RED→GREEN): update the direct `_run_account_prime_ping` tests
  (`test_agent_monitor_auto_prime.py:899/931/967`) to assert it **returns** an
  `AgentPingResult` (ok and not-ok cases) and only raises on resolution/precondition; add
  `_prime_target` behavior tests for the three branches (success telemetry recorded;
  not-ok → `last_error` from failure; exception → `last_error`). RED before the reshape
  (today it returns `None` / raises on failure).

### Slice 2 — reconnect at the loop builder
- Changes: restore the `auto_prime_configs` collection and the `AutoPrimeZeroLimitsWorkflow`
  append branch in `build_monitor_workflows`; remove the disconnection comments.
- Path: `agentos agent accounts monitor` → `build_monitor_workflows(configs)` → the loop
  now includes the auto-prime workflow.
- Observable result: with an auto-prime config present, `build_monitor_workflows` returns
  a tuple that **includes** an `AutoPrimeZeroLimitsWorkflow`; the monitor auto-pings on
  its periodic alarm.
- Check (RED→GREEN): new builder test — `build_monitor_workflows` over configs containing
  an `AUTO_PRIME_ZERO_LIMITS_WORKFLOW` config yields a workflow of that name. RED before
  the branch is restored (it is dropped today).

### Risks / deviation triggers
- **Direct-test churn:** the `_run_account_prime_ping` signature change updates the three
  direct tests — that is intended, not a regression; keep their intent (resolution
  identity, disabled-ping error), adapt the mechanism.
- **Semantics parity:** ran-but-failed and could-not-attempt must both still set
  `last_error` + retry cooldown (no behavior change other than the source of the message
  and the added success telemetry). If a test pins the exact `last_error.message` for a
  ping failure, update it to the `result.failure` text.
- **658 seam:** do not add capture; leave the post-success point clean and commented so
  658 can hook in. Do not delete the 658 reference.
- **Ungated:** do not introduce `profile_check` into the prime path.
- **Scope guard:** no changes to eligibility/period/verification logic, other workflows,
  or the double-resolution.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- `_run_account_prime_ping` returns an `AgentPingResult`; no caller converts a ran-but-
  failed ping into an exception; success records `model` + `elapsed_ms`.
- `build_monitor_workflows` includes the auto-prime workflow when configured (guarded by
  a test); the "TEMPORARILY DISCONNECTED" comments are gone.
- `LimitsTrackingWorkflow` / `AccountRotationWorkflow` behavior unchanged; prime stays
  ungated; 658 seam intact.

## Impl.Log

- Both slices done test-first (RED→GREEN). Suite 243→246 (+2 prime-branch behavior
  tests, +1 builder test; one existing durable-events test updated so its `fake_ping`
  returns an `AgentPingResult` per the new contract). Lint clean. **No deviations.**
- Slice 1: `_run_account_prime_ping` now returns `AgentPingResult` (raises only on
  resolution / `AgentPingError` precondition — no more result→`CliError`→result
  round-trip). `_prime_target` branches three ways; the shared `_record_prime_failure`
  helper serves both the could-not-attempt (exception) and ran-but-failed (`not ok`)
  paths. Success records `ping_model` / `ping_elapsed_ms` (from the result) on both the
  `primed_periods` entry and the `ATTEMPT_SUCCEEDED` event. `workflows.py` now imports
  `AgentPingResult` instead of `AgentPingError`.
- Slice 2: restored the two builder blocks; removed the "TEMPORARILY DISCONNECTED"
  comments. `build_monitor_workflows` now includes the auto-prime workflow when
  configured (guarded by the new builder test).
- Verified: no `profile_check` in the prime path (ungated); the 658 credential-capture
  seam is left clean at the successful-ping point.
