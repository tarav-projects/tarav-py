# Provider / Instance Unification Plan

## Goal
- Unify provider and provider-instance modeling across chat surfaces.
- Replace parallel session/archive/accounts family-instance models with one canonical semantic model.
- Keep surface-specific behavior in handler/context objects, not in the canonical family/instance objects.

## Status
- First, second, third, and fourth implementation slices are complete.
- Added canonical provider model module in `src/agentos/chat/providers.py`.
- Added canonical `ProviderFamily` registry and lookup helpers in `src/agentos/chat/providers.py`.
- Moved canonical `ProviderInstance` and `ProviderInstanceAnchor` out of `chat/sessions.py`.
- Session surface now uses handler/context naming internally:
- `SessionProviderHandler`
- `SessionProviderContext`
- Archive surface now uses handler/context naming internally:
- `ArchiveProviderHandler`
- `ArchiveProviderContext`
- Archive now consumes canonical `ProviderInstance` instead of a separate `ArchiveInstance`.
- Accounts surface now uses handler/context naming internally:
- `AccountProviderHandler`
- `AccountProviderContext`
- Accounts now consumes canonical `ProviderInstance` instead of a separate `AccountProviderInstance`.
- Session/archive/accounts handlers now bind to shared canonical `ProviderFamily` objects.
- Public behavior stayed stable.
- Verified with:
- `uv run pytest tests/test_chat_archive_commands.py -q`
- `uv run pytest tests/test_chat_commands.py tests/test_chat_extract_commands.py -q`
- `uv run pytest tests/test_chat_accounts_commands.py -q`
- `uv run pytest tests/test_chat_commands.py tests/test_chat_extract_commands.py tests/test_chat_archive_commands.py tests/test_chat_accounts_commands.py -q`
- `uv run pytest -q`

## Accepted Direction
- There is one canonical `ProviderFamily`.
- There is one canonical `ProviderInstance`.
- Surface behavior lives in separate handler objects:
- `SessionProviderHandler`
- `ArchiveProviderHandler`
- `AccountProviderHandler`
- Derived runtime state lives in surface-specific context objects, not in `ProviderInstance`.
- Current per-surface “family” objects should be treated as handlers and migrated accordingly.

## Current Parallel Models

### Sessions
- `ProviderFamily` in `src/agentos/chat/core.py`
- `ProviderInstance` in `src/agentos/chat/sessions.py`
- `ProviderInstanceContext` in `src/agentos/chat/core.py`

### Archive
- `ArchiveFamily` in `src/agentos/chat/archive.py`
- `ArchiveInstance` in `src/agentos/chat/archive.py`

### Accounts
- `AccountProviderFamily` in `src/agentos/chat/accounts.py`
- `AccountProviderInstance` in `src/agentos/chat/accounts.py`

## Core Refactor Principle
- Unify the semantic object.
- Do not unify derived surface state into that semantic object.

That means:
- `ProviderFamily` contains provider identity and shared family-level semantics.
- `ProviderInstance` contains declared configured instance data.
- Handlers consume canonical family/instance objects.
- Contexts derive paths, targets, command settings, archive destinations, and similar runtime data.

## Target Architecture

### Canonical Semantic Layer
- `ProviderFamily`
  - provider name / family id
  - shared metadata needed by all surfaces
- `ProviderInstance`
  - family reference or family name
  - canonical instance identity
  - declared bindings/config
  - canonical fingerprint / identity key
  - human label / explicit instance id when configured

### Surface Behavior Layer
- `SessionProviderHandler`
  - discovery
  - query resolution
  - session stats hooks
- `ArchiveProviderHandler`
  - archive source enumeration
  - destination policy
  - include/exclude policy
- `AccountProviderHandler`
  - account stats collection
  - usage refresh behavior
  - command execution/parsing hooks

### Surface Runtime Layer
- `SessionProviderContext`
  - direct targets
  - grep targets
  - sqlite paths
  - existing/missing target partitions
- `ArchiveProviderContext`
  - resolved destination roots
  - effective excludes
  - mirror planning state
- `AccountProviderContext`
  - resolved cli command
  - env mapping
  - timeout
  - any temporary runtime state

## Canonical Instance Boundaries

### Belongs in `ProviderInstance`
- canonical family identity
- declared home bindings
- declared command/runtime config
- explicit instance id / label if configured
- declared archive policy fields if they are configuration, not runtime derivation
- fingerprint / identity key inputs

### Does Not Belong in `ProviderInstance`
- discovered direct targets
- grep targets
- sqlite db scans
- existing vs missing files
- archive destination roots
- persisted stats payloads
- runtime refresh state
- any cache produced by one command execution

## Migration Strategy

### Phase 1. Introduce Canonical Model
- Add a new shared module for canonical provider modeling.
- Introduce:
- `ProviderFamily`
- `ProviderInstance`
- any shared identity/fingerprint helpers
- Do not change command behavior yet.
- Add adapter helpers so current session/archive/accounts code can construct old objects from the new canonical ones during transition.

### Phase 2. Convert Session Surface
- Rename current session `ProviderFamily` role into `SessionProviderHandler`.
- Move session-specific derived path state out of canonical instance handling and into `SessionProviderContext`.
- Refactor session config loading to produce canonical `ProviderInstance` values first.
- Keep public session command behavior unchanged while internal structure changes.

### Phase 3. Convert Archive Surface
- Rename `ArchiveFamily` into `ArchiveProviderHandler`.
- Replace `ArchiveInstance` with canonical `ProviderInstance` plus `ArchiveProviderContext`.
- Keep archive destination naming/exclude logic in archive-specific context/handler code.

### Phase 4. Convert Accounts Surface
- Rename `AccountProviderFamily` into `AccountProviderHandler`.
- Replace `AccountProviderInstance` with canonical `ProviderInstance` plus `AccountProviderContext`.
- Move command/env/timeout resolution into account context-building.

### Phase 5. Unify Registries
- Build one canonical provider-family registry.
- Build one handler registry per surface keyed by family.
- Ensure every surface resolves handler behavior from the same family identity.

### Phase 6. Unify Config Loading
- Introduce one provider-instance config loading pipeline.
- Keep compatibility readers for:
- `chat.session.provider_instances`
- `chat.archive.provider_instances`
- `chat.accounts.provider_instances`
- Decide whether to keep multiple surface-specific config namespaces long-term or consolidate later into one canonical provider-instance namespace.

## Recommended Compatibility Policy
- Unify in-memory semantic model first.
- Preserve current config namespaces initially.
- Add compatibility loaders before any config migration.
- Only after the model is stable decide whether to collapse config namespaces.

This keeps the first pass bounded and avoids mixing model unification with config migration risk.

## First Change Set
- Add new canonical provider model module.
- Define `ProviderFamily` and `ProviderInstance`.
- Move shared fingerprint / identity-key logic there.
- Add session adapters first:
- session family registry -> session handler registry
- session instance loading -> canonical instance loading
- session runtime derivation -> `SessionProviderContext`
- Keep command outputs and tests stable.

### First Change Set Result
- Implemented canonical provider model module.
- Implemented session-side handler/context rename.
- Session command behavior and tests remained stable.
- Archive was migrated in the next slice.
- Accounts are not migrated yet.

## Second Change Set
- Replace `ArchiveFamily` with `ArchiveProviderHandler`.
- Replace `ArchiveInstance` with canonical `ProviderInstance`.
- Add `ArchiveProviderContext` for:
- resolved archive instance name
- effective excludes
- archive destination summary behavior
- Keep archive command output stable while moving archive-specific derivation out of the canonical instance.

### Second Change Set Result
- Implemented archive-side handler/context rename.
- Archive now builds canonical `ProviderInstance` values with home anchors.
- Archive-specific instance naming and exclude derivation now live in `ArchiveProviderContext`.
- Archive command behavior and tests remained stable.

## Third Change Set
- Replace `AccountProviderFamily` with `AccountProviderHandler`.
- Replace `AccountProviderInstance` with canonical `ProviderInstance`.
- Add `AccountProviderContext` for:
- resolved runtime command configuration
- environment mapping
- timeout
- live-usage refresh policy
- Keep account command payloads stable while moving runtime derivation out of the canonical instance.

### Third Change Set Result
- Implemented accounts-side handler/context rename.
- Accounts now builds canonical `ProviderInstance` values from `chat.accounts.provider_instances`.
- Account runtime command/env/timeout/live-refresh state now lives in `AccountProviderContext`.
- Account command behavior and tests remained stable.

## Fourth Change Set
- Adopt the canonical `ProviderFamily` layer across all chat surfaces.
- Add one canonical provider-family registry in `src/agentos/chat/providers.py`.
- Make session/archive/accounts handlers reference canonical `ProviderFamily` objects instead of carrying standalone family strings as their semantic identity.
- Keep per-surface handler lookup and behavior local to each surface.

### Fourth Change Set Result
- Implemented shared canonical provider-family registry and lookup helpers.
- Session/archive/accounts handler registries now consume canonical `ProviderFamily` objects.
- Surface-specific provider choices and command behavior remained stable.
- Remaining major unification work is the provider-instance config-loading pipeline.

## Acceptance Criteria
- There is one canonical provider family type in the codebase.
- There is one canonical provider instance type in the codebase.
- Session/archive/accounts no longer define separate semantic family-instance models.
- Surface-specific handlers consume canonical family/instance objects.
- Surface-specific contexts own derived runtime state.
- Existing command behavior remains stable across the migration.

## Risks
- If config migration is mixed into the first refactor, scope will blow up.
- If handler/context boundaries are not enforced, per-surface instance models will reappear under new names.
- Sessions currently mix identity and derived discovery state the most; that slice should be cleaned first.

## Suggested Order
1. Canonical semantic model
2. Session migration
3. Archive migration
4. Accounts migration
5. Registry unification
6. Config unification decision

## Deferred
- Final config namespace collapse
- exact canonical config schema
- whether provider families should carry optional shared metadata beyond `family`
