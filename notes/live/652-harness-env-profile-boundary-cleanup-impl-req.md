# Harness Env Profile Boundary Cleanup - impl-req

## Impl.Abstract

- **scope:** clean up the Agentos agent profile/env boundary so harness-injected provider home env keys cannot be declared as profile config env
- **status:** proposed
- **source:** cleanup run after fixing profile-resolved provider runtime; user clarified that `CODEX_HOME` must be injected by runtime from selected `home`, not stored beside `homes` in profile `env`
- **owning project:** `agentos-py`
- **primary paths:** `src/agentos/agent/config.py`, `src/agentos/agent/run_runtime.py`, `tests/test_agent_profiles.py`, `notes/live/651-profile-resolved-provider-runtime-impl-req.md`
- **related surfaces:** `agentos-md/skills/agentos-pkg/appendix/Harness.Injected.ENV-appendix.md`, `agentos-md/skills/agentos-pkg/appendix/Config.Injected.ENV-appendix.md`, `notes/live/648-agent-harness-injected-env-allowlist-impl-req.md`

## Impl.Index

### Boundary.Model

Profile `env` is config injection, not provider-home selection.

Hard.Evidence:

- `agentos-md/skills/agentos-pkg/appendix/Config.Injected.ENV-appendix.md` says selected home mapped to `CODEX_HOME` is not config env.
- `agentos-md/skills/agentos-pkg/appendix/Harness.Injected.ENV-appendix.md` classifies `CODEX_HOME`, `CLAUDE_CONFIG_DIR`, and `COPILOT_HOME` as harness-injected home env bindings.
- `src/agentos/agent/run_runtime.py` defines `HARNESS_INJECTED_ENV_ALLOWLIST` with provider-scoped harness env keys.
- `src/agentos/codex/agent.py`, `src/agentos/claude/agent.py`, and `src/agentos/copilot/agent.py` derive home env keys from `agent.home` at command construction time.

Implementation direction:

- Treat harness env keys as reserved at the profile `env` boundary.
- Reject reserved keys during profile/config loading rather than relying on provider runtime override order.
- Keep provider-specific command construction unchanged: selected `home` continues to drive harness env.

### Cleanup.Target

The current loader accepts any string mapping under profile `env`.

Hard.Evidence:

- `src/agentos/agent/config.py::_load_string_mapping(...)` validates only JSON object shape and string values.
- Tests currently prove harness env is allowlisted at command build time, but do not prove profile config cannot declare those keys.
- The recent local Codex profile drift showed `env.CODEX_HOME` can coexist with `homes`, which makes the profile summary model misleading even when runtime override order prevents a bad command.

Implementation direction:

- Add validation where profile env is loaded, not in each provider adapter.
- Reuse the existing `HARNESS_INJECTED_ENV_ALLOWLIST` source of truth.
- Emit a direct `CliError` explaining that harness env is derived by Agentos runtime from selected home or account state.

### Wording.Cleanup

Recent profile-runtime tests and Impl.Req wording use "profile env" loosely.

Hard.Evidence:

- `tests/test_agent_monitor_auto_prime.py::test_limits_tracking_refresh_uses_profile_resolved_runtime_agent` uses a fake `raw.profile_env` payload for a Claude-only check.
- `notes/live/651-profile-resolved-provider-runtime-impl-req.md` correctly says provider adapters add `CODEX_HOME`, but some acceptance wording could be read as requiring Codex home binding to live in profile env.

Implementation direction:

- Keep Claude profile env tests, because Claude update-block variables are actual config env.
- Rename fake payload/test wording where needed so Codex home env is not implied to be profile env.
- Add one focused loader test for each reserved env category through representative providers.

## Execution.Plan

### Slice 1 - Reject Harness Env In Profile Config

- Add a behavior test in `tests/test_agent_profiles.py` that writes profiles declaring reserved harness env keys:
  - `CODEX_HOME` for `codex`
  - `CLAUDE_CONFIG_DIR` for `claude-code`
  - `COPILOT_HOME` for `copilot-cli`
- Assert `load_agent_configs()` raises `CliError` with a message naming the offending key and explaining it is harness-injected.
- Implement validation in `src/agentos/agent/config.py` after profile `env` shape loading and before `AgentConfig` construction.

Observable result:

- A profile cannot declare provider home env keys owned by the harness.
- Ordinary profile env such as `DISABLE_UPDATES` or `AGENTOS_TEST_CONFIG_ENV` still loads.

Validation:

```bash
uv run pytest tests/test_agent_profiles.py -q
```

### Slice 2 - Tighten Boundary Wording And Regression Checks

- Rename the fake monitor status payload key in `tests/test_agent_monitor_auto_prime.py` from `profile_env` to a neutral or Claude-specific key.
- Add or adjust a command-build assertion proving a Codex profile with no config env still emits `CODEX_HOME` from selected home.
- Update `notes/live/651-profile-resolved-provider-runtime-impl-req.md` only if wording implies home-binding env belongs to profile config.

Observable result:

- Tests encode the intended model: profile env carries policy env; harness env carries selected provider home.

Validation:

```bash
uv run pytest tests/test_agent_profiles.py tests/test_agent_monitor_auto_prime.py -q
uv run ruff check src/agentos/agent tests/test_agent_profiles.py tests/test_agent_monitor_auto_prime.py
```

## Risks And Deviation Triggers

- If existing fixture profiles declare harness env, update the fixtures to use `homes` or selected home overrides instead of preserving the invalid shape.
- If provider config env, outside profiles, also accepts these keys, do not broaden this cleanup unless the same validation helper can be applied without reshaping config loading.
- Do not change provider adapter runtime env construction in this cleanup.
- Do not add compatibility warnings; invalid profile config should fail.

## Acceptance.Signals

- Profile loading rejects provider harness env keys in profile `env`.
- Existing config env tests continue to pass for non-harness env.
- Codex command construction still derives `CODEX_HOME` from selected `home`.
- Focused tests and scoped ruff pass.

## Impl.Log

- 2026-06-18: Created from codebase-cleaner scope after the `CODEX_HOME` profile/env model correction. The cleanup target is validation and wording only; provider adapters already derive home env from selected runtime home.
