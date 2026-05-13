# Provider Agent Account Stats Capability - impl-req

## Impl-Req State

Implemented: provider agents now expose `account_stats(...)`, request config passes through orchestration and is narrowed at the provider-agent boundary, old collect-style account stats symbols are removed, and the full test suite passes.

## User Intent

Agentos should expose a common account stats capability on each `<Provider>.Agent`.

The common surface should be a capability entrypoint, not a common implementation strategy:

```txt
agent.account_stats(request) -> dict[str, object]
```

The provider agent owns how account stats are fetched. It may use the generic process runner, direct `subprocess.Popen`, PTY handling, HTTP, JSON-RPC, or any provider-specific combination.

The user explicitly wants:

- keep the existing account stats / account limit data model.
- move and normalize the fetching capability onto provider agents.
- allow package files to move so the package structure reflects the new model.
- support default fetch configuration.
- support provider-specific fetch configuration.
- keep provider strategy details out of the generic process runner.
- no legacy compatibility layer unless explicitly requested.

## Why This Exists

The current account system already has useful normalized output and limit aggregation. The problem is not the account data model.

The problem is ownership. Account fetching is partly centralized in shared account helpers and partly delegated to provider modules. As the providers diverge, the shared layer should stop looking like it owns provider behavior.

The desired boundary is:

```txt
agent/accounts.py
  orchestrates configured agents, calls the capability, aggregates/formats/persists results.

<Provider>.Agent
  owns account_stats(...) and provider fetch strategy/fallbacks.

provider implementation modules
  may exist, but are implementation details behind <Provider>.Agent.

_core.process
  only runs already-prepared commands when useful.
```

## Current Situation

Relevant current surfaces:

- `src/agentos/agent/accounts.py`
  - selects configured provider agents.
  - calls `collect_account_stats(...)` on provider agents.
  - aggregates, formats, and persists account stats payloads.
- `src/agentos/agent/account_runtime.py`
  - contains generic account command helpers such as `run_account_command(...)`, `run_captured_command(...)`, `successful_command_output(...)`, and `AccountCommandError`.
- `src/agentos/codex/agent.py`
  - implements `collect_account_stats(...)` by delegating to `agentos.codex.accounts.collect_codex_account_stats(...)`.
- `src/agentos/codex/accounts.py`
  - auth path uses `codex login status` as a captured CLI command.
  - usage path uses `codex app-server` JSON-RPC over stdin/stdout.
- `src/agentos/claude/agent.py`
  - implements `collect_account_stats(...)` by delegating to `agentos.claude.accounts.collect_claude_account_stats(...)`.
- `src/agentos/claude/accounts.py`
  - auth path uses `claude auth status --json`.
  - live usage can use a PTY/statusline refresh path.
  - live usage can fall back to a `stream-json` CLI command.
- `src/agentos/copilot/agent.py`
  - implements `collect_account_stats(...)` by delegating to `agentos.copilot.accounts.collect_copilot_account_stats(...)`.
- `src/agentos/copilot/accounts.py`
  - auth/check path uses a Copilot CLI JSON-output probe.
  - usage path reads `gh auth token` and calls the GitHub Copilot HTTP API.
- `src/agentos/pi/agent.py`
  - has run/session support but no account stats capability today.
- `src/agentos/_core/process.py`
  - provides generic `terminal`, `capture`, and `stream` process execution modes for already-prepared commands.

## Requested Change

Normalize provider account fetching as a first-class `<Provider>.Agent` capability.

Preferred target API:

```python
agent.account_stats(request: AccountStatsRequest) -> dict[str, object]
```

If implementation keeps the current method name, it must be an explicit design choice. Otherwise replace `collect_account_stats(...)` cleanly with `account_stats(...)`; do not keep a legacy alias unless the user requests one.

Extend `AccountStatsRequest` so it can carry fetch configuration while preserving existing behavior by default. A simple shape is acceptable, for example:

```python
@dataclass(frozen=True)
class AccountStatsRequest:
    refresh_usage: bool = False
    config: Mapping[str, object] = field(default_factory=dict)
```

The request config may include shared defaults and provider-specific sections. Generic orchestration should pass the config through. Provider agents should parse only what they own.

Provider-specific configuration examples may include strategy and fallback choices:

```txt
codex:
  usage_strategy: app-server
  fallback: auth-only

claude-code:
  usage_strategy: statusline
  fallback: stream-json

copilot-cli:
  usage_strategy: github-api
  fallback: auth-only
```

Exact config keys should follow local code style and be kept minimal. Do not design a large schema before a provider needs it.

Package/file organization may change to reflect the new model. For example, provider account modules may become private implementation modules behind their provider agent, or logic may move directly into provider agent files when that is clearer.

## Constraints And Invariants

- Preserve the existing normalized account stats payload model.
- Preserve the existing account limit model and aggregation semantics.
- Preserve existing account stats CLI behavior unless the capability boundary requires a clean internal rename.
- Provider agents own account stats fetching behavior.
- `agent/accounts.py` must not interpret provider-specific strategy/fallback config.
- `_core.process` must not know provider names, account payloads, provider strategy names, or parsing rules.
- Use `run_process(..., mode="capture")` only for already-prepared one-shot commands.
- Use `run_process(..., mode="stream")` only when the caller needs output events while the process runs.
- Keep Codex `app-server` JSON-RPC provider-owned; do not force it through `run_process`.
- Keep Claude PTY/statusline provider-owned; do not force it through `run_process`.
- Keep Copilot GitHub HTTP provider-owned; do not force it through `run_process`.
- Default configuration must preserve the current successful fetch paths.
- Provider-specific configuration is allowed, but it should be parsed at the provider boundary.
- No backward-compatibility aliases or duplicate old/new capability APIs unless explicitly requested.
- Do not disturb unrelated dirty worktree changes.

## Out Of Scope

- No redesign of account stats output JSON.
- No redesign of the account limit model.
- No rewrite of account usage formatting.
- No generic provider strategy engine.
- No provider-specific behavior in `_core.process`.
- No attempt to make JSON-RPC, PTY, HTTP, and subprocess capture all share one execution abstraction.
- No new plugin/config framework beyond the minimal request config needed for this capability.
- No Pi account stats implementation unless there is an existing real Pi account capability to expose.

## Acceptance Signals

- Provider account fetching is exposed through one common provider-agent capability entrypoint.
- The account orchestrator calls the common capability and does not know provider fetch strategy details.
- Existing account stats and account limit payloads remain compatible with current tests and CLI output.
- Default configuration preserves current behavior for Codex, Claude, and Copilot.
- Provider-specific configuration can be supplied through `AccountStatsRequest` and is parsed by the relevant provider agent.
- Codex auth still uses a captured CLI probe and Codex usage still uses provider-owned `app-server` JSON-RPC.
- Claude auth still uses a captured CLI probe and Claude usage still supports the existing statusline path plus fallback behavior.
- Copilot auth/check still uses a captured CLI probe and Copilot usage still uses `gh auth token` plus provider-owned GitHub HTTP.
- Package files are organized so provider-specific account behavior is visibly owned by provider packages/agents.
- No legacy alias remains if the capability is renamed from `collect_account_stats(...)` to `account_stats(...)`.
- Existing account command tests pass.
- Existing agent command tests pass.
- Full test suite passes.

## Implementation Shape

Implement in vertical slices.

### Slice 1. Normalize The Capability Entrypoint

Behavior slice:

- Add or rename the provider-agent account capability to the agreed common name, preferably `account_stats(...)`.
- Update `agent/accounts.py` to call that common capability.
- Keep request construction behavior unchanged except for adding default config support.

Observable check:

- Existing account stats CLI tests pass with default config.
- A focused test proves orchestration calls the common provider-agent capability.

Design assumption validated:

- Common capability ownership can change without changing the account payload model.

### Slice 2. Add Request Configuration Pass-Through

Behavior slice:

- Extend `AccountStatsRequest` with a minimal immutable config field.
- Ensure the account orchestrator passes config through without interpreting provider-specific keys.
- Add provider-local helpers for extracting each provider's config section/defaults.

Observable check:

- A focused test passes provider-specific config and proves only the selected provider interprets its own config.
- Existing default behavior remains unchanged.

Design assumption validated:

- Strategy/fallback selection can be configured without leaking provider semantics into generic account orchestration.

### Slice 3. Move Codex Account Fetch Ownership Behind CodexAgent

Behavior slice:

- Move or wrap Codex account fetch behavior so `CodexAgent.account_stats(...)` owns the path.
- Keep `codex login status` as a captured one-shot command.
- Keep `codex app-server` JSON-RPC specialized and provider-owned.
- If files move, prefer names that make implementation ownership clear, such as provider-private account capability modules.

Observable check:

- Codex account tests pass.
- Tests still cover auth probe parsing and app-server rate-limit parsing/failure behavior.

Design assumption validated:

- Provider-agent ownership does not require flattening provider-specific protocols into generic runner code.

### Slice 4. Move Copilot Account Fetch Ownership Behind CopilotAgent

Behavior slice:

- Move or wrap Copilot account fetch behavior so `CopilotAgent.account_stats(...)` owns the path.
- Keep Copilot CLI auth/check as a captured one-shot command.
- Keep `gh auth token` as captured command infrastructure.
- Keep GitHub Copilot HTTP usage request provider-owned.

Observable check:

- Copilot account tests pass.
- Tests still cover CLI probe behavior, token failure degradation, and HTTP error handling.

Design assumption validated:

- A provider capability may combine CLI capture and HTTP without making generic orchestration aware of either.

### Slice 5. Move Claude Account Fetch Ownership Behind ClaudeAgent

Behavior slice:

- Move or wrap Claude account fetch behavior so `ClaudeAgent.account_stats(...)` owns the path.
- Keep `claude auth status --json` as a captured one-shot command.
- Keep statusline PTY refresh provider-owned.
- Keep stream-json fallback behavior.
- Add config-driven strategy/fallback selection only to the extent supported by current behavior.

Observable check:

- Claude account tests pass.
- Tests still cover refresh usage, statusline path, stream-json fallback, and error compaction.

Design assumption validated:

- Complex provider fetch behavior can live behind the same simple capability entrypoint as simpler providers.

### Slice 6. Remove Or Shrink Old Shared/Provider Surfaces

Behavior slice:

- Delete obsolete public provider account wrapper functions if the capability moved onto provider agents.
- Keep shared account runtime helpers only when they are genuinely provider-agnostic.
- Move files or rename modules when it makes ownership clearer.

Observable check:

- `rg` shows no old capability name remains if renamed.
- No legacy adapter or duplicate old/new API remains.
- Full test suite passes.

Design assumption validated:

- The package structure reflects provider-agent capability ownership without preserving an old parallel model.

## Relevant Files Or Surfaces

- `src/agentos/agent/accounts.py`
- `src/agentos/agent/account_runtime.py`
- `src/agentos/agent/primitives.py`
- `src/agentos/codex/agent.py`
- `src/agentos/codex/accounts.py`
- `src/agentos/claude/agent.py`
- `src/agentos/claude/accounts.py`
- `src/agentos/copilot/agent.py`
- `src/agentos/copilot/accounts.py`
- `src/agentos/pi/agent.py`
- `src/agentos/_core/process.py`
- `tests/test_agent_accounts_commands.py`
- `tests/test_agent_commands.py`
- `tests/test_process_runner.py`
- `notes/live/570-provider-agent-account-capability-refactor-impl-req.md`
- `notes/live/585-process-runner-output-modes-impl-req.md`

## Open Questions

- Should the final common method name be `account_stats(...)` or should the current `collect_account_stats(...)` name be retained as the common capability name?
- Where should account fetch config come from first: CLI options, global/project config, or only programmatic `AccountStatsRequest` construction in the first slice?
- Should provider-specific config be namespaced by provider id, provider family, or passed already narrowed to each provider?
- Should strategy/fallback config be modeled as provider dataclasses immediately, or start as small provider-local mapping parsers?

## Related Impl-Reqs

- `570-provider-agent-account-capability-refactor-impl-req.md`
- `585-process-runner-output-modes-impl-req.md`

## End Log

- 2026-05-13: Created after alignment that account stats should be a common provider-agent capability entrypoint while provider agents own implementation strategy, default/provider-specific fetch config, and any package movement needed to reflect that ownership.
- 2026-05-13: Implemented the common `account_stats(...)` provider-agent capability in `src/agentos/agent/primitives.py`, switched account orchestration in `src/agentos/agent/accounts.py` to call it, extended `AccountStatsRequest` with config pass-through, narrowed provider config in Codex/Claude/Copilot agents, and removed old `collect_*account_stats` symbols from `src` and `tests`. Focused account/agent/process tests passed.
- 2026-05-13: Updated the stale activity-log tests to match the current dirty worktree schema/path (`.agentos/activity`, schema version 2), removing the full-suite blocker. `uv run pytest` now passes with 310 tests.
