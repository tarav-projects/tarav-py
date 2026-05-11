# Agent Run Prompt And Argv Split - impl-req

## Impl-Req State

Implemented: `agentos agent run` now separates explicit `--prompt` prompt mode from raw provider argv after `--` across the runnable Codex, Copilot, and Pi provider agents.

## User Intent

Make `agentos agent run` the unified surface for both normalized prompt runs and raw provider argument execution.

The prompt must be passed through an explicit option:

```sh
agentos agent run \
  --provider codex \
  --profile codex-main \
  --prompt "hello"
```

Trailing args after `--` must be provider argv, not prompt text:

```sh
agentos agent run \
  --provider codex \
  --profile codex-main \
  -- exec hello
```

This must be ported to every runnable `<Provider>.Agent`, not handled as a Codex-only special case.

## Why This Exists

The removed `agentos codex --` surface provided raw Codex argument passthrough:

```sh
agentos codex -- <raw codex args>
```

That behavior cannot be represented by the current `agentos agent run` implementation because all positional args are joined into one prompt string. This makes the normalized `agentos agent` interface incomplete for common provider-agent usage.

The target is not to bring back `agentos codex`. The target is to make `<Provider>.Agent.run(...)` expressive enough to launch provider agents with either:

- normalized prompt-run semantics
- raw provider argv passthrough

## Current Situation

`src/agentos/agent/run_runtime.py` defines:

```py
AgentRunRequest
  prompt: str
  model: str | None
  cwd: Path
  account: str | None
```

`src/agentos/agent/commands.py` resolves prompt input by joining all positional args:

```py
prompt = _resolve_prompt(args.prompt)
```

Provider run implementations then append that prompt into provider-specific command shapes.

Current runnable provider agents include:

- `src/agentos/codex/agent.py`
- `src/agentos/copilot/agent.py`
- `src/agentos/pi/agent.py`

`ClaudeAgent` currently does not implement `run`, so it cannot be migrated to the new semantics until provider-native Claude run support exists.

## Requested Change

Change the run request model so prompt and raw argv are separate concepts.

Target shape:

```py
AgentRunRequest
  prompt: str | None
  argv: tuple[str, ...]
  model: str | None
  cwd: Path
  account: str | None
```

Update `agentos agent run` CLI:

```txt
agentos agent run
  --provider <provider>
  [--profile <profile>]
  [--home <home>]
  [--account <account>]
  [--model <model>]
  [--project [project]]
  [--cwd <cwd>]
  [--dry-run]
  [--prompt <text>]
  [-- <provider-argv>...]
```

Rules:

- `--prompt <text>` selects normalized prompt-run mode.
- trailing args after `--` select raw provider argv mode.
- no positional prompt mode remains.
- exactly one of `--prompt` or raw provider argv is required unless stdin prompt mode is deliberately preserved.
- if stdin prompt mode is preserved, it must behave as prompt-run mode and must not blur raw argv semantics.
- if both `--prompt` and raw provider argv are supplied, reject the command with a clear error.

## Provider Semantics

Every runnable `<Provider>.Agent` must receive the same `AgentRunRequest` shape and choose the correct command construction.

### Prompt Mode

Prompt mode uses the provider's configured prompt-run behavior:

- `cli_command`
- `run_args`
- `model` / `default_model` through `model_flag`
- provider prompt shaping through `prompt_flag`
- provider env and home behavior
- provider account behavior where supported

Example Codex prompt mode:

```sh
agentos agent run --provider codex --profile codex-main --prompt "hello"
```

Expected dry-run shape:

```txt
CODEX_HOME=/Users/pereiro/.codex codex exec --dangerously-bypass-approvals-and-sandbox --model gpt-5.4 hello
```

### Raw Argv Mode

Raw argv mode uses:

- `cli_command`
- raw `request.argv`
- provider env and home behavior
- provider account behavior where supported

Raw argv mode must not automatically prepend configured `run_args`, append prompt text, or inject prompt-run flags.

Example Codex raw argv mode:

```sh
agentos agent run --provider codex --profile codex-main -- exec hello
```

Expected dry-run shape:

```txt
CODEX_HOME=/Users/pereiro/.codex codex exec hello
```

This is the equivalent replacement for the old:

```sh
agentos codex -- exec hello
```

### Model Handling

`--model` is prompt-mode behavior by default.

If `--model` is supplied with raw provider argv, either:

- reject with a clear error, or
- only support it for a provider that deliberately translates model into raw argv.

For the first implementation, prefer rejecting `--model` in raw argv mode unless there is already an obvious provider-owned translation.

### Account Handling

Provider account behavior remains provider-owned.

For Codex:

- `--account` should continue to link managed auth before execution in both prompt mode and raw argv mode.
- `--home` should continue to control `CODEX_HOME`.

For providers that do not support `--account`, keep the current clear provider capability error.

## Constraints And Invariants

- Do not reintroduce `agentos codex`.
- Do not add a parallel `agentos agent exec` command for this pass.
- Do not keep positional prompt compatibility unless the user explicitly reverses this decision.
- Do not silently reinterpret raw argv as prompt text.
- Keep provider command construction provider-owned.
- Keep `agentos.agent.commands` thin:
  - parse CLI args
  - resolve configured provider agent
  - build `AgentRunRequest`
  - call `agent.run(...)` or `agent.run_dry(...)`
  - print dry-run lines
- Preserve `--provider`, `--profile`, `--home`, `--account`, `--model`, `--project`, `--cwd`, and `--dry-run` axes.
- Preserve existing prompt-run behavior where the new `--prompt` form maps to the old prompt behavior.
- Port the request shape and semantics to every currently runnable provider agent, not just Codex.

## Out Of Scope

- Re-adding top-level provider commands such as `agentos codex`.
- Adding `agentos agent exec`.
- Implementing provider-native Claude run if it is not already supported.
- Redesigning agent config fields.
- Redesigning account storage or account linking beyond preserving current Codex account behavior.
- Changing Chatlas/session behavior.

## Acceptance Signals

- `agentos agent run --help` shows `--prompt`.
- `agentos agent run --help` no longer describes positional args as prompt text.
- `agentos agent run --provider codex --profile codex-main --prompt "hello" --dry-run` produces the existing Codex prompt-run command shape.
- `agentos agent run --provider codex --profile codex-main --dry-run -- exec hello` produces raw argv shape: `codex exec hello` plus `CODEX_HOME`.
- Codex raw argv mode does not duplicate `exec` or prepend configured prompt `run_args`.
- Codex `--account` works in both prompt mode and raw argv mode.
- Copilot prompt mode still uses configured prompt-run behavior.
- Copilot raw argv mode passes raw provider args after `cli_command`.
- Pi prompt mode still uses configured prompt-run behavior.
- Pi raw argv mode passes raw provider args after `cli_command`.
- Raw argv mode with `--model` is rejected with a clear error unless provider-owned behavior is explicitly implemented.
- Supplying both `--prompt` and raw provider argv is rejected with a clear error.
- Supplying neither prompt nor raw argv is rejected with a clear error unless stdin prompt mode is intentionally preserved and tested.
- Tests no longer rely on positional prompt args for `agentos agent run`.
- The shell alias replacement becomes valid:

```zsh
alias acodex='agentos agent run --provider codex --profile codex-main --'
```

## Implementation Shape

Implement in vertical slices.

### Slice 1. Request Model And CLI Parse Split

Change `AgentRunRequest` to carry `prompt: str | None` and `argv: tuple[str, ...]`.

Update `agentos agent run` parser to add `--prompt` and treat `argparse.REMAINDER` as raw provider argv.

Observable checks:

- `agentos agent run --help` shows `--prompt`.
- `agentos agent run --provider codex --profile codex-main --dry-run --prompt hello` reaches provider `run_dry` with `prompt="hello"` and `argv=()`.
- `agentos agent run --provider codex --profile codex-main --dry-run -- exec hello` reaches provider `run_dry` with `prompt=None` and `argv=("exec", "hello")`.
- both modes together produce a clear error.

### Slice 2. Codex Prompt And Raw Modes

Update `CodexAgent` command construction:

- prompt mode: preserve existing prompt-run behavior
- raw argv mode: `cli_command + argv`
- both modes keep Codex home/env behavior
- Codex account linking still applies before execution and appears in dry-run output

Observable checks:

- Codex prompt dry-run matches existing behavior through `--prompt`.
- Codex raw dry-run matches `CODEX_HOME=<home> codex <argv...>`.
- Codex raw mode with account prints/performs auth link before raw command.

### Slice 3. Copilot And Pi

Update `CopilotAgent` and `PiAgent` with the same split:

- prompt mode uses current provider prompt-run behavior
- raw argv mode passes raw args after `cli_command`
- unsupported account behavior remains unchanged

Observable checks:

- Existing prompt-run tests are migrated to `--prompt` and still pass.
- New raw dry-run tests prove raw args are not converted into prompt text.

### Slice 4. Error Semantics

Add focused tests for invalid combinations:

- `--prompt` plus raw argv
- `--model` plus raw argv, unless provider-owned translation is implemented
- no prompt and no raw argv when stdin is not being used

Observable check:

- errors are explicit and provider-neutral where possible.

### Slice 5. Alias Validation

After implementation, validate the intended alias shape:

```sh
agentos agent run --provider codex --profile codex-main --dry-run -- exec hello
```

Expected:

```txt
CODEX_HOME=/Users/pereiro/.codex codex exec hello
```

Then update `~/.zshrc`:

```zsh
alias acodex='agentos agent run --provider codex --profile codex-main --'
```

Only update the alias after the command behavior is verified.

### Slice 6. Final Verification

Run focused checks:

```sh
uv run ruff check src/agentos/agent src/agentos/codex src/agentos/copilot src/agentos/pi tests/test_agent_commands.py
uv run pytest tests/test_agent_commands.py tests/test_agent_accounts_commands.py -q
uv run python -m compileall -q src/agentos/agent src/agentos/codex src/agentos/copilot src/agentos/pi
agentos agent run --help
agentos agent run --provider codex --profile codex-main --dry-run -- exec hello
```

After CLI changes, refresh the installed executable:

```sh
uv tool install --reinstall --editable .
```

## Relevant Files Or Surfaces

- `src/agentos/agent/run_runtime.py`
- `src/agentos/agent/commands.py`
- `src/agentos/agent/primitives.py`
- `src/agentos/codex/agent.py`
- `src/agentos/copilot/agent.py`
- `src/agentos/pi/agent.py`
- `tests/test_agent_commands.py`
- `~/.zshrc`
- `notes/live/572-provider-native-agent-run-capability-impl-req.md`
- `notes/live/573-agent-link-command-surface-impl-req.md`

## Open Questions

- Should stdin prompt mode remain supported when `--prompt` is omitted and no raw argv is supplied?
- Should any provider support `--model` in raw argv mode by translating it into provider argv, or should raw mode be strictly user-owned argv?
- Should provider agents expose helper methods for prompt-command and raw-command construction, or keep the split inside each `_run_command` method?

## Related Impl-Reqs

- `572-provider-native-agent-run-capability-impl-req.md` - made `agentos agent run` provider-native.
- `573-agent-link-command-surface-impl-req.md` - removed top-level `agentos codex` and moved Codex linking under `agentos agent link`.

## End Log

- 2026-05-10: Created after agreeing that prompt input must become explicit via `--prompt`, while trailing args after `--` become raw provider argv for every runnable `<Provider>.Agent`.
- 2026-05-10: Implemented. Updated `AgentRunRequest` with `prompt: str | None` and `argv`, changed `agentos agent run` parsing to use `--prompt` for normalized prompt runs and `--` for raw provider argv, updated Codex/Copilot/Pi provider command construction, refreshed tests, updated `acodex` in `~/.zshrc`, reinstalled the editable CLI, and verified with focused ruff/pytest/compileall plus installed CLI smoke checks.
