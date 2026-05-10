# Agent Session Model Duplication Followup - impl-req

## Impl-Req State

This request has been implemented for the current Agent/Session duplication points; remaining `AgentConfig`/`AgentBase`/`Agent` field repetition is intentionally left as boundary documentation for now.

## User Intent

Continue removing duplicated functionality around the Agentos Agent and Session models.

The user wants the codebase to keep converging on:

- `AgentConfig` as construction input, not a second runtime agent.
- `<Provider>.Agent` as the provider-native runtime object.
- `<Provider>.SessionRef` as the lightweight session handle.
- `<Provider>.Session` as the full provider-native session model.
- Agentos and Chatlas coordination layers that consume those objects instead of rebuilding parallel partial models.

## Why This Exists

The previous cleanup moved a lot of model behavior into the right places:

- Shared Agent runtime behavior lives in `AgentBase`.
- Account code now wraps real agents.
- Provider refs own lightweight list/query metadata.
- Provider sessions now expose `sources()` and own heavier source/timestamp interpretation.
- `BackingArtifact` is now only a compatibility output adapter.

Code inspection after that work still shows duplicated model-adjacent behavior. This follow-up exists to remove that remaining duplication without changing the accepted object responsibilities.

## Current Situation

Observed duplication points:

1. `ProviderSessionRefEntry` and `ChatlasProviderSessionRef` both expose `sources()` by calling `session_ref.to_session().sources()` and both convert `SessionSource` to `BackingArtifact`.
   - `src/agentos/agent/sessions.py`
   - `src/agentos/chatlas/core.py`

2. `agentos.agent.session_refs` still exposes thin adapter helpers such as `session_ref_backing_artifacts()` and `session_ref_created_timestamp()`. Some call sites now use session/provider methods directly, while others still route through the adapter layer.
   - `src/agentos/agent/session_refs.py`
   - `src/agentos/agent/sessions.py`
   - `src/agentos/chatlas/core.py`

3. Provider agent classes still repeat boilerplate for `from_config()`, provider validation, `discover_session_refs()`, and `load_session()`.
   - `src/agentos/codex/agent.py`
   - `src/agentos/claude/agent.py`
   - `src/agentos/copilot/agent.py`
   - `src/agentos/gemini/agent.py`
   - `src/agentos/openclaw/agent.py`
   - `src/agentos/opencode/agent.py`
   - `src/agentos/pi/agent.py`

4. Generic provider-session helper functions are copied across provider session modules:
   - `_coerce_timestamp`
   - `_safe_path_mtime`
   - `_glob_paths`
   - `_primary_source_path`
   - `_string_or_none`
   - `_primary_transcript_artifact`
   - `_source_ref_id_for_artifact`

5. Provider-specific stats/dialog-count behavior still lives in Agentos and Chatlas central code for Codex and OpenClaw.
   - `src/agentos/agent/sessions.py`
   - `src/agentos/chatlas/core.py`

6. `AgentConfig`, `AgentBase`, and the `Agent` protocol repeat the same field list. This is lower-risk duplication but still worth tracking.
   - `src/agentos/agent/primitives.py`

## Requested Change

Remove the remaining duplicated Agent/Session model behavior in small, verifiable slices.

The target direction:

- Keep model responsibilities where they belong:
  - Provider runtime behavior on `<Provider>.Agent`.
  - Lightweight session handle behavior on `<Provider>.SessionRef`.
  - Full session/source/content behavior on `<Provider>.Session`.
  - Query, URI, dedupe, registry, and subsystem-specific output formatting above provider objects.
- Replace duplicated wrapper behavior with one shared helper only when the helper is truly Agentos coordination behavior.
- Do not move downstream Chatlas concerns into provider agents or provider sessions.

## Constraints And Invariants

- Do not put `sources()` or content-heavy behavior on `<Provider>.SessionRef`.
- Do not make `BackingArtifact` a target abstraction; it remains transitional compatibility only.
- Do not move Chatlas raw mirror policy, destination mapping, or archive configuration into `<Provider>.Agent`.
- Keep CLI behavior stable.
- Keep provider-native discovery semantics stable.
- Do not add compatibility aliases unless explicitly requested.
- Prefer deleting redundant adapter use over adding another wrapper.
- Preserve the current dirty worktree and do not revert unrelated edits.

## Out Of Scope

- Redesigning Chatlas raw mirror policy.
- Removing all persisted `backing_artifact` fields from Chatlas output in this pass.
- Renaming config fields.
- Reworking provider discovery algorithms.
- Changing the user-facing command surface.
- Collapsing `AgentConfig` into `AgentBase` unless the duplication can be removed without making config parsing less explicit.

## Acceptance Signals

- `ProviderSessionRefEntry` and `ChatlasProviderSessionRef` no longer duplicate `SessionSource` / `BackingArtifact` conversion logic.
- Remaining `session_ref_*` helpers are either deleted, reduced to clearly necessary compatibility functions, or no longer used by coordination paths that can call provider objects directly.
- Provider agent modules have less repeated boilerplate, or the remaining repetition is explicitly provider-specific and justified by code shape.
- Generic provider-session helpers are shared where doing so reduces real duplication without hiding provider-native discovery logic.
- Codex/OpenClaw dialog-count or provider stats behavior is moved toward provider session methods or a provider-owned normalizer surface, or the central location is explicitly narrowed to output formatting only.
- No provider-specific source/artifact interpretation is reintroduced into central `isinstance` chains.
- Focused tests for agent commands, account commands, session/query output, and Chatlas update/query still pass.

## Implementation Shape

Implement in vertical slices.

### Slice 1. SessionSource Compatibility Helper

- Create one shared compatibility function for `SessionSource -> BackingArtifact` while `BackingArtifact` remains.
- Update `ProviderSessionRefEntry` and `ChatlasProviderSessionRef` to use it.
- Avoid adding new Chatlas-specific fields to `SessionSource`.

### Slice 2. Thin SessionRef Adapter Layer

- Audit all `session_ref_*` helper call sites.
- Replace trivial helper calls with direct `SessionRef` or `Session` methods where that improves clarity.
- Keep only compatibility helpers still required by older output paths.

### Slice 3. Provider Agent Boilerplate Cleanup

- Remove unused imports introduced by prior refactors.
- Consolidate repeated `from_config()` validation/mapping if a small shared helper can do it clearly.
- Keep provider identity explicit and readable.
- Do not obscure the provider-specific `discover_session_refs()` differences, especially OpenCode sqlite paths and Codex index/session targets.

### Slice 4. Shared Provider Session Utilities

- Move repeated generic helpers to a provider-session-oriented shared module.
- Good candidates:
  - timestamp coercion
  - safe path mtime
  - source primary-path selection
  - basic string coercion
  - artifact/source lookup helpers for Chatlas payload reconstruction
- Leave provider-native parsing/discovery algorithms in provider modules.

### Slice 5. Provider-Owned Stats Behavior

- Review central Codex/OpenClaw stats and dialog-count code.
- Move provider-native count/extraction behavior to provider session methods if it is a fact about one provider session.
- Keep Agentos/Chatlas central code responsible only for deciding whether and how to include those stats in output.

### Slice 6. Agent Field Duplication Audit

- Reassess `AgentConfig`, `AgentBase`, and `Agent` protocol after the higher-value cleanup.
- If the field list duplication can be reduced without weakening the config/runtime boundary, do it.
- If not, document why this duplication is intentional for now.

## Relevant Files Or Surfaces

- `agentos-py/src/agentos/agent/primitives.py`
- `agentos-py/src/agentos/agent/session_refs.py`
- `agentos-py/src/agentos/agent/sessions.py`
- `agentos-py/src/agentos/chatlas/core.py`
- `agentos-py/src/agentos/codex/agent.py`
- `agentos-py/src/agentos/claude/agent.py`
- `agentos-py/src/agentos/copilot/agent.py`
- `agentos-py/src/agentos/gemini/agent.py`
- `agentos-py/src/agentos/openclaw/agent.py`
- `agentos-py/src/agentos/opencode/agent.py`
- `agentos-py/src/agentos/pi/agent.py`
- `agentos-py/src/agentos/codex/session.py`
- `agentos-py/src/agentos/claude/session.py`
- `agentos-py/src/agentos/copilot/session.py`
- `agentos-py/src/agentos/gemini/session.py`
- `agentos-py/src/agentos/openclaw/session.py`
- `agentos-py/src/agentos/opencode/session.py`
- `agentos-py/src/agentos/pi/session.py`
- `agentos-py/tests/test_agent_commands.py`
- `agentos-py/tests/test_agent_accounts_commands.py`
- `agentos-py/tests/test_chatlas_commands.py`

## Open Questions

- Should shared session utilities live in `agentos.agent.primitives`, a new `agentos.agent.session_primitives`, or another provider-session module?
- Should provider stats methods have a common protocol, or should each provider expose only the methods it actually supports?
- Should `BackingArtifact` conversion stay in `agentos.agent.session_refs`, move next to `SessionSource`, or move into output formatting modules while it is transitional?
- Is the `Agent` protocol field duplication acceptable because it documents runtime expectations, or should it be reduced after provider agents stabilize?

## Related Impl-Reqs

- `566-agent-model-duplication-cleanup-impl-req.md`
- `567-provider-session-source-model-impl-req.md`
- `562-provider-session-ref-model-cleanup-impl-req.md`
- `561-provider-native-agent-session-model-rewrite-impl-req.md`

## End Log

- 2026-05-10: Created from a post-567 codebase audit of remaining duplicated functionality around Agent and Session model responsibilities.
- 2026-05-10: Implemented the follow-up cleanup. Added shared session utilities, centralized `SessionSource` to `BackingArtifact` compatibility conversion, removed thin `session_ref_*` adapters, moved Codex/OpenClaw provider stats and Codex supplemental findings onto provider session/ref objects, reduced provider agent `from_config()` boilerplate, and verified with compileall plus focused agent/account/Chatlas tests.
