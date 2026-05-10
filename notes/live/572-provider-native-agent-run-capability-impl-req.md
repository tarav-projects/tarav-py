# Provider Native Agent Run Capability - impl-req

## Impl-Req State

Implemented: `agentos agent run` now calls provider-native `run` / `run_dry` methods, with Codex/Copilot/Pi command behavior owned by provider agents.

## User Intent

Make `agentos agent run` provider-native.

The target model is:

```txt
AgentConfig -> <Provider>.Agent -> run / run_dry capability
```

The user explicitly prefers a provider API shaped like:

```py
agent.run(request)
agent.run_dry(request)
```

instead of making the generic command layer understand provider-specific run plans or pre-run actions.

## Why This Exists

`agentos agent run` currently resolves real provider agent objects, but command construction still happens through generic `AgentBase.resolve_run()` and `resolve_terminal_agent_run()`.

That means provider agents mostly carry config fields while Agentos central code still owns provider command semantics:

- command prefix
- run args
- model flag behavior
- prompt placement
- Codex home/env handling
- Codex account auth linking

This is inconsistent with the current Agentos model direction: provider-native behavior should live on `<Provider>.Agent`.

## Current Situation

Current command surface:

```sh
agentos agent run --provider <provider> [--profile <id>] [--home <path>] [--account <account>] [--model <model>] [--project [path]] [--cwd <path>] [--dry-run] -- <prompt>
```

Current flow in `src/agentos/agent/commands.py`:

1. Parse CLI args.
2. Resolve one provider agent with `resolve_agent(...)`.
3. Resolve prompt from argv or stdin.
4. Call `agent.resolve_run(prompt=..., model=...)`.
5. Special-case Codex account/home behavior in `_prepare_account_run(...)`.
6. Print the command for `--dry-run` or execute it with `subprocess.run(...)`.

Current generic run construction in `src/agentos/agent/primitives.py`:

- `AgentBase.resolve_run()` calls `resolve_terminal_agent_run(...)`.
- `resolve_terminal_agent_run(...)` appends:
  - `agent.cli_command`
  - `agent.run_args`
  - `agent.model_flag` and model/default model
  - prompt by `agent.prompt_flag` or positional prompt

This makes provider command behavior generic configuration instead of provider-owned behavior.

## Requested Change

Refactor agent running so provider agents own their run behavior.

The desired public provider capability is:

```py
agent.run(request) -> AgentRunResult
agent.run_dry(request) -> AgentRunDryResult
```

`agentos agent run` should coordinate only:

- CLI parsing
- prompt/stdin handling
- config/project/profile/home resolution
- building a run request
- invoking `agent.run(...)` or `agent.run_dry(...)`
- printing dry-run output
- returning the provider process exit code

Provider agents should own:

- provider command construction
- provider env overrides
- prompt/model placement
- provider-specific run args
- provider-specific account/profile/auth behavior
- provider-specific pre-run mutation

Codex-specific auth linking must move out of `agentos.agent.commands`.

## Target Runtime Shape

Use a small shared request/result surface, but keep provider semantics in provider agents.

Suggested narrow objects:

```py
AgentRunRequest
  prompt: str
  model: str | None
  cwd: Path
  account: str | None

AgentRunResult
  exit_code: int

AgentRunDryResult
  lines: tuple[str, ...]
```

Exact names are flexible. The important boundary is that Agentos does not interpret provider actions.

Provider agents may use internal plan objects if helpful:

```py
def run_dry(self, request):
    return self._resolve_run_plan(request).dry_result()

def run(self, request):
    plan = self._resolve_run_plan(request)
    plan.apply_pre_run_actions()
    return plan.execute()
```

The plan should remain provider-internal unless a later design explicitly promotes it.

## Provider-Specific Expectations

### Codex

`Codex.Agent` should own:

- `codex exec --dangerously-bypass-approvals-and-sandbox`
- `--model <model>`
- positional prompt
- `CODEX_HOME` env override from configured or explicit home
- `--account <name>` interpretation
- auth link mutation for normal run
- auth link preview for dry run

`agentos.agent.commands` should not import Codex auth-link helpers or know Codex auth file layout.

### Copilot

`Copilot.Agent` should own:

- `copilot`
- `--allow-all-tools --no-ask-user`
- `--model <model>`
- `-p <prompt>`

### Pi

`Pi.Agent` should own:

- `pi`
- `--model <model>`
- `-p <prompt>`

### Other Providers

Providers that do not support `agent run` should fail at the provider capability boundary with a clear error.

Do not fake support by keeping a generic terminal command fallback unless the provider agent explicitly opts into it.

## Constraints And Invariants

- Keep the current `agentos agent run` command name and flags stable.
- Keep current dry-run output behavior stable unless the provider-native boundary requires a clearly justified adjustment.
- Keep current normal-run subprocess behavior stable:
  - process cwd comes from `--cwd` or current directory
  - environment starts from `os.environ` plus provider env overrides
  - return provider process exit code
- Keep prompt behavior stable:
  - prompt after `--`
  - stdin fallback when no prompt args
  - error on missing/empty prompt
- Keep `AgentConfig` as config parser output / provider agent constructor input.
- Do not redesign `agentos agent accounts`.
- Do not involve sessions or Chatlas.
- Do not add compatibility aliases.
- Do not revert unrelated dirty worktree changes.

## Out Of Scope

- Renaming CLI flags.
- Changing config field names.
- Changing provider model defaults unless necessary to move ownership into provider agents.
- Redesigning `agentos codex`.
- Adding streaming output capture or rich run telemetry.
- Adding process cancellation/control abstractions.
- Making all providers runnable in this pass.

## Acceptance Signals

- `agentos agent run` invokes `agent.run(...)` for normal execution.
- `agentos agent run --dry-run` invokes `agent.run_dry(...)`.
- `agentos.agent.commands` no longer imports Codex auth-link helpers.
- `agentos.agent.commands` no longer contains Codex-specific account/home linking logic.
- Provider-specific command construction for Codex, Copilot, and Pi lives on provider-owned surfaces.
- `AgentBase.resolve_run()` and `resolve_terminal_agent_run()` are removed or no longer used by the command path.
- Focused tests prove the CLI calls provider-native run methods.
- Existing command behavior remains stable for:
  - configured Codex run
  - Codex `--home`
  - Codex `--account --dry-run`
  - Copilot run
  - Pi run
  - `--project`
  - `--cwd`
  - stdin prompt

## Implementation Shape

Implement in vertical slices.

### Slice 1. Introduce Run Request And Provider Methods

- Add small shared run request/result types.
- Add default `run(...)` / `run_dry(...)` capability shape where appropriate.
- Keep existing behavior operational.

Observable check:

- One provider agent can be called directly with a run request and produces the expected command/dry-run output.

### Slice 2. Move Codex Run

- Move Codex command construction and account-link handling into `Codex.Agent` or `agentos.codex.run`.
- Keep `agentos agent run --provider codex ...` output/behavior stable.
- Remove Codex auth-link imports from `agentos.agent.commands`.

Observable check:

- Existing Codex run tests pass.
- A test proves command layer calls `Codex.Agent.run_dry(...)` for dry-run.

### Slice 3. Move Copilot And Pi Run

- Move Copilot run construction into `Copilot.Agent`.
- Move Pi run construction into `Pi.Agent`.
- Keep generic command layer provider-neutral.

Observable check:

- Existing Copilot and Pi run tests pass.
- Search shows provider-specific run args are not assembled in `agentos.agent.commands`.

### Slice 4. Delete Generic Run Resolver From Command Path

- Remove command-path use of `AgentBase.resolve_run()`.
- Remove or narrow `resolve_terminal_agent_run(...)` if no longer needed.
- Keep config fields only if still needed as provider agent constructor data.

Observable check:

- `agentos agent run` works through provider run capability only.
- Static search shows no central run construction path for provider commands.

### Slice 5. Cleanup And Tests

- Update tests to assert provider-native boundary.
- Keep behavior tests for existing command output.
- Run focused checks.

Observable check:

```sh
uv run ruff check src/agentos/agent src/agentos/codex src/agentos/copilot src/agentos/pi tests/test_agent_commands.py
uv run pytest tests/test_agent_commands.py -q
```

## Relevant Files Or Surfaces

- `src/agentos/agent/commands.py`
- `src/agentos/agent/primitives.py`
- `src/agentos/agent/config.py`
- `src/agentos/agent/providers.py`
- `src/agentos/codex/agent.py`
- `src/agentos/codex/commands.py`
- `src/agentos/copilot/agent.py`
- `src/agentos/pi/agent.py`
- `tests/test_agent_commands.py`

## Open Questions

- Should shared run request/result types live in `agentos.agent.primitives`, a new `agentos.agent.run_runtime`, or provider-local modules?
- Should provider `run(...)` execute subprocess directly, or delegate to a shared provider-neutral subprocess helper?
- Should dry-run rendering be provider-owned strings, or a small shared result with `lines`?
- Should unsupported providers omit `run(...)`, or implement it and raise a clear `CliError`?

## Related Impl-Reqs

- `565-agent-command-profile-and-chat-package-reorg-impl-req.md`
- `566-agent-model-duplication-cleanup-impl-req.md`
- `570-provider-agent-account-capability-refactor-impl-req.md`

## End Log

- 2026-05-10: Created after agreeing that provider-native run should expose `agent.run(request)` and `agent.run_dry(request)`, with any internal run plan hidden inside provider-owned implementation.
- 2026-05-10: Implemented provider-native run capability. Added shared `AgentRunRequest`, `AgentRunResult`, and `AgentRunDryResult`; moved Codex/Copilot/Pi command construction into provider agents; moved Codex account link behavior out of `agentos.agent.commands`; removed the generic resolver names from the command path; added CLI boundary tests for `agent.run` and `agent.run_dry`. Verification passed with `uv run ruff check src/agentos/agent src/agentos/codex src/agentos/copilot src/agentos/pi tests/test_agent_commands.py`, `uv run pytest tests/test_agent_commands.py tests/test_agent_accounts_commands.py -q`, `uv run pytest tests/test_agent_commands.py -q`, and `uv run python -m compileall -q src/agentos/agent src/agentos/codex src/agentos/copilot src/agentos/pi`.
