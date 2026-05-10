# Provider Agent Account Capability Refactor - impl-req

## Impl-Req State

Implemented on 2026-05-10.

## User Intent

Move account stats collection behind provider-native agent capabilities.

The desired model is:

```txt
AgentConfig -> <Provider>.Agent -> agent account capability
```

The user explicitly agrees this is the correct direction and wants a dedicated refactor request for it.

## Why This Exists

The account stats command now starts from real configured Agentos agents:

- `AgentConfig` is parsed from config.
- `load_configured_agents()` builds real `<Provider>.Agent` objects.
- `AccountProviderContext` wraps an `Agent`.

That is good, but account collection still switches centrally on provider name inside `agentos.agent.accounts`. This keeps provider account behavior in the Agentos coordination layer instead of on the provider agent model.

The result is only halfway aligned with the current design direction:

```txt
AgentConfig -> <Provider>.Agent -> AccountProviderContext -> central provider switch
```

The target is:

```txt
AgentConfig -> <Provider>.Agent -> account capability
```

## Current Situation

The relevant command surface is:

```sh
agentos agent accounts stats
agentos agent accounts stats --output=usage --refresh-usage
```

Current code shape:

- `src/agentos/agent/providers.py` builds configured provider agents.
- `src/agentos/agent/accounts.py` selects account-capable agents and wraps them in `AccountProviderContext`.
- `AccountProviderContext` delegates runtime fields to the real agent:
  - `provider`
  - `instance_id`
  - `label`
  - `cli_command`
  - `env`
  - `timeout_sec`
  - `account_live_usage_refresh`
  - `account_usage_progression_limit`
- `_collect_account_payload()` still branches on `context.provider`.
- Codex, Claude Code, and Copilot account collectors still live centrally in `src/agentos/agent/accounts.py`.
- Command construction is assembled centrally from `instance.cli_command` plus provider-specific argument tuples.

This means Agentos owns too much provider-specific account behavior.

## Requested Change

Refactor account stats collection so account behavior is owned by provider agents or provider-owned account modules.

The target responsibilities:

- `<Provider>.Agent` models provider reality and owns provider-native capabilities.
- Account collection is a provider-agent capability.
- Agentos account command code coordinates:
  - selecting configured agents
  - filtering providers/instance ids
  - running collection concurrently
  - assembling aggregate payloads
  - formatting JSON/Markdown/usage output
  - persisting history
- Agentos account command code should not know Codex, Claude Code, or Copilot account command details.

The account collector flow should become conceptually:

```txt
configured Agentos agents
  -> filter account-capable agents
  -> agent.collect_account_stats(request)
  -> Agentos aggregate/format/persist
```

Exact method names are not fixed, but the provider-owned capability boundary is.

## Constraints And Invariants

- Do not redesign the account stats output schema in this refactor.
- Keep the user-facing command path and flags stable.
- Keep `agentos agent accounts stats`, `--output=usage`, `--refresh-usage`, `--provider`, instance-id filtering, and `--project` behavior stable.
- Do not involve `<Provider>.Session` or `SessionRef`; account stats is agent/account runtime state, not session data.
- Do not move account stats history persistence into provider agents.
- Do not move usage output formatting into provider agents.
- Do not add compatibility aliases.
- Do not revert unrelated dirty worktree changes.
- Preserve existing subprocess behavior unless a provider-agent method makes the same behavior clearer.
- Account-specific config fields may remain on `AgentConfig` and `AgentBase` if they are needed to build/configure provider agents.

## Out Of Scope

- Redesigning `agent accounts stats --loop`.
- Changing provider usage parsing semantics.
- Changing account stats JSON, Markdown, or usage output schemas.
- Changing Chatlas behavior.
- Changing Session model behavior.
- Renaming config fields.
- Reworking history tape storage.
- Adding provider cancellation hooks unless needed by a later loop implementation.

## Acceptance Signals

- `agentos.agent.accounts._collect_account_payload()` no longer switches on provider family to call central Codex/Claude/Copilot collectors.
- Provider-specific account collection code is moved to provider-owned surfaces, such as:
  - `agentos.codex.agent` / `agentos.codex.accounts`
  - `agentos.claude.agent` / `agentos.claude.accounts`
  - `agentos.copilot.agent` / `agentos.copilot.accounts`
- The Agentos account coordination layer invokes account capability behavior through the real provider agent.
- `AccountProviderContext`, if retained, is only a narrow coordination/view wrapper over an `Agent`, not a provider collector owner.
- Provider-specific command arguments like `login status`, `auth status --json`, Copilot auth checks, Codex app-server usage checks, and Claude live usage refresh no longer live in central `agentos.agent.accounts`.
- Existing focused account command tests pass.
- Tests demonstrate that account stats collectors receive/use real `<Provider>.Agent` objects, not duplicated account config DTOs.

## Implementation Shape

Implement in vertical slices.

### Slice 1. Define Account Capability Boundary

- Add a small account stats request/result surface that provider agents can implement.
- Keep the shape narrow:
  - request includes refresh usage and any needed account-runtime options
  - result remains a provider account payload dict compatible with existing aggregation
- Prefer provider-agent methods over a new runtime DTO.

Observable check:

- A test can call one provider agent account capability directly and receive the same account payload shape the central collector expects.

### Slice 2. Move One Provider First

- Move Codex account collection behind `Codex.Agent`.
- Preserve current Codex auth and usage behavior.
- Keep Agentos aggregation output unchanged.

Observable check:

- `agentos agent accounts stats --provider codex` still returns the same payload shape.
- A test proves central account coordination does not call a Codex-specific central collector.

### Slice 3. Move Claude Code

- Move Claude Code auth and live usage refresh behavior behind `Claude.Agent`.
- Keep `--refresh-usage` and `account_live_usage_refresh` semantics unchanged.
- Keep Claude refresh workspace/history interactions where they belong; do not move Agentos history persistence into the provider.

Observable check:

- Existing Claude account stats and live usage tests pass.
- The provider agent owns the provider-specific subprocess command details.

### Slice 4. Move Copilot

- Move Copilot auth and usage collection behind `Copilot.Agent`.
- Preserve token/env behavior and error shaping.

Observable check:

- Existing Copilot account tests pass.
- Central account coordination no longer has Copilot-specific branches.

### Slice 5. Delete Central Provider Switch

- Replace `_collect_account_payload()` provider branching with a capability call.
- Keep unsupported-provider validation at the selection/capability boundary.
- If an account-capable protocol is needed, keep it minimal and focused on behavior, not a parallel config model.

Observable check:

- Searching `src/agentos/agent/accounts.py` shows no provider-specific collector branches for Codex, Claude Code, or Copilot.
- Account command tests still pass.

### Slice 6. Cleanup And Documentation

- Remove unused central helper functions that moved to provider modules.
- Keep shared generic subprocess helpers central only if they are truly provider-agnostic utility, not provider behavior.
- Update this impl-req end log after implementation.

Observable check:

- Focused tests pass:

```sh
uv run pytest tests/test_agent_accounts_commands.py tests/test_agent_commands.py -q
```

## Relevant Files Or Surfaces

- `src/agentos/agent/accounts.py`
- `src/agentos/agent/primitives.py`
- `src/agentos/agent/providers.py`
- `src/agentos/codex/agent.py`
- `src/agentos/claude/agent.py`
- `src/agentos/copilot/agent.py`
- Potential provider-owned modules:
  - `src/agentos/codex/accounts.py`
  - `src/agentos/claude/accounts.py`
  - `src/agentos/copilot/accounts.py`
- `tests/test_agent_accounts_commands.py`
- `tests/test_agent_commands.py`

## Open Questions

- Should the account capability live directly as `<Provider>.Agent.collect_account_stats(...)`, or should the agent expose a small `account` capability object?
- Should shared subprocess helpers stay in `agentos.agent.accounts`, move to a provider-neutral helper module, or be duplicated locally until the provider boundary stabilizes?
- Should account capability support streaming/progressive partial results, or should streaming remain entirely in the Agentos coordination layer over per-agent futures?
- Should unsupported providers expose no account method, or should there be an explicit account-capable protocol check?

## Related Impl-Reqs

- `566-agent-model-duplication-cleanup-impl-req.md`
- `568-agent-session-model-duplication-followup-impl-req.md`
- `569-agent-accounts-stats-loop-redesign-impl-req.md`

## End Log

- 2026-05-10: Created as a follow-up to the account stats loop assessment. The user confirmed the target model: `AgentConfig -> <Provider>.Agent -> agent account capability`.
- 2026-05-10: Implemented the provider-agent account capability refactor.
  - Added a narrow provider-facing account runtime surface in `src/agentos/agent/account_runtime.py`.
  - Added `collect_account_stats(...)` capability methods on Codex, Claude, and Copilot agents.
  - Moved provider-specific account command construction and collection into:
    - `src/agentos/codex/accounts.py`
    - `src/agentos/claude/accounts.py`
    - `src/agentos/copilot/accounts.py`
  - Changed `agentos.agent.accounts._collect_account_payload()` to call the real provider agent capability instead of switching on provider family.
  - Removed central Codex/Claude/Copilot account collectors and provider command construction from `src/agentos/agent/accounts.py`.
  - Kept Agentos account coordination responsible for filtering, concurrency, aggregation, formatting, and persistence.
  - Updated focused tests so provider account tests use real provider agent objects rather than duplicated account DTOs.
  - Verification:
    - `uv run python -m compileall -q src/agentos/agent src/agentos/codex src/agentos/claude src/agentos/copilot`
    - `uv run pytest tests/test_agent_accounts_commands.py tests/test_agent_commands.py -q`
