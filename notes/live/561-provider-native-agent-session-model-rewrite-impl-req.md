# Provider-Native Agent Session Model Rewrite - impl-req

## Impl-Req State

First Codex agent-run model slice implemented; remaining work includes Codex.Session, Codex.Normalizer, Chatlas/account/session migration, other providers, and legacy model removal.

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

The current codebase contains a lot of working functionality, but its model is wrong for the accepted design.

Current provider-related code is organized around generic or subsystem-owned shapes:

- `ProviderInstance` mixes configured actor data, home roots, launch config, session discovery facts, account behavior, Chatlas raw policy, identity/fingerprint behavior, and transitional config semantics.
- `SessionSource` is close to native session data, but it is named and shaped as a chat-discovery source, not as `<Provider>.Session`.
- `SessionProviderHandler`, `AccountProviderHandler`, and `ChatlasProviderHandler` describe subsystem provider adapters as separate centers.
- `AgentosAgent` currently wraps `ProviderInstance` instead of being a provider-native agent.
- `run_profiles.py` encodes flat provider command defaults that risk becoming a generic schema.

The newer design explicitly rejects letting that existing model remain the architecture. Agentos should not treat "provider" as one central object with all capabilities. It should model concrete provider agents and provider sessions first, with shared primitives used only where they genuinely fit.

## Current Situation

Relevant current surfaces:

- `src/agentos/providers.py`
  - Shared provider family list, home-slot topology, and home anchors.
  - This is useful as low-level vocabulary, but it should not become the conceptual center of the model.
- `src/agentos/chat/providers.py`
  - Defines `ChatProviderSpec`, config parsing from `agent.instances[]`, `ProviderInstance`, config helpers, and selection helpers.
  - This is the main overloaded legacy model surface.
- `src/agentos/agent/providers.py`
  - Defines `AgentosAgent` as a thin wrapper around `ProviderInstance`.
  - Useful behavior exists here, but the wrapper should not be the final model.
- `src/agentos/agent/run_profiles.py`
  - Holds provider command defaults and flag defaults.
  - These mechanics may be reused, but should move behind provider-specific runner capabilities.
- `src/agentos/chat/sessions.py`
  - Defines `SessionSource`, `ChatSession`, and provider-specific source classes such as `CodexSessionSource`, `ClaudeCodeSessionSource`, `PiSessionSource`.
  - This contains important provider-native session facts and should be mined for `<Provider>.Session`, not merely renamed in place without reconsidering boundaries.
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
uv run pytest tests/test_agent_commands.py -q
uv run pytest tests/test_chat_commands.py tests/test_chat_extract_commands.py -q
uv run pytest tests/test_chatlas_commands.py -q
uv run pytest tests/test_chat_accounts_commands.py -q
```

Recommended incremental verification:

```sh
uv run pytest tests/test_agent_commands.py -q
uv run pytest tests/test_chatlas_commands.py -q -k "codex or session_model or export"
uv run pytest tests/test_chat_commands.py -q -k codex
uv run pytest tests/test_chat_accounts_commands.py -q -k codex
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
- `src/agentos/agent/run_profiles.py`
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
- `tests/test_chat_commands.py`
- `tests/test_chat_extract_commands.py`
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
