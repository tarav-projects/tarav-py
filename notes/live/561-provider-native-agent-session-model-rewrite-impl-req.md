# Provider-Native Agent Session Model Rewrite - impl-req

## Impl-Req State

Implementation pass complete: provider-native agent/session slices, provider-owned Chatlas retention policy, narrowed config/context boundaries, provider-session Chatlas normalization, legacy model symbol removal, flat run-profile removal, and verification/audit have been completed.

## User Intent

Rewrite the Agentos Python provider/agent/session runtime model around provider-native modules and objects.

The accepted design direction is:

- Do not let the existing `ProviderInstance`, `SessionSource`, or subsystem handler model shape the new implementation.
- Reuse working functionality where useful, but treat current code as mechanics to extract, not architecture to preserve.
- Avoid a generic central `agentos.providers` model surface as the conceptual center.
- Make provider-specific modules the centers of provider behavior.
- Use `<Provider>.Agent` and `<Provider>.Session` as the two primary provider-native anchors.
- Let subsystem behavior hang from the provider agent where useful.
- Keep `Agentos.Session` / `Session.Model` provider-agnostic derived output.

Target conceptual shape:

```text
agentos.agent
  Agentos.Agent abstract concept
  shared runner/config/terminal primitives only

agentos.codex
  Codex.Agent
  Codex.Session
  Codex.Normalizer

agentos.claude
  Claude.Agent
  Claude.Session
  Claude.Normalizer

agentos.pi
  Pi.Agent
  Pi.Session
  Pi.Normalizer
```

Subsystem behavior should attach to provider agents as provider-specific capabilities:

```text
Codex.Agent.Runner
Codex.Agent.Chatlas
Codex.Agent.Accounts
Codex.Agent.Home
```

Exact Python module/class names are implementation details, but the model boundary is not: provider-native modules own provider behavior; shared Agentos code only owns minimal common primitives and orchestration contracts.

## Why This Exists

At request time, the codebase contained a lot of working functionality, but its model was wrong for the accepted design.

Provider-related code was organized around generic or subsystem-owned shapes:

- `ProviderInstance` mixed configured actor data, home roots, launch config, session discovery facts, account behavior, Chatlas raw policy, identity/fingerprint behavior, and transitional config semantics.
- `SessionSource` is close to native session data, but it is named and shaped as a chat-discovery source, not as `<Provider>.Session`.
- `SessionProviderHandler`, `AccountProviderHandler`, and `ChatlasProviderHandler` describe subsystem provider adapters as separate centers.
- `AgentosAgent` wrapped `ProviderInstance` instead of being a provider-native agent.
- `run_profiles.py` encodes flat provider command defaults that risk becoming a generic schema.

The newer design explicitly rejects letting that existing model remain the architecture. Agentos should not treat "provider" as one central object with all capabilities. It should model concrete provider agents and provider sessions first, with shared primitives used only where they genuinely fit.

## Current Situation

Relevant original/current surfaces:

- `src/agentos/providers.py`
  - Shared provider family list, home-slot topology, and home anchors.
  - This is useful as low-level vocabulary, but it should not become the conceptual center of the model.
- `src/agentos/chat/providers.py`
  - Now defines `ChatProviderSpec`, config parsing from `agent.instances[]`, `LegacyProviderConfig`, config helpers, and selection helpers.
  - This remains the legacy config input boundary, not a runtime provider model.
- `src/agentos/agent/providers.py`
  - Now resolves configured provider-native agents through narrow shared primitives.
- `src/agentos/agent/run_profiles.py`
  - Deleted during implementation; command defaults now live only as legacy config input mechanics, with a narrow default-run capability query in `agent.providers`.
- `src/agentos/chat/sessions.py`
  - Now defines `ChatSession`, `ChatSessionRecord`, and provider-specific record bridge classes over provider-native sessions.
  - Provider-native session facts have moved into `<Provider>.Session` modules.
- `src/agentos/chat/core.py`
  - Owns session discovery/find/stats handlers and many provider-specific scanners/readers.
  - This contains reusable mechanics for session discovery and stats, but currently makes chat/session discovery the architectural owner.
- `src/agentos/chat/accounts.py`
  - Owns account provider contexts and account-stat collectors.
  - This contains useful provider-specific account mechanics, but current context objects still depend on `ProviderInstance`.
- `src/agentos/chatlas/raw.py`
  - Owns Chatlas raw mirroring handlers, include/exclude policy, and archive mechanics.
  - This should become provider-agent Chatlas capability behavior, not a separate generic provider center.
- `src/agentos/chatlas/core.py`
  - Owns Chatlas settings, provider selection, archive/update/query/index materialization, and raw-to-index flow.
  - It currently reconstitutes provider instances and emits normalized Chatlas session dicts.
- `src/agentos/chatlas/session_model/`
  - Owns Chatlas standard session model export and provider-specific raw normalizers.
  - Current export normalizes from a Chatlas session `dict`; target export should normalize from `<Provider>.Session`.
- `src/agentos/codex/commands.py`
  - Contains Codex-specific mux behavior that still loads `agent.instances[]` into `ProviderInstance`.

Relevant design surfaces:

- `notes/live/557-agentos-agent-model-design-session.md`
- `notes/live/560-agentos-agent-session-model-design-summary.md`
- `notes/index/102-Agentos.Agent.Model.md`
- `notes/live/558-agent-provider-infra-redesign-impl-req.md`

The older `558` impl-req is partly superseded by this request. Its first refactor pass produced useful shared mechanics, but its subsystem-adapter direction should not be treated as the final architecture where it conflicts with provider-native `Agent` and `Session` anchors.

## Requested Change

Rewrite the runtime model in incremental, behavior-preserving vertical slices, starting with Codex.

### Target Architecture

Use provider-native modules as the primary ownership boundary.

The new architecture should be understandable as:

```text
Agentos shared layer:
  - abstract Agent concept
  - abstract Session concept if useful
  - shared primitives only
  - command/result/config input primitives only where truly common

Provider-native layer:
  - Codex.Agent
  - Codex.Session
  - Codex.Normalizer
  - Claude.Agent
  - Claude.Session
  - Claude.Normalizer
  - etc.

Subsystem capabilities:
  - Provider.Agent.Runner
  - Provider.Agent.Chatlas
  - Provider.Agent.Accounts
  - Provider.Agent.Home
```

Do not build a new universal provider superclass that forces every provider through the same fields. Shared protocols can exist, but they must stay narrow and capability-shaped.

### Phase 1: Establish The New Model Surface

Add a clean model surface for provider-native agent/session objects.

Expected direction:

- `agentos.agent` contains only shared Agentos-level primitives and abstract coordination concepts.
- Provider-specific modules such as `agentos.codex`, `agentos.claude`, and `agentos.pi` own concrete provider objects.
- Avoid naming a new central model package `agentos.providers` unless it is strictly low-level vocabulary with no ownership of provider behavior.

Minimum useful shared primitives may include:

- provider id/family constants or value objects
- terminal command data
- environment override data
- artifact references
- config input records
- run request/result data

These shared primitives must not become a forced schema for all providers.

### Phase 2: Implement Codex As The Reference Vertical Slice

Create a Codex-native object model first.

Codex should be used as the reference because it exercises multiple subsystems:

- runner behavior through the Codex CLI
- home resolution through Codex home roots
- Chatlas raw archiving through Codex sessions/history/rules/artifacts
- session discovery through rollout JSONL and session index artifacts
- standard session normalization through Codex raw rollout parsing
- account stats through existing Codex usage/rate-limit logic
- Codex mux behavior through `src/agentos/codex/commands.py`

Expected objects/capabilities, subject to implementation naming:

```text
Codex.Agent
Codex.Session
Codex.Normalizer
Codex.Agent.Runner
Codex.Agent.Chatlas
Codex.Agent.Accounts
Codex.Agent.Home
```

`Codex.Agent` should be the configured actor and composition point for task-specific subsystem data. It may start from minimal config and be enriched/resolved for a task by combining home, runner, account, Chatlas, and terminal facts.

`Codex.Session` should capture native session facts:

- native session id
- rollout artifact path
- session index path and locator when present
- thread name when present
- timestamps where available
- provider-native raw artifact references
- derived native metadata needed by Codex normalization

`Codex.Normalizer` should convert:

```text
Codex.Session -> Agentos.Session / Session.Model
```

### Phase 3: Load Existing Config Into Provider Agents

Keep `agent.instances[]` as a temporary input format during this rewrite, but do not keep `ProviderInstance` as the runtime model.

Current config parsing can be reused as a compatibility input reader, but its output should become provider-native agents:

```text
agent.instances[] entry -> Codex.Agent / Claude.Agent / Pi.Agent / ...
```

During the transition, a narrow DTO can exist for parsed legacy config, but it should not own behavior or be passed deep into runner, account, Chatlas, or session code.

Rules:

- Do not add new behavior to `ProviderInstance`.
- Do not make new features depend on `ProviderInstance`.
- Do not expose `Agent.Instance` as a design or command concept.
- Keep user-facing behavior stable unless a separate config migration is explicitly approved.

### Phase 4: Move Subsystem Entrypoints To Provider Agents

Refactor command and service entrypoints so they ask provider agents for capability-specific behavior.

Target flow examples:

```text
agentos agent run
  -> resolve configured provider agent
  -> agent.runner resolves command
  -> run subprocess

agentos agent accounts stats
  -> resolve configured provider agents with account capability
  -> agent.accounts collects stats

agentos chat/session discovery
  -> resolve provider agents with session/chat capability
  -> provider-native session discovery returns <Provider>.Session

agentos chatlas archive
  -> resolve provider agents with Chatlas capability
  -> agent.chatlas mirrors raw artifacts

agentos chatlas export
  -> resolve or reconstruct <Provider>.Session
  -> <Provider>.Normalizer builds Agentos.Session / Session.Model
```

The subsystem entrypoints can remain in their current command modules during the transition, but their model dependency should point at provider-native agents/sessions, not `ProviderInstance`.

### Phase 5: Move Chatlas Normalization To Provider Sessions

Refactor `src/agentos/chatlas/session_model/` so provider-specific normalizers consume provider-native session objects.

Current shape:

```text
Chatlas session dict
  -> primary backing artifact path
  -> provider raw parser
  -> Session.Model
```

Target shape:

```text
Codex.Session
  -> Codex.Normalizer
  -> Agentos.Session / Session.Model
```

The current raw parsers in `_codex.py`, `_claude.py`, and `_copilot.py` contain valuable mechanics. Reuse them, but do not let their current `session: dict` input define the new interface.

### Phase 6: Migrate Other Providers

After Codex proves the model, migrate other providers one by one.

Suggested order:

1. Claude
   - complex sessions, account refresh behavior, multiple home slots, useful second proof.
2. Copilot CLI
   - event JSONL sessions and account/API behavior.
3. Pi
   - simpler local session model and runner semantics.
4. OpenCode
   - SQLite plus diff artifacts.
5. OpenClaw and Gemini
   - session/archive coverage as supported.

Each provider should implement only the capabilities it actually supports. Do not force no-op capability objects for unsupported behavior.

### Phase 7: Remove Or Narrow Legacy Model Surfaces

After enough consumers have moved:

- Remove or narrow `ProviderInstance`.
- Remove or replace `SessionSource`.
- Remove or replace `SessionProviderHandler`.
- Remove or replace `AccountProviderHandler`.
- Remove or replace `ChatlasProviderHandler`.
- Remove the `AgentosAgent` wrapper if provider-native agents replace it.
- Move or delete flat run-profile helpers that imply a generic provider schema.

This phase should happen only when consumers are already migrated. Do not break behavior by deleting the old model before replacement flows exist.

## Constraints And Invariants

- Provider-native modules are the model centers.
- Shared Agentos code must stay small and primitive-oriented.
- Do not create a new generic all-purpose provider object.
- Do not create or preserve `Agent.Instance` as a conceptual target.
- Treat `ProviderInstance` as a legacy config DTO or migration input only.
- Do not let `SessionSource` become the target model by simple rename without reconsidering its chat-discovery bias.
- Provider-specific complexity must stay provider-specific.
- Capabilities are per provider and per subsystem.
- Existing user-facing CLI behavior should remain stable during internal refactors unless explicitly changed.
- Existing config format can remain temporarily, but internal runtime objects should move to provider-native agents.
- Reuse existing mechanics only behind the new model boundary.
- Do not add backward-compatibility aliases or duplicate public APIs unless explicitly requested.
- Keep changes incremental and testable.
- Start with Codex as a vertical slice, not a cross-codebase mechanical rename.
- Preserve unrelated dirty worktree changes.

## Out Of Scope

- Designing the final user-facing config schema for provider agents.
- Removing `agent.instances[]` in the first implementation slice.
- Rewriting every provider in one commit.
- Rewriting Chatlas storage format.
- Changing the standard `Session.Model` schema unless required by provider-session normalization.
- Replacing all account-stat collection behavior.
- Redesigning Codex mux UX.
- Public command renames.
- New provider support.

## Acceptance Signals

Strong acceptance signals:

- A concrete provider-native `Codex.Agent` exists and is used by at least one real command path.
- A concrete `Codex.Session` exists and is used by Codex session discovery and/or Chatlas export.
- Codex Chatlas normalization takes `Codex.Session` or an equivalent provider-native object, not a generic Chatlas session `dict`.
- `agentos agent run` resolves a provider-native agent before command construction.
- Chatlas archive/update can use provider-agent Chatlas capability data instead of treating `ProviderInstance` as the model.
- Account stats can use provider-agent account capability data for at least Codex.
- `ProviderInstance` stops accumulating new responsibilities.
- New or updated tests prove that provider capability support is per provider and per subsystem.

Behavioral acceptance:

- Existing focused tests still pass or are intentionally updated to the new internal model:

```sh
uv run python -m pytest tests/test_agent_commands.py -q
uv run python -m pytest tests/test_chatlas_commands.py -q
uv run python -m pytest tests/test_chat_accounts_commands.py -q
uv run python -m pytest -q
```

Recommended incremental verification:

```sh
uv run python -m pytest tests/test_agent_commands.py -q
uv run python -m pytest tests/test_chatlas_commands.py -q -k "codex or session_model or export"
uv run python -m pytest tests/test_chat_accounts_commands.py -q -k codex
```

## Relevant Files Or Surfaces

Design:

- `notes/live/557-agentos-agent-model-design-session.md`
- `notes/live/560-agentos-agent-session-model-design-summary.md`
- `notes/index/102-Agentos.Agent.Model.md`
- `notes/index/006-Session.Model.md`
- `notes/index/007-Chatlas.Standard.Model.Contract.md`

Related / superseded implementation request:

- `notes/live/558-agent-provider-infra-redesign-impl-req.md`

Current runtime surfaces:

- `src/agentos/providers.py`
- `src/agentos/agent/commands.py`
- `src/agentos/agent/providers.py`
- `src/agentos/agent/run_profiles.py` (deleted during implementation)
- `src/agentos/chat/providers.py`
- `src/agentos/chat/sessions.py`
- `src/agentos/chat/core.py`
- `src/agentos/chat/accounts.py`
- `src/agentos/chatlas/raw.py`
- `src/agentos/chatlas/core.py`
- `src/agentos/chatlas/session_model/`
- `src/agentos/codex/commands.py`

Tests:

- `tests/test_agent_commands.py`
- `tests/test_chatlas_commands.py`
- `tests/test_chat_accounts_commands.py`
- `tests/test_chatlas_session_hashes.py`

## Open Questions

- What exact Python package names should hold provider-native models?
  - Working preference: provider-specific top-level modules such as `agentos.codex`, `agentos.claude`, and `agentos.pi`, with shared primitives under `agentos.agent`.
- Should Codex become the only first implementation slice, or should the first slice also add a tiny abstract shared agent/session primitive layer?
  - Working preference: add only the shared primitives needed by Codex.
- Should `ProviderInstance` be renamed immediately to a legacy config DTO?
  - Working preference: not in the first slice; first stop using it as runtime model, then narrow/rename after consumers move.
- Should `ChatSession` become the provider-agnostic `Agentos.Session` wrapper, or should a new object be introduced?
  - Working preference: decide after Codex.Session normalization is implemented.
- How much of `src/agentos/chat/core.py` should move into provider modules versus remain as orchestration?
  - Working preference: provider-specific scanners/readers move provider-side; generic query/list formatting can remain orchestration.

## Related Impl-Reqs

- Supersedes the final architecture direction of `notes/live/558-agent-provider-infra-redesign-impl-req.md` where that request implies subsystem provider adapters as the model center.
- Builds on `notes/live/560-agentos-agent-session-model-design-summary.md`.
- Should update `notes/live/557-agentos-agent-model-design-session.md` after the first implementation slice clarifies naming and package layout.

## End Log

- 2026-05-08: Created after design discussion converged on provider-native modules as the model centers, with `Agentos.Agent` as shared abstract concept and `<Provider>.Agent` / `<Provider>.Session` as concrete anchors.
- 2026-05-08: Implemented the first narrow Codex agent-run slice. Added shared run primitives in `src/agentos/agent/primitives.py`, added `src/agentos/codex/agent.py` with `CodexAgent` and `CodexAgentRunner`, made configured Codex entries resolve to `CodexAgent` for `agent run` / `agent list`, and added focused test coverage that configured Codex agents use the provider-native model. Remaining phases are not complete.
- 2026-05-08: Implemented the first Codex session-normalizer slice. Added `src/agentos/codex/session.py` with `CodexSession`, routed the Codex Chatlas raw rollout normalizer through `CodexSession`, and added focused test coverage for building a provider-native Codex session from current Chatlas payloads. Full Chatlas/session/account migration remains incomplete.
- 2026-05-08: Moved Codex Chatlas default raw retention include/exclude policy into `src/agentos/codex/chatlas.py` and made the existing generic chat provider spec consume that provider-native policy. This starts moving Chatlas ownership provider-side without changing archive behavior.
- 2026-05-08: Added `src/agentos/codex/accounts.py` with `CodexAgentAccounts` and made Codex account stats convert the legacy account context into that provider-native capability before collecting login/usage data. Added focused test coverage that the Codex rate-limit reader receives `CodexAgentAccounts`. Broader account orchestration still uses the legacy generic context.
- 2026-05-08: Moved Codex rollout/index session discovery into `src/agentos/codex/session.py` as provider-native `CodexSession` discovery functions. `chat.core` now bridges those native sessions into its existing `CodexSessionSource` wrapper for legacy orchestration, and focused tests cover native discovery. Full removal of legacy `SessionSource` remains incomplete.
- 2026-05-08: Added `CodexAgentChatlas` in `src/agentos/codex/chatlas.py` and made Chatlas raw context construction use it for Codex effective include/exclude policy. The archive pipeline still carries `ProviderInstance`, but Codex Chatlas policy resolution is now provider-native.
- 2026-05-08: Updated Codex mux default-instance resolution to return provider-native `CodexAgent` instead of using `ProviderInstance` as the runtime object. Added focused test coverage for the mux default instance resolver.
- 2026-05-08: Added `src/agentos/claude/session.py` with provider-native `ClaudeSession` and routed the Claude Chatlas raw-session normalizer through it. Added focused test coverage for building `ClaudeSession` from current Chatlas payloads. Claude discovery/account/Chatlas capability migration remains incomplete.
- 2026-05-08: Added `src/agentos/copilot/session.py` with provider-native `CopilotSession` and routed the Copilot Chatlas raw-events normalizer through it. Added focused test coverage for building `CopilotSession` from current Chatlas payloads. Copilot discovery/account/Chatlas capability migration remains incomplete.
- 2026-05-08: Moved Claude project/desktop session discovery into `src/agentos/claude/session.py` as provider-native `ClaudeSession` discovery functions. `chat.core` now bridges those native sessions into its existing `ClaudeCodeSessionSource` wrapper for legacy orchestration, and focused tests cover native project-session discovery. Claude account and Chatlas capability migration remain incomplete.
- 2026-05-08: Moved Copilot CLI session discovery into `src/agentos/copilot/session.py` as provider-native `CopilotSession` discovery functions. `chat.core` now bridges those native sessions into its existing `CopilotCliSessionSource` wrapper, and focused Chatlas tests cover the Copilot update/export path through the native session bridge. Copilot account and Chatlas capability migration remain incomplete.
- 2026-05-08: Added `src/agentos/pi/session.py` with provider-native `PiSession` discovery functions and moved Pi JSONL session parsing out of `chat.core`. `chat.core` now bridges native Pi sessions into `PiSessionSource` for legacy orchestration, and focused tests cover native Pi session discovery plus the configured Pi Chatlas update path. Pi runner/account/Chatlas capability migration remains incomplete.
- 2026-05-08: Added `src/agentos/opencode/session.py` with provider-native `OpencodeSession` discovery for session diff JSON files and SQLite session rows. `chat.core` now bridges native OpenCode sessions into `OpencodeSessionSource`, and focused tests cover native OpenCode discovery plus the existing Chatlas update path. OpenCode Chatlas capability migration and standard-model normalization remain incomplete.
- 2026-05-08: Added `src/agentos/gemini/session.py` with provider-native `GeminiSession` discovery and moved Gemini CLI JSON session parsing out of `chat.core`. `chat.core` now bridges native Gemini sessions into `GeminiCliSessionSource`, and focused tests cover native Gemini discovery. Gemini Chatlas capability migration and standard-model normalization remain incomplete.
- 2026-05-08: Added `src/agentos/openclaw/session.py` with provider-native `OpenclawSession` discovery for per-agent session indexes, transcripts, and logical session keys. `chat.core` now bridges native OpenClaw sessions into `OpenclawSessionSource`, and focused tests cover native OpenClaw discovery plus the existing logical-key query path. OpenClaw Chatlas capability migration and standard-model normalization remain incomplete.
- 2026-05-08: Moved Chatlas raw retention include/exclude constants for Claude, Copilot CLI, Gemini CLI, OpenCode, Pi, and OpenClaw into provider-owned `chatlas.py` modules. `chat.providers` still registers the policies for legacy orchestration, but no longer owns those provider-specific policy literals. Focused Chatlas retention/update tests pass.
- 2026-05-08: Narrowed raw Chatlas `ChatlasProviderContext` so it no longer stores `ProviderInstance`; it now carries only family, instance name, default flag, homes, and effective policy needed by raw mirroring. `ProviderInstance` remains at config parsing, selection, and validation boundaries. Focused Chatlas update tests pass.
- 2026-05-08: Narrowed `AccountProviderContext` so it no longer stores `ProviderInstance`; it now carries only provider, instance id, label, command, environment, timeout, refresh, and usage-progression fields needed by account collectors. `ProviderInstance` remains at account config selection and validation boundaries. Focused account tests pass.
- 2026-05-08: Replaced the non-Codex `AgentosAgent` provider-instance wrapper with `LegacyConfiguredAgent`, a narrow configured-agent object that copies only the fields needed by agent list/run. Codex still resolves to provider-native `CodexAgent`; other providers no longer carry `ProviderInstance` as their runtime agent object. Focused agent command tests pass.
- 2026-05-08: Narrowed `SessionProviderContext` with copied provider summary and fingerprint fields used by stats and URI resolution. `ProviderInstance` remains only as the temporary bridge input for `SessionSource` construction. Focused Chatlas query/update tests pass.
- 2026-05-08: Narrowed `SessionSource` so discovered chat sessions now carry a copied `SessionProviderIdentity` instead of the full legacy `ProviderInstance`. Chatlas session indexing and chat stats now read provider identity/fingerprint through that narrow object, and tests cover the bridge. Full test suite passes: `uv run python -m pytest -q` reported 290 passed. `ProviderInstance` remains at config parsing, provider selection, Chatlas archive reconstruction, and temporary session bridge entrypoints.
- 2026-05-08: Narrowed `SessionProviderContext` further so it no longer stores `SessionProviderHandler`; direct discovery/find orchestration now resolves the handler from the provider family at call time. Full test suite passes: `uv run python -m pytest -q` reported 290 passed. `SessionProviderHandler` still exists as the legacy orchestration registry and remains a later removal target.
- 2026-05-08: Narrowed `AccountProviderContext` and `ChatlasProviderContext` so neither stores its subsystem handler object. Handler registries still exist as legacy orchestration registries, but subsystem contexts now carry only task data. Affected suites pass: `uv run python -m pytest tests/test_chat_accounts_commands.py tests/test_chatlas_commands.py -q` reported 108 passed. Full test suite passes: `uv run python -m pytest -q` reported 290 passed.
- 2026-05-08: Removed unused runner/model fields from `SessionProviderHandler`, keeping Codex run defaults out of chat/session discovery orchestration. Chatlas suite passes: `uv run python -m pytest tests/test_chatlas_commands.py -q` reported 53 passed. Full test suite passes: `uv run python -m pytest -q` reported 290 passed.
- 2026-05-08: Removed `ProviderInstance` from `SessionProviderContext`; session discovery context now carries `SessionProviderIdentity` plus target paths, and the legacy config object is converted at context construction. Chatlas suite passes: `uv run python -m pytest tests/test_chatlas_commands.py -q` reported 53 passed. Full test suite passes: `uv run python -m pytest -q` reported 290 passed.
- 2026-05-08: Added provider-native `Agent` objects for Agents, Claude, Copilot, Pi, OpenCode, Gemini, and OpenClaw, and made configured agent resolution return those concrete objects instead of the `LegacyConfiguredAgent` runtime wrapper. Removed the generic configured command fallback. Agent command tests pass: `uv run python -m pytest tests/test_agent_commands.py -q` reported 14 passed. Full test suite passes: `uv run python -m pytest -q` reported 291 passed.
- 2026-05-08: Removed `AccountProviderHandler`; account orchestration now carries supported provider families as low-level provider vocabulary and dispatches collection by `AccountProviderContext.provider`. Account context remains a task-data object, not a subsystem handler wrapper. Account tests pass: `uv run python -m pytest tests/test_chat_accounts_commands.py -q` reported 55 passed. Full test suite passes: `uv run python -m pytest -q` reported 291 passed.
- 2026-05-08: Removed `SessionProviderHandler`; session orchestration now carries supported provider families as low-level provider vocabulary, dispatches discovery/find/stats by provider-native session source type, and exposes session home-slot lookup separately for Chatlas archive reconstruction. Chatlas tests pass: `uv run python -m pytest tests/test_chatlas_commands.py -q` reported 53 passed. Full test suite passes: `uv run python -m pytest -q` reported 291 passed.
- 2026-05-08: Removed `ChatlasProviderHandler`; raw Chatlas support now resolves directly from provider specs and provider-owned retention constants instead of a subsystem handler object. Chatlas/agent tests pass: `uv run python -m pytest tests/test_chatlas_commands.py tests/test_agent_commands.py -q` reported 67 passed. Full test suite passes: `uv run python -m pytest -q` reported 291 passed.
- 2026-05-08: Added narrow `AgentConfig` as the provider-agent constructor input and moved `ProviderInstance` conversion to `agent.providers` and Codex mux boundaries. Provider-native agent modules no longer import or accept `ProviderInstance` directly. Agent/Codex tests pass: `uv run python -m pytest tests/test_agent_commands.py tests/test_codex_commands.py -q` reported 30 passed. Full test suite passes: `uv run python -m pytest -q` reported 291 passed.
- 2026-05-08: Removed the `ProviderInstance` dependency from `chat.sessions`; `SessionProviderIdentity` is now a narrow identity object, and the legacy DTO conversion happens in `chat.core` at session context construction. Chatlas tests pass: `uv run python -m pytest tests/test_chatlas_commands.py -q` reported 53 passed. Full test suite passes: `uv run python -m pytest -q` reported 291 passed.
- 2026-05-08: Added narrow `ChatlasArchiveConfig` for raw Chatlas archive context construction and changed `CodexAgentChatlas` to consume that archive config instead of the legacy `ProviderInstance` DTO. Legacy conversion is now at Chatlas provider selection/validation boundaries. Chatlas tests pass: `uv run python -m pytest tests/test_chatlas_commands.py -q` reported 53 passed. Full test suite passes: `uv run python -m pytest -q` reported 291 passed.
- 2026-05-08: Reviewed the recent `src/agentos/copilot/session.py` provider-native session slice and fixed timestamp coercion so ISO Chatlas payload timestamps are retained; Copilot session merge now preserves the newest known timestamp. Focused Copilot Chatlas tests pass: `uv run python -m pytest tests/test_chatlas_commands.py -q -k "copilot_session_model or copilot"` reported 5 passed. Full test suite passes: `uv run python -m pytest -q` reported 291 passed.
- 2026-05-08: Added narrow `SessionProviderConfig` so session discovery context construction no longer accepts `ProviderInstance` directly. Legacy conversion now happens before context construction in `chat.core` and Chatlas session-index reconstruction. Chatlas/session suites pass: `uv run python -m pytest tests/test_chat_cli_common.py tests/test_chatlas_session_hashes.py tests/test_chatlas_commands.py -q` reported 65 passed. Full test suite passes: `uv run python -m pytest -q` reported 291 passed.
- 2026-05-08: Removed the temporary `ProviderInstance` rehydration from Chatlas session-index reconstruction; archived homes now become `SessionProviderConfig` directly before provider-native session discovery. Chatlas/session-index tests pass: `uv run python -m pytest tests/test_chatlas_commands.py tests/test_chatlas_session_hashes.py -q` reported 59 passed. Full test suite passes: `uv run python -m pytest -q` reported 291 passed.
- 2026-05-08: Added narrow `AccountProviderConfig` so account context construction no longer accepts `ProviderInstance` directly. Legacy conversion now happens before context construction in account request resolution and focused tests. Account tests pass: `uv run python -m pytest tests/test_chat_accounts_commands.py -q` reported 55 passed. Full test suite passes: `uv run python -m pytest -q` reported 291 passed.
- 2026-05-08: Changed `ChatlasSettings` to carry narrow `ChatlasArchiveConfig` objects instead of legacy `ProviderInstance` objects. Chatlas core now uses `ProviderInstance` only at config loading/selection boundaries, then archives and materializes sessions from archive configs. Chatlas/session-index tests pass: `uv run python -m pytest tests/test_chatlas_commands.py tests/test_chatlas_session_hashes.py -q` reported 59 passed. Full test suite passes: `uv run python -m pytest -q` reported 291 passed.
- 2026-05-08: Changed account provider selection to return `AccountProviderConfig` objects instead of exposing configured `ProviderInstance` objects to account stats request resolution. Account tests pass: `uv run python -m pytest tests/test_chat_accounts_commands.py -q` reported 55 passed. Full test suite passes: `uv run python -m pytest -q` reported 291 passed.
- 2026-05-08: Changed chat/session discovery grouping to work from `SessionProviderConfig` objects instead of configured/default `ProviderInstance` objects. `configured_provider_instances` remains a config-boundary helper, while runtime session contexts are built from narrow config. Chatlas/session suites pass: `uv run python -m pytest tests/test_chat_cli_common.py tests/test_chatlas_commands.py tests/test_chatlas_session_hashes.py -q` reported 65 passed. Full test suite passes: `uv run python -m pytest -q` reported 291 passed.
- 2026-05-08: Replaced the legacy `SessionSource` bridge surface with `ChatSessionRecord` and provider-specific `*SessionRecord` bridge classes. `ChatSession` now wraps a `record` rather than a `source`, and chat/session orchestration uses record naming for dedupe, sorting, and stats. Provider-native discovery remains the source of these records. Chatlas/session suites pass: `uv run python -m pytest tests/test_chat_cli_common.py tests/test_chatlas_commands.py tests/test_chatlas_session_hashes.py -q` reported 65 passed. Full test suite passes: `uv run python -m pytest -q` reported 291 passed.
- 2026-05-08: Replaced the misleading `ProviderInstance` DTO name with `LegacyProviderConfig` and renamed related config parser/selector helpers. The `agent.instances[]` user-facing config shape is unchanged, but runtime code no longer exposes a `ProviderInstance` model symbol. Targeted suites pass: `uv run python -m pytest tests/test_agent_commands.py tests/test_codex_commands.py tests/test_chat_accounts_commands.py tests/test_chat_cli_common.py tests/test_chatlas_commands.py tests/test_chatlas_session_hashes.py -q` reported 150 passed. Full test suite passes: `uv run python -m pytest -q` reported 291 passed.
- 2026-05-08: Removed the flat `src/agentos/agent/run_profiles.py` module. Provider command defaults now live only inside the legacy config reader in `chat.providers`, while `agent.providers` exposes a narrow `supported_default_run_provider_families()` capability query for tests and callers that need only support shape. Targeted suites pass: `uv run python -m pytest tests/test_agent_commands.py tests/test_chatlas_commands.py tests/test_chat_accounts_commands.py -q` reported 122 passed. Full test suite passes: `uv run python -m pytest -q` reported 291 passed.
- 2026-05-08: Moved Chatlas standard-model export dispatch so provider-specific normalizers consume provider-native `CodexSession`, `ClaudeSession`, and `CopilotSession` objects directly instead of receiving a generic Chatlas session `dict`. Removed the old dict-shaped provider normalizer wrappers. Focused export/session-model tests pass: `uv run python -m pytest tests/test_chatlas_commands.py -q -k "session_model or export or codex or claude or copilot"` reported 31 passed. Full test suite passes: `uv run python -m pytest -q` reported 291 passed.
- 2026-05-08: Final cleanup renamed leftover internal functions that still said provider instance / legacy provider config after they had become configured-agent or Chatlas provider-context flows. Final audit scan found no remaining `ProviderInstance`, `SessionSource`, subsystem handler, `AgentosAgent`, `LegacyConfiguredAgent`, `ConfiguredCommandAgent`, `run_profiles`, `AgentRunProvider`, flat run-profile helper, or dict-shaped provider-normalizer wrapper symbols in `src/agentos` or `tests`. Full test suite passes: `uv run python -m pytest -q` reported 291 passed.
