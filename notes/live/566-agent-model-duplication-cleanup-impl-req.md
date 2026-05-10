# Agent Model Duplication Cleanup - impl-req

## Impl-Req State

This request is partially implemented; the remaining work should preserve the lightweight `<Provider>.SessionRef` / full `<Provider>.Session` responsibility split before moving more session behavior.

## User Intent

Remove unnecessary duplicated Agent model shapes from the Agentos Python CLI/runtime.

The user wants the codebase to converge on a clean model where:

- `AgentConfig` is the parsed configuration input needed to build an agent.
- `Agentos.Agent` / `<Provider>.Agent` is the runtime object.
- Provider agent classes own provider-native behavior, including session discovery/loading where applicable.
- Subsystems such as accounts, sessions, registry/query, and Chatlas should use real agent/session objects or explicit subsystem capability objects instead of copying agent fields into parallel context/config DTOs.

## Why This Exists

The recent refactor moved the design away from legacy `ProviderInstance` / generic session bridge architecture and toward `<Provider>.Agent`, `<Provider>.SessionRef`, and `<Provider>.Session` objects.

The codebase still carries several duplicated Agent-like structures:

- `AgentConfig`
- `Agent` protocol
- `<Provider>Agent` dataclasses with the same copied field set
- `ConfiguredAgent` alias
- `ProviderAgentContext`
- account-specific `AccountProviderConfig` and `AccountProviderContext`
- provider-specific account mirror objects such as `CodexAgentAccounts`
- duplicated provider/home/chat provider specs

This creates drift pressure: each subsystem can silently invent its own partial Agent model.

## Current Situation

The current code has the right high-level direction, but too much duplicated shape remains.

Observed duplication points from code inspection:

- `agentos.agent.primitives.AgentConfig` and `agentos.agent.primitives.Agent` repeat a large field set.
- Each provider agent class repeats the same dataclass fields, `from_config()` mapping, and `summary()` implementation.
- `agentos.agent.providers.ConfiguredAgent = Agent` is a name alias that preserves old transitional language without adding semantics.
- `agentos.agent.sessions.ProviderAgentContext` wraps a real agent and copies provider, summary, identity, fingerprint, URI key, and target path state.
- `agentos.agent.sessions.ProviderSessionRefEntry` wraps a provider `SessionRef` and centralizes query/URI/registry behavior around the wrapper.
- `agentos.agent.session_refs` uses central `isinstance` chains to know provider-specific `SessionRef` artifact, display, timestamp, and native payload semantics.
- `agentos.agent.accounts.AccountProviderConfig` and `AccountProviderContext` duplicate a subset of Agent fields for the accounts subsystem.
- `agentos.codex.accounts.CodexAgentAccounts` duplicates account context fields again.
- `agentos.providers.ProviderFamilySpec`, `agentos.home.providers.HomeProvider`, and `agentos.agent.config.ChatProviderSpec` overlap around provider family/home slots; `ChatProviderSpec` also mixes Chatlas defaults into the Agent config path.
- Agent selection helpers exist both for configs and runtime agents.

## Requested Change

Refactor the Agent model code so Agent state has one obvious source of truth and subsystem-specific objects stop duplicating Agent fields unnecessarily.

The implementation should:

1. Introduce or consolidate a shared Agent runtime base/helper for common Agent fields, identity, summary rendering, and terminal run resolution.
2. Reduce provider agent classes to provider identity plus provider-native behavior.
3. Keep `AgentConfig` as constructor input from config/CLI/profile merging, but avoid treating it as a runtime Agent duplicate.
4. Remove the `ConfiguredAgent` alias and use `Agent` / provider agent types directly.
5. Replace account-specific provider config/context duplication with real Agent objects or clear account capability adapters.
6. Thin `ProviderAgentContext` so it only contains coordination/cache data that is not already available from the agent, or remove it if call sites can use the agent directly.
7. Remove provider-specific session behavior from central Agentos helpers, but place each behavior on the right provider object: lightweight list/query/load-pointer facts on `<Provider>.SessionRef`, full provider-native session/export/normalization facts on `<Provider>.Session`.
8. Separate Chatlas-specific defaults/config from the core Agent provider/home model.
9. Consolidate duplicated selection-by-profile/instance logic into one helper where possible.

## Constraints And Invariants

- Do not add backwards-compatibility aliases unless explicitly requested.
- Keep the public CLI behavior stable unless this request or a related accepted impl-req explicitly changes it.
- `--profile` remains the user-facing name for selecting a configured agent profile.
- `AgentConfig` may remain as the parsed/merged construction DTO.
- Provider agents remain the runtime objects used by commands and subsystems.
- A provider agent may contain provider-specific fields only when they are needed to configure or operate the provider runtime.
- Session-content facts belong on `<Provider>.Session` or `<Provider>.SessionRef`, not on Agent objects.
- `<Provider>.SessionRef` is a lightweight identity/lookup handle with minimal metadata needed to list, resolve, dedupe, and load a full session.
- `<Provider>.Session` is the full provider-native model for one session and owns richer session facts, full native payloads, artifact interpretation, and normalization inputs.
- `<Provider>.Session.sources()` should expose provider/session source refs directly; Chatlas and other downstream subsystems should consume those refs without requiring a new Agentos-level backing-artifact target object.
- Querying, registry/indexing, and cross-provider coordination belong above provider session objects.
- Chatlas-specific backing/mirroring/defaults are Chatlas concerns, not core provider Agent model concerns.
- Prefer small vertical slices with tests over a broad unverified rewrite.
- Preserve existing user changes in the worktree.

## Out Of Scope

- Redesigning Chatlas update/indexing behavior beyond removing accidental Agent model duplication.
- Removing the full session bridge architecture unless required by this cleanup slice; that belongs to the provider session cleanup impl-req.
- Renaming all persisted config fields in one pass unless the change is necessary and tests can cover it.
- Changing provider-native session discovery semantics.
- Reworking account usage collection algorithms or display output beyond model-boundary cleanup.

## Acceptance Signals

- Provider agent classes no longer repeat a large identical field list, `from_config()` mapping, and `summary()` implementation.
- `ConfiguredAgent` is gone or reduced to no active use.
- Account stats code consumes real Agent runtime objects or explicit capability adapters without parallel Agent-like config/context DTOs.
- Session coordination wraps agents only for non-agent coordination state, or uses agents directly.
- Provider-specific session facts are no longer centralized primarily through long `isinstance` chains in `agentos.agent.session_refs`; lightweight facts live on refs and full session facts live on provider sessions.
- Chatlas-specific include/exclude defaults are not part of a generic Agent/provider spec object.
- Tests for `agentos agent list`, `agentos agent run`, `agentos agent accounts stats`, and session listing/querying still pass.
- New tests or updated tests cover any changed construction/selection behavior.

## Implementation Shape

Implement in vertical slices. Each slice should leave the CLI runnable and tests meaningful.

### Slice 1. Shared Agent Runtime Shape

- Create a single common implementation for shared Agent fields and `summary()`.
- Keep provider classes as concrete provider runtime classes.
- Convert one or two low-risk providers first, then apply the same pattern to the rest.
- Keep `AgentConfig` as the parser/constructor DTO.
- Verify `agent list` and `agent run --dry-run` tests.

### Slice 2. Provider Construction Cleanup

- Replace repeated `from_config()` field-copy code with a shared helper or constructor path.
- Keep provider validation explicit: a `CodexAgent` should still reject non-`codex` config.
- Remove `ConfiguredAgent` if call sites can use the `Agent` protocol or concrete provider union directly.

### Slice 3. Account Capability Cleanup

- Refactor account stats selection to operate on runtime agents.
- Delete or shrink `AccountProviderConfig`.
- Delete or shrink `AccountProviderContext`.
- Reassess `CodexAgentAccounts`; keep only if it expresses real Codex account capability behavior rather than copied context fields.
- Verify account command tests.

### Slice 4. Session Coordination Cleanup

- Thin or remove `ProviderAgentContext`.
- Keep only computed/cached coordination data that is genuinely not part of Agent state.
- Ensure session listing, resolving, and stats still use provider agents to discover/load provider session refs.

### Slice 5. SessionRef / Session Behavior Cleanup

- Define the explicit split between `<Provider>.SessionRef` and `<Provider>.Session` before moving behavior.
- Keep `<Provider>.SessionRef` focused on session identity, minimal display/list metadata available without loading, timestamps available from the source, and source pointers needed to load the full session.
- Move full native payloads, richer source/artifact interpretation, normalization inputs, and content-derived metadata to `<Provider>.Session`.
- Add a small session source/ref shape only if needed to express `Session.sources()`; do not introduce a new target `BackingArtifact` abstraction for Chatlas.
- Replace central `isinstance` chains with protocol methods or provider-local adapters, but do not bloat refs into half-session objects.
- Keep cross-provider query/registry behavior above the provider objects.

### Slice 6. Provider Spec Boundary Cleanup

- Reassess `ProviderFamilySpec`, `HomeProvider`, and `ChatProviderSpec`.
- Keep one core provider/home source for provider reality.
- Move Chatlas include/exclude defaults into Chatlas-owned configuration/capability code.

## Relevant Files Or Surfaces

- `agentos-py/src/agentos/agent/primitives.py`
- `agentos-py/src/agentos/agent/config.py`
- `agentos-py/src/agentos/agent/providers.py`
- `agentos-py/src/agentos/agent/commands.py`
- `agentos-py/src/agentos/agent/accounts.py`
- `agentos-py/src/agentos/agent/account_commands.py`
- `agentos-py/src/agentos/agent/sessions.py`
- `agentos-py/src/agentos/agent/session_refs.py`
- `agentos-py/src/agentos/providers.py`
- `agentos-py/src/agentos/home/providers.py`
- `agentos-py/src/agentos/codex/agent.py`
- `agentos-py/src/agentos/claude/agent.py`
- `agentos-py/src/agentos/copilot/agent.py`
- `agentos-py/src/agentos/gemini/agent.py`
- `agentos-py/src/agentos/openclaw/agent.py`
- `agentos-py/src/agentos/opencode/agent.py`
- `agentos-py/src/agentos/pi/agent.py`
- `agentos-py/src/agentos/agents/agent.py`
- `agentos-py/src/agentos/codex/accounts.py`
- `agentos-py/tests/test_agent_commands.py`
- `agentos-py/tests/test_agent_accounts_commands.py`
- `agentos-py/tests/test_codex_commands.py`

Related design and implementation notes:

- `agentos-py/notes/live/560-agentos-agent-session-model-design-summary.md`
- `agentos-py/notes/live/561-provider-native-agent-session-model-rewrite-impl-req.md`
- `agentos-py/notes/live/562-provider-session-ref-model-cleanup-impl-req.md`
- `agentos-py/notes/live/565-agent-command-profile-and-chat-package-reorg-impl-req.md`

## Open Questions

- Should the common Agent runtime shape be implemented as a dataclass base class, composition around `AgentConfig`, or a small helper module that preserves independent provider dataclasses?
- Should account collection become methods/capabilities on each provider agent, or should it remain an Agentos account subsystem that accepts provider agents?
- How far should this implementation pass go into the `SessionRef` / `Session` cleanup versus leaving that to the dedicated session-ref impl-req?
- Should Chatlas include/exclude config be moved immediately, or only after the Agent class duplication is removed?

## Related Impl-Reqs

- `561-provider-native-agent-session-model-rewrite-impl-req.md` defines the broader provider-native Agent/Session target.
- `562-provider-session-ref-model-cleanup-impl-req.md` defines the provider `SessionRef` direction.
- `565-agent-command-profile-and-chat-package-reorg-impl-req.md` covers CLI/profile and package reorganization context.

## End Log

- 2026-05-10: Created from codebase inspection of duplicated Agent model/state objects after the provider agent/session refactor discussion.
- 2026-05-10: Partially implemented shared `AgentBase`, provider construction cleanup, account context cleanup, and a first thinning of `ProviderAgentContext`; remaining session cleanup was realigned so lightweight facts stay on `<Provider>.SessionRef` while full provider-native facts belong on `<Provider>.Session`.
- 2026-05-10: Moved lightweight ref display/query metadata methods onto provider `SessionRef` classes and removed the matching central `isinstance` dispatch from `agentos.agent.session_refs`; backing artifact interpretation and full payload behavior remain out of refs.
- 2026-05-10: Moved Chatlas raw include/exclude defaults out of the generic agent provider spec and into `agentos.chatlas.raw`; the provider spec now carries provider/home/session-discovery facts only.
- 2026-05-10: Moved lightweight ref sort timestamp calculation onto provider `SessionRef` classes; central dispatch now remains only for heavier backing-artifact and created-timestamp extraction concerns.
- 2026-05-10: Clarified that Chatlas should consume `<Provider>.Session.sources()` directly; any existing `BackingArtifact` use is transitional compatibility, not a new target design object.
