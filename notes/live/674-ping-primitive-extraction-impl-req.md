# 674 — extract the agent-ping primitive (de-leak ping from CLI + monitor)

## Impl.Abstract

- **Scope:** `agent ping` is a real agent operation but has **no primitive**. The
  config is modeled (`AgentPingConfig` on `AgentConfig`), but the *operation*
  — build a non-interactive ping command from `agent.ping`, run it capture-mode,
  validate exit code + expected number in the output — is reimplemented **twice,
  near byte-identically** in two consumers:
  - CLI: `commands.py:_cmd_agent_ping` + `_validate_agent_ping_result` + `_PING_NUMBER_PATTERN` (`commands.py:31`).
  - Monitor prime: `monitor/workflows.py` prime-ping block + `_validate_prime_ping_result` + `_PING_NUMBER_PATTERN` (`workflows.py:84`).
  This is the "important stuff leaking to the CLI" case: ping is a primitive
  masquerading as two consumer-local helper pairs. A secondary smell: the monitor
  copy raises `CliError` deep inside a monitor workflow (CLI error type leaking down).
- **Decision:** introduce one ping primitive — a new module
  `src/agentos/agent/ping.py` exposing `ping_agent(agent, *, cwd) -> AgentPingResult`
  (sibling to the `capture` / `activation` / `materialization` / `rotation` primitive
  modules). It owns: the `enabled`/runnable precondition, the
  `AgentCommandConfig(... interaction_mode="non_interactive")` construction, the
  capture-mode `agent.run`, the elapsed-time measurement, the resolved model, and the
  exit-code + expected-number validation (the `_PING_NUMBER_PATTERN` extraction). It
  returns a structured `AgentPingResult` carrying the outcome — it does **not** raise
  `CliError`. The two consumers become thin: the CLI maps the result to its `pong …`
  line / `CliError`; the monitor maps a failed result to its own raise. One source,
  two consumers, zero duplication.
- **Key decision (surfaced):** run outcomes are returned, not raised. The primitive
  returns `AgentPingResult` with an `ok` flag and a `failure` reason string for run
  outcomes (nonzero exit, missing expected number). Only a true precondition violation
  (ping disabled / agent not `RunCapable`) raises a small domain error
  (`AgentPingError`, defined in `ping.py`). This keeps `CliError` out of the primitive
  **and** out of the monitor's prime path, fixing the leak. Reversible if a consumer
  later needs raise-on-failure.
- **Status:** READY.
- **Source context:** this session's "primitives that run agent commands" audit.
  Verdict: `run`, `account_status`, `account_usage` are coherent primitives; **`ping`
  is the only leak**. House rule in play: *primitives are the source of truth; the
  CLI/monitor are just consumers.*
- **Out of scope (do NOT touch):**
  - `AgentPingConfig` schema / loading (`config.py` `_load_ping_*`) — the config is
    fine; only the *operation* is missing.
  - `agent.run`, `account_status`, `account_usage` — already coherent, untouched.
  - The deferred credential auto-capture on prime (the `# … Impl.Req 658` comment in
    the monitor prime block) — leave behavior and comment as-is.
  - Any change to ping defaults (prompt `"What is 423 + 322? …"`, `expected_number=745`)
    or to the `non_interactive` / `capture` semantics — behavior is preserved exactly.

## Impl.Index

### Block A: ping is duplicated, not a primitive (`Hard.Evidence`)
- `commands.py:31` and `workflows.py:84` define `_PING_NUMBER_PATTERN =
  re.compile(r"(?<![\d.])-?\d+(?![\d.])")` — byte-identical.
- `_validate_agent_ping_result` (`commands.py:261`) and `_validate_prime_ping_result`
  (`workflows.py:2373`) are near-identical: same exit-code check, same
  number-extraction, same `expected_number not in numbers` check, same error strings
  ("agent ping failed: …").
- Both consumers independently build the same `AgentCommandConfig(prompt=ping.prompt,
  argv=ping.argv, model=ping.model, interaction_mode="non_interactive")` and run it
  with `process_mode="capture"`, and both guard on `agent.ping.enabled` with the same
  "ping disabled" `CliError`.
- The config side is already a primitive: `AgentPingConfig`
  (`primitives.py`, fields `enabled/prompt/argv/expected_number/model`). Only the
  operation is missing.

### Block B: the primitive shape
- `ping.py`:
  - `AgentPingError(CliError-free domain error)` — precondition violation (disabled /
    not runnable). Plain `Exception` subclass local to the module.
  - `AgentPingResult` (frozen dataclass): `ok: bool`, `model: str`, `elapsed_ms: int`,
    `exit_code: int`, `output: str`, `failure: str | None`. `failure` is `None` iff
    `ok`. Messages are the operation-level reason (no "agent ping failed:" prefix —
    that framing belongs to the consumer).
  - `ping_agent(agent, *, cwd: Path) -> AgentPingResult`: precondition-guard →
    build command config → time + `agent.run(..., process_mode="capture")` → validate
    → return result. Model resolution mirrors today's `_agent_ping_model`
    (`command_config.model or agent.default_model or "<provider-default>"`). Output
    join mirrors `_agent_ping_output` (stdout+stderr, skip empties).
- Consumers:
  - CLI `_cmd_agent_ping`: call `ping_agent(agent, cwd=cwd)`; on `failure` raise
    `CliError(f"agent ping failed: {result.failure}")`; else print
    `f"pong model={result.model} elapsed_ms={result.elapsed_ms}"`. Catch
    `AgentPingError` → `CliError`.
  - Monitor prime block: call `ping_agent(agent, cwd=Path.cwd().resolve())`; on
    `failure` raise as it does today (keep the upstream `except (CliError, …)` at
    `workflows.py:336` working — wrap `result.failure` / `AgentPingError` in `CliError`
    at the prime call site so the monitor's existing error funnel is unchanged).

## Execution.Plan

Three vertical slices, test-first. First observable endpoint = the primitive itself
exercised by a stub runnable agent (no real subprocess). `No.Regression`: do not add
tests for unchanged config/loading; cover the primitive once, then keep the existing
CLI/monitor boundary tests green.

### Slice 1 — the `ping_agent` primitive (first endpoint)
- Changes: add `src/agentos/agent/ping.py` (`AgentPingError`, `AgentPingResult`,
  `ping_agent`). Move `_PING_NUMBER_PATTERN` + validation logic here as the single home.
- Path: a stub agent whose `run()` returns a canned `AgentRunResult` → `ping_agent`
  → `AgentPingResult`. No subprocess; the stub stands in for `RunCapable`.
- Observable result: `ping_agent` returns `ok=True` with populated
  `model`/`elapsed_ms`/`output` when output contains the expected number; `ok=False`
  with a `failure` reason when the number is missing or exit code is nonzero;
  `AgentPingError` when `agent.ping.enabled` is false or the agent is not `RunCapable`.
- Check (RED→GREEN): new `tests/test_agent_ping.py` written first — cases:
  happy-path ok, expected-number-missing failure, nonzero-exit failure,
  disabled→`AgentPingError`, non-runnable→`AgentPingError`. RED before `ping.py` exists.

### Slice 2 — CLI consumes the primitive
- Changes: rewrite `_cmd_agent_ping` to call `ping_agent`; delete
  `_validate_agent_ping_result`, the CLI `_PING_NUMBER_PATTERN`, and
  `_agent_ping_output`/`_agent_ping_model` (their logic now lives in the primitive).
- Path: `agentos agent ping` → `_cmd_agent_ping` → `ping_agent` → print/`CliError`.
- Observable result: success still prints `pong model=… elapsed_ms=…` and returns 0;
  failure still raises `CliError` with the same user-facing "agent ping failed: …"
  text; `--account`/`--model`/disabled behavior unchanged.
- Check (RED→GREEN): the existing ping CLI tests
  (`tests/test_agent_profiles.py` and any `_cmd_agent_ping` coverage) stay green; if a
  test pins the exact pong/error string, it is the contract — keep it. Add a focused
  test only if no existing test asserts the `pong` line / failure string.

### Slice 3 — monitor prime consumes the primitive
- Changes: rewrite the prime-ping block in `monitor/workflows.py` to call
  `ping_agent`; delete `_validate_prime_ping_result` and the monitor
  `_PING_NUMBER_PATTERN`. Wrap a failed result / `AgentPingError` in `CliError` at the
  prime call site so the existing `except (CliError, …)` funnel (`workflows.py:336`) is
  preserved. Leave the deferred-capture comment intact.
- Path: monitor auto-prime tick → prime block → `ping_agent` → validate → (raise on
  failure).
- Observable result: prime still succeeds on a valid ping and still raises on a bad
  ping / disabled agent, with monitor error handling unchanged.
- Check (RED→GREEN): `tests/test_agent_monitor_auto_prime.py` stays green. No new test
  beyond green unless a behavior gap appears.

### Risks / deviation triggers
- **String-pinned tests:** the consumer-visible `pong …` line and "agent ping failed:"
  prefix are the contract — preserve them exactly. If a test asserts them, that is the
  spec; do not change the wording to suit the refactor.
- **Monitor error funnel:** the monitor catches `CliError` at `workflows.py:336`. If
  the prime path stops raising `CliError`, that funnel breaks — keep wrapping at the
  call site. Reshaping the monitor's error handling is out of scope; if the refactor
  forces it, stop and surface.
- **`cwd` source:** CLI passes its resolved `cwd`; monitor passes
  `Path.cwd().resolve()`. Keep both — `ping_agent` takes `cwd` as a required keyword,
  it does not invent its own.
- **Scope guard:** do not touch `AgentPingConfig`, the config loader, `agent.run`,
  account_status, or usage. A change that reshapes those aborts the slice.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- `_PING_NUMBER_PATTERN`, `_validate_agent_ping_result`, `_validate_prime_ping_result`
  no longer exist anywhere; the validation logic exists once, in `ping.py`.
- `CliError` no longer appears in the ping operation itself — it is raised only by the
  consumers (CLI, and the monitor's call-site wrapper).
- `agentos agent ping` output and failure text unchanged; monitor auto-prime behavior
  unchanged.

## Impl.Log

- (pending execution)
