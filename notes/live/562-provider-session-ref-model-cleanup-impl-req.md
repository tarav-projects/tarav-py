# Provider SessionRef Model Cleanup - impl-req

## Impl-Req State

Provider SessionRef and provider-agent discovery/loading APIs are implemented for session-discovery providers, and Chatlas update/query/export no longer depend on the generic session bridge; the legacy `chat session` runtime bridge path and final bridge-object removal remain open.

## User Intent

Implement the clarified provider-native session model in `agentos-py`.

The accepted design is:

```text
<Provider>.Agent
  -> discovers <Provider>.SessionRef

<Provider>.Agent
  -> loads <Provider>.Session from <Provider>.SessionRef

<Provider>.Session
  -> provider-native facts for one full session

Agentos coordination
  -> list/query/index/export across provider session refs
```

`<Provider>.SessionRef` is a lightweight provider-native description of one session. It is not the full session content. It carries basic metadata and locator facts needed for listing, indexing, selection, querying, and later loading a full `<Provider>.Session`.

## Why This Exists

The current implementation moved many mechanics toward provider-native modules, but the session runtime still keeps a generic bridge architecture alive.

Current transitional objects such as `ChatSession`, `ChatSessionRecord`, provider-specific `*SessionRecord` classes, `SessionProviderConfig`, `SessionProviderContext`, and `SessionProviderIdentity` still act as a generic center between provider-native sessions and Agentos/Chatlas coordination.

That is not the clean target design.

The design should be positive and provider-native:

- `<Provider>.Agent` models one configured provider actor.
- `<Provider>.Agent` owns provider-native capabilities such as session ref discovery and session loading.
- `<Provider>.SessionRef` models one lightweight provider-native session reference.
- `<Provider>.Session` models one full native session and contains all provider-relevant facts about that session.
- Agentos-level services coordinate cross-provider list/query/index/export behavior.

## Current Situation

Durable design source:

- `notes/index/102-Agentos.Agent.Model.md`

The note now defines three provider-native anchors:

```text
<Provider>.Agent
<Provider>.SessionRef
<Provider>.Session
```

Current implementation evidence from the previous review:

- Provider-native `Agent` objects exist under provider modules such as `src/agentos/codex/agent.py`.
- Provider-native `Session` objects exist under provider modules such as `src/agentos/codex/session.py`, `src/agentos/claude/session.py`, and related provider packages.
- Chat/session orchestration still passes through generic bridge objects in `src/agentos/chat/sessions.py` and `src/agentos/chat/core.py`.
- Chatlas update session materialization still converts archived provider homes into `SessionProviderConfig` / `SessionProviderContext`, then into `ChatSession` and provider-specific record bridges before writing index rows.
- Chatlas export still resolves a Chatlas session dict and reconstructs provider-native sessions for normalization.

## Requested Change

Refactor session runtime around provider-native session refs and provider-agent session loading.

### Phase 1: Define The Runtime Boundary

Define the smallest shared coordination contract Agentos needs, without creating a generic session model.

Provider-owned objects:

```text
<Provider>.Agent
<Provider>.SessionRef
<Provider>.Session
```

Shared coordination may rely on minimal facts only:

- provider family
- configured agent identity
- native session id
- display/title hints
- created/updated timestamps
- primary/source artifact refs
- native locator facts needed to reload the full session

Acceptance signals:

- At least Codex has `Codex.SessionRef` and `Codex.Session`.
- `Codex.Agent` discovers `Codex.SessionRef` and loads `Codex.Session`.
- No new generic session wrapper is introduced.

### Phase 2: Move Discovery Onto Provider Agents

For each provider agent, expose provider-native session ref discovery and full session loading:

```text
Codex.Agent.discover_session_refs(...)
Codex.Agent.load_session(ref)

Claude.Agent.discover_session_refs(...)
Claude.Agent.load_session(ref)

Copilot.Agent.discover_session_refs(...)
Copilot.Agent.load_session(ref)
```

Existing provider discovery functions can become helpers behind the agent methods.

Acceptance signals:

- Configured provider agents return provider-native refs.
- Full sessions load through provider agents.
- Existing standalone discovery functions are private helpers or thin compatibility wrappers.

### Phase 3: Introduce Agentos Coordination Over SessionRefs

Add an Agentos-level coordination layer that consumes provider-native refs directly.

Possible concepts:

```text
SessionRefIndexRow
SessionRegistry
SessionQuery
SessionResolution
```

This layer handles cross-provider concerns:

- list
- query
- dedupe
- sort
- resolve one session
- build index rows

Acceptance signals:

- Cross-provider list/query uses `<Provider>.SessionRef`, not full sessions.
- Querying does not live on `<Provider>.Session`.
- Index rows point back to provider agent plus provider session ref.

### Phase 4: Update Chatlas Session Indexing

Change `chatlas update` session materialization.

Current shape:

```text
ChatlasArchiveConfig
  -> SessionProviderConfig
  -> SessionProviderContext
  -> ChatSession
  -> ChatSessionRecord
  -> index row
```

Target shape:

```text
ChatlasProviderContext
  -> backed ProviderAgent view
  -> <Provider>.Agent.discover_session_refs()
  -> <Provider>.SessionRef
  -> Agentos/Chatlas index row
```

Raw mirroring remains Chatlas-owned.

Acceptance signals:

- `chatlas update` writes session index rows from provider-native refs.
- Chatlas raw mirroring still uses Chatlas backing/context objects.
- Chatlas no longer depends on `ChatSession`, `ChatSessionRecord`, or `SessionProviderContext`.

### Phase 5: Update Export/Normalizer Resolution

Current export still starts from a Chatlas session dict and reconstructs provider sessions.

Target:

```text
query
  -> SessionResolution
  -> <Provider>.SessionRef
  -> <Provider>.Agent.load_session(ref)
  -> <Provider>.Session
  -> <Provider>.Normalizer
  -> Session.Model
```

Acceptance signals:

- `agentos chatlas export <query>` resolves one provider-native session ref.
- The provider agent loads the full provider-native session.
- Normalizers consume only `<Provider>.Session`.

### Phase 6: Remove Transitional Session Bridge Objects

Delete or collapse:

```text
ChatSession
ChatSessionRecord
CodexSessionRecord
ClaudeCodeSessionRecord
CopilotCliSessionRecord
GeminiCliSessionRecord
PiSessionRecord
OpenclawSessionRecord
OpencodeSessionRecord
SessionProviderConfig
SessionProviderContext
SessionProviderIdentity
```

Keep only low-level primitives if still valuable:

```text
BackingArtifact / SourceRef
timestamp helpers
path/signature helpers
```

Acceptance signals:

- `rg` finds no runtime dependency on removed bridge objects.
- Tests cover session list/query, Chatlas update, Chatlas export, and provider discovery.

## Constraints And Invariants

- Do not introduce a generic session wrapper to replace `ChatSession`.
- Do not make `<Provider>.Session` own global query, registry, index, or export semantics.
- Do not move Chatlas backing/mirroring policy into `<Provider>.Agent`; Chatlas backing remains a Chatlas concern.
- `<Provider>.Agent` owns provider-native session ref discovery and full session loading.
- `<Provider>.SessionRef` is lightweight identity and metadata, not full session content.
- `<Provider>.Session` contains all provider-relevant facts about one full native session.
- Agentos-level coordination may consume shared facts from provider session refs.
- Provider-specific objects may have different fields and behavior.
- Preserve existing user-facing CLI behavior unless a separate interface change is explicitly approved.
- Reuse existing parsing, scanning, timestamp, artifact, and normalization mechanics where they fit behind the new model boundary.
- Preserve unrelated dirty worktree changes.

## Out Of Scope

- Redesigning the user-facing provider config schema.
- Redesigning Chatlas raw storage layout.
- Changing the `Session.Model` schema unless needed to preserve the new boundary.
- Rewriting account or runner behavior except where provider-agent construction must be shared.
- Removing Chatlas backing/context objects that legitimately model Chatlas mirroring.
- Public command renames.

## Acceptance Signals

Strong acceptance signals:

- `Codex.Agent.discover_session_refs()` returns `Codex.SessionRef` objects.
- `Codex.Agent.load_session(ref)` returns `Codex.Session`.
- The same pattern is implemented for other providers supported by session discovery.
- Cross-provider session list/query/index code consumes provider-native session refs directly.
- Chatlas update writes session index rows from provider-native session refs.
- Chatlas export resolves a session ref and loads the full provider-native session before normalization.
- Provider normalizers consume provider-native sessions, not generic Chatlas session dicts.
- `ChatSession`, `ChatSessionRecord`, `SessionProviderContext`, and related bridge objects are removed from runtime code.

Behavioral acceptance:

```sh
uv run python -m pytest tests/test_chatlas_commands.py -q
uv run python -m pytest tests/test_chatlas_session_hashes.py -q
uv run python -m pytest tests/test_chat_cli_common.py -q
uv run python -m pytest tests/test_agent_commands.py -q
uv run python -m pytest -q
```

## Relevant Files Or Surfaces

Design:

- `notes/index/102-Agentos.Agent.Model.md`
- `notes/index/006-Session.Model.md`
- `notes/index/007-Chatlas.Standard.Model.Contract.md`

Current runtime surfaces:

- `src/agentos/agent/providers.py`
- `src/agentos/codex/agent.py`
- `src/agentos/codex/session.py`
- `src/agentos/claude/session.py`
- `src/agentos/copilot/session.py`
- `src/agentos/pi/session.py`
- `src/agentos/opencode/session.py`
- `src/agentos/gemini/session.py`
- `src/agentos/openclaw/session.py`
- `src/agentos/chat/sessions.py`
- `src/agentos/chat/core.py`
- `src/agentos/chatlas/core.py`
- `src/agentos/chatlas/session_model/`

Tests:

- `tests/test_chatlas_commands.py`
- `tests/test_chatlas_session_hashes.py`
- `tests/test_chat_cli_common.py`
- `tests/test_agent_commands.py`

Related impl-req:

- `notes/live/561-provider-native-agent-session-model-rewrite-impl-req.md`

## Open Questions

- Should the shared coordination types live under `agentos.sessions`, `agentos.agent.sessions`, or another package?
- Should `BackingArtifact` be renamed to `SourceRef` as part of this cleanup, or left as a later naming cleanup?
- Should all providers receive `SessionRef` in one implementation pass, or should Codex prove the pattern first?
- How much of existing `chat` command behavior should survive as Agentos session coordination versus moving behind Chatlas-specific commands?

## Related Impl-Reqs

- Builds on `notes/live/561-provider-native-agent-session-model-rewrite-impl-req.md`.
- Depends on the clarified design in `notes/index/102-Agentos.Agent.Model.md`.

## End Log

- 2026-05-09: Created after discussion clarified `<Provider>.SessionRef` as the lightweight provider-native session reference between `<Provider>.Agent` discovery and `<Provider>.Session` loading.
- 2026-05-09: Implemented the first Codex SessionRef vertical slice. Added `CodexSessionRef`, Codex session-ref discovery/read helpers, `load_codex_session`, and `CodexAgent.discover_session_refs()` / `CodexAgent.load_session()`. Existing `discover_codex_sessions` remains as a compatibility wrapper for this chunk. Focused verification passed: `uv run python -m pytest tests/test_agent_commands.py -q`, `uv run python -m pytest tests/test_codex_commands.py tests/test_chatlas_commands.py -q -k "codex"`, and `uv run python -m compileall -q src/agentos/codex tests/test_agent_commands.py`.
- 2026-05-09: Added provider-native `SessionRef` classes plus `discover_session_refs()` / `load_session()` agent APIs for Claude, Copilot CLI, Pi, OpenCode, Gemini CLI, and OpenClaw. Added shared `provider_session_paths()` helper for provider-agent home-slot session target derivation. Focused verification passed: `uv run python -m compileall -q src/agentos tests/test_agent_commands.py`, `uv run python -m pytest tests/test_agent_commands.py -q`, and `uv run python -m pytest tests/test_chatlas_commands.py -q -k "session_discovery or native"`.
- 2026-05-09: Migrated `chatlas update` session-index materialization to build raw-backed provider agents, call `<Provider>.Agent.discover_session_refs()`, and write index rows from provider-native refs. Migrated supported Chatlas Session.Model export normalizers to reconstruct provider `SessionRef`s from the selected index row and load full provider sessions through `agent.load_session(ref)`. The legacy `chat session` runtime and some Chatlas resolved-stats/provider-stats helpers still depend on `ChatSession`, `SessionProviderConfig`, `SessionProviderContext`, and provider `*SessionRecord` bridge objects. Focused verification passed: `uv run python -m compileall -q src/agentos tests`, `uv run python -m pytest tests/test_chatlas_commands.py tests/test_chatlas_session_hashes.py -q`, and `uv run python -m pytest tests/test_agent_commands.py tests/test_chatlas_commands.py tests/test_chatlas_session_hashes.py tests/test_chat_cli_common.py -q`.
- 2026-05-09: Removed Chatlas core dependencies on `ChatSession`, `SessionProviderConfig`, `SessionProviderContext`, and `SessionProviderIdentity`. `chatlas query --include-provider-stats`, `chatlas_resolved_session_stats`, and `resolve_chatlas_sessions` now operate from indexed session rows/backing artifacts instead of rebuilding bridge sessions. Full verification passed: `uv run python -m compileall -q src/agentos tests` and `uv run python -m pytest -q` (`301 passed`).
