# Agent Harness Injected ENV Allowlist - impl-req

## Impl.Abstract

- **scope:** add a tested `Harness.Injected.ENV` allowlist for agent command construction, classify profile env as `Config.Injected.ENV`, and move any current non-allowlisted hardcoded run-affecting env values out of provider code and into explicit profile/config surfaces
- **status:** implemented
- **source:** 2026-06-16 design alignment after adding `Harness.Injected.ENV` and `Config.Injected.ENV` to the Agentos index; user request: "profiles + args, no hidden config" and "any other non HARNESS_INJECTED_ENV_ALLOWLIST env variable currently hardcode, move them to profiles"
- **owning project:** `agentos-py`
- **primary paths:** `src/agentos/claude/agent.py`, `src/agentos/codex/agent.py`, `src/agentos/copilot/agent.py`, `src/agentos/claude/account_status.py`, `tests/test_agent_profiles.py`, `tests/test_agent_run_account_preflight.py`, optional local profiles under `~/.agentos/profiles`
- **related surfaces:** `agentos-md/skills/agentos-pkg/index/104-index.md` (`Harness.Injected.ENV`, `Config.Injected.ENV`), `agentos-md/skills/agentos-pkg/appendix/Harness.Injected.ENV-appendix.md`, `agentos-md/skills/agentos-pkg/appendix/Config.Injected.ENV-appendix.md`

## Impl.Index

### Harness.Injected.ENV.Allowlist

- `Harness.Injected.ENV` keys must be explicit and tested
- the allowlist is provider-scoped because provider mechanisms differ below `Agentos.Agent.Adapter`
- default command builds with no config env may emit only allowlisted harness env keys
- config-declared env is not harness env
- credential env remains harness env when it exposes a selected managed credential through the provider mechanism

Current allowlist:

```python
HARNESS_INJECTED_ENV_ALLOWLIST = {
    "codex": {"CODEX_HOME"},
    "claude-code": {"CLAUDE_CONFIG_DIR", "CLAUDE_CODE_OAUTH_TOKEN"},
    "copilot-cli": {"COPILOT_HOME"},
    "pi": set(),
    "gemini-cli": set(),
    "opencode": set(),
    "openclaw": set(),
}
```

Hard.Evidence:

- `src/agentos/codex/agent.py` injects `CODEX_HOME` from `agent.home`.
- `src/agentos/claude/agent.py` injects `CLAUDE_CONFIG_DIR` from `agent.home`.
- `src/agentos/claude/agent.py` injects `CLAUDE_CODE_OAUTH_TOKEN` for selected Claude OAuth-token accounts.
- `src/agentos/copilot/agent.py` injects `COPILOT_HOME` from `agent.home`.
- `src/agentos/pi/agent.py` passes only `self.env`; current Pi env is therefore config injection.
- Gemini, OpenCode, and OpenClaw adapters do not inject run env in current code.

### Config.Injected.ENV.Boundary

- `Config.Injected.ENV` is declared configuration passed into provider execution
- profile `env` and project/provider env are config injection
- launch-policy env belongs in config injection
- provider adapters may transport config env
- provider adapters must not author config env
- tests should prove config env appears only when the test profile/config declares it

Hard.Evidence:

- `RunnableMixin._build_command_with_env(...)` already merges adapter env overrides into the command object.
- Provider adapters start run env from `dict(self.env)` or `self.env`.
- Current local profiles already use explicit `env` for some provider policy, such as Pi profile `PI_CODING_AGENT_DIR`.

### Hidden.Env.Cleanup

- non-allowlisted hardcoded env values must not be invented by provider code for normal command execution
- current detected non-allowlisted hardcoded env values are Claude account-status refresh values
- `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` is hardcoded in `src/agentos/claude/account_status.py`
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` is hardcoded in `src/agentos/claude/account_status.py`
- those values should move to explicit profile/config env if they are still wanted
- the account-status subprocess may continue to apply subsystem-specific parent-env isolation
- inherited environment allowlists such as `HOME`, `PATH`, `USER`, and `LC_*` are not Agentos-injected env and are outside this allowlist

Implementation direction:

- Remove the two hardcoded Claude disable-env assignments from `account_status.py`.
- Ensure account-status refresh uses the command env already produced from `AgentConfig.env` and harness-injected home env.
- Add the Claude disable env values to relevant local or fixture profiles only when the profile explicitly wants that policy.
- Do not add a new profile schema field for this; use existing profile `env`.

### Adjacent.Hidden.Argv

- Claude `--dangerously-skip-permissions` injection is not ENV
- it is still hidden launch policy and violates the same "profiles + args" direction
- it should be handled either in this implementation as an adjacent cleanup or in a follow-up Impl.Req if scope needs to stay ENV-only

Hard.Evidence:

- `src/agentos/claude/agent.py::_claude_command_config(...)` injects `--dangerously-skip-permissions` for `non_interactive`.
- `claude-main` currently also carries `--dangerously-skip-permissions` in profile `cli_command`, causing duplicated dry-run output for `--non-interactive`.

Recommended implementation direction:

- Remove the hardcoded Claude non-interactive permission argv injection.
- Keep `--non-interactive` as prompt-mode normalization only.
- Put permission policy in `cli_command`, `run_args`, or explicit provider args.
- Adjust tests that expected the implicit argv.

## Execution.Plan

### Slice 1 - Add Harness ENV Allowlist Test Contract

- Add a focused test module or focused cases in `tests/test_agent_profiles.py`.
- Define the provider-scoped `HARNESS_INJECTED_ENV_ALLOWLIST` in tests or a small production helper if production code needs it.
- Build minimal runnable provider configs with no profile/config env.
- Assert command env override keys are a subset of the provider allowlist.
- Include a separate case where profile `env` is declared and prove those keys are config injection, not harness injection.

Observable result:

- A provider adapter cannot silently add a new env key without changing the allowlist test.
- `CODEX_HOME`, `CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_OAUTH_TOKEN`, and `COPILOT_HOME` remain accepted harness env.

RED.GREEN.Test.Suite:

```bash
uv run pytest tests/test_agent_profiles.py tests/test_agent_run_account_preflight.py -q
```

### Slice 2 - Remove Hardcoded Non-Allowlisted Claude Env

- Remove hardcoded assignments:
  - `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`
  - `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`
- Preserve account-status subprocess parent-env isolation.
- Ensure account-status refresh still receives profile `env` through the existing command-building path.
- Add or update tests to prove those env keys appear only when profile/config `env` declares them.

Observable result:

```bash
rg -n "CLAUDE_CODE_DISABLE_AUTO_MEMORY|CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC" src/agentos tests
```

has no provider-code hardcoded assignment matches; test fixtures may contain explicit profile env declarations.

Validation:

```bash
uv run pytest tests/test_claude_account_status.py tests/test_agent_profiles.py -q
uv run ruff check src/agentos/claude tests
```

### Slice 3 - Move Desired Policy Env To Profiles

- Identify local Claude profiles that should keep the disable env behavior.
- Add those values under profile `env` where desired:

```json
"env": {
  "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
  "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"
}
```

- Do not add these env values to every profile unless that is the explicit intended policy.
- Keep test profiles minimal unless the test is exercising `Config.Injected.ENV`.

Observable result:

- Desired local Claude runs keep the same behavior through explicit profile env.
- Minimal command-build tests remain free of non-allowlisted env.

Validation:

```bash
agentos agent run --profile claude-main --dry-run -- --version
agentos agent run --profile claude-br --dry-run -- --version
```

### Slice 4 - Optional Hidden Argv Cleanup

- Remove Claude non-interactive hardcoded `--dangerously-skip-permissions` injection from `ClaudeAgent`.
- Move desired permission policy to Claude profiles or explicit command args.
- Add/adjust tests so `--non-interactive` no longer implies permission policy by itself.

Observable result:

```bash
agentos agent run --profile claude-main --non-interactive --dry-run --prompt test
```

does not duplicate `--dangerously-skip-permissions`; it appears only if profile/args declare it.

Validation:

```bash
uv run pytest tests/test_claude_account_status.py tests/test_agent_profiles.py -q
```

## Risks And Deviation Triggers

- If Claude account-status refresh fails without the disable env policy, do not restore hidden hardcoded env. Add explicit fixture/profile env or surface the need for a profile policy decision.
- If a provider requires a new env key to enable functionality, add it to the allowlist and document why it is `Harness.Injected.ENV`.
- If a new env key expresses preference, safety posture, telemetry, model choice, permission policy, or sandbox policy, reject it as harness env and require `Config.Injected.ENV`.
- If hidden argv cleanup grows beyond a small local change, split it into a follow-up Impl.Req rather than weakening the ENV allowlist work.

## Acceptance.Signals

- `Harness.Injected.ENV` allowlist is enforced by tests.
- Minimal provider command builds emit only allowlisted harness env keys.
- Profile/config env appears only when explicitly declared.
- No non-allowlisted env variable is hardcoded into provider run command construction.
- Claude account-status disable env policy, if kept, is profile/config-declared.
- Focused and full tests pass.

## Impl.Log

- 2026-06-16: Created from design alignment around `Harness.Injected.ENV` / `Config.Injected.ENV`. Current evidence identifies `CODEX_HOME`, `CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_OAUTH_TOKEN`, and `COPILOT_HOME` as harness env, and two Claude account-status disable env values as non-allowlisted hidden policy env.
- 2026-06-16: Executed in Autonomous mode. Decision: keep the two Claude disable-policy env values for local Claude profiles by declaring them in profile `env`; this preserves local statusline behavior as `Config.Injected.ENV`. Decision: remove the Claude non-interactive hidden `--dangerously-skip-permissions` injection in this implementation because the change was local and covered by focused tests; local Claude profiles carry that permission policy explicitly where desired. Validation note: full `uv run pytest -q` passed; full `uv run ruff check .` remains blocked by pre-existing `_DEPRECATED/` and `dev/account-usage.py` lint errors, while scoped `uv run ruff check src/agentos/claude tests` passed.
