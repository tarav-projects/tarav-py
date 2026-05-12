# Chatlas Delta Scan - impl-req

## Impl-Req State

Implemented as the first real `index-only` slice after the Chatlas v1 runtime was archived and replaced with stubs.

## User Intent

Implement `Chatlas.Delta.Scan` for the new `agentos chatlas update` system. The first implementation should produce/update the Chatlas session index efficiently and safely by copying changed provider-native raw session artifacts into Chatlas-controlled raw storage, then deriving index rows from the copied artifacts.

## Why This Exists

The old `chatlas update` implementation mixed raw mirroring, session discovery, index materialization, cache management, git finalization, manifest writing, query/export support, and CLI reporting in one runtime. That code is now dead reference code under `_DEPRECATED/chatlas-update-v1/`. The new runtime needs a clean first phase that proves `Raw.Copy.Index.Flow` and gives later phases an index substrate without reintroducing the monolith.

## Current Situation

Live Chatlas runtime now has a first real update phase:

- `src/agentos/chatlas/core.py` wires `chatlas_update()` to the new `Chatlas.Delta.Scan` implementation.
- `src/agentos/chatlas/delta_scan.py` implements the first `index-only` path: provider-native delta detection, raw copy into Chatlas storage, and provider/home-local index upserts from copied raw artifacts.
- `src/agentos/chatlas/commands.py` still registers the existing `agentos chatlas` command surface and update flags.
- Query/stats/raw/export helpers remain explicit stubs.
- `_DEPRECATED/chatlas-update-v1/` contains the old implementation as non-runtime reference only.

The active design-session and summary establish:

- `index-only` is the first phase.
- `Raw.Copy.Index.Flow`: copy provider raw session sources first, then index from the copied Chatlas raw substrate.
- `Provider.Model.Boundary`: use existing Agentos `<Provider>.Agent` and `<Provider>.Session` models; do not create a parallel Chatlas provider model.
- `Ref.First.Load.Control`: discover lightweight refs first; control and cache any expensive full-session/raw loads.
- `Chatlas.Delta.Scan`: native-based delta detection, Chatlas-raw-based index derivation.

## Requested Change

Replace the `chatlas_update` stub with the first real `index-only` implementation based on `Chatlas.Delta.Scan`.

The implementation must:

1. Resolve configured Chatlas provider instances using existing Agentos agent/provider configuration surfaces.
2. Scan `native-raw-artifacts` in provider homes through provider Agent/Session capabilities.
3. Maintain `cache/session-index-derivations-v1` as private native-derived scan/cache state.
4. Detect delta sessions/artifacts from native scan signatures and the derivation cache.
5. Copy only delta raw artifacts into Chatlas-controlled raw storage.
6. Derive/update session index rows from `chatlas-raw-artifacts`, not directly from native provider homes.
7. Upsert only delta session rows into provider/home-local session index files.
8. Return a JSON/progress payload with useful counts for scan, copy, cache, and index work.

## Constraints And Invariants

- `_DEPRECATED` is dead reference code. Do not import it, package it, test it, or use it as fallback.
- Preserve the current `agentos chatlas` command registration.
- Keep `index-only` isolated from later phases. It must not implement query/export/stats, broad raw archive lifecycle policy, git finalization, manifests, or commits.
- Chatlas must use existing Agentos provider Agent/Session abstractions. Provider-specific raw interpretation belongs in provider session code.
- Delta detection is native-based. The derivation cache answers what changed in native provider storage.
- Index derivation is Chatlas-raw-based. The session index answers what sessions are represented by copied Chatlas raw artifacts.
- `cache/session-index-derivations-v1` is private acceleration state and may be deleted/rebuilt.
- The derivation cache and session index may have different row sets. Dropping a cache entry absent from current native scan does not imply deleting an index row backed by copied Chatlas raw artifacts.
- Avoid eager full-session/raw loading. Any full `Provider.Session` load or raw-content read during indexing must be explicit, justified by an index field, and cacheable by source signature.
- Prefer provider/home-local partitions for both derivation cache files and session index files so one scan pass does not repeatedly load unrelated files.

## Out Of Scope

- Reimplementing `chatlas query`, `chatlas stats`, `chatlas raw path/export`, or `chatlas export`.
- Finalizing broad raw retention semantics beyond copying raw sources needed for session index support.
- Git commit, manifest, and dataset finalization behavior.
- Runtime migration from old v1 index/cache formats.
- Depending on global identity-hash sharding as the first index layout if it conflicts with provider/home locality.
- Adding compatibility bridges to the deprecated implementation.

## Acceptance Signals

- `agentos chatlas update --output-mode=json` exits successfully and returns `"status": "ok"` with phase/report fields for the real `index-only` path.
- `agentos chatlas update --provider codex --output-mode=json` restricts work to the selected provider and reports that selection.
- A fixture-backed provider-home run copies expected raw session artifacts into Chatlas raw storage.
- The resulting session index rows are derived from copied Chatlas raw paths, not native provider-home paths.
- A second unchanged run reports unchanged/cache-hit/no-delta behavior and does not rewrite or reload unnecessary session raw content.
- A changed native artifact run copies only the changed artifact/session set and upserts only the matching index rows.
- If a native artifact disappears after being copied, the derivation cache can drop the native entry while the existing session index row remains when backed by Chatlas raw storage.
- `rg "_DEPRECATED" src/agentos` returns no runtime imports.
- Focused tests cover the above behavior without restoring old monolithic update tests.

## Implementation Shape

### Slice 1: Command Surface And Report Contract

Behavior:

When `agentos chatlas update --output-mode=json` runs against an empty or no-selection fixture, the command returns a real `index-only` shaped payload rather than the stub payload.

Observable result:

- JSON includes `status`, `command`, `phase`, `selection`, `raw_copy`, `session_index`, and `cache` or equivalent fields.
- Provider filters are reflected in `selection`.
- Existing quiet/progress behavior remains intentional.

Check:

- Focused CLI tests in `tests/test_chatlas_commands.py`.

Design assumption validated:

- The stub can be replaced by a real phase entrypoint without reintroducing query/export/stats behavior.

### Slice 2: Provider/Home Partition And Native Derivation Cache

Behavior:

For a fixture provider home with session raw artifacts, the scan builds provider/home-local native signatures and writes `cache/session-index-derivations-v1` partitions.

Observable result:

- Cache files exist under a provider/home-local layout.
- Cache entries represent current `native-raw-artifacts` signatures.
- Removing a native artifact removes or marks the cache entry on the next scan.

Check:

- Unit or behavior tests around the cache partition read/write and native scan compare.

Design assumption validated:

- `session-index-derivations` is native scan state, not public index authority.

### Slice 3: Delta Raw Copy

Behavior:

Changed/new native raw artifacts are copied into Chatlas-controlled raw storage. Unchanged artifacts are skipped using native signatures and cache state.

Observable result:

- First run copies fixture artifacts.
- Second unchanged run reports no copied/updated artifacts.
- Mutating one artifact copies only that changed artifact/session set.

Check:

- Fixture test with file mtimes/sizes/content changes and JSON count assertions.

Design assumption validated:

- `Chatlas.Delta.Scan` can reduce work by processing deltas while preserving `Raw.Copy.Index.Flow`.

### Slice 4: Index Rows From Chatlas Raw Artifacts

Behavior:

For delta sessions, build provider session refs/sessions pointed at the copied Chatlas raw substrate and upsert rows into provider/home-local session index files.

Observable result:

- Index rows contain copied Chatlas raw backing artifact paths.
- Rows include stable identity/session fields required by the existing provider session ref model.
- Deleting a native artifact after it was copied does not delete the index row merely because the native scan no longer sees it.

Check:

- Fixture tests read the index JSONL rows and assert source paths, session ids, provider fields, and retention of copied-row state across native disappearance.

Design assumption validated:

- Delta detection can be native-based while index derivation remains Chatlas-raw-based.

### Slice 5: Cache Reuse And Load Control

Behavior:

On unchanged runs, index rows are reused from derivation/cache state or existing index partitions without eager full raw/session loading.

Observable result:

- Cache hit/unchanged counters increase on second run.
- Tests can monkeypatch a provider full-session/raw-load path to fail on unchanged runs, while the command still succeeds.

Check:

- Focused tests using monkeypatch or provider fixture instrumentation.

Design assumption validated:

- `Ref.First.Load.Control` is enforced by behavior, not only by code shape.

## Relevant Files Or Surfaces

- `notes/live/578-chatlas-delta-scan-design-summary.md`
- `notes/live/577-chatlas-update-index-design-session.md`
- `notes/live/575-chatlas-update-workflow-split-design-summary.md`
- `notes/live/576-chatlas-update-v1-deprecation-stub-impl-req.md`
- `_DEPRECATED/chatlas-update-v1/README.md`
- `_DEPRECATED/chatlas-update-v1/src/agentos/chatlas/core.py`
- `_DEPRECATED/chatlas-update-v1/src/agentos/chatlas/raw.py`
- `_DEPRECATED/chatlas-update-v1/src/agentos/chatlas/session_model/`
- `src/agentos/chatlas/commands.py`
- `src/agentos/chatlas/core.py`
- `src/agentos/chatlas/raw.py`
- `src/agentos/chatlas/_cache_io.py`
- `src/agentos/chatlas/session_model/_hashes.py`
- `src/agentos/agent/primitives.py`
- `src/agentos/agent/providers.py`
- `src/agentos/agent/session_refs.py`
- `src/agentos/*/session.py`
- `tests/test_chatlas_commands.py`
- `tests/test_chatlas_session_hashes.py`

## Open Questions

- What exact provider/home partition path should be used for `cache/session-index-derivations-v1` and session index files?
- Should large provider histories be split by provider-native grouping, time, or hash bucket inside provider/home partitions?
- What is the minimal first-slice index row schema? The old v1 schema is useful reference, but the implementation should not preserve it blindly.
- Should the first public CLI expose `--phase index-only`, or should `agentos chatlas update` run only the first phase until later phases exist?

## Related Impl-Reqs

- `notes/live/576-chatlas-update-v1-deprecation-stub-impl-req.md`

## Related Design Artifacts

- `notes/live/578-chatlas-delta-scan-design-summary.md`
- `notes/live/577-chatlas-update-index-design-session.md`
- `notes/live/575-chatlas-update-workflow-split-design-summary.md`

## End Log

- 2026-05-12: Created implementation request for the first real `Chatlas.Delta.Scan` / `index-only` implementation, grounded in the active design-session and design-summary artifacts.
- 2026-05-12: Implemented the first `Chatlas.Delta.Scan` runtime in `src/agentos/chatlas/delta_scan.py` and wired `chatlas_update()` to it. The implementation uses provider/home-local partitions under `raw/<provider>/<fingerprint>/home`, `cache/session-index-derivations-v1/<provider>/<fingerprint>/sessions.json`, and `index/sessions/<provider>/<fingerprint>/sessions.index.jsonl`; query/export/stats remain explicit stubs. Verified with focused Delta Scan tests, full pytest, touched-file Ruff, `_DEPRECATED` import scan, installed CLI refresh, and an isolated `agentos chatlas update --output-mode=json` smoke test.
- 2026-05-12: Extended the `chatlas update --output-mode=json` payload with top-level and per-provider/home stats for source artifacts, cache hits/misses, raw-copy work, index upserts, and scan/update timing.
- 2026-05-12: Added the same scan/cache/artifact/index/timing summary to the default progress output printed by `agentos chatlas update`, with total and per provider/home lines.
