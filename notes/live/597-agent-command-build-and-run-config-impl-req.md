# Agent Command Build And Run Config - impl-req

## Impl.Abstract

- **scope:** split provider-agent command fabrication from process execution by introducing explicit command and run configuration models.
- **status:** implemented.
- **source:** current design discussion on `agent.run`, Codex non-interactive `exec`, and the monitor/account-status need for captured agent execution.
- **goal:** make provider-native command construction inspectable and testable independently from running, while letting callers combine provider interaction mode with process output mode deliberately.

## Impl.Index

### Current.State.Evidence

- `src/agentos/agent/run_runtime.py` already has `build_agent_run_command(...)`, `format_agent_run_command(...)`, and `execute_agent_run_command(...)`.
- The current command builder is generic. It does not model provider-specific interaction semantics such as Codex `exec`.
- Each runnable provider has a private `_run_command(request)` method. This is command fabrication, but it is not a public provider-agent capability.
- `Agent.run(...)` currently combines:
  - command fabrication;
  - provider env construction;
  - account-link side effects where supported;
  - process execution.
- `execute_agent_run_command(...)` always calls `_core.process.run_process(..., mode="terminal")`.
- `agent ping` defaults to `AgentPingConfig(prompt="ping")`; for Codex this builds `codex ... ping`, which is the interactive UI path and fails without a TTY.
- `codex exec ping` is the non-interactive Codex command shape and works with `_core.process.run_process(..., mode="capture")`.

### Concept.Split

- Introduce a first-class split:

```txt
AgentCommandConfig
  provider-native command intent
  affects argv/env/setup construction

AgentRunConfig
  process execution policy
  affects how an already-built command is run

AgentCommand
  concrete argv/env/setup output from a provider agent
```

- `terminal`, `capture`, and `stream` are process output modes owned by `AgentRunConfig`.
- `interactive` and `non_interactive` are provider interaction modes owned by `AgentCommandConfig`.
- Process output mode must not silently rewrite provider-native argv.
- Callers must request a rational combination explicitly. CLI surfaces may choose defaults, but those defaults must be visible in their config-to-command path.

### Command.Config.Model

- Add a provider-neutral command config model, replacing the old conceptual `AgentRunRequest` role over time:

```python
AgentCommandConfig(
    prompt: str | None = None,
    argv: tuple[str, ...] = (),
    model: str | None = None,
    account: str | None = None,
    interaction_mode: Literal["interactive", "non_interactive"] = "interactive",
)
```

- `prompt` and `argv` keep their current meanings:
  - `prompt` is normalized provider prompt-run intent.
  - `argv` is raw provider-native argv.
- `interaction_mode` may affect provider argv construction.
- For Codex:

```txt
interactive prompt:
  codex <base args> [model args] <prompt>

non_interactive prompt:
  codex <base args> [model args] exec <prompt>

raw argv:
  codex <base args> [model args] <argv...>
```

- For providers that do not have distinct interactive/non-interactive command shapes yet, keep behavior explicit:
  - either ignore the distinction only when both modes are genuinely equivalent;
  - or raise a clear unsupported-mode error.

### Run.Config.Model

- Add process execution config:

```python
AgentRunConfig(
    cwd: Path,
    process_mode: Literal["terminal", "capture", "stream"] = "terminal",
    timeout_sec: int | None = None,
)
```

- `process_mode` maps directly to `_core.process.run_process(..., mode=...)`.
- `timeout_sec` should use the request value when provided, otherwise fall back to agent config timeout when the current code already supports or can cleanly support it.
- Stream callbacks are out of scope unless an existing caller already needs them. If required by typing, model them as internal execution wiring, not provider command construction.

### Agent.Command.Model

- Add a structured command result:

```python
AgentCommand(
    argv: tuple[str, ...],
    env_overrides: dict[str, str],
    setup_lines: tuple[str, ...] = (),
)
```

- `setup_lines` preserves dry-run visibility for provider setup/link actions.
- The concrete command object must be printable through the existing shell formatter.
- The command object should be serializable enough for tests to assert exact argv/env without parsing shell strings.

### Provider.Agent.API

- Add a public provider-agent capability:

```python
agent.build_command(command_config: AgentCommandConfig) -> AgentCommand
agent.run(command_config: AgentCommandConfig, run_config: AgentRunConfig) -> AgentRunResult
```

- Drop the proposed `cli_cmd` name. The accepted name is `build_command`.
- `run(...)` should delegate to `build_command(...)`, then execute the returned `AgentCommand`.
- `run_dry(...)` should also delegate to `build_command(...)`, then format the returned command plus setup lines.
- Keep compatibility shims only if needed for an incremental slice, and remove them before completion. The final surface should not keep two command-construction APIs.

### Codex.Mode.Semantics

- Codex must own the `interaction_mode` translation.
- Codex `non_interactive` prompt mode must insert `exec` before the prompt.
- Codex `interactive` prompt mode must preserve current prompt command behavior.
- Codex raw `argv` mode must not inject `exec`; caller-supplied argv is already provider-native.
- Account-linking behavior must be revisited:
  - system homes prepared by `agent accounts link` contain copied `auth.json`;
  - old run-time `--account` linking expects a symlink and can reject valid system homes;
  - command-building must not accidentally mutate verified system homes.

### CLI.Surface.Defaults

- `agent run --prompt ...` should initially preserve current interactive behavior unless explicitly extended with a flag.
- `agent run -- ...` remains raw provider argv behavior.
- `agent ping` should choose a non-interactive command intent for Codex so the default ping can run without a TTY.
- The command path for ping must be visible in tests as an `AgentCommandConfig(interaction_mode="non_interactive", prompt="ping")` or equivalent.
- Do not make `process_mode="capture"` imply `interaction_mode="non_interactive"`.

### Monitor.Readiness

- The monitor limits-tracking workflow will later need to run provider status commands in a non-interactive, captured mode.
- This Impl.Req does not implement the monitor workflow.
- It must leave a clear supported path for future code:

```python
command_config = AgentCommandConfig(
    prompt="ping",
    interaction_mode="non_interactive",
)
run_config = AgentRunConfig(
    cwd=...,
    process_mode="capture",
)
result = agent.run(command_config, run_config)
```

## Execution.Plan

### Slice 1 - Add Structured Command And Run Models

- Add `AgentCommandConfig`, `AgentRunConfig`, and `AgentCommand` in `src/agentos/agent/run_runtime.py` or a closely related module.
- Update `AgentRunResult` to carry captured output fields if `process_mode="capture"` needs to expose them:

```txt
exit_code
stdout
stderr
```

- Preserve existing result behavior for terminal mode.
- Check:
  - focused unit tests for model construction and command formatting;
  - no provider behavior changes yet.

### Slice 2 - Expose `build_command` On Provider Agents

- Add `build_command(command_config)` to `AgentBase` and the `Agent` protocol.
- Implement `build_command(...)` for Codex, Claude, Copilot, and Pi by moving existing private `_run_command` + env construction into the structured command result.
- Keep unsupported providers raising the existing clear unsupported-run error.
- Update `run_dry(...)` to use `build_command(...)`.
- Check:
  - tests assert exact `AgentCommand.argv` and `env_overrides` for at least Codex;
  - dry-run output remains compatible where intentionally unchanged.

### Slice 3 - Rework `run` Around Command And Run Config

- Change runnable providers so `run(command_config, run_config)`:
  - calls `build_command(command_config)`;
  - executes through `_core.process.run_process(...)` using `run_config.process_mode`;
  - returns `AgentRunResult(exit_code, stdout, stderr)` as available.
- Keep CLI `agent run` behavior working by mapping CLI args into `AgentCommandConfig` and `AgentRunConfig(process_mode="terminal")`.
- If temporary adapters are needed for existing tests, keep them local and remove before finishing.
- Check:
  - `agent run --provider codex --profile ... --dry-run -- exec ping`;
  - focused tests for terminal and capture modes using monkeypatched process runner.

### Slice 4 - Implement Codex Interaction Mode Translation

- In `CodexAgent.build_command(...)`, implement:
  - `interaction_mode="interactive"` + prompt -> current `codex ... <prompt>`;
  - `interaction_mode="non_interactive"` + prompt -> `codex ... exec <prompt>`;
  - raw argv unchanged.
- Validate prompt/argv combinations consistently with current CLI rules.
- Check:
  - unit test for `interactive` prompt command;
  - unit test for `non_interactive` prompt command;
  - unit test that raw `argv=("exec", "ping")` is not double-prefixed.

### Slice 5 - Make Ping Non-Interactive Where Supported

- Update `agent ping` command construction so Codex uses:

```txt
AgentCommandConfig(prompt=<ping prompt>, interaction_mode="non_interactive")
AgentRunConfig(process_mode="capture" or terminal, as selected by final CLI behavior)
```

- Keep provider-specific unsupported-mode handling explicit.
- Decide whether ping should print captured stdout directly or only return exit status; preserve current practical behavior unless the current tests force otherwise.
- Check:
  - `agentos agent ping --provider codex --profile codex-jp --home ~/.agentos/agent/homes/codex/jp` can run without a TTY and produce `pong`;
  - existing ping tests updated away from asserting the old prompt-only request shape.

### Slice 6 - Remove Stale Run Request Surface

- Remove or fully demote the old `AgentRunRequest` if it has been replaced.
- Ensure final public concepts are:

```txt
AgentCommandConfig
AgentRunConfig
AgentCommand
AgentRunResult
```

- No final code should require parsing dry-run shell strings to understand command shape.
- Check:
  - `rg "AgentRunRequest|_run_command\\(" src tests`;
  - only accepted compatibility references remain, ideally none.

## Validation

- Focused tests:

```sh
uv run pytest tests/test_agent_commands.py tests/test_process_runner.py -q
```

- Full test suite when the implementation is stable:

```sh
uv run pytest -q
```

- Manual verification after reinstalling the editable CLI if command code changed:

```sh
uv tool install --reinstall --editable .
agentos agent run --provider codex --profile codex-jp --home ~/.agentos/agent/homes/codex/jp --dry-run -- exec ping
agentos agent ping --provider codex --profile codex-jp --home ~/.agentos/agent/homes/codex/jp
```

Expected ping result: non-TTY execution succeeds and returns `pong`.

## Risks And Deviation Triggers

- Stop and realign if changing provider run signatures creates large cross-provider churn outside runnable provider agents.
- Stop and realign if any provider cannot honestly support `interaction_mode="non_interactive"` and needs a provider-specific capability model.
- Stop and realign if account linking would mutate or reject already verified Agentos system homes.
- Do not silently make `capture` mean non-interactive. That would reintroduce the conflation this Impl.Req is designed to remove.

## Acceptance Signals

- Provider agents expose an inspectable `build_command(...)` capability.
- `run(...)` consumes command config plus run config and delegates command construction to `build_command(...)`.
- Codex non-interactive prompt commands use `codex exec <prompt>`.
- Process mode is controlled by run config, not by command config.
- `agent ping` for Codex works without a TTY against the prepared `jp` Agentos system home.
- Tests assert structured command objects rather than only formatted dry-run strings.

## Impl.Log

- 2026-05-14: Created from discussion after validating that `codex exec ping` works non-interactively and that current `agent ping` incorrectly builds the interactive `codex ping` command shape.
- 2026-05-14: Implemented structured `AgentCommandConfig`, `AgentRunConfig`, and `AgentCommand` models. Provider agents now expose `build_command(...)`, `run(...)` executes a built command through run config, and `run_dry(...)` formats the structured command.
- 2026-05-14: Implemented Codex `interaction_mode="non_interactive"` prompt translation as `codex ... exec <prompt>` while leaving raw argv unchanged. `agent ping` now requests non-interactive Codex command intent.
- 2026-05-14: Removed the stale `AgentRunRequest` and private `_run_command(...)` surface from runnable providers. Codex run command construction no longer invokes the old runtime symlink account linker.
- 2026-05-14: Verified with focused tests, full tests, scoped ruff, editable CLI reinstall, Codex dry-run, and non-TTY `agentos agent ping` against the `codex/jp` system home.
