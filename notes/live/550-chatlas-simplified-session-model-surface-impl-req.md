# Chatlas Simplified Session Model Surface - impl-req

## Impl-Req State

Implementation in progress; Phase 4 promoted the session model to `chatlas session-model export`.

## User Intent

Simplify Chatlas so it only backs up provider raw artifacts, maintains a lightweight session index, and provides an on-demand in-memory normalized session model.

The user explicitly wants to remove transcript and summary features for now because they are unused and make Chatlas harder to reason about. Those features may return later as views over the standard session model.

## Why This Exists

Chatlas currently mixes several responsibilities:

- raw provider artifact backup
- lightweight session discovery/indexing
- derived transcript materialization
- derived summary materialization
- transcript/summary export commands
- experimental standard-model export

The accepted direction is to reduce Chatlas to its core boundary:

```text
raw provider artifacts
  -> raw archive
  -> sessions.index.jsonl
  -> in-memory session model export
```

This keeps provider-specific parsing isolated at the normalizer boundary and avoids persisting unstable derived views before the standard model has settled.

## Current Situation

- `agentos chatlas update` mirrors provider raw artifacts, materializes `normalized/sessions.jsonl`, materializes derived transcripts, materializes derived summaries, and commits the dataset.
- `agentos chatlas export` supports transcript and summary exports.
- `agentos chatlas query` supports transcript text filters and summary expansions.
- `agentos chatlas experimental export` builds the current standard session model in memory.
- The accepted storage decision is that `session.std.model` remains in memory/export-time only for now.

## Requested Change

Implement the new Chatlas command and dataset surface:

```text
agentos chatlas update
agentos chatlas stats
agentos chatlas query [query]
agentos chatlas session-model export <query>
agentos chatlas raw path <query>
agentos chatlas raw export <query>
```

Dataset layout should converge to:

```text
raw/
index/sessions.index.jsonl
manifests/updates/
cache/
```

Remove the current transcript and summary product surfaces:

- derived transcript materialization
- derived summary materialization
- transcript and summary caches
- `agentos chatlas export --artifact-kind transcript`
- `agentos chatlas export --artifact-kind summary`
- transcript text query filters
- query summary expansions
- `agentos chatlas experimental export`

Promote the session-model surface:

- Move the current experimental session-model package to a non-experimental namespace such as `agentos.chatlas.session_model`.
- Rename the public API to a stable name, for example `chatlas_export_session_model`.
- Add `agentos chatlas session-model export <query>`.
- Change the model envelope from `agentos.chatlas.experimental.session_model` to `agentos.chatlas.session_model`.
- Drop the top-level `experimental: true` field.
- Keep provider-specific normalizers isolated behind the session-model builder.

## Constraints And Invariants

- Do not persist the full `session.std.model` yet.
- Do not add compatibility aliases for removed commands.
- Do not preserve legacy transcript/summary tests for compatibility.
- Keep raw provider artifacts as the durable provider-native truth.
- Keep the session model provider-neutral.
- Keep `source_refs` as the bridge from standard-model records back to raw artifacts.
- Missing provider normalizers should error clearly instead of falling back silently.
- `query` should be metadata/session lookup only, not transcript text search.
- `sessions.index.jsonl` is a lightweight session catalog, not the full chat model.
- Use `uv` for Python test/tooling commands.
- After changing the installed CLI, refresh with `uv tool install --reinstall --editable .`.

## Out Of Scope

- Reintroducing transcript or summary views.
- Persisting `session.std.model`.
- Designing stable content-addressed event ids.
- Building a UI.
- Adding search over message text.
- Changing provider raw retention policy except as required by removed derived artifacts.

## Acceptance Signals

- `agentos chatlas update` backs up raw artifacts and refreshes `index/sessions.index.jsonl` without creating derived transcripts or summaries.
- `agentos chatlas query` works for metadata/session lookup and no longer exposes transcript text filters or summary expansions.
- `agentos chatlas session-model export <query>` returns the promoted standard model with `class: agentos.chatlas.session_model`.
- `agentos chatlas raw path <query>` resolves one session and prints its backing raw artifact paths.
- `agentos chatlas raw export <query>` resolves one session and emits raw artifact contents.
- `agentos chatlas experimental export` is removed.
- `agentos chatlas export --artifact-kind transcript|summary` is removed.
- Current standard-model reference sessions for Codex, Copilot CLI, and Claude Code still pass contract tests through the new command.
- Tests cover the reduced command surface rather than legacy behavior.

## Suggested Implementation Phases

1. **Rename the session catalog**
   - Move the materialized catalog from `normalized/sessions.jsonl` to `index/sessions.index.jsonl`.
   - Rename internal concepts from "normalized sessions" to "session index" where practical.
   - Update update payloads, manifests, stats, and tests to use session-index wording.

2. **Remove derived transcript and summary materialization**
   - Delete update phases that create `derived/transcripts/` and `derived/summaries/`.
   - Remove transcript/summary cache loading and writing.
   - Remove update/stat fields that report derived transcript or summary counts.

3. **Simplify query**
   - Remove transcript filters and summary expansion flags from the command parser and core query implementation.
   - Keep provider, instance, identity, sort, limit, extractable, artifacts, match, and provider stats behavior if still useful.

4. **Promote session model**
   - Move `src/agentos/chatlas/experimental/` to `src/agentos/chatlas/session_model/`.
   - Rename public functions and imports.
   - Add `chatlas session-model export`.
   - Update class name and envelope fields.
   - Convert experimental tests to stable session-model tests.

5. **Remove old export and experimental commands**
   - Delete transcript/summary export command support.
   - Delete `chatlas experimental export`.
   - Remove associated tests instead of adding compatibility coverage.

6. **Add raw commands**
   - Implement `chatlas raw path <query>`.
   - Implement `chatlas raw export <query>`.
   - Start with one-session resolution and clear ambiguous/no-match errors.

7. **Final cleanup**
   - Remove dead helpers, constants, dataclasses, and cache paths.
   - Refresh the installed CLI.
   - Run focused Chatlas command tests and the full Chatlas test module if practical.

## Relevant Files Or Surfaces

- `src/agentos/chatlas/core.py`
- `src/agentos/chatlas/commands.py`
- `src/agentos/chatlas/experimental/`
- `tests/test_chatlas_commands.py`
- `notes/live/534-chatlas-standard-chat-model.md`
- `notes/live/544-chatlas-event-first-standard-model.md`
- `notes/live/546-chatlas-provider-neutral-standard-model-plan.md`
- `notes/live/547-chatlas-standard-model-contract.md`
- `dev/session-samples/`

## Open Questions

- Should the session index file be exactly `index/sessions.index.jsonl`, or should the index directory use a different name later?
- Should `raw export` emit all backing artifacts concatenated, a JSON envelope, or require `--source` once multiple sources exist?
- Should `chatlas stats` keep provider raw artifact size/count details in the first cleanup pass, or stay limited to provider/session counts?

## Related Impl-Reqs

- None.

## End Log

- 2026-04-30: Created after the user accepted the simplified Chatlas command surface and requested an implementation request artifact.
- 2026-04-30: Phase 1 started. The session catalog now materializes at `index/sessions.index.jsonl`, update payloads expose `session_index_path` / `session_index_count`, and the update cache flag is now `--session-index-cache`.
- 2026-04-30: Phase 2 removed update-time derived transcript and summary materialization, removed derived transcript cache loading/writing, removed derived count fields from update/stats output, and pruned tests for update-provided transcript/search summary behavior.
- 2026-04-30: Phase 3 simplified query to session-index metadata lookup by removing transcript-content filters, summary expansions, transcript filter match output, and the now-unused summary cache readers from the query path.
- 2026-04-30: Phase 4 moved the session-model implementation from `agentos.chatlas.experimental` to `agentos.chatlas.session_model`, added `agentos chatlas session-model export`, renamed the public export API to `chatlas_export_session_model`, changed the envelope class to `agentos.chatlas.session_model`, and removed the top-level `experimental` flag from the model contract.
