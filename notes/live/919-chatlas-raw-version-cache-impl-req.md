# Chatlas cache freshness from the raw data — implementation request

<!-- tarav.sessions
3537df0a = claude-code:2bff854f-66a0-4e8c-8f96-9078af34c479 @3537df0a6015d884a94e9594478f971cb92e38df63776b87b5eea38741740d8a
-->

## Impl.Abstract

Status: ready, 2026-10-18.
Knowledge.Surface: wiki.
Alignment.Mode: autonomous.

Make the Chatlas Normal Model cache usable for every session, as a step
towards a Tarav Center Chatlas workflow (search chats, view a chat). A cached
artifact is fresh exactly when the raw data it was built from has not changed:
each cached part records the `raw_version` it was built from, and the Session
Index row carries the current `raw_version`. The library exposes every cached
part with its standing (present, built from, current, stale); public surfaces
such as the CLI keep choosing a safe path.

Non-goals: a cross-session search index, new JSON commands (both still under
discussion), slimmer builds of single parts, any change to retained raw
provider data.
<!-- tarav.breadcrumb bbd470fe2dd8 -->
<!-- tarav.breadcrumb 5d205cd639d9 -->

## Design

### Why

The cache key mixed three things: the stat fingerprints of the transcript
sources, the Normal Model schema version, and the tarav-py Git HEAD
(`normal_model_producer_commit()`). Every tarav-py commit therefore made every
cached model stale; on 2026-10-18 only 71 of 10,178 indexed sessions had a
cached model, under twenty different producer commits. The cache also required
all four collection files plus `cache.json`, so a model was either complete and
fresh or rebuilt.

### Decisions (User)

- Remove the Git HEAD from the cache key.
  <!-- tarav.breadcrumb e930f0ef51d5 -->
- Cache validation is only about whether the raw data changed. Each cached
  artifact is paired with the `raw.version` of the raw data it used, a hash
  computed from that data. Code evolution is out of the validation workflow:
  invalidating after a normalizer change is the maintainers' responsibility,
  not the code's.
  <!-- tarav.breadcrumb ef0d1fcbca84 -->
  <!-- tarav.breadcrumb eaec9b2a2edf -->
- The fingerprint basis stays path + size + modification time; the capture
  side computes `raw_version` and writes it into the Session Index row, so a
  freshness check is a string comparison.
  <!-- tarav.breadcrumb d6167873d975 -->
- Parts are cached and judged separately. Some consumers (search) use what is
  cached; others request a brand new model. Reading one part does not need the
  others; cross-part checks belong to building.
  <!-- tarav.breadcrumb 1c6b3cf1f379 -->
  <!-- tarav.breadcrumb 0aa07a5359dd -->
- Separate the core library from the CLI. The library provides all access with
  full information: paths that return what is cached together with a stale
  flag. The CLI and other public surfaces decide how to be safe and convenient.
  <!-- tarav.breadcrumb 76d93d03716c -->
- Migrate whatever Chatlas derived data needs it; retained provider raw data is
  immutable for this implementation.
  <!-- tarav.breadcrumb cbbab766ef66 -->

Already done earlier in the same session, before this request: the depot
stopped tracking `normal-model/` in Git (`.gitignore`, staged `git rm
--cached`), and the stale `session-models/`, `chatlas2/` and old-layout
`normal-model/` entries were deleted.
<!-- tarav.breadcrumb 7cebdd0de6e6 -->

### Agent decisions

- `raw_version` is `sha256:` over the sorted `(path, size_bytes, modified_ns)`
  of the session's transcript sources, the same sources the pipeline
  normalizes (current backing artifacts plus archive versions). Paths stay
  absolute: index rows already store absolute backing-artifact paths, so a
  relative hash would not make a moved depot valid. A missing source makes the
  version `None`.
- It is computed in `_merged_session_index_row`, the one join point of delta
  upserts and `index redo`, and stripped by `plain_index_version` so it never
  changes archive-version identity.
- Transcript source selection moves from `normal_model/pipeline.py` to
  `index_writer.py`: the index must not import `normal_model`
  (`test_the_normal_model_layer_sits_on_capture_and_not_the_other_way`), and
  the pipeline already imports `archive_versions_for` from there.
- `cache.json` becomes schema version 5 and records `parts`: one
  `raw_version` per part (`main`, `events`, `messages`, `turns`,
  `loaded_contexts`). A build writes every part with the row's version.
- `NormalModelCache` (in `normal_model_cache.py`) is the policy-free view:
  `parts()` returns a `CachedPart` per part (present, raw_version,
  current_raw_version, stale); `read(part)` yields stored rows whatever their
  standing; `model()` opens what is stored; `build()` rebuilds every part.
  `ChatSession.cache()` returns it.
- The safe path `provide_normal_model_reader_from_row(row, parts=…)` returns
  the cached model when every requested part (default: all) is present and
  fresh, otherwise builds. The CLI behaves as before.
- A row without `raw_version` (written before this change) makes every part
  stale. Migration runs `tarav chatlas index redo` (reads raw, rewrites the
  derived index only); no fallback computes versions at read time.
- The Normal Model header keeps `metadata.commit` as build provenance; it no
  longer participates in validation.

## Current implementation observations

Inspected 2026-10-18:

- `src/tarav/l1/chatlas/normal_model_cache.py`: `_cache_identity` hashes
  `session_identity`, `_source_fingerprints(row)`,
  `NORMAL_MODEL_SCHEMA_VERSION` and `normal_model_producer_commit()`;
  `normal_model_cache_status_from_row` requires every file.
- `src/tarav/l1/chatlas/normal_model/pipeline.py`: `transcript_paths`,
  `_transcript_sources`, `_version_transcript_paths`,
  `normal_model_producer_commit` (runs `git rev-parse HEAD`).
- `src/tarav/l1/chatlas/index_writer.py`: `_session_index_row`,
  `_merge_session_index_rows`, `_merged_session_index_row`,
  `plain_index_version`, `_dedupe_versions`.
- `src/tarav/l1/chatlas/sessions.py`: `ChatSession.model()` delegates to
  `provide_normal_model_reader`.
- Depot `~/Documents/tarav/chatlas`: `index/` and `normal-model/` are derived
  and Git-ignored; `raw/` is retained evidence.
- The Chatlas cache tests were pruned in `2b01171`; no cache test exists.

## Impl.Req.Wiki

- Product project: `tarav-py`.
- Wiki owner: `tarav-md` (`notes/wiki/`), which holds Chatlas design notes.
- Relevant note: `notes/wiki/chatlas-normal-model.md` (Cache decoration).
- Supporting chat: `claude-code:2bff854f-66a0-4e8c-8f96-9078af34c479`.
- Capture status: pending.

## Execution.Plan

Core data shape: Session Index row field `raw_version: str | None`;
`cache.json` `{schema, schema_version: 5, session_identity, parts: {part:
raw_version}}`; `CachedPart(name, present, raw_version, current_raw_version,
stale)`.

1. Refactor — transcript source selection lives in `index_writer`.
   Result: pipeline imports it; behavior unchanged. Check: architecture tests,
   one model build through the CLI. Status: pending.
2. Feature — index rows carry `raw_version`. Result: merged rows get the
   version; archive versions are unaffected. Check: new
   `tests/chatlas/test_raw_version.py`. Status: pending.
3. Feature — per-part cache validated by `raw_version`. Result:
   `NormalModelCache`, `CachedPart`, `parts=` on the safe path,
   `ChatSession.cache()`; Git HEAD out of the key. Check: new
   `tests/chatlas_normal_model/test_cache.py`. Status: pending.
4. Migration — depot index redo, drop schema-4 caches. Result: every row has
   `raw_version`; a second CLI query is a cache hit. Check: scripted count and
   timing. Status: pending.
5. Docs — ARCHITECTURE Chatlas paragraph, Wiki capture. Status: pending.

Deviation triggers: index redo failing on real data; a consumer depending on
`transcript_paths` from the pipeline module outside tarav-py.

## Impl.Log

- 2026-10-18: request written by the designing Agent in the session above.
