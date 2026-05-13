# Chatlas Index Stats - impl-req

## Impl-Req State

Implemented: `agentos chatlas stats` now reports index-only stats over the new Chatlas session index.

## User Intent

Implement `agentos chatlas stats` as a useful command again, but keep it aligned with the redesigned Chatlas system.

The command should answer:

```text
What is currently represented in the Chatlas session index?
```

It must not answer by scanning native provider homes, copied raw artifact contents, or private derivation cache files.

## Why This Exists

The Chatlas v1 runtime was archived and replaced with explicit stubs so the system could be rebuilt around the new index-first architecture.

The current rebuilt surfaces already establish:

- `agentos chatlas index update` produces/updates the session index.
- `agentos chatlas index query` cheaply selects rows from `index/sessions/**/*.jsonl`.
- `agentos chatlas export`, `raw path`, and `raw export` use the session index as their selector boundary.

`agentos chatlas stats` is still visible in the CLI but remains stubbed. It should be the next low-risk command to restore because it only needs indexed metadata and can reinforce the session index as the cheap public substrate.

## Current Situation

The active CLI still registers:

```sh
agentos chatlas stats
agentos chatlas stats --provider codex
agentos chatlas stats --format json
agentos chatlas stats --full-output
```

The implementation is currently stubbed in `src/agentos/chatlas/core.py`:

- `chatlas_stats(...)`
- `format_chatlas_stats_markdown(...)`

The index query implementation already loads session index rows from:

```text
~/Documents/chatlas/index/sessions/**/*.jsonl
```

That loading behavior currently lives inside `src/agentos/chatlas/index_query.py`.

## Requested Change

Reimplement `agentos chatlas stats` as an index-only stats command.

It should:

- read only Chatlas session index files under `index/sessions/**/*.jsonl`
- summarize total sessions, extractable sessions, non-extractable sessions, provider count, instance count, shard/partition count, scanned rows, skipped rows, and timestamp range
- summarize counts by provider
- summarize counts by provider/instance
- support `--provider` filters
- support `--format markdown` as default human output
- support `--format json` for automation
- keep useful zero-count behavior for explicit provider filters

## Constraints And Invariants

- Do not import or call `_DEPRECATED/chatlas-update-v1`.
- Do not scan native provider homes.
- Do not read copied raw artifact contents.
- Do not read `cache/session-index-derivations-v1`.
- Do not call the future broad `chatlas query` surface.
- Treat the session index as the source of truth for stats.
- Missing index files should produce a successful zero-count stats payload, not an error.
- Malformed, blank, or non-object index rows should be counted as skipped rows and should not crash the command.
- Keep the current option-based CLI shape.
- Do not add positional arguments.
- Keep `--format json` and default markdown output.
- `--full-output` should not force config/native reads. In the first implementation it may mean: keep explicit provider buckets requested through `--provider` even if they have zero indexed sessions.

## Out Of Scope

- Reimplementing `agentos chatlas query`.
- Reading provider-native homes to discover configured zero-session providers.
- Reading copied raw artifacts for provider-specific derived stats.
- Full-text/content stats.
- Token, message, or transcript-derived stats that require raw/session model loading.
- Git, manifest, or dataset finalization reporting.
- Compatibility with the archived v1 stats behavior.

## Acceptance Signals

- `agentos chatlas stats` returns a human-readable summary instead of the reimplementation stub error.
- `agentos chatlas stats --format json` returns a stable JSON payload with top-level totals and provider/instance breakdowns.
- `agentos chatlas stats --provider codex --format json` filters to Codex indexed rows.
- `agentos chatlas stats --provider codex --full-output --format json` includes a Codex provider bucket even when zero Codex rows match.
- Missing `index/sessions/` returns zero counts and exits successfully.
- Malformed or blank index lines increment `skipped_row_count`.
- Tests prove stats still works after native provider artifacts and copied raw artifact contents are absent or irrelevant, as long as index files exist.
- Runtime code under `src/agentos` still has no `_DEPRECATED` imports.

## Implementation Shape

### Slice 1: Shared Index Row Store

Behavior:

Move the low-level session index row loading out of `index_query.py` into a small shared module, such as:

```text
src/agentos/chatlas/index_store.py
```

The shared helper should load session index rows and return both valid rows and scan metadata:

- `chatlas_root`
- `session_index_root`
- `partition_count`
- `scanned_row_count`
- `skipped_row_count`
- `rows`

Observable result:

- `agentos chatlas index query` keeps its current behavior.
- The stats implementation can reuse the same loader without duplicating file traversal and JSON-line tolerance rules.

Check:

- Existing index query tests still pass.

Design assumption validated:

- Cheap index consumers share one index-file loading boundary.

### Slice 2: JSON Stats Payload

Behavior:

Implement `chatlas_stats(...)` using the shared index row loader.

Recommended payload shape:

```json
{
  "status": "ok",
  "command": "chatlas stats",
  "chatlas_root": "...",
  "session_index_root": "...",
  "filters": {
    "providers": ["codex"]
  },
  "stats": {
    "session_count": 123,
    "extractable_session_count": 120,
    "non_extractable_session_count": 3,
    "provider_count": 2,
    "instance_count": 5,
    "partition_count": 5,
    "scanned_row_count": 123,
    "skipped_row_count": 0,
    "oldest_updated_at": "2026-03-01T10:00:00Z",
    "latest_updated_at": "2026-05-12T14:22:01Z"
  },
  "by_provider": {
    "codex": {
      "session_count": 80,
      "extractable_session_count": 80,
      "non_extractable_session_count": 0,
      "instance_count": 3,
      "oldest_updated_at": "2026-03-01T10:00:00Z",
      "latest_updated_at": "2026-05-12T14:22:01Z"
    }
  },
  "by_instance": {
    "codex/codex-main": {
      "provider": "codex",
      "instance": "codex-main",
      "session_count": 50,
      "extractable_session_count": 50,
      "non_extractable_session_count": 0,
      "oldest_updated_at": "2026-03-01T10:00:00Z",
      "latest_updated_at": "2026-05-12T14:22:01Z"
    }
  }
}
```

Observable result:

- JSON output can be consumed by tests and future commands.

Check:

- Focused CLI tests in `tests/test_chatlas_commands.py`.

Design assumption validated:

- Dataset-level stats can be derived from the public session index only.

### Slice 3: Default Markdown Output

Behavior:

Implement `format_chatlas_stats_markdown(...)` for the default command output.

Recommended output shape:

```text
Chatlas session index

Sessions: 123
Extractable: 120
Non-extractable: 3
Providers: 2
Instances: 5
Index shards: 5
Skipped rows: 0
Updated range: 2026-03-01T10:00:00Z .. 2026-05-12T14:22:01Z

Providers:
- codex: 80 sessions, 3 instances
- claude-code: 43 sessions, 2 instances
```

Observable result:

- `agentos chatlas stats` is immediately useful in a terminal without requiring JSON parsing.

Check:

- CLI test asserts key default-output lines.

Design assumption validated:

- The command has a stable human-facing summary while keeping detailed JSON available.

### Slice 4: Boundary Tests

Behavior:

Add tests that make the index-only boundary hard to regress.

Checks:

- Create index rows directly or through the existing update fixture, then remove native provider files and prove stats still works.
- Create malformed/blank index lines and assert skipped rows are counted.
- Run or keep an `_DEPRECATED` import scan check.
- Run focused and full test suites.

Design assumption validated:

- Stats remains an index consumer, not a hidden raw/native scan.

## Relevant Files Or Surfaces

- `src/agentos/chatlas/commands.py`
- `src/agentos/chatlas/core.py`
- `src/agentos/chatlas/index_query.py`
- `src/agentos/chatlas/index_store.py` if added
- `tests/test_chatlas_commands.py`
- `notes/live/575-chatlas-update-workflow-split-design-summary.md`
- `notes/live/576-chatlas-update-v1-deprecation-stub-impl-req.md`
- `notes/live/578-chatlas-delta-scan-design-summary.md`
- `notes/live/579-chatlas-delta-scan-impl-req.md`
- `notes/live/580-chatlas-index-query-command-impl-req.md`
- `notes/live/581-chatlas-export-index-selection-impl-req.md`

## Open Questions

- Should `by_instance` be keyed by `provider/instance`, or should it be a list sorted by provider and instance? Recommended for first implementation: keyed object for compact lookup, with `provider` and `instance` repeated in each value.
- Should timestamp range use `updated_at` only, or also include `created_at` when present? Recommended for first implementation: use `updated_at`, because index query already sorts and filters by it.
- Should `--full-output` later include configured providers with zero rows by reading Agentos config? Recommended: not in this implementation, because that would weaken the index-only boundary.

## Related Impl-Reqs

- `notes/live/576-chatlas-update-v1-deprecation-stub-impl-req.md`
- `notes/live/579-chatlas-delta-scan-impl-req.md`
- `notes/live/580-chatlas-index-query-command-impl-req.md`
- `notes/live/581-chatlas-export-index-selection-impl-req.md`

## End Log

- 2026-05-12: Created from the accepted plan to restore `agentos chatlas stats` as an index-only command over `index/sessions/**/*.jsonl`, with no native/raw/cache reads and no deprecated runtime fallback.
- 2026-05-12: Implemented the request. Added a shared session-index row loader, restored `chatlas_stats(...)` and markdown formatting as index-only consumers, added provider/instance aggregate stats, added focused CLI tests for zero indexes, provider filtering, explicit zero buckets, malformed rows, markdown output, and index-only operation without raw artifacts. Verification passed with touched-file Ruff, focused Chatlas command tests, full pytest, diff whitespace checks, `_DEPRECATED` runtime import scan, editable CLI reinstall, and an isolated `agentos chatlas stats --format json` smoke test.
