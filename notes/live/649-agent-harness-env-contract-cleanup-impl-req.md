# Agent Harness ENV Contract Cleanup - impl-req

## Impl.Abstract

- **scope:** centralize the `Harness.Injected.ENV` allowlist and provider harness env key names in production code, then point tests and adapters at that single contract
- **status:** implemented
- **source:** cleanup pass after `648-agent-harness-injected-env-allowlist-impl-req.md`; current code has the allowlist only in `tests/test_agent_profiles.py` while provider adapters define related env key constants locally
- **owning project:** `agentos-py`
- **primary paths:** `src/agentos/agent/run_runtime.py`, `src/agentos/claude/agent.py`, `src/agentos/codex/agent.py`, `src/agentos/copilot/agent.py`, `tests/test_agent_profiles.py`
- **mode:** cleanup; stay narrow, no new frameworks, no compatibility layer, prefer replacing repeated knowledge with a small existing-module contract

## Impl.Index

### Cleanup.Target

- repeated knowledge exists between the test-only `HARNESS_INJECTED_ENV_ALLOWLIST` and provider adapter env constants
- the allowlist is a runtime command construction contract, not just test data
- production code should own the provider-scoped harness env key names
- tests should verify the production contract rather than redefining it
- the cleanup should not change command behavior

Hard.Evidence:

- `tests/test_agent_profiles.py` defines `HARNESS_INJECTED_ENV_ALLOWLIST`.
- `src/agentos/codex/agent.py` defines `CODEX_HOME_ENV_VAR`.
- `src/agentos/claude/agent.py` defines `CLAUDE_CONFIG_DIR_ENV_VAR` and uses literal `CLAUDE_CODE_OAUTH_TOKEN`.
- `src/agentos/copilot/agent.py` defines `COPILOT_HOME_ENV_VAR`.
- `src/agentos/agent/run_runtime.py` already owns command/env construction primitives.

### Contract.Shape

- put the shared contract near command runtime code, preferably in `src/agentos/agent/run_runtime.py`
- expose named constants for harness env keys that adapters use
- expose `HARNESS_INJECTED_ENV_ALLOWLIST` as a provider-scoped mapping
- adapters should import the relevant constants instead of redefining string literals
- tests should import the allowlist and constants from production
- keep config-injected env behavior unchanged
- keep managed Claude credential redaction behavior unchanged

### Out.Of.Scope

- no schema changes
- no CLI changes
- no new provider behavior
- no broad env-injection abstraction
- no compatibility alias for old module-local constants unless still needed internally during the edit

## Execution.Plan

### Slice 1 - Move Harness ENV Names Into Runtime Contract

- Add production constants to `src/agentos/agent/run_runtime.py`:
  - `CODEX_HOME_ENV_VAR`
  - `CLAUDE_CONFIG_DIR_ENV_VAR`
  - `CLAUDE_CODE_OAUTH_TOKEN_ENV_VAR`
  - `COPILOT_HOME_ENV_VAR`
  - `HARNESS_INJECTED_ENV_ALLOWLIST`
- Export the constants through `__all__`.
- Update `tests/test_agent_profiles.py` to import the production allowlist instead of declaring its own.

Observable result:

- tests fail before adapter imports are updated only if stale local definitions diverge; after the slice, tests use the production contract.

RED.GREEN.Test.Suite:

```bash
uv run pytest tests/test_agent_profiles.py -q
```

### Slice 2 - Point Provider Adapters At The Runtime Contract

- Remove local env-name constants from Codex, Claude, and Copilot adapters.
- Import the relevant constants from `agentos.agent.run_runtime`.
- Replace Claude literal `CLAUDE_CODE_OAUTH_TOKEN` uses with `CLAUDE_CODE_OAUTH_TOKEN_ENV_VAR`.
- Keep `_run_env_overrides()` behavior unchanged.

Observable result:

- provider command env output remains identical, but env key ownership is centralized.

Validation:

```bash
uv run pytest tests/test_agent_profiles.py tests/test_claude_account_status.py tests/test_agent_run_account_preflight.py -q
uv run ruff check src/agentos/agent/run_runtime.py src/agentos/claude/agent.py src/agentos/codex/agent.py src/agentos/copilot/agent.py tests/test_agent_profiles.py
```

### Slice 3 - Cleanup Verification

- Search for duplicate local harness env constants and hardcoded Claude OAuth env strings.
- Confirm no behavior change in relevant dry-run tests.

Validation:

```bash
rg -n "CODEX_HOME_ENV_VAR|CLAUDE_CONFIG_DIR_ENV_VAR|COPILOT_HOME_ENV_VAR|CLAUDE_CODE_OAUTH_TOKEN" src/agentos tests
uv run pytest -q
```

## Risks And Deviation Triggers

- If moving constants into `run_runtime.py` creates an import cycle, stop and move the contract into a small `agentos.agent.env_injection` module instead; record the deviation in `Impl.Log`.
- If tests reveal command output changes, revert the behavior change and keep only ownership cleanup.
- If cleanup starts expanding into command-build API changes, abort and request a new design scope.

## Acceptance.Signals

- production code owns `HARNESS_INJECTED_ENV_ALLOWLIST`
- adapters import harness env names from production contract
- tests no longer define their own allowlist
- command env behavior remains unchanged
- focused validation passes
- full pytest passes or any unrelated blocker is explicitly documented

## Impl.Log

- 2026-06-16: Created by `hugentics-codebase-cleaner` after preparing `agentos-py` with commit `64f5230 feat: enforce harness env injection boundaries`.
- 2026-06-16: Executed as written in Autonomous mode. No design deviations. Validation passed with focused profile/status/preflight tests, focused ruff, `uv run pytest -q`, duplicate env-name search, dry-run command check, and `git diff --check`.
