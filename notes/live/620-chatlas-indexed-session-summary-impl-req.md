# Chatlas Indexed Session Summary - impl-req

## Impl.Abstract

- **scope:** add provider-neutral indexed session summary metadata to Chatlas session index rows, then use it to make query filters such as `--min-user-turns` index-speed.
- **status:** implemented.
- **source:** direct design discussion after observing that `agentos chatlas query --updated-after 2026-05-12T00:00:00-04:00 --min-user-turns 6 --sort newest --limit 5` took about `43.5s`, while equivalent index-only selection took about `1s`.
- **goal:** compute visible transcript summary during Chatlas index derivation/update, store it in each session index row, and make query use that indexed summary instead of rebuilding full session models for turn-count filtering.
- **strong constraint:** no legacy support for old index rows. After the implementation, run `agentos chatlas index redo` to rebuild the index. Do not add fallback code that silently parses old rows without summary.

## Impl.Index

### Current.Query.Design

- CLI entrypoint: `src/agentos/chatlas/commands.py`.
- Metadata-only query path:
  - `agentos chatlas index query`
  - `src/agentos/chatlas/index_query.py`
  - loads all session index JSONL rows through `load_chatlas_session_index_rows(...)`
  - filters by fields already stored on the row: provider, session id, display name, extractable, updated timestamp, etc.
- General query path:
  - `agentos chatlas query`
  - `src/agentos/chatlas/query.py`
  - first applies index-row filters
  - then applies `--raw-contains` by reading raw artifacts
  - then applies standard-model filters by calling `build_chatlas_session_model_from_index_row(row)` for every scanned candidate
- Current expensive filters:
  - `--user-contains`
  - `--assistant-contains`
  - `--message-contains`
  - `--min-user-turns`
- Current default scan window:
  - `scan_limit=5000`
  - output `limit=50`

### Current.Index.Design

- Session index rows are derived in `src/agentos/chatlas/delta_scan.py`.
- Main row builder:
  - `_session_index_row(...)`
- Current index row fields include:
  - provider / instance / fingerprint / home
  - project path
  - URI / session id / display name
  - created / updated timestamps
  - extractability and backing artifact metadata
  - native metadata
  - identity hash
- Chatlas update already uses a delta path:
  - unchanged sessions avoid full re-index work through session-index derivation cache
  - changed sessions are copied to raw storage and have index rows re-derived
- Because index derivation is already part of refresh, summary derivation belongs there, not in query.

### Performance.Evidence

- Dataset observed on 2026-05-19:
  - `session_count`: `23612`
  - `partition_count`: `7`
  - `copilot-cli` dominates the current row count with `19242` sessions
- Measured commands:
  - `agentos chatlas index query --updated-after 2026-05-12T00:00:00-04:00 --sort newest --limit 5` took about `0.9s`
  - `agentos chatlas query --updated-after 2026-05-12T00:00:00-04:00 --sort newest --limit 5` took about `1.0s`
  - `agentos chatlas query --updated-after 2026-05-12T00:00:00-04:00 --min-user-turns 6 --sort newest --limit 5` took about `43.5s`
- For the slow query:
  - `index_matched_row_count`: `2336`
  - `candidate_row_count`: `2336`
  - `query_matched_row_count`: `31`
  - `returned_row_count`: `5`
- Interpretation:
  - The slow part is standard-model reconstruction for each candidate row.
  - `--min-user-turns` should not require full standard-model construction at query time once the index carries visible turn counts.

### Summary.Schema

- Add a provider-neutral `summary` object to every session index row.
- Initial schema:

```json
{
  "summary": {
    "visible_user_turn_count": 7,
    "visible_assistant_turn_count": 6,
    "visible_message_count": 13,
    "visible_user_text_char_count": 12345,
    "visible_assistant_text_char_count": 45678,
    "visible_text_char_count": 58023,
    "first_user_text_excerpt": "...",
    "last_user_text_excerpt": "...",
    "last_assistant_text_excerpt": "..."
  }
}
```

- Do not add redundant boolean fields such as:
  - `has_visible_user_text`
  - `has_visible_assistant_text`
- Those are derivable from counts and should not be stored.
- Excerpt policy:
  - excerpts are for quick inspection, not full transcript storage
  - trim leading/trailing whitespace
  - collapse excessive whitespace enough to keep one-line JSON rows readable
  - cap excerpts to a small fixed length, e.g. `240` characters
  - exact cap can be a local constant in the implementation
- Count policy:
  - count only visible conversation messages, matching the existing query semantics in `src/agentos/chatlas/query.py`
  - `visible_user_turn_count`: count visible user messages
  - `visible_assistant_turn_count`: count visible assistant messages
  - `visible_message_count`: visible user + visible assistant messages
  - char counts are based on the same visible text extracted from those messages

### Query.Semantics

- `--min-user-turns N` must use `row["summary"]["visible_user_turn_count"]`.
- If summary is missing or malformed, the row should not match summary-backed filters.
- Do not fall back to `build_chatlas_session_model_from_index_row(...)` for `--min-user-turns`.
- Rationale:
  - there is no legacy support
  - after implementation, the operator should run `agentos chatlas index redo`
  - query should remain fast and predictable
- Existing content filters can remain standard-model based for now:
  - `--user-contains`
  - `--assistant-contains`
  - `--message-contains`
- Future work may use indexed text/search metadata, but this Impl.Req only requires optimizing summary-backed predicates.

### Index.Redo.Required

- This change introduces required indexed data.
- The implementation must not carry stale row compatibility.
- After installing the implementation, run:

```sh
agentos chatlas index redo
```

- Then verify that current index rows contain `summary`.

### No.Legacy.Allowed

- Do not add compatibility fallback for old rows without `summary`.
- Do not preserve old query behavior for `--min-user-turns`.
- Do not add a second query engine.
- Do not compute indexed summary lazily inside query.
- Do not add a sidecar cache for summaries separate from the session index row.
- Do not expand scope into search indexing for `--user-contains`, `--assistant-contains`, or `--message-contains`.

## Execution.Plan

### Slice 1 - Add Summary Derivation

Status: implemented.

- Add provider-neutral summary derivation for a session index row.
- Preferred path:
  - build the standard session model once during index derivation for the changed session
  - extract visible user/assistant message texts using the same semantics currently used by query
  - write `summary` into `_session_index_row(...)`
- Keep failures local:
  - if a session cannot be normalized, produce a summary with zero counts and no excerpts or report the derivation failure consistently with current indexing behavior
  - do not crash the whole index update for one bad raw artifact unless current index derivation already treats it as fatal
- Tests:
  - index row derivation includes `summary`
  - counts distinguish visible user and assistant messages
  - excerpts use first/last user and last assistant text

### Slice 2 - Make `--min-user-turns` Use Indexed Summary

Status: implemented.

- Update `src/agentos/chatlas/query.py`.
- Move `--min-user-turns` out of the standard-model filter path.
- Add an index-summary predicate:
  - row matches when `summary.visible_user_turn_count >= min_user_turns`
  - row does not match when summary is missing/malformed
- Keep content filters on the existing standard-model path.
- Tests:
  - `--min-user-turns` filters using `summary`
  - a matching row without raw artifacts can pass when summary count is high enough
  - a row missing `summary` does not match
  - `--user-contains` still uses standard-model content filtering

### Slice 3 - Query Output And Inspection

Status: implemented.

- Include `summary` in compact query result rows.
- Rationale:
  - the summary is now useful user-facing inspection metadata
  - it helps explain why `--min-user-turns` matched
- Tests:
  - `agentos chatlas query ...` compact rows include `summary`
  - full row shape still includes the full index row as before

### Slice 4 - Redo Index And Validate Performance

Status: implemented.

- Refresh installed CLI after runtime changes:

```sh
uv tool install --reinstall --editable .
```

- Rebuild the index:

```sh
agentos chatlas index redo
```

- Verify summary presence:

```sh
agentos chatlas query --updated-after 2026-05-12T00:00:00-04:00 --sort newest --limit 1
```

- Re-run the measured slow query:

```sh
agentos chatlas query --updated-after 2026-05-12T00:00:00-04:00 --min-user-turns 6 --sort newest --limit 5
```

- Acceptance:
  - query no longer performs full model reconstruction for `--min-user-turns`
  - elapsed time should be close to index-only query time for this selector
  - row counts remain semantically correct after index redo

### Slice 5 - Test And Lint

Status: implemented.

- Run focused tests:

```sh
uv run pytest tests/test_chatlas_commands.py -q
```

- Run lint on touched paths:

```sh
uv run ruff check src/agentos/chatlas tests/test_chatlas_commands.py
```

## Impl.Log

- Created as the execution handoff for adding indexed Chatlas session summaries. The plan intentionally requires index redo and forbids compatibility fallback for old rows without `summary`.
- Implemented indexed session summaries in `src/agentos/chatlas/delta_scan.py`.
  - Added `summary` derivation to `_session_index_row(...)`.
  - Counts/excerpts are computed from visible conversation user/assistant messages after standard session normalization.
  - Bumped the session-index derivation cache directory from `session-index-derivations-v1` to `session-index-derivations-v2` so stale cached derivations cannot preserve old rows without `summary`.
- Implemented summary-backed `--min-user-turns` filtering in `src/agentos/chatlas/query.py`.
  - `--min-user-turns` now uses `row["summary"]["visible_user_turn_count"]`.
  - Missing or malformed `summary` rows do not match.
  - Content filters remain on the existing standard-model filtering path.
  - Compact query rows now include `summary`.
- Added focused tests in `tests/test_chatlas_commands.py`.
  - Index derivation stores counts and first/last excerpts.
  - `--min-user-turns` matches from indexed summary without raw artifacts.
  - Rows missing `summary` do not match summary-backed filtering.
  - Existing visible-role content filtering remains covered.
- Verification:
  - `uv run pytest tests/test_chatlas_commands.py -q` passed: `47 passed`.
  - `uv run ruff check src/agentos/chatlas tests/test_chatlas_commands.py` passed.
  - `uv tool install --reinstall --editable .` completed and refreshed the installed `agentos` executable.
  - `agentos chatlas index redo` rebuilt `23612` indexed sessions across `7` partitions.
  - Summary presence check: `rg -n '"summary"' /Users/pereiro/Documents/chatlas/index/sessions | wc -l` returned `23612`, matching the rebuilt row count.
  - Acceptance query `agentos chatlas query --updated-after 2026-05-12T00:00:00-04:00 --sort newest --limit 1` returned compact rows with `summary`.
  - Acceptance query `agentos chatlas query --updated-after 2026-05-12T00:00:00-04:00 --min-user-turns 6 --sort newest --limit 5` returned `query_matched_row_count: 31`, `returned_row_count: 5`, and completed in about `0.69s`.
