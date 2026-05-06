# Agent Provider Infra Redesign - impl-req

## Impl-Req State

Implemented for the first behavior-preserving refactor pass: provider-family metadata is shared outside chat, home and agent-run provider surfaces exist, and `agent run` resolves an internal `AgentosAgent` wrapper before execution.

## User Intent

Update the existing provider infrastructure toward the new Agentos agent design.

The design direction is:

- `Agentos.Agent` is the runnable provider CLI configuration model.
- `Agent.Instance` should not exist as a first-class design concept.
- Provider behavior should be organized by subsystem, using the conceptual shape `<Subsystem>.<family>.Provider`.
- Examples include `Agent.Codex.Provider`, `Home.Codex.Provider`, `Session.Codex.Provider`, `Account.Codex.Provider`, and `Chatlas.Codex.Provider`. These names are examples, not final API names.
- Provider support is per subsystem. A family can support agent running but not account stats, or Chatlas raw archiving but not a runnable agent.

## Why This Exists

Current provider infrastructure works, but provider knowledge is fragmented and overloaded.

The main overloaded object is `ProviderInstance`, loaded from `agent.instances[]`. It currently carries user config and derived provider facts for launch, home topology, session discovery, Chatlas raw retention, and account behavior. This makes it hard to evolve toward explicit `Agentos.Agent`, `Provider.Account`, `Agent.Home`, `Agent.Session`, and `Agent.RunProfile` components.

The target is not to build a universal provider class. The target is to make provider-specific behavior explicit at each subsystem boundary while keeping shared provider-family metadata discoverable.

## Current Situation

Provider-related code currently lives across several surfaces:

- `src/agentos/chat/providers.py`
  - Defines `ProviderFamily`, `ProviderHomeSlot`, `ChatProviderSpec`, canonical provider family lists, home-slot topology, Chatlas include/exclude defaults, provider launch defaults, config loading from `agent.instances[]`, and the overloaded `ProviderInstance` dataclass.
  - This file currently mixes provider registry, home topology, run defaults, config parsing, identity/fingerprint behavior, and generic helper functions.
- `src/agentos/agent/commands.py`
  - Implements `agent list` and `agent run`.
  - Resolves `ProviderInstance` directly and builds subprocess commands from fields such as `cli_command`, `run_args`, `default_model`, `model_flag`, `prompt_flag`, and `env`.
- `src/agentos/chat/core.py`
  - Defines `SessionProviderHandler` and per-family session discovery/find/stats adapters.
  - Builds handlers from `canonical_chat_provider_specs()` and selected `ProviderInstance` records.
- `src/agentos/chat/accounts.py`
  - Defines `AccountProviderHandler`, account contexts, and account-stat collectors for supported providers.
  - Reuses `ProviderInstance` for account configuration.
- `src/agentos/chatlas/raw.py`
  - Defines `ChatlasProviderHandler` and raw mirroring behavior.
  - Builds Chatlas provider handlers from `canonical_chat_provider_specs()`.
- `src/agentos/chatlas/core.py`
  - Selects configured provider instances for Chatlas using `chatlas.instance_ids`.
  - Reuses `ProviderInstance` and Chatlas raw provider handlers.
- `src/agentos/codex/commands.py`
  - Contains Codex-specific mux/account behavior that reads `agent.instances[]` and expects `ProviderInstance`.
- Tests under `tests/test_agent_commands.py`, `tests/test_chat_accounts_commands.py`, `tests/test_chatlas_commands.py`, `tests/test_chat_commands.py`, and related session/model tests encode the current behavior.

The active design-session artifact is `notes/live/557-agentos-agent-model-design-session.md`.

## Requested Change

Refactor provider infrastructure in stages so provider behavior is organized by subsystem while current user-facing behavior remains intact during the first pass.

### Phase 1: Introduce provider-infra vocabulary without changing behavior

Add a small provider-infra layer that can represent:

- provider family identity
- shared home-slot topology
- provider family capability metadata
- subsystem-specific provider adapters

The implementation should not create one large all-purpose provider class. It should make room for subsystem provider adapters, conceptually shaped like:

- `Agent.<family>.Provider`
- `Home.<family>.Provider`
- `Session.<family>.Provider`
- `Account.<family>.Provider`
- `Chatlas.<family>.Provider`

Exact module names and class names are implementation details. Prefer names that fit the existing Python package style.

### Phase 2: Separate shared provider metadata from subsystem adapters

Move or isolate shared provider-family metadata from `src/agentos/chat/providers.py` so it is no longer implicitly owned by the chat subsystem.

Shared metadata should cover only facts that are truly shared, such as:

- canonical provider family ids
- supported home slot keys and default home roots
- stable provider family lookup and validation

Subsystem-specific facts should move behind subsystem providers:

- run command defaults belong to the agent/run subsystem
- session discovery and session source stats belong to the session subsystem
- account stats support belongs to the account subsystem
- Chatlas raw include/exclude policies belong to the Chatlas subsystem

### Phase 3: Introduce Agentos.Agent as the runnable config model

Introduce an internal `Agentos.Agent` model or equivalent loader result for `agent run`.

This should replace `ProviderInstance` as the conceptual object used by the agent runner. The current `agent.instances[]` config can remain as an input format during this phase, but the loaded object should not be described or expanded as `Agent.Instance`.

`Agentos.Agent` should resolve enough provider-specific config to:

- build the provider-native command
- prepare environment, home, account, cwd, and prompt context
- run the subprocess
- return or expose enough metadata to relate the run to a session

Provider-specific implementation should be allowed. For example, Codex and Claude do not need to share native account or home semantics.

### Phase 4: Split Home, Session, Account, and Chatlas provider responsibilities

Refactor existing handlers toward subsystem-owned provider adapters.

Expected direction:

- `Home.<family>.Provider` owns home-slot validation and derived paths.
- `Session.<family>.Provider` owns session discovery/find/source stats.
- `Account.<family>.Provider` owns usage/account collection behavior.
- `Chatlas.<family>.Provider` owns raw mirroring include/exclude behavior.
- `Agent.<family>.Provider` owns command/run-profile materialization.

This can be incremental. Do not require every provider family to implement every subsystem provider.

### Phase 5: Reduce the role of ProviderInstance

After subsystem providers exist, reduce `ProviderInstance` to either:

- a transitional config DTO for existing `agent.instances[]`, or
- a renamed, narrower data model that no longer implies the removed `Agent.Instance` concept.

Do not add new behavior to `ProviderInstance` while performing this refactor. New behavior should land in `Agentos.Agent`, `Agent.Home`, `Provider.Account`, `Agent.Session`, `Agent.RunProfile`, or subsystem provider adapters.

### Phase 6: Update command surfaces and docs

Update command help, README text, and tests to reflect the new model where useful.

The first implementation pass should preserve existing command behavior unless the user explicitly approves a command/interface change. In particular:

- `agentos agent run` should continue to run configured provider CLI commands.
- `agentos agent accounts stats` should continue to work.
- Chatlas provider selection through configured instance ids should continue to work until a later config migration is designed.

## Constraints And Invariants

- Do not introduce `Agent.Instance` as a new design or public API concept.
- Do not create a universal provider interface that forces all provider families to implement all subsystem behaviors.
- Provider support must be capability-based and per subsystem.
- Keep provider-specific behavior provider-specific. Do not fake uniform account, home, command, or session semantics across Codex, Claude, Gemini, Pi, Copilot, OpenCode, and OpenClaw.
- Preserve current behavior during internal refactoring unless a specific behavior change is explicitly requested.
- Keep config migration separate from internal refactoring unless a small compatibility-preserving parser change is necessary.
- Follow `agentos-py/AGENTS.md`: use `uv`, prefer direct `agentos ...` only when checking installed CLI behavior, and refresh installed CLI with `uv tool install --reinstall --editable .` after changing CLI code.
- Do not add backward-compatibility aliases or compatibility layers unless explicitly requested. For this impl-req, preserving existing behavior means avoiding unnecessary public breakage, not adding duplicate new names.

## Out Of Scope

- Designing the full final config schema for `Agentos.Agent`, `Agent.Home`, `Provider.Account`, `Agent.Session`, and `Agent.RunProfile`.
- Implementing disposable auxiliary home creation.
- Implementing a new session capture/run-file format.
- Removing all current `agent.instances[]` support in one pass.
- Redesigning Chatlas storage or the standard session model.
- Renaming every provider-related class in one mechanical sweep without improving boundaries.

## Acceptance Signals

- Provider-family metadata is no longer treated as chat-owned by default.
- Run defaults are not stored only as helper functions in `chat.providers`.
- Session, account, Chatlas raw, and agent-run provider adapters are distinguishable subsystem surfaces.
- `agent run` uses an internal runnable agent model or provider-run adapter instead of directly treating `ProviderInstance` as the runnable concept.
- Existing focused tests still pass for agent run, account stats, Chatlas provider selection/update, and session discovery.
- New or updated tests show that provider capability support is per subsystem.
- Documentation and comments avoid introducing `Agent.Instance` as the target model.

Suggested verification commands:

```sh
uv run pytest tests/test_agent_commands.py -q
uv run pytest tests/test_chat_accounts_commands.py -q
uv run pytest tests/test_chatlas_commands.py -q
uv run pytest tests/test_chat_commands.py tests/test_chat_extract_commands.py -q
```

Run narrower subsets first while refactoring, then broaden before closing.

## Relevant Files Or Surfaces

- `notes/live/557-agentos-agent-model-design-session.md`
- `src/agentos/chat/providers.py`
- `src/agentos/agent/commands.py`
- `src/agentos/chat/core.py`
- `src/agentos/chat/accounts.py`
- `src/agentos/chatlas/raw.py`
- `src/agentos/chatlas/core.py`
- `src/agentos/codex/commands.py`
- `tests/test_agent_commands.py`
- `tests/test_chat_accounts_commands.py`
- `tests/test_chatlas_commands.py`
- `tests/test_chat_commands.py`
- `tests/test_chat_extract_commands.py`

## Open Questions

- Should the first shared provider-infra module live under `agentos.providers`, `agentos.agent.providers`, or another package?
- Should `ProviderInstance` be renamed in this refactor or first narrowed while keeping its current name?
- Should `ChatProviderSpec` be split immediately, or should the first pass add a shared provider registry and move consumers gradually?
- Should `agent.instances[]` remain the config input name for the first internal refactor, or should a separate config-schema design session precede implementation?

## Related Impl-Reqs

- `notes/live/557-agentos-agent-model-design-session.md` is the active design-session source for the Agentos agent model.

## End Log

- 2026-05-06: Created impl-req after scanning current provider infrastructure and active design-session notes.
- 2026-05-06: Implemented the first internal refactor slice. Added shared provider-family metadata in `src/agentos/providers.py`, moved agent run defaults into `src/agentos/agent/run_profiles.py`, added `src/agentos/home/providers.py` for home subsystem provider topology, added `src/agentos/agent/providers.py` with `AgentosAgent` run resolution, updated `agent run` to use the wrapper, made chat provider specs consume shared home topology through the home provider surface, refreshed agent CLI wording, refreshed the installed CLI, and verified with the full test suite (`307 passed`).
