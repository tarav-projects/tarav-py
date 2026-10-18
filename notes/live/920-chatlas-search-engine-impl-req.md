# Chatlas search engine — implementation request

<!-- tarav.sessions
3537df0a = claude-code:2bff854f-66a0-4e8c-8f96-9078af34c479 @3537df0a6015d884a94e9594478f971cb92e38df63776b87b5eea38741740d8a
-->

## Impl.Abstract

Status: complete, 2026-10-18; search speed needs alignment (see Impl.Log).
Knowledge.Surface: wiki.
Alignment.Mode: interactive.

Let Tarav search across chats. The Chatlas workflow provides a search engine
for Tarav's Search workflow (`tarav.l1.search`): a minimal interface with
simple queries over the cached Normal Models of every indexed session.
Turns are the default unit of a hit; a session without a cached Model is
built when searched. The engine is the base a Tarav Center chat search view
will call.

Non-goals: a dedicated text index, regular expressions or ranking, a new
`tarav chatlas` command, the Tarav Center workflow itself, faster
unvalidated reads.
<!-- tarav.breadcrumb 1d2075c14d88 -->
<!-- tarav.breadcrumb 0fc80cd3a31f -->

## Design

### Decisions (User)

- `tarav.l1.search` does not know about Chatlas. The Chatlas workflow
  provides a search engine for Chatlas data; Chatlas is the one that knows how
  to search its database. It provides a minimal interface, with simple queries
  for now.
  <!-- tarav.breadcrumb 91febf2a5462 -->
- The search can be split by construction: search only messages, or turns.
  The interface lets the caller decide; there are defaults, but the API is
  general.
  <!-- tarav.breadcrumb caaef1499dc4 -->
- Turns are the default target. A session with no cache is built.
  <!-- tarav.breadcrumb 2dd85716165b -->
- Carried from request 919: the library gives full information, such as a
  stale flag per cached part; public surfaces choose a safe path.
  <!-- tarav.breadcrumb ce32aa8b2699 -->

### Agent decisions

- `ChatlasSearchQuery(SearchQuery)` in `tarav.l1.chatlas.search` carries:
  `target` (`"turns"`, default, or `"messages"`), `text` (literal,
  case-insensitive, optional), `side`, session filters read from index rows
  (`provider`, `project` as a path prefix of `project_path`, `since` and
  `until` on `last_activity_at`), `times` (turn start times, default off) and
  `build_missing` (default on). `max_hits` and `engines` come from
  `SearchQuery`.
- `ChatlasSearchEngine(SearchEngine)` accepts only `ChatlasSearchQuery`. It
  walks index rows newest activity first and yields hits session by session,
  newest first inside a session, so the incremental stream gives recent hits
  first and `max_hits` stops the scan early.
- The target decides which cached parts are read: `messages` reads
  `messages`; `turns` reads `turns` and `messages`, plus `events` only when
  `times` is on. Turn selection reuses `ChatlasQueryEngine` (Chatlas Query owns
  selection and record assembly); it gains `ChatlasQuery.times` (default on,
  so `tarav chatlas query` is unchanged) to skip events.
- A stale cache is searched as stored. Every hit carries `ChatlasSearchHit`:
  the session facts from its row, the target, the turn match or message, and
  the `CachedPart` standing of each part it read. A session whose cache cannot
  be built (for example a transcript without conversation) is skipped and
  logged at debug level.
- The installed runtime registers the engine in `runtime.search` as
  `chatlas`.

### Known cost

Measured 2026-10-18 on the warm cache (10,146 Models): validated reads of
2,000 sessions took 2.7 s for messages and 5.2 s for turns, so a full scan of
every session costs roughly 15 s (messages) to 40 s (turns). A raw JSON scan
of all messages took 1–3 s; validation dominates. Filters and `max_hits`
bound ordinary use; a faster read path is separate performance work.

## Current implementation observations

Inspected 2026-10-18:

- `src/tarav/l1/search/__init__.py`: `SearchQuery`, `SearchHit`,
  `SearchEngine` with its `Search` namespace (`accepts`, `_iter_hits`),
  `SearchService.register(name, engine)`.
- `src/tarav/l1/actions/views.py`: `ActionResolver` is an existing engine.
- `src/tarav/l3/runtime.py`: `search = SearchWorkflow.service()`; nothing
  registers in it yet.
- `src/tarav/l1/chatlas/query.py`: `ChatlasQuery`, `ChatlasQueryEngine.run`
  always reads events for selected turns (`_started_at_for_turn`).
- `src/tarav/l1/chatlas/normal_model_cache.py`: `NormalModelCache`,
  `CachedPart`, `PARTS` (request 919).
- `src/tarav/l1/chatlas/index_store.py`:
  `load_chatlas_session_index_rows(chatlas_root=, providers=)`.

## Impl.Req.Wiki

- Product project: `tarav-py`.
- Wiki owner: `tarav-md` (`notes/wiki/`).
- Relevant note: `notes/wiki/chatlas-normal-model.md`.
- Supporting chat: `claude-code:2bff854f-66a0-4e8c-8f96-9078af34c479`.
- Capture status: see Impl.Log.

## Execution.Plan

Core data shape: `ChatlasSearchQuery` (above); `ChatlasSearchHit(session,
target, turn, message, parts)` where `turn` is a `ChatlasTurnMatch` for the
turns target and `message` a Chat.Message record for the messages target.

1. Feature — `ChatlasQuery.times`. Result: a turn query without times reads no
   events. Check: test over a cached Model without `events.jsonl`; CLI JSON
   unchanged apart from the new query field. Status: done (ba6b177).
2. Feature — `tarav.l1.chatlas.search`. Result: the query, hit and engine.
   Check: `tests/chatlas/test_search.py` over a temporary depot (index rows +
   caches): target, text, side, filters, order, `max_hits`, build of a missing
   cache, stale flag. Status: done (d4dcc5e).
3. Feature — runtime registration. Result: `get_runtime().search` answers a
   `ChatlasSearchQuery`. Check: real search on the depot for a phrase of this
   session; timing recorded. Status: done (421a8b0).
4. Docs — ARCHITECTURE Chatlas paragraph; Wiki capture. Status: done.

Deviation triggers: the Search namespace pattern not fitting a long-running
scan; `ChatlasQueryEngine` reuse forcing semantic changes to the CLI.

## Impl.Log

- 2026-10-18: request written by the designing Agent in the session above.
- 2026-10-18, Execute (same session, cold reload). Start checkpoints:
  tarav-py 97ff7e1 (this note), tarav-md 7fbc137 (empty); external tarav-md
  work found at the start was committed apart as 84ee2cc and 9faef09
  (unknown session).
- Slice 1: `ChatlasQuery.times`. `tests/chatlas/test_query_times.py` failed
  first (TypeError, unknown `times`), then 2 passed. The CLI JSON gains
  `"times": true` and still reports start times. The Normal Model fixture
  moved to `tests/chatlas/_helpers.py` (`normal_model_fixture`) for the cache,
  query and search tests. Breadcrumb on `query.py` (1). Commit ba6b177.
- Slice 2: `tarav.l1.chatlas.search`. `tests/chatlas/test_search.py` failed
  at collection (no module), then 9 passed. `tests/test_architecture.py`
  lists `search.py` among the Normal Model consumers, beside `sessions.py`
  and `references.py`; the rule for capture and index modules is unchanged.
  Breadcrumbs on `search.py` (5). Commit d4dcc5e.
- Slice 3: `runtime.search` registers the engine as `chatlas`; a routing test
  (10 search tests). Real depot through the installed runtime: turns, user
  side, "raw.version", `max_hits=5`: 3 hits in 80.5 s (fewer than five hits,
  so the whole depot was scanned); messages, "tarav-center": 29 hits in
  30.6 s; turns, "tarav-center": 28 hits in 88.3 s. Hits came from this
  session (fresh) and from the live session d82f1801 (stale, correctly
  flagged). Breadcrumb on `runtime.py` (1). Commit 421a8b0.
- Observation, measured: a full scan costs about twice the designed estimate.
  A profile of a turns search over 78 recent sessions (17.9 s) puts 91% of
  it in `_validated_collection_row`, the kernel `from_record`/`to_record`
  round trip of every cached turn and message; turns alone take 14.3 s.
  Cached streams were validated when built. A trusted read of cache rows is
  the main lever and needs a User decision; it is outside this request.
- Slice 4: ARCHITECTURE paragraph; 2 Breadcrumbs, 43 shifted positions
  refreshed, audit clean.
