# Provider Session Source Model - impl-req

## Impl-Req State

This request has been implemented for the current provider sessions; remaining `BackingArtifact` usage is a compatibility output adapter.

## User Intent

Define and implement the provider-owned session source model needed to finish removing central provider-specific session interpretation from Agentos coordination code.

The user wants:

- `<Provider>.SessionRef` to remain a lightweight handle.
- `<Provider>.Session` to be the full provider-native session model.
- `<Provider>.Session.sources()` to expose where the session comes from.
- Chatlas to consume `session.sources()` directly instead of requiring a new Agentos-level backing-artifact target object.

## Why This Exists

The agent model cleanup in `566-agent-model-duplication-cleanup-impl-req.md` moved lightweight ref metadata onto provider `SessionRef` classes, but central provider-specific dispatch remains for heavier source/artifact interpretation.

That remaining dispatch should not be moved onto `SessionRef`, because doing so would bloat refs into partial session models. The correct destination is `<Provider>.Session`.

## Current Situation

Current code still has central provider-specific knowledge in `agentos.agent.session_refs`, especially:

- `session_ref_backing_artifacts()`
- `session_ref_created_timestamp()`

Those functions know details such as:

- Codex rollout files and session index records.
- Claude JSONL transcripts versus JSON metadata.
- Copilot `events.jsonl` session roots.
- Gemini and Pi artifact paths.
- OpenClaw transcript/index pairs and session-key locators.
- OpenCode diff files and sqlite session rows.

The code also has a transitional `BackingArtifact` object. That object may remain temporarily for old Agentos output paths, but it is not the target model.

## Requested Change

Introduce a provider session source model and make provider sessions own source/artifact interpretation.

The target should be:

- `<Provider>.SessionRef`: identity, minimal list/query metadata, sort timestamp, and load pointers only.
- `<Provider>.Session`: full provider-native session model, source refs, content-derived facts, native payloads, and normalization/export inputs.
- `SessionSource`: the small source/ref shape returned by `<Provider>.Session.sources()`.
- Chatlas: consumes `session.sources()` directly and owns how those refs are mirrored, stored, or rendered.

Draft shape:

```python
@dataclass(frozen=True)
class SessionSource:
    role: str
    path: Path
    storage_kind: str | None = None
    locator: dict[str, object] | None = None
```

The exact module location is open, but it should be provider-session owned rather than Chatlas owned. A small shared session primitives module is acceptable if all providers use the same shape.

## Constraints And Invariants

- Do not put `sources()` on `<Provider>.SessionRef`.
- Do not make `BackingArtifact` the new target abstraction.
- Chatlas should be able to consume `session.sources()` directly.
- `BackingArtifact` may remain only as a compatibility adapter while older Agentos output paths still expect it.
- Keep cross-provider URI, registry, dedupe, sorting, and query coordination above provider session objects.
- Keep CLI behavior stable during the migration.
- Preserve provider-native discovery semantics.
- Prefer small vertical slices with tests.

## Out Of Scope

- Redesigning Chatlas raw mirror policy.
- Replacing all Chatlas output schemas in one pass.
- Renaming persisted config fields.
- Reworking provider session discovery algorithms.
- Moving lightweight ref metadata back out of provider refs.

## Acceptance Signals

- A common `SessionSource` shape exists for provider sessions.
- Every `<Provider>.Session` exposes `sources() -> tuple[SessionSource, ...]`.
- Source roles from current behavior are preserved initially: `transcript`, `metadata`, `session_index`, `session_root`, `session_diff`, `sqlite_session_row`.
- `agentos.agent.session_refs.session_ref_backing_artifacts()` is reduced to a compatibility adapter over `ref.to_session().sources()` or an equivalent provider-session path.
- Provider-specific backing/source interpretation no longer lives primarily in central `isinstance` chains.
- Created timestamp behavior is moved toward `<Provider>.Session` where it requires content/source interpretation.
- Chatlas code has a clear path to consume `session.sources()` directly, even if some old output code still uses compatibility adapters.
- Existing agent/session/chatlas tests continue to pass.

## Implementation Shape

Implement in vertical slices.

### Slice 1. Define SessionSource

- Add `SessionSource` in a provider-session-oriented shared module.
- Keep it minimal: `role`, `path`, optional `storage_kind`, optional `locator`.
- Do not add Chatlas-specific fields.

### Slice 2. Add sources() To Provider Sessions

- Implement `sources()` on all provider session classes.
- Preserve current roles and locators from `session_ref_backing_artifacts()`.
- Keep refs unchanged except for existing load pointers.

Provider mapping:

- `CodexSession`: `transcript` for rollout paths; `session_index` for index paths with JSONL record locator by native session id.
- `ClaudeSession`: `transcript` for `.jsonl` paths; `metadata` for `.json` paths.
- `CopilotSession`: `transcript` for `events_path`; `session_root` for `events_path.parent` when the filename is `events.jsonl`.
- `GeminiSession`: `transcript` for artifact paths.
- `PiSession`: `transcript` for artifact paths.
- `OpenclawSession`: `transcript` for transcript path; `session_index` for sessions index path with session-key or native-id locator.
- `OpencodeSession`: `session_diff` for diff path; `sqlite_session_row` for sqlite db path with table/key locator.

### Slice 3. Compatibility Adapter

- Keep `BackingArtifact` only if current Agentos output still needs it.
- Convert `SessionSource` to `BackingArtifact` in one adapter function.
- Make the compatibility path use `ref.to_session().sources()` rather than provider-specific central dispatch.

### Slice 4. Created Timestamp Ownership

- Move content-derived created timestamp behavior to provider sessions where practical.
- Keep any temporary central adapter thin and transitional.
- Do not add extractor-heavy behavior to `SessionRef`.

### Slice 5. Chatlas Direct Consumption

- Update Chatlas/session output paths to consume `session.sources()` directly where the surrounding code can load full sessions.
- Leave compatibility adapters only for paths that still operate on refs.

## Relevant Files Or Surfaces

- `agentos-py/notes/live/566-agent-model-duplication-cleanup-impl-req.md`
- `agentos-py/src/agentos/agent/session_refs.py`
- `agentos-py/src/agentos/agent/sessions.py`
- `agentos-py/src/agentos/chatlas/core.py`
- `agentos-py/src/agentos/claude/session.py`
- `agentos-py/src/agentos/codex/session.py`
- `agentos-py/src/agentos/copilot/session.py`
- `agentos-py/src/agentos/gemini/session.py`
- `agentos-py/src/agentos/openclaw/session.py`
- `agentos-py/src/agentos/opencode/session.py`
- `agentos-py/src/agentos/pi/session.py`
- `agentos-py/tests/test_agent_commands.py`
- `agentos-py/tests/test_chatlas_commands.py`

## Open Questions

- Should `SessionSource` live in `agentos.agent.session_primitives`, `agentos.agent.primitives`, or another provider-session module?
- Should `created_timestamp()` be required on all provider sessions, or optional with a helper fallback?
- Which Chatlas paths can load full sessions immediately, and which need a temporary ref compatibility adapter?

## Related Impl-Reqs

- `566-agent-model-duplication-cleanup-impl-req.md` defines the broader agent duplication cleanup and records that `BackingArtifact` is transitional.
- `562-provider-session-ref-model-cleanup-impl-req.md` defines the provider `SessionRef` direction.
- `561-provider-native-agent-session-model-rewrite-impl-req.md` defines the broader provider-native Agent/Session target.

## End Log

- 2026-05-10: Created from the accepted design direction that Chatlas should consume `<Provider>.Session.sources()` directly and that full source/artifact interpretation belongs on `<Provider>.Session`, not `<Provider>.SessionRef`.
- 2026-05-10: Implemented `SessionSource`, added `sources()` and provider-owned created timestamp behavior to all current provider session models, reduced `agentos.agent.session_refs.session_ref_backing_artifacts()` to a `SessionSource` -> `BackingArtifact` compatibility adapter, and updated Agentos/Chatlas ref-entry paths to derive artifacts from session sources. Verified with compileall and `uv run pytest tests/test_chatlas_commands.py tests/test_agent_commands.py tests/test_agent_accounts_commands.py -q`.
