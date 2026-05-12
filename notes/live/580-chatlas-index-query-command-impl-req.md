# Chatlas Index Query Command - impl-req

## Impl-Req State

This request has been implemented for the option-only `agentos chatlas index query` command.

## User Intent

Add an index-specific query command for Chatlas sessions:

```sh
agentos chatlas index query
```

The command should use explicit option names for query fields. It should not accept a positional query argument.

## Why This Exists

The new Chatlas update system is moving toward explicit phases and explicit data surfaces. The session index is now a first-class product under `agentos chatlas index`, so users need a small query command that reads that index directly without invoking broader Chatlas query/export behavior.

This command should be the first real consumer of the new index files.

## Current Situation

`agentos chatlas index update`, `agentos chatlas index reset`, and `agentos chatlas index redo` are the current index command surface.

The older top-level command:

```sh
agentos chatlas query
```

remains an explicit stub and should stay separate. Do not turn it into an alias for index query.

The session index lives under:

```text
~/Documents/chatlas/index/sessions/
```

with provider/home-local JSONL partitions shaped by the current `Chatlas.Delta.Scan` implementation.

## Requested Change

Add:

```sh
agentos chatlas index query
```

The command should query only Chatlas session index rows. It should not read native provider artifacts, copied raw artifacts, or derivation cache files.

The query surface should be option-only. Examples:

```sh
agentos chatlas index query --display-name "delta scan" --provider codex --sort newest --limit 10 --format json
agentos chatlas index query --session-id 019ccafa-7835-7fc3-ac17-0e0a0f675fd5 --format json
agentos chatlas index query --identity-hash abc123 --format json
agentos chatlas index query --provider codex --instance codex-work --extractable --sort newest --limit 25 --format json
```

Expected query options:

- `--uri`
- `--identity-hash`
- `--provider`
- `--instance`
- `--provider-instance-fingerprint`
- `--session-id`
- `--display-name`
- `--extractable`
- `--updated-after`
- `--sort lexical|newest|oldest`
- `--limit N`
- `--format json`

At least one query/filter option should be allowed, but the command may also support a no-filter listing mode if implementation keeps that simple and bounded by `--limit`.

## Constraints And Invariants

- No positional query argument.
- Query field options use the indexed field names directly where practical.
- Read only `index/sessions/**/*.jsonl`.
- Do not read `raw/`.
- Do not read native provider homes.
- Do not read `cache/session-index-derivations-v1/`.
- Do not import or revive `_DEPRECATED/chatlas-update-v1`.
- Keep `agentos chatlas query` as a separate stub.
- JSON output is enough for the first slice; do not add markdown/text formats unless explicitly requested later.
- Keep implementation simple and reuse existing helpers when they fit.

## Out Of Scope

- Session export.
- Raw artifact path lookup.
- Transcript extraction.
- Full-text search over raw transcripts.
- Fuzzy search.
- Reintroducing the old Chatlas query system.
- Path filtering.

## Acceptance Signals

- `agentos chatlas index query --session-id <id> --format json` returns matching index rows.
- `agentos chatlas index query --display-name <name> --format json` returns matching index rows.
- `--provider` filters by provider.
- `--instance` filters by indexed instance value.
- `--extractable` keeps only extractable rows.
- `--updated-after` filters by indexed `updated_at`.
- `--sort newest` and `--sort oldest` sort by indexed `updated_at`.
- `--limit` caps returned rows.
- Malformed or blank JSONL rows are skipped defensively.
- Empty or missing index returns an `"ok"` payload with zero matches.
- Tests prove the command does not require raw/native artifacts after index files exist.

## Implementation Shape

Slice 1: Load and list index rows.

- Add a small index-query runtime function, likely in the Chatlas core/indexing area currently used by `chatlas index` commands.
- Read all `sessions.index.jsonl` files under the configured Chatlas session index root.
- Return JSON with scan counts and rows.
- Add a test for missing/empty index.

Slice 2: Exact field filters.

- Add option-only CLI parsing under `chatlas index query`.
- Implement exact or simple substring matching for named fields; prefer exact matching for ids/hashes/provider/fingerprint and case-insensitive contains for `display_name`.
- Add tests for `--session-id`, `--display-name`, `--provider`, and `--instance`.

Slice 3: Query controls.

- Add `--extractable`, `--updated-after`, `--sort`, and `--limit`.
- Add focused tests for each control.

Slice 4: Boundary tests.

- Verify malformed JSONL rows are skipped.
- Verify index query still works after native/raw artifacts are absent, as long as index files exist.
- Verify top-level `agentos chatlas query` remains the explicit stub.

## Relevant Files Or Surfaces

- `src/agentos/chatlas/commands.py`
- `src/agentos/chatlas/core.py`
- `src/agentos/chatlas/delta_scan.py`
- `tests/test_chatlas_commands.py`
- `notes/live/578-chatlas-delta-scan-design-summary.md`
- `notes/live/579-chatlas-delta-scan-impl-req.md`

## Open Questions

- Should `--display-name` be exact match or case-insensitive contains? Recommended first slice: case-insensitive contains because display names are human-facing labels.
- Should no-filter listing be allowed? Recommended first slice: allow it only with `--limit`, defaulting to a conservative limit.

## Related Impl-Reqs

- `notes/live/576-chatlas-update-v1-deprecation-stub-impl-req.md`
- `notes/live/579-chatlas-delta-scan-impl-req.md`

## End Log

- 2026-05-12: Created implementation request for option-only `agentos chatlas index query`.
- 2026-05-12: Began implementation against `src/agentos/chatlas/commands.py`, `src/agentos/chatlas/core.py`, and a focused index-query runtime.
- 2026-05-12: Implemented `agentos chatlas index query` with option-only filters, JSON output, index-only JSONL reads, focused command tests, full test-suite verification, and installed CLI refresh.
