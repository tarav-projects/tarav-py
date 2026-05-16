# Provider CLI Command Authority - impl-req

## Impl.Abstract

- **scope:** introduce provider-level executable configuration under `~/.agentos/config.json` at `agent.providers.<provider>.cli_command`, make runnable agent paths use that provider authority, and stop relying on bare executable defaults such as `claude` when running provider commands.
- **status:** implemented.
- **source:** follow-up from Claude Code monitor failures where `agentos agent accounts monitor` resolved `claude` through cmux/PATH and ran Claude Code `v2.1.69`, while the intended configured executable `/opt/homebrew/bin/claude` runs the newer Claude Code that emits `statusLine.rate_limits`.
- **goal:** Agentos provider command execution should be deterministic and configured once per provider. If a runnable provider has no configured `cli_command`, `agent.run`, `agent.ping`, `account_status`, and monitor should fail with a clear setup error instead of silently using PATH.

## Impl.Index

### Observed.Failure

- `~/.agentos/logs/claude-statusline-last-run.json` captured failing monitor runs.
- The failing run used:

```txt
argv[0] = "claude"
version = "2.1.69"
PATH starts with /Applications/cmux.app/Contents/Resources/bin
```

- The captured statusLine payload existed but lacked `rate_limits`:

```txt
capture.exists = true
invalid_capture_error = capture payload is missing rate_limits
```

- The user's shell shows `claude` is affected by cmux:

```sh
which claude
claude () {
        "$_CMUX_CLAUDE_WRAPPER" "$@"
}
```

- Python `subprocess.Popen` does not inherit shell functions, but it does resolve bare `claude` through `PATH`. The cmux path can therefore still affect executable selection.

### Current.Code.Evidence

- Registered-account agents are built in:

```txt
src/agentos/agent/providers.py
  build_registered_account_agent(...)
  _default_registered_account_agent_config(...)
```

- Current registered-account construction ignores configured provider/instance executable data and starts from `default_agent_configs()`.
- Default agent configs currently embed bare executable names:

```txt
src/agentos/agent/config.py
  _agent_default_cli_command("claude-code") -> ("claude",)
  _agent_default_cli_command("codex") -> ("codex",)
```

- Agent command execution already fails when `cli_command` is empty:

```txt
src/agentos/agent/run_runtime.py
  build_agent_command_argv(...)
    if not cli_command:
      raise CliError(...)
```

- Existing global config has instance-level `cli_command` values, including:

```json
{
  "provider": "claude-code",
  "id": "claude-main",
  "cli_command": ["/opt/homebrew/bin/claude"]
}
```

- That instance-level value does not help monitor registered-account agents because monitor uses `build_registered_account_agent(...)`, which currently returns a default provider agent with bare `("claude",)`.

### Target.Config.Model

- Add provider-level config:

```json
{
  "agent": {
    "providers": {
      "claude-code": {
        "cli_command": ["/opt/homebrew/bin/claude"]
      },
      "codex": {
        "cli_command": ["/opt/homebrew/bin/codex"]
      }
    }
  }
}
```

- `agent.providers.<provider>.cli_command` is the provider executable authority.
- Provider-level config applies to:
  - default provider agents
  - registered-account agents
  - monitor/account-status agents
  - `agent ping`
  - `agent run`
- Instance-level `agent.instances[].cli_command` may still override provider-level `cli_command` for that explicit instance.

### Required.Semantics

- Runnable providers must not silently fall back to bare executable defaults.
- If `agent.providers.<provider>.cli_command` is missing and an instance does not provide `cli_command`, runnable command construction must fail with a setup error that names the missing config field.
- The error should include a useful JSON example, especially for Claude:

```txt
agent provider claude-code requires agent.providers.claude-code.cli_command
example:
{
  "agent": {
    "providers": {
      "claude-code": {
        "cli_command": ["/opt/homebrew/bin/claude"]
      }
    }
  }
}
```

- This is not a PATH lookup feature. Do not call `which`, `shutil.which`, or shell resolution as a replacement for config.
- This is not a compatibility shim. Remove executable defaults for runnable providers instead of preserving legacy bare names.

### Registered.Account.Agent.Behavior

- `build_registered_account_agent(provider, account, home, start_path=...)` should:
  - validate the registered account as it does today
  - load provider-level config from the same config discovery surfaces as other agent config
  - build an agent config from the provider-level provider config plus canonical provider defaults for non-executable metadata
  - override `home` with the registered account system home
  - attach `AgentAccountContext`
- It must not select `agent.instances` by profile and must not infer executable config from arbitrary instance ambiguity.
- It may reuse parsing/merging helpers from `agent.config`; avoid duplicating config parsing.

### Config.Migration

- Update `~/.agentos/config.json` to add `agent.providers` with at least:
  - `claude-code.cli_command = ["/opt/homebrew/bin/claude"]`
  - `codex.cli_command = ["/opt/homebrew/bin/codex"]`
- Do not delete existing `agent.instances[].cli_command` in this slice unless the implementation explicitly proves they are redundant and tests cover the cleanup. Keeping them is acceptable while provider-level authority is introduced.

### Out.Of.Scope

- Do not redesign monitor workflows.
- Do not remove the Claude statusLine last-run log.
- Do not add automatic executable discovery.
- Do not change registered account/home linking semantics.
- Do not migrate all instance config fields into `agent.providers`; this slice is about `cli_command` authority first.
- Do not make `agent.instances` the monitor target model.

## Execution.Plan

### Slice 1 - Parse Provider-Level CLI Command Config

Status: complete.

- Add config support for:

```txt
agent.providers.<provider>.cli_command
```

- Prefer a small provider-config model/helper in `src/agentos/agent/config.py`.
- Reuse existing `_load_string_argv(...)` validation.
- Check:
  - provider-level `cli_command` loads from global config
  - project config can also supply provider-level config through existing config document discovery
  - invalid provider config shape produces a clear `CliError`

### Slice 2 - Make Agent Config Resolution Inherit Provider CLI Command

Status: complete.

- Apply provider-level `cli_command` to `AgentConfig` creation.
- Instance-level `cli_command` overrides provider-level `cli_command`.
- Remove bare runnable defaults from `_agent_default_cli_command(...)` or make them empty for runnable providers.
- Check:
  - configured instance without `cli_command` inherits `agent.providers.<provider>.cli_command`
  - configured instance with `cli_command` keeps its own value
  - command construction fails when no provider/instance `cli_command` is configured

### Slice 3 - Registered Account Agents Use Provider Authority

Status: complete.

- Update `build_registered_account_agent(...)` so registered-account agents use provider-level executable config instead of `default_agent_configs()` bare command defaults.
- Preserve account context and system-home override behavior.
- Check:
  - `build_registered_account_agent(provider="claude-code", account="browser-jp", home=...)` gets `/opt/homebrew/bin/claude` from provider config
  - monitor path uses the same command because `LimitsTrackingWorkflow` calls `build_registered_account_agent(...)`
  - missing provider `cli_command` produces a clear setup error before invoking Claude/Codex

### Slice 4 - Update Global Config

Status: complete.

- Update `~/.agentos/config.json`:

```json
"agent": {
  "providers": {
    "claude-code": {
      "cli_command": ["/opt/homebrew/bin/claude"]
    },
    "codex": {
      "cli_command": ["/opt/homebrew/bin/codex"]
    }
  }
}
```

- Preserve existing config fields and formatting as much as practical.
- Check:
  - `agentos agent run --provider claude-code --home ~/.agentos/agent/homes/claude-code/browser-jp --dry-run -- echo` or an equivalent dry-run shows `/opt/homebrew/bin/claude`
  - `agentos agent accounts monitor --once` uses Claude Code from `/opt/homebrew/bin/claude`, not cmux `claude`

### Slice 5 - Validation

Status: complete.

- Run focused tests:

```sh
uv run pytest tests/test_agent_commands.py tests/test_agent_account_registry_commands.py -q
```

- Run lint:

```sh
uv run ruff check src/agentos/agent/config.py src/agentos/agent/providers.py tests/test_agent_commands.py tests/test_agent_account_registry_commands.py
```

- Refresh installed CLI:

```sh
uv tool install --reinstall --editable .
```

- Real smoke:

```sh
agentos agent accounts monitor --once
```

- Inspect:

```sh
~/.agentos/logs/claude-statusline-last-run.json
```

- Acceptance signals:
  - log `argv[0]` is `/opt/homebrew/bin/claude`
  - log `version` is the intended Claude Code version from the stable executable
  - Claude statusLine payload includes `rate_limits`
  - monitor displays fresh Claude limits without fallback fetch error

## Impl.Log

- Created after diagnosing that Claude monitor failures were caused by executable ambiguity: bare `claude` resolved to a cmux/older Claude Code path that emitted statusLine payloads without `rate_limits`.
- User aligned on provider-level `cli_command` as important global config and on failing when it is missing instead of relying on implicit PATH defaults.
- Implemented provider-level CLI command authority in `src/agentos/agent/config.py`, registered-account provider resolution in `src/agentos/agent/providers.py`, and provider setup errors in `src/agentos/agent/run_runtime.py`.
- Updated `~/.agentos/config.json` with `agent.providers.claude-code.cli_command = ["/opt/homebrew/bin/claude"]` and `agent.providers.codex.cli_command = ["/opt/homebrew/bin/codex"]`.
- Added focused tests for provider CLI inheritance from global and project config, instance override, invalid `agent.providers` shape, registered-account provider CLI use, and the missing-provider-command setup error.
- Validation passed:
  - `uv run pytest tests/test_agent_commands.py tests/test_agent_account_registry_commands.py -q` -> `129 passed`.
  - `uv run ruff check src/agentos/agent/config.py src/agentos/agent/providers.py src/agentos/agent/run_runtime.py tests/_helpers.py tests/test_agent_commands.py tests/test_agent_account_registry_commands.py` -> passed.
  - `uv tool install --reinstall --editable .` refreshed the installed `agentos` executable.
  - `agentos agent run --provider claude-code --home ~/.agentos/agent/homes/claude-code/browser-jp --dry-run -- echo` emitted `/opt/homebrew/bin/claude`.
  - `agentos agent accounts monitor --once` displayed fresh Claude usage limits.
  - `~/.agentos/logs/claude-statusline-last-run.json` recorded `argv[0] = "/opt/homebrew/bin/claude"`, `version = "2.1.140"`, and `statusline_payload.rate_limits` with `five_hour` and `seven_day`.
