# Profile Resolved Provider Runtime - impl-req

## Impl.Abstract

- **scope:** make every Agentos subsystem that runs a provider command construct its agent through profile resolution, so profile `cli_command`, `env`, `run_args`, `ping`, account scope, home scope, and runtime policy stay together
- **status:** proposed
- **source:** 2026-06-18 incident: `agentos agent accounts monitor` ran Claude statusline refresh for `claude-code/browser-br` and `browser-jp` through an unprofiled registered-account agent, dropping profile-declared `DISABLE_AUTOUPDATER=1` and `DISABLE_UPDATES=1`; user directive: "every Agentos subsystem that runs a provider command must run through profile resolution"
- **owning project:** `agentos-py`
- **primary paths:** `src/agentos/agent/providers.py`, `src/agentos/agent/profile_scope.py`, `src/agentos/agent/monitor/config.py`, `src/agentos/agent/monitor/workflows.py`, `src/agentos/claude/account_reconcile.py`, `src/agentos/codex/account_reconcile.py`, `tests/test_agent_profiles.py`, `tests/test_agent_monitor_auto_prime.py`, `tests/test_claude_account_reconcile.py`, `tests/test_codex_account_reconcile.py`, `tests/test_claude_account_status.py`
- **related surfaces:** `notes/live/613-provider-cli-command-authority-impl-req.md`, `notes/live/636-claude-reconcile-verification-impl-req.md`, `notes/live/648-agent-harness-injected-env-allowlist-impl-req.md`, `notes/live/649-agent-harness-env-contract-cleanup-impl-req.md`, `agentos-md/skills/tarav-agent-account-management/SKILL.md`

## Impl.Index

### Runtime.Profile.Authority

Provider-command runtime authority is the resolved profile, not only `{provider, account, home}`.

Hard.Evidence:

- `src/agentos/agent/providers.py::resolve_agent(...)` loads a profile, validates provider, applies home override through `select_allowed_home(...)`, then adapts the resulting `AgentConfig`.
- `src/agentos/agent/primitives.py::RunnableMixin._check_account_scope(...)` validates explicit account overrides against profile accounts.
- `src/agentos/claude/agent.py::_run_env_overrides(...)` starts from `dict(self.env)` and adds `CLAUDE_CONFIG_DIR`.
- `src/agentos/codex/agent.py::_run_env_overrides(...)` starts from `dict(self.env)` and adds `CODEX_HOME`.
- Local Claude profiles currently declare important runtime policy under profile `env`, including `DISABLE_AUTOUPDATER=1` and `DISABLE_UPDATES=1`.
- `notes/live/648-agent-harness-injected-env-allowlist-impl-req.md` established that run-affecting policy env is `Config.Injected.ENV`, not hidden harness env.

Implementation direction:

- Treat profile resolution as the mandatory entry point for provider-command execution.
- A runtime agent may still carry an account context from the account registry, but that account context must be attached to a profile-resolved `AgentConfig`.
- The profile must validate or infer the intended home and account before any provider process starts.
- Do not repair this incident by extending Claude statusline parent-env allowlists; that hides the dropped-profile bug.

### Registered.Account.Agent.Drift

`build_registered_account_agent(...)` is currently unsafe as a provider-command runtime constructor.

Hard.Evidence:

- `src/agentos/agent/providers.py::build_registered_account_agent(...)` loads a registered account, builds a provider default config, applies provider-level config, overrides home, and attaches `AgentAccountContext`.
- The same function does not load or infer any profile, so `profile_id` is `None` and `env` is empty for monitor Claude targets that have configured profiles.
- Live reconstruction from installed `agentos` showed:
  - `browser-jp target profile: claude-jp`, but registered agent `profile_id: None`, `env: {}`
  - `browser-br target profile: claude-br`, but registered agent `profile_id: None`, `env: {}`
- `src/agentos/agent/monitor/workflows.py::LimitsTrackingWorkflow._refresh_target(...)` calls `build_registered_account_agent(...)` and then `agent.account_status()`.
- `src/agentos/agent/monitor/workflows.py::_run_account_prime_ping(...)` calls `build_registered_account_agent(...)` and then `agent.run(...)`.
- `src/agentos/claude/account_reconcile.py::_run_reconcile_ping(...)` and `src/agentos/codex/account_reconcile.py::_run_reconcile_ping(...)` use the same unprofiled constructor before running live ping commands.

Implementation direction:

- Keep a low-level helper only for non-running registry mechanics if still needed.
- Introduce a separate runtime resolver whose name makes the policy explicit, for example `resolve_account_runtime_agent(...)`.
- Replace provider-command call sites with the runtime resolver.
- Make unprofiled runtime execution fail loudly unless the caller explicitly opts into a diagnostic or low-level non-profile mode.

### Account.Runtime.Resolver

A single helper should own account + profile + home runtime resolution.

Proposed API:

```python
def resolve_account_runtime_agent(
    *,
    provider: str,
    account: str,
    home: Path | str,
    profile: str | None,
    start_path: Path | str = ".",
) -> AgentConfig:
    ...
```

Required behavior:

- Load the registered account and build `AgentAccountContext(provider, account)`.
- If `profile` is provided:
  - call `resolve_agent_config(provider=provider, profile=profile, home=home, start_path=start_path)`;
  - validate the requested account is allowed by the resolved profile accounts;
  - attach the requested account context with `dataclasses.replace(...)`;
  - return `agent_from_config(...)`.
- If `profile` is not provided:
  - inspect configured profiles from `load_agent_configs(start_path=start_path)`;
  - find profiles whose provider matches, whose homes contain the normalized home, and whose accounts contain the requested account;
  - if exactly one profile matches, use it;
  - if none match, fail with an actionable `CliError` explaining that provider-command runtime requires a profile or a unique profile match;
  - if more than one matches, fail with an ambiguity error that names the matching profile ids.
- The helper must preserve profile `env`, `cli_command`, `run_args`, `default_model`, `ping`, `account_policy`, `timeout_sec`, `homes`, and provider config inheritance.
- The helper should live in `src/agentos/agent/providers.py` unless that creates import pressure; if so, use a small adjacent module such as `agentos.agent.runtime_resolution`.

Rejected alternatives:

- Do not infer runtime policy from `agent.providers.<provider>` alone.
- Do not construct a default provider agent and then copy selected fields from profiles.
- Do not use shell environment as a fallback for missing profile env.
- Do not keep `build_registered_account_agent(...)` as the visible runtime entry point for provider commands.

### Monitor.Runtime.Profile

Monitor config already models profile scope, but the runtime path discards it.

Hard.Evidence:

- `src/agentos/agent/monitor/models.py::MonitorTarget` has `profile: str | None`.
- `src/agentos/agent/monitor/config.py::_validate_profile_target(...)` validates that `target.profile` uses the requested provider, allows the target account, and allows the target home.
- `src/agentos/agent/monitor/workflows.py::_new_target_state(...)` stores provider/account/home but not profile.
- `LimitsTrackingWorkflow._refresh_target(...)` ignores `target.profile` and calls the unprofiled registered-account constructor.
- Auto-prime derives source target state from limits-tracking state; because profile is not stored, `_run_account_prime_ping(...)` cannot use it.

Implementation direction:

- Store `profile` in monitor target state.
- In limits-tracking refresh, use `resolve_account_runtime_agent(...)` with `target.profile`.
- In auto-prime ping, use the same resolver with the profile carried in source target state.
- Preserve monitor setup validation, but add runtime tests proving profile-resolved config reaches `account_status()` and `run()`; provider home env remains harness-derived from selected `home`.
- Prefer adding profile to target state summaries so monitor JSON exposes which profile was used.

### Reconcile.Ping.Profile

Reconcile ping is a provider-command runtime path and must not run through unprofiled homes.

Hard.Evidence:

- Claude and Codex `_KnownHome` records currently store `home`, `source`, `account`, and `system_managed`, but not `profile`.
- `_configured_homes(...)` in both providers iterates `load_agent_configs(start_path=...)`, so it has access to `config.profile_id`.
- `_run_reconcile_ping(...)` receives only `account`, `home`, and `start_path`, then builds an unprofiled registered-account agent and calls `agent.run(...)`.
- Reconcile ping records verification evidence after a successful real provider call, so wrong runtime policy can corrupt the verification story.

Implementation direction:

- Add `profile: str | None` to each provider `_KnownHome`.
- Populate `profile=config.profile_id` for homes discovered from configured profiles.
- Preserve `profile` when merging duplicate known homes. If two configured profiles for the same provider/account/home disagree, keep the ambiguity visible rather than silently choosing one.
- Pass `known_home.profile` into `_run_reconcile_ping(...)`.
- If no profile exists for a ping candidate and no unique profile can be inferred, report a verification warning/action and skip the provider command rather than running unprofiled.
- Keep passive reconcile non-networking; this change only affects `ping=True` live verification.

### Provider.Internal.Subprocess.Audit

Profile-resolved callers are necessary but not sufficient if provider-owned subprocesses bypass profile env or command construction.

Hard.Evidence:

- Codex account status app-server uses `_build_codex_account_status_command(agent, ...)` and then `subprocess.Popen(...)` with the command env.
- Claude statusline account status uses `agent._build_command(...)` and `_claude_statusline_process_environment(command.env_overrides)`.
- Copilot account status reads a GitHub token via `run_process(("gh", "auth", "token"), env_overrides=dict(agent.env), ...)`.
- Claude account registry uses macOS `security` commands for Keychain reads/writes; these are OS credential-storage commands, not provider runtime commands.

Implementation direction:

- Audit all active `agent.run(...)`, `agent.account_status(...)`, `execute_agent_command(...)`, `run_process(...)`, and direct `subprocess` call sites under `src/agentos`.
- For provider runtime commands, ensure they start from a profile-resolved agent and use that agent's config/env.
- Provider-owned OS helpers such as macOS `security` may remain outside profile command resolution, but this distinction must be explicit in code review.
- If a provider status helper needs a provider-adjacent CLI such as `gh`, either ensure its behavior is profile-configurable or document why it is not part of the provider command contract.

## Execution.Plan

### Slice 1 - Add Runtime Resolver Contract

- Add `resolve_account_runtime_agent(...)` and supporting profile inference helpers.
- Reuse `resolve_agent_config(...)`, `select_allowed_home(...)`, and `validate_account_override(...)`.
- Attach the requested `AgentAccountContext` to the resolved profile config.
- Keep or rename `build_registered_account_agent(...)` only as a low-level non-runtime helper; mark it unsuitable for provider command execution in code comments and tests.
- Add focused tests in `tests/test_agent_profiles.py`.

Observable result:

- A profile-resolved runtime agent for `claude-code/browser-br` keeps profile `env`, profile `cli_command`, profile `run_args`, and account context.
- A runtime request with no explicit profile can use exactly one matching configured profile.
- A runtime request with no match or multiple matches fails before any provider command can run.

RED.GREEN.Test.Suite:

```bash
uv run pytest tests/test_agent_profiles.py -q
```

Target test additions:

- `resolve_account_runtime_agent(... profile="claude-br" ...)` preserves `DISABLE_AUTOUPDATER` and `DISABLE_UPDATES`.
- requested account outside profile accounts raises `CliError`.
- requested home outside profile homes raises `CliError`.
- omitted profile with exactly one provider/account/home match infers that profile.
- omitted profile with no match or multiple matches raises `CliError`.

### Slice 2 - Make Monitor Usage Refresh Profile-Resolved

- Replace `build_registered_account_agent(...)` in `LimitsTrackingWorkflow._refresh_target(...)`.
- Pass `target.profile`, `target.account`, `target.provider`, `target.home`, and monitor `start_path` or equivalent config context into the runtime resolver.
- If monitor workflows currently do not retain `start_path`, add it to `MonitorWorkflowConfig` or workflow construction state rather than falling back to `Path.cwd()` accidentally.
- Store `profile` in `_new_target_state(...)`, target summaries, and JSON output.
- Add tests that mock the resolver or fake agent and assert monitor refresh receives profile-derived env/account context.

Observable result:

- A monitor target with `profile: claude-br` calls `account_status()` on an agent whose env includes the profile env keys.
- The statusline last-run log for Claude can show `DISABLE_AUTOUPDATER` and `DISABLE_UPDATES` because the env came through profile config, not parent shell inheritance.

RED.GREEN.Test.Suite:

```bash
uv run pytest tests/test_agent_monitor_auto_prime.py tests/test_claude_account_status.py -q
```

Target test additions:

- limits-tracking with a profiled Claude target preserves profile env into the fake `account_status()` agent.
- monitor config with profiled targets still rejects unscoped account/home as before.
- monitor JSON target state includes `profile` when configured.

### Slice 3 - Make Monitor Auto-Prime Profile-Resolved

- Carry `profile` from limits-tracking target state into auto-prime source target state.
- Replace `build_registered_account_agent(...)` in `_run_account_prime_ping(...)`.
- Ensure ping uses profile `ping`, `env`, command, model, timeout, and account scope.
- If a source target lacks profile and no unique profile can be inferred, record an auto-prime failure/skip with a clear error rather than running a provider command.

Observable result:

- Auto-prime ping for a profiled target runs with the same runtime profile as limits tracking.
- Auto-prime verification events remain accurate because the provider command ran under the intended profile.

RED.GREEN.Test.Suite:

```bash
uv run pytest tests/test_agent_monitor_auto_prime.py -q
```

Target test additions:

- `_run_account_prime_ping(...)` receives source target state with `profile` and resolves a profile runtime agent.
- fake profile `ping.model` / `ping.prompt` is honored.
- successful Claude/Codex auto-prime still records verification source `monitor.auto_prime`.

### Slice 4 - Make Reconcile Ping Profile-Resolved

- Add `profile` to Claude and Codex `_KnownHome`.
- Populate it in `_configured_homes(...)`.
- Preserve it through `_add_known_home(...)` merges; ambiguous configured profiles for one provider/account/home should produce a warning/action or fail before ping.
- Change `_run_reconcile_ping(...)` signatures to accept `profile`.
- Use `resolve_account_runtime_agent(...)`.
- In `check=True`, continue reporting `would_ping` without constructing or running live agents.

Observable result:

- `reconcile_*_accounts(..., ping=True)` runs live pings only through the originating configured profile or a unique inferred profile.
- Passive reconcile behavior remains non-networking.

RED.GREEN.Test.Suite:

```bash
uv run pytest tests/test_claude_account_reconcile.py tests/test_codex_account_reconcile.py -q
```

Target test additions:

- configured Claude/Codex home ping preserves profile config and uses harness-derived provider home env.
- configured profile ping preserves profile-specific `ping` settings.
- `--check --ping` still does not build a live agent.
- no-profile/no-unique-profile ping candidate is skipped or fails with a clear safe diagnostic, not an unprofiled provider run.

### Slice 5 - Audit Remaining Provider Command Paths

- Search active code for:

```bash
rg -n "build_registered_account_agent|agent\\.run\\(|agent\\.account_status\\(|execute_agent_command\\(|run_process\\(|subprocess\\." src/agentos agentos-chatlas-py/src/agentos_chatlas
```

- Classify each result:
  - profile-resolved runtime path;
  - provider-owned subprocess using a profile-resolved agent;
  - OS helper outside provider runtime, such as macOS Keychain `security`;
  - unrelated infrastructure.
- Update any provider runtime command that still bypasses profile resolution or profile env.
- Add a focused test or note for any intentionally exempt OS helper.

Observable result:

- No active provider command path runs through `build_registered_account_agent(...)`.
- Cross-package runtime callers such as Chatlas commit staging continue using `resolve_agent(...)`.
- Provider internal subprocesses either use the profile-resolved agent env/command path or have a documented exemption.

Validation:

```bash
rg -n "build_registered_account_agent" src/agentos tests
uv run pytest tests/test_agent_profiles.py tests/test_agent_monitor_auto_prime.py tests/test_claude_account_reconcile.py tests/test_codex_account_reconcile.py tests/test_claude_account_status.py -q
uv run ruff check src/agentos/agent src/agentos/claude src/agentos/codex tests/test_agent_profiles.py tests/test_agent_monitor_auto_prime.py tests/test_claude_account_reconcile.py tests/test_codex_account_reconcile.py tests/test_claude_account_status.py
```

### Slice 6 - Installed CLI Smoke

- Refresh installed CLI after implementation:

```bash
uv tool install --reinstall --editable .
```

- Run monitor long enough to force live refresh:

```bash
agentos agent accounts monitor --max-ticks 8 --interval-sec 10 --json
```

- Inspect:

```bash
~/.agentos/logs/claude-statusline-last-run.json
```

Observable result:

- Claude statusline log env includes profile-declared update-block env when the target profile declares them.
- Monitor no longer constructs Claude/Codex runtime agents with `profile_id=None` for configured profiled targets.
- Any remaining `browser-br` fallback is attributable to actual credential failure, not dropped profile runtime policy.

Validation:

```bash
agentos agent accounts monitor --max-ticks 8 --interval-sec 10 --json
```

## Risks And Deviation Triggers

- If monitor has targets without explicit `profile` and no unique configured profile can be inferred, fail loudly or surface a skipped-target error. Do not run a provider command through an unprofiled default.
- If adding `start_path` to monitor workflow state becomes invasive, stop and choose the smallest explicit config-context carrier. Do not use process cwd as hidden authority.
- If `build_registered_account_agent(...)` remains necessary for passive file/registry inspection, keep it private or clearly documented as non-runtime. Do not use it before `agent.run(...)`, `agent.account_status(...)`, or provider subprocess launch.
- If tests need local `~/.agentos` mutation, stop. Use `AgentosTestEnvironment` fixtures.
- If provider-internal subprocesses require separate command configuration, create a follow-up only after this invariant is enforced at the agent runtime boundary.
- If an implementation tries to solve the Claude incident by adding `DISABLE_UPDATES` to a parent env allowlist, reject it. The root fix is profile-resolved runtime construction.

## Acceptance.Signals

- Every active code path that calls `agent.run(...)` or `agent.account_status(...)` uses a profile-resolved agent.
- Monitor limits tracking preserves target profile config and policy env.
- Monitor auto-prime preserves target profile config, harness-derived provider home env, and ping settings.
- Claude and Codex reconcile `--ping` preserve configured profile policy env, harness-derived provider home env, and ping settings.
- No provider command path uses unprofiled `build_registered_account_agent(...)`.
- Runtime without an explicit or uniquely inferred profile fails before provider command execution.
- Claude statusline env contains profile-declared `DISABLE_AUTOUPDATER` and `DISABLE_UPDATES` when run for local Claude profiles that declare those values.
- Focused tests and scoped ruff pass; full tests pass or any unrelated blocker is recorded.

## Impl.Log

- 2026-06-18: Created after diagnosing monitor/statusline profile drift. Current code validates monitor target profiles but discards them at runtime through `build_registered_account_agent(...)`, causing profile env such as Claude update-block variables to be dropped. This request realigns monitor, auto-prime, and reconcile ping with the profile/env contract established in prior Agentos runtime notes.
- 2026-06-18: Implemented `resolve_account_runtime_agent(...)` as the account-bound runtime constructor. It requires an explicit profile or exactly one configured provider/account/home profile match, validates account scope, and injects the registered account context after profile resolution.
- 2026-06-18: Replaced monitor limits refresh, monitor auto-prime ping, and Claude/Codex reconcile ping runtime construction with profile-resolved construction. Reconcile uses lazy resolver wrappers to avoid provider/account-status import cycles.
- 2026-06-18: Removed the old `build_registered_account_agent(...)` provider helper and added a CLI guard so `agent run`/`agent ping` reject `--provider --home` default runtime without `--profile`.
- 2026-06-18: Validation passed for focused profile/monitor/reconcile/run-preflight suites and `rg build_registered_account_agent` found no remaining references. Installed CLI refresh succeeds from `agentos-cli`; direct tool install from `agentos-py` fails because that package no longer provides the executable.
- 2026-06-18: Installed CLI monitor smoke proves the invariant is active. Claude monitor targets carry `claude-jp`/`claude-br` profiles and remain ok. Codex live refresh now fails loudly because global monitor targets default to `~/.agentos/agent/homes/codex/*`, while configured Codex profiles are scoped to `~/.codex-*`; this is an operational config repair, not a code fallback to reintroduce unprofiled runtime.
