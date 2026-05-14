# Minimal Active Account Usage Capability - impl-req

## Impl.Abstract

- **scope:** implement the first active `account_status(...)` provider-agent capability for registered-account-bound Agentos agents, using the design captured in `594-minimal-active-account-usage-capability-design-session.md`.
- **status:** implemented.
- **source:** `notes/live/594-minimal-active-account-usage-capability-design-session.md`.
- **goal:** provide a minimal typed account-status model and Codex-first provider capability that the account monitor can later consume for limits tracking, without restoring the deprecated `agent accounts stats` command as a whole.

## Impl.Index

### Account.Context.Model

- Add `AgentAccountContext(provider, account)` as registered account identity on the agent object.
- Extend `AgentConfig`, `AgentBase`, and the `Agent` protocol with `account: AgentAccountContext | None = None`.
- Preserve the invariant from the design session:

```txt
agent.account = registered account identity
agent.home = provider execution context
```

- Do not add `account_home`; a home is an execution context that may be linked to an account, not account-owned state.
- Do not introduce `AccountStatusRequest`; fetch controls are keyword arguments on `agent.account_status(...)`.

### Account.Status.Model

- Add typed public account-status dataclasses for the provider-agent capability boundary.
- Keep provider raw data available in `raw: dict[str, object]`.
- Use this initial status vocabulary:

```txt
check_status = ok | error
usage_status = ok | error | unavailable
identity_match = verified | mismatched | unknown | unavailable
```

- `errors` are setup/auth/check-level problems.
- `usage_errors` are usage/limits fetch problems.
- Preserve partial-success semantics: auth/identity can be valid while usage refresh fails.

Required model shape:

```txt
AccountStatus
  provider
  account
  home
  check_status
  usage_status
  link_state
  expected_identity
  fetched_identity
  identity_match
  auth_summary
  usage_summary
  limits
  errors
  usage_errors
  raw
```

Required limit model:

```txt
AccountLimit
  limit_class
  limit_name
  limit_label
  usage_over_time
  provider_limit

UsageOverTimeLimitData
  used_percent
  period_started_at
  period_ends_at
  period_duration_mins
  resets_at
```

### Registered.Account.Agent.Builder

- Add a reusable builder for account-bound provider agents:

```python
build_registered_account_agent(
    *,
    provider: str,
    account: str,
    home: Path | str,
    start_path: Path | str = ".",
) -> Agent
```

- The builder must:
  - validate the registered account through `load_account(provider, account)`;
  - reuse existing provider config resolution and home override behavior;
  - attach `AgentAccountContext(provider, account)` to the resulting agent config;
  - construct the provider agent through existing `agent_from_config(...)`.
- The builder must not bootstrap, link, copy, repair, or mutate homes.
- The default monitor home remains outside this builder: `~/.agentos/agent/homes/<provider>/<account>`.

### Setup.Validation.Reuse

- Reuse existing registry and provider-home inspection machinery.
- Do not duplicate account registration, artifact matching, link registry, or home-auth inspection logic.
- Required validation layers:

```txt
setup validation:
  agent has account
  agent has home
  registry account exists
  home link state is inspected when provider machinery exists

fetched status validation:
  provider status fetch runs
  fetched provider identity is compared with registry identity when possible
  mismatches become AccountStatus.errors entries
```

- Codex must use `inspect_codex_account_home(home=...)` for home/link/auth inspection.
- Claude claimed-home inspection should be extracted from CLI-only code into reusable account-registry/provider machinery only when implementing Claude account status. Do not block the Codex slice on Claude extraction.

### Codex.Account.Status

- Implement `CodexAgent.account_status(...)` first.
- Use current Agentos process utility for one-shot Codex auth status commands.
- Keep Codex `app-server` JSON-RPC provider-owned; do not force it through `_core.process`.
- Reuse parsing ideas from `_DEPRECATED/agent-accounts-stats`, but introduce active code deliberately.
- When `refresh_usage=False`, return auth/check status with `usage_status="unavailable"`.
- When `refresh_usage=True`, fetch and parse Codex rate limits into `AccountLimit` objects.
- Compare fetched/inspected Codex identity against the registered account record's `account_id`.
- Identity mismatch must be represented as an `AccountStatus.errors` entry, not as a monitor-crashing exception.

### Monitor.Integration.Readiness

- Do not wire `LimitsTrackingWorkflow` in the first implementation unless all account-status slices are already green.
- The first implementation should make monitor wiring straightforward by exposing:
  - `build_registered_account_agent(...)`;
  - `agent.account_status(refresh_usage=True)`;
  - serializable account-status objects.
- Monitor-specific rendering and throttling remain a follow-up Impl.Req unless explicitly requested in the same execution.

## Execution.Plan

### Slice 1 — Add account context and status model

- Add active account-status model definitions in a provider-neutral module, preferably `src/agentos/agent/account_status.py`.
- Add `AgentAccountContext` to `AgentConfig`, `AgentBase`, and the `Agent` protocol.
- Add `account_status(...)` to `AgentBase` and the `Agent` protocol with keyword-only fetch controls.
- Update config-to-agent kwargs so account context flows through provider agents.
- Observable: provider agents can carry `agent.account`, and model objects can be serialized for tests.
- Check: focused unit tests for dataclass summaries/serialization and account context propagation.
- status: implemented

### Slice 2 — Add registered-account agent builder

- Implement `build_registered_account_agent(...)` using existing `load_account(...)`, provider config resolution, home override behavior, account-context attachment, and `agent_from_config(...)`.
- Add tests proving:
  - unregistered accounts fail through existing registry error behavior;
  - the returned agent has the requested `AgentAccountContext`;
  - the returned agent has the requested resolved home;
  - no home directories or links are created by the builder.
- Observable: monitor-like code can build an account-bound provider agent from provider/account/home.
- Check: focused tests in the existing agent account registry command test area or a new focused provider-agent test file.
- status: implemented

### Slice 3 — Implement Codex auth/check account status

- Implement `CodexAgent.account_status(refresh_usage=False, ...)`.
- Reuse `inspect_codex_account_home(home=...)` for link/auth inspection.
- Use `run_process(..., mode="capture")` through active account-status helper code for `codex login status`.
- Build `AccountStatus` with:
  - provider/account/home;
  - link state from Codex home inspection;
  - expected identity from `load_account("codex", account)`;
  - fetched identity from inspected auth and/or provider auth status;
  - `usage_status="unavailable"`;
  - raw provider/home inspection payloads.
- Add identity mismatch coverage.
- Observable: Codex account status can validate a registered account/home without fetching rate limits.
- Check: tests with fake Codex auth registry/home data and monkeypatched command execution.
- status: implemented

### Slice 4 — Implement Codex limits refresh

- Implement `CodexAgent.account_status(refresh_usage=True, ...)` limits refresh.
- Port only the minimal active Codex `app-server` JSON-RPC and rate-limit parsing needed to populate `AccountLimit`.
- Preserve partial-success behavior: if limits fetch fails after auth/check succeeds, return `check_status="ok"` and `usage_status="error"` with `usage_errors`.
- Add tests for:
  - parsed primary/secondary windows;
  - usage unavailable when refresh is false;
  - usage error when app-server returns an error or invalid output.
- Observable: Codex account status returns normalized `AccountLimit` values.
- Check: focused Codex tests plus affected agent/account tests.
- status: implemented

### Slice 5 — CLI/JSON diagnostic surface

- Add a minimal diagnostic path only if needed for verification, for example `agent accounts status --provider codex --home ... --account ... --json` or a direct test-only serialization helper.
- Prefer not adding a new user-facing command unless implementation/testing needs it.
- If CLI changes are made, refresh installed CLI with `uv tool install --reinstall --editable .`.
- Observable: account-status objects can be inspected as JSON without relying on deprecated stats command behavior.
- Check: focused CLI test if CLI is changed; otherwise serialization unit tests are enough.
- status: skipped; no CLI change was needed because account-status serialization is covered directly by model tests.

### Slice 6 — Verification and artifact update

- Run focused tests for the touched account/provider surfaces.
- Run broader tests that cover existing account registry and provider agent behavior.
- Run `uv run ruff check` on changed source/tests.
- Update this Impl.Req's `Impl.Abstract` and `Impl.Log` with implementation results, deviations, and remaining follow-up.
- Observable: implementation state is documented and verification commands are recorded.
- Check: command outputs and final diff review.
- status: implemented

## Deviation.Triggers

- Stop if provider config resolution through existing machinery forces monitor targets to select `agent.instances` by id. The design requires registered-account-first targets.
- Stop if Codex home validation cannot reuse `inspect_codex_account_home(...)` without duplicating registry/artifact logic.
- Stop if rate-limit fetch requires broad changes to `_core.process`; specialized Codex JSON-RPC should stay provider-owned.
- Stop if a proposed implementation bootstraps, mutates, links, copies, or repairs homes as part of `account_status(...)` or `build_registered_account_agent(...)`.
- Stop if the model cannot represent partial success without throwing away useful auth/check data.

## Acceptance.Signals

- `AgentConfig`, `AgentBase`, and `Agent` carry `AgentAccountContext | None`.
- Provider agents expose `account_status(...)` with keyword-only fetch controls and no `AccountStatusRequest`.
- `build_registered_account_agent(...)` builds an account-bound provider agent from registered account + home and does not mutate setup.
- Codex account status returns typed `AccountStatus`.
- Codex identity mismatch is detected against the registered account record and represented as an account-status error.
- `refresh_usage=False` returns usage unavailable without attempting limits refresh.
- `refresh_usage=True` returns normalized `AccountLimit` values for successful Codex rate-limit payloads.
- Limits fetch failures produce `usage_status="error"` and `usage_errors` while preserving successful auth/check data.
- No deprecated `agent accounts stats` command is restored.
- Existing account registry behavior remains intact.
- Focused tests and lint pass.

## Out.Of.Scope

- No full monitor `LimitsTrackingWorkflow` wiring in this Impl.Req unless explicitly approved during execution.
- No TUI rendering changes.
- No historical usage aggregation.
- No account stats tape/history persistence.
- No Copilot implementation in the first slice.
- No Claude live usage implementation in the first slice unless explicitly approved after Codex is green.
- No automatic home setup, bootstrap, linking, copying, or repair.
- No compatibility alias named `account_stats(...)`.

## Impl.Log

- 2026-05-14: Created from design-session `594` after implementation execution was requested but the source artifact was not an Impl.Req. The plan resolves the remaining implementation-shaping questions into a Codex-first, typed-model execution path.
- 2026-05-14: Implemented `AgentAccountContext`, typed account-status/limit/error models, `Agent.account_status(...)` protocol/base capability, `build_registered_account_agent(...)`, and Codex `account_status(...)` with auth/check and limits refresh support.
- 2026-05-14: Added focused tests in `tests/test_agent_account_registry_commands.py` for model serialization, registered-account agent construction without home mutation, Codex auth/check status, identity mismatch, parsed rate limits, and partial success when usage refresh fails.
- 2026-05-14: Verification passed: `uv run pytest tests/test_agent_account_registry_commands.py -q` (`33 passed`), `uv run pytest tests/test_agent_commands.py tests/test_agent_account_registry_commands.py -q` (`67 passed`), scoped `uv run ruff check ...` on touched agent/codex/test surfaces, and full `uv run pytest -q` (`295 passed`).
- 2026-05-14: Full-repo `uv run ruff check src tests` was attempted but failed on pre-existing unrelated lint issues outside the touched account-status surfaces.
