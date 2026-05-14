# Chatlas Query Command - impl-req

## Impl.Abstract

- **scope:** implement the minimal `agentos chatlas query` command as the full Chatlas session query caller
- **status:** implemented
- **source:** `591-chatlas-query-command-design-session.md`
- **target:** replace the current `chatlas query` stub with a layered query pipeline over index rows, raw artifacts, and standard session model text
- **non-goals:** do not change `agentos chatlas export` or `agentos chatlas raw`; do not add a query DSL, OR groups, regex matching, or detailed match provenance in this first cut

## Impl.Index

### Chatlas.Query.Command.Surface

- `agentos chatlas query` should be an explicit-flag command with no positional query argument.
- The first implementation should keep the command simple and scriptable.
- Query output is JSON only.
- Query returns normalized session rows, not raw artifacts, index rows, or standard-model records as primary results.
- Existing `agentos chatlas index query` remains the low-level full-index-row selector.

#### appendix

Original implementation state:

- `src/agentos/chatlas/commands.py` wires `chatlas query`.
- `src/agentos/chatlas/core.py` raised the explicit `chatlas query is under reimplementation` stub before this implementation.
- `src/agentos/chatlas/index_query.py` already provides index-row loading, filtering, sorting, and single-row selection primitives.
- `tests/test_chatlas_commands.py` had a stub-failure test that should be replaced.

#### meta

- source: `591-chatlas-query-command-design-session.md`
- status: ready for implementation

### Query.Layered.Pipeline

- Query should run in sequential layers:

```text
index rows -> raw artifact filters -> standard model filters -> projection
```

- Index filters run first and should reuse existing index-row matching behavior where practical.
- Raw artifact filters run only for candidate rows that survived index filtering.
- Standard-model filters run only for candidate rows that survived index and raw filtering.
- All supplied filters compose with simple AND semantics.

#### appendix

Minimal first-cut filters:

```text
index:
  --uri
  --identity-hash
  --provider
  --session-id
  --display-name
  --extractable
  --updated-after
  --sort
  --limit
  --scan-limit

raw:
  --raw-contains

standard model:
  --user-contains
  --assistant-contains
  --message-contains
```

Use literal case-insensitive substring matching for all `contains` filters. Repeated `contains` filters should compose with AND. Regex and case-sensitivity controls are out of scope.

#### meta

- status: accepted first-cut scope

### Query.Limit.Semantics

- `--scan-limit` bounds candidate rows entering expensive raw and standard-model filters.
- `--limit` bounds final returned rows after all filters have been applied.
- Default `--scan-limit` should be `5000`.
- Default `--limit` should be `50`.
- Final result ordering should preserve the selected index sort order after later filters remove non-matching rows.

#### appendix

This avoids the common false-negative shape where a caller asks for:

```sh
agentos chatlas query --sort newest --limit 20 --raw-contains chatlas
```

and misses matches because `--limit` was applied before raw filtering.

The intended execution is:

```text
index filter and sort -> scan_limit candidates -> raw/model filters -> limit returned rows
```

#### meta

- status: accepted by implementation-design common-sense default

### Query.Result.Row

- The default query projection should return minimal normalized session rows.
- Row fields:
  - `uri`
  - `provider`
  - `session_id`
  - `updated_at`
  - `home`
  - `project_path`
- `home` and `project_path` should be returned as `null` when unknown.
- Do not expose full index rows by default.
- First-cut query should not include detailed match provenance.

#### appendix

Default row shape:

```json
{
  "uri": "agentos://chat-session/...",
  "provider": "codex",
  "session_id": "...",
  "updated_at": "...",
  "home": "/Users/pereiro/.codex",
  "project_path": "/Users/pereiro/projects/agentos-project"
}
```

Candidate payload shape:

```json
{
  "status": "ok",
  "command": "chatlas query",
  "filters": {},
  "sort": "newest",
  "scan_limit": 5000,
  "limit": 50,
  "scanned_row_count": 123,
  "index_matched_row_count": 50,
  "candidate_row_count": 50,
  "query_matched_row_count": 3,
  "returned_row_count": 3,
  "rows": []
}
```

Exact count names may follow local code style, but the payload should distinguish scanned/index candidates, post-filter matches, and returned rows.

#### meta

- status: accepted first-cut output contract

### Query.Failure.Policy

- Missing indexes and zero matches should return a successful empty result payload.
- Malformed index rows should follow existing index loader behavior.
- Unreadable raw artifacts should not crash the whole query; the affected session should simply fail the raw filter.
- Standard-model build failures should not crash the whole query; the affected session should simply fail standard-model filters.
- This first cut should not report per-row errors unless the existing codebase already has a simple pattern for doing so.

#### appendix

The minimal query command is a discovery surface. It should favor robust scanning and empty matches over failing the entire command when one candidate has incomplete artifacts or an unsupported normalizer.

#### meta

- status: accepted first-cut policy

### Query.Envelope.Normalization

- `agentos chatlas query` should read as an extension of `agentos chatlas index query`.
- Both commands should share the same top-level response envelope where practical.
- Row payloads may differ:
  - `agentos chatlas index query` returns full index rows.
  - `agentos chatlas query` returns normalized session rows by default.
  - A later `chatlas query` projection option may allow full index rows.
- Normalize count fields around explicit query phases instead of relying on ambiguous `matched_row_count`.
- Preferred shared count fields:
  - `scanned_row_count`
  - `skipped_row_count`
  - `index_matched_row_count`
  - `candidate_row_count`
  - `query_matched_row_count`
  - `returned_row_count`
- For `agentos chatlas index query`, the phase counts collapse:
  - `index_matched_row_count` is rows matching index filters before limit.
  - `candidate_row_count` equals `index_matched_row_count` unless index query later adds a scan-limit phase.
  - `query_matched_row_count` equals `index_matched_row_count`.
  - `returned_row_count` is rows after limit.
- For `agentos chatlas query`, the phase counts remain layered:
  - `index_matched_row_count` is rows matching index filters before scan-limit.
  - `candidate_row_count` is rows entering raw/model filtering after scan-limit.
  - `query_matched_row_count` is rows surviving all query filters before final limit.
  - `returned_row_count` is rows after final limit.
- Avoid adding raw/model-specific count fields in the minimal version unless diagnostics require them.

#### appendix

Normalized envelope sketch:

```json
{
  "status": "ok",
  "command": "chatlas query",
  "chatlas_root": "...",
  "session_index_root": "...",
  "filters": {},
  "sort": "lexical",
  "scan_limit": 5000,
  "limit": 50,
  "partition_count": 0,
  "scanned_row_count": 0,
  "skipped_row_count": 0,
  "index_matched_row_count": 0,
  "candidate_row_count": 0,
  "query_matched_row_count": 0,
  "returned_row_count": 0,
  "rows": []
}
```

`agentos chatlas index query` may omit `scan_limit` until it has a scan-limit phase, but should otherwise use the same count vocabulary.

#### meta

- status: follow-up accepted

## Execution.Plan

### Slice 1 - Replace query stub with metadata-only query

- create or update a query implementation module, likely `src/agentos/chatlas/query.py`
- wire `agentos chatlas query` to the new implementation instead of the stub in `core.py`
- remove the positional `query` argument from the CLI
- support index-layer filters for the first observable endpoint:
  - `--uri`
  - `--identity-hash`
  - `--provider`
  - `--session-id`
  - `--display-name`
  - `--extractable`
  - `--updated-after`
  - `--sort`
  - `--scan-limit`
  - `--limit`
- return minimal normalized rows with `home` and `project_path` as `null` when unknown
- path: CLI parser -> query service -> index rows -> minimal JSON result
- observable: `agentos chatlas query --session-id <id>` returns session rows instead of the reimplementation stub
- check: focused CLI tests for no index, one matching row, zero matches, no positional argument, default limit, and final row shape
- status: implemented

### Slice 2 - Add raw artifact contains filtering

- add `--raw-contains`, repeatable
- evaluate raw filters only for rows that survived index filtering and scan-limit selection
- treat each filter as a literal case-insensitive substring
- repeated `--raw-contains` filters compose with AND
- inspect extractable backing artifacts from each candidate row; do not return raw artifacts as primary results
- unreadable artifacts should make that candidate fail the raw filter rather than failing the entire query
- path: index candidate row -> backing artifact paths -> text scan -> session predicate -> minimal row
- observable: `agentos chatlas query --raw-contains chatlas` returns only sessions whose indexed backing artifacts contain the text
- check: tests with two indexed sessions and copied raw artifacts where only one contains the requested text
- status: implemented

### Slice 3 - Add standard-model text filters

- add `--user-contains`, `--assistant-contains`, and `--message-contains`, each repeatable
- evaluate standard-model filters only after index and raw filters
- build or project the standard session model for each remaining candidate using existing Chatlas session model helpers
- `--user-contains` searches visible user-authored message text
- `--assistant-contains` searches visible assistant-authored message text
- `--message-contains` searches visible user or assistant message text
- use literal case-insensitive substring matching
- repeated flags compose with AND
- unsupported normalization or build failure should make that candidate fail the standard-model filter rather than failing the entire query
- path: candidate index row -> standard session model -> visible messages -> session predicate -> minimal row
- observable: standard-model text filters can distinguish user text from assistant text
- check: tests with fixture sessions where user and assistant messages contain different text
- status: implemented

### Slice 4 - Tighten command surface and validation

- remove legacy query-only options that are not part of the first minimal design:
  - positional `query`
  - `--compact`
  - `--include-match`
  - `--include-artifacts`
  - `--include-provider-stats`
  - `--updated-since`
- keep `--updated-after` for consistency with index selectors
- make `agentos chatlas query --help` reflect the minimal layered query surface
- ensure `agentos chatlas index query`, `export`, `raw`, `views`, and `stats` behavior remains unchanged
- path: parser definitions -> help text -> command dispatch tests
- observable: help has no positional query and no deferred expansion flags
- check: CLI parser/help tests and existing Chatlas command tests
- status: implemented

### Slice 5 - Verify installed CLI behavior

- run focused Chatlas command tests
- run broader relevant tests if focused tests pass
- reinstall editable CLI after code changes using `uv tool install --reinstall --editable .`
- smoke test the installed `agentos chatlas query --help`
- smoke test a simple installed query against the local Chatlas dataset when practical
- path: tests -> editable install -> installed CLI smoke
- observable: installed `agentos` exposes the new query surface and no longer reports the stub error
- check:
  - `uv run python -m pytest tests/test_chatlas_commands.py -q`
  - targeted additional tests if new query tests live elsewhere
  - `uv tool install --reinstall --editable .`
  - `agentos chatlas query --help`
- status: implemented

### Slice 6 - Normalize query envelopes

- update `agentos chatlas index query` to emit explicit phase counts:
  - `index_matched_row_count`
  - `candidate_row_count`
  - `query_matched_row_count`
  - `returned_row_count`
- update `agentos chatlas query` to use `query_matched_row_count` for rows surviving all query layers before final limit.
- remove or de-emphasize ambiguous `matched_row_count` from both command payloads unless a compatibility decision is made separately.
- keep row projection differences intact:
  - index query rows are full index rows.
  - chatlas query rows are normalized session rows by default.
- path: index query service -> chatlas query service -> command tests
- observable: both command payloads use the same count vocabulary while preserving their row shapes.
- check: focused tests for `chatlas index query` and `chatlas query` envelope fields and count semantics.
- status: implemented

## Impl.Log

- 2026-05-14: Created implementation request from `591-chatlas-query-command-design-session.md` after user accepted the minimal first-cut query design.
- 2026-05-14: Implemented `agentos chatlas query` as a layered explicit-flag command. Added `src/agentos/chatlas/query.py`, wired `core.py` and `commands.py`, removed the query positional argument and deferred expansion flags, added raw and standard-model contains filters, and replaced the stub test with focused behavior coverage.
- 2026-05-14: Verified with `uv run python -m pytest tests/test_chatlas_commands.py -q` (32 passed), `uv run python -m pytest -q` (281 passed), `uv tool install --reinstall --editable .`, `agentos chatlas query --help`, and `agentos chatlas query --sort newest --limit 2` against the local Chatlas dataset.
- 2026-05-14: Captured follow-up decision to normalize `chatlas index query` and `chatlas query` envelopes around explicit phase counts while allowing their `rows` projections to differ.
- 2026-05-14: Implemented Slice 6 envelope normalization. `agentos chatlas index query` now emits explicit phase counts, `agentos chatlas query` reports `query_matched_row_count`, and the ambiguous `matched_row_count` field was removed from both payloads.
- 2026-05-14: Verified Slice 6 with `uv run python -m pytest tests/test_chatlas_commands.py -q` (32 passed), `uv run python -m pytest -q` (283 passed), `uv tool install --reinstall --editable .`, `agentos chatlas index query --session-id 2434a1a6-34b2-4054-8525-64c27a30e1c5 --format json`, and `agentos chatlas query --session-id 2434a1a6-34b2-4054-8525-64c27a30e1c5`.
