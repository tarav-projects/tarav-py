# The Normal Models index and a consumer-controlled Chatlas pipeline — implementation request

<!-- tarav.sessions
3537df0a = claude-code:2bff854f-66a0-4e8c-8f96-9078af34c479 @3537df0a6015d884a94e9594478f971cb92e38df63776b87b5eea38741740d8a
-->

## Impl.Abstract

Status: complete, 2026-10-18.
Knowledge.Surface: wiki.
Alignment.Mode: interactive.

Add a third derived Chatlas stage, a SQLite database at
`index/normal-models.sqlite`, built from the JSON Normal Model cache, and make
cross-chat search read it. Expose the pipeline (native provider folders →
raw capture → JSON cache → index) as separate operations the consumer
controls, each with a read-only standing and an explicit update over a
selection of sessions. Search reads the index as it is; flags on the search
query run chosen parts of the pipeline first.

Non-goals: moving events and loaded contexts into the database, replacing
the JSON cache, automatic indexing during `chatlas update`, a new CLI command,
the Tarav Center view.
<!-- tarav.breadcrumb 8971c1c7879b -->
<!-- tarav.breadcrumb e85f7cf2f365 -->

## Design

### Why

After requests 919–921 a scan over every cached chat still costs 12.9 s
(messages) and 24.8 s (turns). Profiled 2026-10-18: about 31,000 file opens,
73,000 `stat` calls and per-line JSON parsing across 10,146 chats; pydantic is
0.7 s of it. A plain open-read-match scan has a 1–3 s floor. One indexed
database answers in milliseconds and supports richer queries.
<!-- tarav.breadcrumb c6f817fe4edb -->

### Decisions (User)

- Chatlas is responsible for producing and caching the Normal Models; an
  index on top gives fast and expressive search. The index is named for what
  it holds, not for search, because other consumers can use it:
  `index/normal-models.sqlite`.
  <!-- tarav.breadcrumb c9d789540b35 -->
  <!-- tarav.breadcrumb aedabfc0907d -->
  <!-- tarav.breadcrumb 3ca16cc871de -->
- The JSON Normal Model stays. The chain is generation → cache → SQL index,
  triggered on demand, with an expressive API so consumers control how it
  runs.
  <!-- tarav.breadcrumb c3c0bd78c3fb -->
  <!-- tarav.breadcrumb f85ddd3a6939 -->
- One freshness rule along the chain: the raw data declares its version, each
  cache file declares its own version, a pass-through of the `raw_version` it
  used, and so on; each stage is fresh when the version it recorded is still
  the one its input declares.
  <!-- tarav.breadcrumb 305bdef3a6a0 -->
  <!-- tarav.breadcrumb 0209a68d7c47 -->
- Search reads the index only. Updating is on request, through flags; there
  are different flags for different parts of the pipeline, and together they
  run the whole update from the native provider folders to the index.
  <!-- tarav.breadcrumb 2e8ac6ff5506 -->
  <!-- tarav.breadcrumb 753727e180e0 -->
- Search may run on the data as stored, without checks, configured like the
  rest of the query; other paths keep their own policies.
  <!-- tarav.breadcrumb 7c74f7c5b2ff -->

### Agent decisions

- **Stages and their versions.** Raw: `raw_version` in the Session Index row
  (request 919). Cache: each part file records the `raw_version` it was built
  from (`cache.json`). Index: per session and part, the cache part version it
  was built from. A maintainer who rebuilds the cache after a normalizer fix
  deletes the index too (the cache version passes the raw version through).
- **What the index holds first.** Tables `sessions` (identity, provider,
  instance, session id, project path, last activity), `parts` (identity,
  part, version indexed), `messages` (identity, position, message address,
  side, text, the message's turn hash, the JSON row as stored), `turns`
  (identity, position, turn address, turn hash, side, the JSON row), and a
  full-text table over message text. WAL mode, so readers run while one
  writer updates.
- **Built only from the JSON cache**, never from raw; one transaction per
  session replaces that session's rows.
- **Pipeline API, placeholder names.** The library offers, per stage, a
  read-only *standing* and an *update* over a selection with a policy
  (missing; missing and stale; all), returning what was done and what
  failed: capture (native → raw, today's delta scan scoped through
  `ScanScope`), cache (raw → JSON parts, `NormalModelCache.build`), index
  (JSON → database). A convenience runs any chosen stages in order. Names
  and exact signatures are settled during execution, not here.
- **Selection** uses Session Index facts: provider, project path prefix,
  activity window, identities. Capture can only be narrowed by provider,
  sessions and time window; project filters apply from the cache stage on.
- **Search.** `ChatlasSearchEngine` reads the index. `ChatlasSearchQuery`
  keeps its fields; `build_missing` and the cache standing fields are
  replaced by per-stage update flags (capture, cache, index), off by default,
  applied to the sessions the query selects. Hits keep session facts, the
  turn or message, and its position.
- **One system.** The per-file scan in `search.py` is removed, not kept as a
  fallback.
- **On demand.** `chatlas update` keeps capturing only; nothing indexes
  implicitly.

### Clarification (User), at execution

The interface is expressive, even allowing direct SQL queries. The executing
Agent reads it as: word matching through FTS5, substring matching through
plain SQL over message text, and read-only SQL for anything else; agent
messages are indexed with `side` as a column. This answers the two questions
below.
<!-- tarav.breadcrumb 24d4e731069b -->

### Open questions (User), answered above

1. Text matching: by **words** (FTS5 default tokenizer: compact, ranked,
   phrases and prefixes, no search inside a word), or by **substring**
   (trigram tokenizer: today's literal "contains", index several times larger,
   weaker ranking)? The designing Agent proposes words.
2. Agent messages indexed too, with `side` as a column? Proposed: yes.

## Current implementation observations

Inspected 2026-10-18:

- `src/tarav/l1/chatlas/search.py`: `ChatlasSearchQuery`, `ChatlasSearchHit`,
  `ChatlasSearchEngine` (scan over `NormalModelCache`), registered as
  `chatlas` in `src/tarav/l3/runtime.py`.
- `src/tarav/l1/chatlas/normal_model_cache.py`: `NormalModelCache`
  (`parts`, `model`, `build`), `CachedPart`, `PARTS`.
- `src/tarav/l1/chatlas/delta_scan.py`: `chatlas_delta_scan(scope=ScanScope,
  ...)`; `src/tarav/l1/chatlas/paths.py`: `SESSION_INDEX_ROOT =
  index/sessions`.
- Depot `~/Documents/tarav/chatlas/index/` is Git-ignored; 10,146 of 10,180
  sessions have a cached model.
- Python's `sqlite3` is SQLite 3.49.1 with FTS5.

## Impl.Req.Wiki

- Product project: `tarav-py`. Wiki owner: `tarav-md`; note
  `notes/wiki/chatlas-normal-model.md`.
- Supporting chat: `claude-code:2bff854f-66a0-4e8c-8f96-9078af34c479`.
- Capture status: see Impl.Log.

## Execution.Plan

Core data shape: the tables above, and a per-stage *standing* record
(session, stage, part, recorded version, current version, state: missing,
stale, fresh).

1. Feature — the index stage. Build and update `index/normal-models.sqlite`
   from the JSON cache for a selection; standing per session and part. Check:
   tests over a temporary depot (fresh, stale after a cache rebuild, missing,
   one-transaction replacement); real build over the depot, time and size
   recorded.
2. Feature — the pipeline API. Standing and update for capture, cache and
   index over one selection, plus the convenience runner. Check: tests with a
   fake provider home; a real scoped run for one session.
3. Feature — search on the index. Engine and query reworked, per-stage update
   flags, the scan removed. Check: the search tests rewritten for the index;
   the real "tarav-center" searches timed against 12.9 s and 24.8 s.
4. Docs — ARCHITECTURE, Wiki.

Deviation triggers: FTS5 query syntax leaking through `text` in a way that
changes plain-text searches; index size far beyond the estimate.

## Impl.Log

- 2026-10-18: request designed in the session above; handed off as
  needs-alignment on the two open questions.
- 2026-10-18, Execute (same session). Clarification recorded; start
  checkpoints: tarav-py acbf539, tarav-md 789651d (empty).
- Slice 1: `NormalModelsIndex` (`src/tarav/l1/chatlas/normal_models_index.py`)
  and `NormalModelCache.rows(part)`. `tests/chatlas/test_normal_models_index.py`
  failed at collection (no module), then 3 passed; the index joined the
  Normal Model consumers in `tests/test_architecture.py`. Real build: 10,146
  sessions indexed, 34 skipped (no conversation), 0 failed, 39 s, 1,032 MB;
  phrase match 3 ms, `instr` substring scan 1.9 s; an update with nothing to
  do 2.2 s. Commit 563906a.
- Deviation trigger (size) raised with the User: the JSON copies of each turn
  (428 MB, mostly event references) and message (182 MB) took most of it.
  User decision: keep only what lookups need; full records stay in the JSON
  cache.
  Schema 2 without the record columns: rebuilt in 31 s, 338 MB; phrase
  match 2 ms, substring scan 1.1 s.
  <!-- tarav.breadcrumb 9f02077f9d08 -->
- Slice 2: `ChatlasStages` (`src/tarav/l1/chatlas/stages.py`): `select`,
  `standing`, `capture` (wraps `chatlas_update` with provider, session ids
  and a window from `since`), `update_cache`, `update_index`, `run`;
  `CachedPart.state` speaks the same missing/stale/fresh as the index.
  `tests/chatlas/test_stages.py` failed at collection, then 4 passed. Real
  scoped run for this session: before, cache fresh and index stale; `run`
  2.5 s (capture ok, 1 cached, 1 indexed); after, both fresh.
- Slice 3: `search.py` reads the index: `text` (words as a phrase), `match`
  (FTS5 expression), `contains` (substring through SQL), the same filters,
  and `capture`/`cache`/`index` flags that run those stages first for the
  query's selection; hits carry the session facts, the turn and its
  messages (or the message) as the index holds them. The per-file scan,
  `build_missing`, `times` and the cache standing in hits are gone.
  `NormalModelsIndex.rows` streams, so `max_hits` stops early.
  `tests/chatlas/test_search.py` rewritten: 6 of 7 failed on the old engine,
  then 7 passed. Real searches: messages "tarav-center" 17 ms (was 12.9 s),
  turns 121 ms (was 24.8 s), substring 1.5 s, first 20 turns for "cache"
  64 ms. Word matching finds 64 messages where the substring finds 33,
  because the phrase also matches "Tarav Center".
- Slice 4: ARCHITECTURE describes the search engine on the index and the
  three stages (3 Breadcrumbs); Wiki `tarav-md` `chatlas-normal-model.md`
  and the daily note (commit 5e0328e).
