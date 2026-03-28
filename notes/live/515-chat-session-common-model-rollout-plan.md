# Chat Session Common Model Rollout Plan

## Goal
- Extend the new `chat session` common model beyond `list`, `find`, and `stats`.
- Prioritize the next command that materially benefits from the model: `extract`.
- Define how future session-scoped commands should consume the common model without bloating default output.

## Status
- Phase 1 is implemented.
- `extract` now resolves through a shared internal extract-target abstraction.
- Query-based extraction now selects from canonical `backing_artifacts` instead of directly reading `primary_artifact_path()`.
- `--file` now uses backing-artifact terminology in central resolution and error paths.
- Added coverage for backing-artifact terminology and `opencode.db` requiring explicit session identity context.

## Accepted Direction
- `extract` is the next existing command that should benefit directly from the common model.
- `extract` should keep transcript-first output by default.
- `extract --file` should be treated as a `backing_artifact` entrypoint, not a separate resolution system.
- Session metadata should only be added to `extract` as an opt-in expansion, not as a default wrapper.
- Future session-scoped commands should resolve through the common `session` object first.

## Scope

### In Scope
- Internal `extract` refactor onto the common `session` and `backing_artifact` model.
- Clarify and normalize `--file` semantics around `backing_artifact`.
- Define minimal extension points for future commands to reuse common resolution and artifact selection.
- Add tests that lock the model contract in for `extract`.

### Out of Scope
- Changing default `extract` stdout shape.
- Adding new top-level `chat session` verbs right now.
- Building compare/audit/inspect commands in this change set.

## Design Targets

### 1. `extract` Uses the Common Resolver
- Session-query extraction should resolve to a canonical `session` first.
- Artifact choice for extraction should be derived from `session.backing_artifacts()`, not ad hoc file probing.
- Ambiguity handling should remain explicit and deterministic.

### 2. `--file` Becomes a Backing-Artifact Entry Point
- `--file` input should be modeled as: “extract from this backing artifact”.
- If the artifact needs session identity context, reuse the same session-id resolution rules already used by provider extractors.
- Error messages should refer to artifact provenance and session ambiguity using common-model language.

### 3. Metadata Stays Opt-In
- Keep default `extract` output unchanged for shell pipelines and scripting.
- If metadata is added later, add it behind an explicit option such as:
- `--include-session` for machine-readable formats
- `--header` or similar for markdown-oriented human output

### 4. Future Commands Must Be Session-First
- Any future detail/inspection/compare command should:
- resolve session(s) through the common resolver
- attach canonical `session` rows
- attach `backing_artifacts`, `stats`, `search_findings`, or derived views as opt-in expansions

## Implementation Phases

### Phase 1. Extract Resolution Cleanup
- Introduce an internal extract-target abstraction:
- resolved `session`
- selected `backing_artifact`
- optional provider-specific extraction context
- Replace any remaining extractor-path special cases with common-model-driven artifact selection where possible.
- Make extractor selection explicitly flow from provider plus backing artifact provenance.

### Phase 2. `--file` Semantic Alignment
- Define one internal path for `extract --file`:
- infer provider from artifact provenance
- normalize artifact path
- derive required session context if the provider needs it
- reuse common extraction target selection logic
- Tighten error messages around unsupported or non-extractable artifacts.

### Phase 3. Optional Metadata Expansions
- Decide whether `extract` needs an opt-in metadata mode now.
- If yes, add a narrow first version only for structured output.
- Keep markdown and jsonl transcript defaults unchanged.

### Phase 4. Reusable Foundation for Future Commands
- Extract reusable helpers for:
- resolve one session
- resolve many sessions
- select primary extractable backing artifact
- distinguish `backing_artifacts` from `search_findings`
- This becomes the foundation for any later `inspect`/`compare` style command work.

## First Change Set
- Add a shared internal “resolved extract target” helper.
- Refactor `extract_chat_session()` to consume the helper for both query and `--file` paths.
- Normalize all artifact-selection logic to `backing_artifacts`.
- Update extractor-facing tests to cover:
- query resolution
- `--file` artifact entry
- ambiguity handling
- provider-specific non-extractable artifact behavior

## Acceptance Criteria
- `extract <query>` still emits the same transcript output for existing users.
- `extract --file` is documented and implemented as a backing-artifact entrypoint.
- Internal extract logic no longer depends on legacy flat session JSON fields.
- Session and artifact terminology is consistent in code and error messages.
- Tests cover both session-query and backing-artifact-driven extraction flows.

## Deferred Items
- Session metadata wrappers for `extract` output.
- New session inspection commands.
- Two-session compare or diff commands.

## Suggested Sequence
1. Refactor `extract` internals onto the common model without changing output.
2. Tighten `--file` semantics and errors.
3. Add missing tests around artifact selection.
4. Reassess whether `extract` needs opt-in session metadata.
5. Only then design additional session-scoped commands on top of the shared model.

## Verification
- `uv run pytest tests/test_chat_commands.py tests/test_chat_extract_commands.py -q`
- `uv run pytest -q`
