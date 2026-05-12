# Chatlas Delta Scan - design-summary

## Summary

This design defines `Chatlas.Delta.Scan`, the first scan/update strategy for the new `agentos chatlas update` `index-only` phase. The strategy copies changed provider-native raw session artifacts into Chatlas-controlled raw storage, then updates the session index from the copied Chatlas raw artifacts for only the delta session set.

## Accepted Decisions

1. `index-only` uses `Raw.Copy.Index.Flow`.

   The phase first copies provider raw session sources into Chatlas-controlled storage, then discovers and indexes sessions from the copied substrate. The indexer must not derive final index rows directly from live provider homes after copying.

2. Provider integration is a hard boundary.

   Chatlas uses existing Agentos `<Provider>.Agent` and `<Provider>.Session` models. Chatlas owns orchestration, raw-copy boundaries, index rows, cache/reporting, and phase boundaries. Providers own raw-session interpretation and session-ref/session loading behavior.

3. `Chatlas.Delta.Scan` is the first implementation strategy.

   The scan explores `native-raw-artifacts` in provider homes, compares them with native-derived derivation cache state, produces a delta session/artifact set, copies only delta artifacts into `chatlas-raw-artifacts`, then derives/upserts index rows from the copied artifacts for the delta set.

4. Delta detection is native-based; index derivation is Chatlas-raw-based.

   `session-index-derivations` is maintained directly from `native-raw-artifacts` and exists to detect what changed in provider storage. The session index is maintained from `chatlas-raw-artifacts` and represents what Chatlas has copied and owns.

5. `session-index-derivations` is a private acceleration cache.

   Use `cache/session-index-derivations-v1` as the cache family. The cache may be deleted and rebuilt. Future phases must not treat it as authoritative product state.

6. The derivation cache and session index have different authority and may have different row sets.

   The derivation cache may drop entries absent from the latest native provider-home scan because it models current native scan state. The session index may retain rows for copied Chatlas raw artifacts that are no longer present in native provider homes, because the index models the Chatlas-owned raw substrate.

7. Scan/update locality should be provider/home oriented.

   `Chatlas.Delta.Scan` should avoid repeatedly loading unrelated files session by session. When the scan reaches a provider/home partition, it should load the matching derivation cache partition and process the related native artifacts/sessions together.

8. Session index files should align with provider/home locality.

   The public session index files should be grouped by provider/home partition, using a layout compatible with the derivation cache partitions. This favors efficient delta upserts over global identity-hash sharding for the first `index-only` implementation.

9. `Ref.First.Load.Control` applies inside the scan.

   Provider session discovery should produce lightweight refs first. Full `Provider.Session` loading or raw-content reads are allowed only when required for an explicit index field, and those loads should be visible, cacheable, and justified.

10. `index-only` does not know about later phases.

   It may update copied raw sources, derivation cache, and session index files. It must not include query/export/stats behavior, broad raw archive lifecycle policy, or git finalization policy.

## Execution Plan

1. Define the public/private data contract.

   Establish `chatlas-raw-artifacts`, provider/home-partitioned session index files, and `cache/session-index-derivations-v1` as separate artifact families with separate authority.

2. Define provider/home partition keys.

   Choose a stable partition key from provider family plus provider instance/home identity. Decide whether large histories need sub-buckets within a provider/home partition.

3. Implement native scan state.

   For each configured provider/home, scan native raw session artifacts through existing provider Agent/Session capabilities and produce lightweight native artifact/session signatures.

4. Implement derivation cache compare.

   Load the provider/home derivation cache partition, compare native signatures, and produce a delta set of changed/new native artifacts or sessions. Rewrite that cache partition from current native scan state.

5. Copy delta raw artifacts.

   Copy only delta artifacts from provider homes into Chatlas-controlled raw storage. The copied paths become the source for index derivation.

6. Derive delta index rows from Chatlas raw artifacts.

   Rebuild index rows only for delta sessions using provider SessionRef/Session behavior pointed at the copied Chatlas raw substrate.

7. Upsert provider/home index files.

   Load the corresponding provider/home index file partition, replace rows for delta sessions, preserve rows for non-delta Chatlas raw sessions, and write the partition back deterministically.

8. Report phase results.

   Return counts for native scan, cache hits/misses or unchanged/changed sessions, copied raw artifacts, and index rows created/updated/unchanged.

## Deferred Items

- Final query/export/stats behavior is deferred. Those phases should consume the session index later.
- Broad raw archive lifecycle policy is deferred. `index-only` copies raw sources needed to support index production but does not define full retention semantics.
- Git finalization, manifest writing, and commit policy are deferred.
- Exact provider/home partition and sub-bucket naming are deferred to the next design question.
- Full index row schema is deferred beyond the fields required to reason about scan/update authority and cache boundaries.

## Relevant Files Or Surfaces

- `notes/live/577-chatlas-update-index-design-session.md`
- `notes/live/575-chatlas-update-workflow-split-design-summary.md`
- `_DEPRECATED/chatlas-update-v1/src/agentos/chatlas/core.py`
- `_DEPRECATED/chatlas-update-v1/src/agentos/chatlas/raw.py`
- `src/agentos/chatlas/`
- `src/agentos/*/session.py`
- `src/agentos/agent/`

## Open Questions

- What is the exact provider/home partition key and path layout for both session index files and `session-index-derivations` cache files?
- Should large provider histories be split by time, hash bucket, or provider-native grouping inside a provider/home partition?
- What is the minimal index row schema required for first implementation?
- What exact counts belong in the `index-only` JSON report payload?

## End Log

- 2026-05-11: Created to capture the converged `Chatlas.Delta.Scan` design as a dedicated design summary linked from the active design-session artifact.
