# Chatlas Update Workflow Split - design-summary

## Summary

`agentos chatlas update` should be split into explicit phases, starting with an `index-only` phase that refreshes the Chatlas session index as the canonical substrate for later work. The split should keep the current behavior intact while removing the current monolithic orchestration shape in `src/agentos/chatlas/core.py`.

## Accepted Decisions

1. Add `index-only` as the first named phase of `chatlas update`.
   Rationale: the current update flow interleaves raw mirroring, session discovery, index materialization, git staging, manifest writing, cache writes, and commit creation. The first split should make session indexing an explicit unit with its own typed result and reporting.

2. Treat `<Provider>.Session` / provider session code as the owner of provider-native session metadata normalization.
   Rationale: provider-specific knowledge belongs near the provider session implementation, not in Chatlas orchestration code. Chatlas should consume normalized session records.

3. Preserve current `chatlas update` behavior through composition of phases, not through legacy compatibility branches.
   Rationale: the implementation should keep raw mirroring, session index shard writing, manifest writing, git commits, cache behavior, and CLI reporting, but the command should orchestrate named phases instead of embedding all responsibilities in one function.

4. Keep `index-only` integrated with the current raw-backed discovery model until a separate source model is designed.
   Rationale: today `_materialize_session_index()` discovers sessions by building provider agents whose homes point at `chatlas_root/raw/...`. `index-only` therefore still needs the indexed source tree required by provider discovery, and the design should not pretend the current index can be refreshed from live provider homes without changing semantics.

5. Cache normalized session metadata in the Chatlas session index/cache.
   Rationale: the existing session-index cache already bypasses `_session_ref_index_record()` when source signatures match. The split should make cache hits/misses visible in the index phase result and keep future passes from rereading raw artifacts for session-level metadata.

6. Make later Chatlas phases depend on the session index phase result.
   Rationale: stats, query, raw-path lookup, export selection, manifest summaries, and future derived work should consume indexed session rows wherever they only need session-level metadata.

7. Keep command reporting aligned across progress output and JSON output.
   Rationale: users running the CLI interactively and agents consuming `--output-mode=json` should see the same phase outcomes and counts.

## Execution Plan

1. Name the current phases in code and model them as typed results.
   Current phases are: settings/provider selection, git/cache preparation, raw archive mirror, session index materialization, git/manifest finalization, and cache persistence.

2. Introduce an index phase function that owns session discovery, index-row materialization, cache reuse, and shard writing.
   The likely extraction point is `_materialize_session_index()`, expanded into a result that records discovered refs, indexed rows, cache hits, cache misses, shard writes, and selected provider/instance context.

3. Add `index-only` to the Chatlas update workflow as the first executable phase.
   The existing `chatlas update` command should call the same index phase used by `index-only` instead of duplicating logic. The phase result should become part of the command JSON payload and progress output.

4. Keep raw archive mirroring as a separate phase that can remain in full `chatlas update`.
   The current implementation mirrors raw provider homes via `_archive_chatlas_provider_contexts()` and `_mirror_chatlas_provider_context()`. The split should preserve this behavior and its scan-cache optimization while making it a sibling phase, not a prerequisite hidden inside one large function.

5. Define the dependency order precisely.
   Full `chatlas update` should run source preparation/mirroring as needed, then run `index-only`, then run dataset finalization. Future commands can target `index-only` directly once the CLI surface is added.

6. Move provider-native session metadata normalization into provider session modules where it is missing or currently inferred by Chatlas.
   Existing provider `SessionRef` classes already own `display_name()`, `display_name_field()`, `native_ref_metadata()`, `sort_timestamp()`, `to_session()`, and `sources()` through the loaded `<Provider>.Session`. New metadata required by downstream phases should follow that pattern.

7. Extend the session-index cache shape only where the phase split requires it.
   Keep the existing source-signature comparison model, but add phase counters and any newly required normalized metadata to the cached session row rather than introducing a second cache.

8. Rework downstream update phases to consume the materialized index result instead of rediscovering or rereading raw artifacts for session-level decisions.

9. Update CLI progress messages and `--output-mode=json` payloads so each phase reports comparable counts.
   Preserve existing top-level fields while adding a `phases`/`index` shaped payload so current functionality remains visible and future phase-specific reporting has a stable home.

10. Add focused tests around cache reuse, phase reporting, and downstream dependence on the session index.
    Existing tests already cover raw retention, sharded index writes, no-op update commits, and cache bypass behavior. New tests should assert the `index-only` phase result and that full update reuses that same phase path.

## Deferred Items

- Specific provider-by-provider metadata fields are deferred until implementation inspects each provider session model.
- Command-surface changes beyond `agentos chatlas update` phase selection and reporting are deferred.
- Dataset migration policy for existing Chatlas index/cache files is deferred until the final index schema change is known.

## Relevant Files Or Surfaces

- `src/agentos/chatlas/core.py`
- `src/agentos/chatlas/commands.py`
- `src/agentos/chatlas/raw.py`
- `src/agentos/chatlas/_cache_io.py`
- `src/agentos/agent/primitives.py`
- `src/agentos/agent/session_refs.py`
- `src/agentos/*/session.py`
- `tests/test_chatlas_commands.py`
- `notes/live/560-agentos-agent-session-model-design-summary.md`
- `notes/live/562-provider-session-ref-model-cleanup-impl-req.md`
- `notes/live/567-provider-session-source-model-impl-req.md`

## Open Questions

- What exact CLI spelling should select the phase: `agentos chatlas update --phase index-only`, `agentos chatlas update --index-only`, or a subcommand under `chatlas update`?
- Should raw mirroring remain part of full `chatlas update` after the split, or become an explicit sibling phase with its own command surface later?
- What is the minimum stable session-index schema that downstream passes need before raw artifacts can be treated as optional inputs?

## End Log

- 2026-05-11: Created focused design summary for splitting `agentos chatlas update` into a session-index-first workflow.
- 2026-05-11: Deepened the design after inspecting the current `chatlas update` implementation, including raw mirroring, session-index materialization, cache behavior, git finalization, provider `SessionRef` discovery, and existing tests.
