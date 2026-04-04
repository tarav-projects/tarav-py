# Chatlas Session Absorption Plan

## Goal
- Absorb the useful functionality of `agentos chat session` into `agentos chatlas`.
- Make Chatlas the source of truth for session data.
- Avoid a command-for-command migration of the old live/provider-facing surface.
- Prefer one query surface with expansion flags over multiple overlapping session verbs.

## Accepted Direction
- `agentos chatlas` should become the primary product surface for session data.
- `agentos chat session` should not remain a parallel truth source over live provider homes.
- Chatlas should answer session questions from dataset artifacts it owns:
- `raw/`
- `normalized/`
- `derived/`
- Live/provider-facing machinery should remain as connector and ingestion infrastructure, not as the main session UX.
- Do not preserve the old `list/find/stats/extract` shape just because it already exists.

## Core Rationale
- If session data can be queried both from live provider homes and from Chatlas, the system has two competing truths.
- Making Chatlas answer all session queries forces update discipline and keeps the preserved dataset operationally relevant.
- This is aligned with the product goal of preserving chat data instead of treating provider homes as the long-term interface.

## New Boundary

### `agentos chatlas`
- Owns session inventory.
- Owns session identity resolution.
- Owns session stats over the maintained dataset.
- Owns transcript export and summary export.
- Owns any future session-oriented user-facing workflows.

### `agentos chat`
- Owns provider connectors and ingestion helpers.
- Owns provider/account/runtime diagnostics.
- Owns low-level extraction/debug workflows that bypass the maintained dataset.
- Should not be the normal end-user entrypoint for session browsing and querying.

## Session Capability Review

### Keep, But Reframe Inside Chatlas
- Cross-provider session inventory.
- Exact session identity resolution.
- Aggregate session stats.
- Transcript export.
- Session summary export.

### Do Not Preserve As-Is
- Provider-home grep findings as a main public feature.
- Arbitrary `--file` extraction in the main Chatlas UX.
- Provider-diagnostic-heavy default responses.
- Separate session verbs whose only purpose was working around live-home query limitations.

## Command Surface Direction

### Primary Surface
- `agentos chatlas update`
- `agentos chatlas query`
- `agentos chatlas stats`
- `agentos chatlas export`

### Query-First Rule
- Use `chatlas query` as the main entrypoint for session selection.
- Do not split inventory and exact resolution into separate core verbs unless a later need is clearly demonstrated.
- Prefer one selection surface plus optional expansions over a growing family of overlapping commands.

## Expansion Model Direction

### Base `query`
- Returns normalized session rows.
- Supports cross-provider filtering and ordering.
- Supports exact identity queries and broader dataset filters.

### Suggested Query Filters
- `--provider`
- `--updated-since`
- `--text-contain`
- `--user-contain`
- `--limit`
- `--sort`

### Suggested Query Expansions
- `--include-match`
- `--include-artifacts`
- `--include-lineage`
- `--include-summary`
- `--include-summary-level <brief|detailed>`
- `--include-transcript-metadata`

### Reason For Expansions
- “Query many sessions” and “inspect one session deeply” should use the same base selection model.
- Expansions let Chatlas expose richer detail without inventing a new top-level verb for each projection.
- This keeps the surface closer to the accepted query-first direction already established in the session model notes.

## `stats` Direction
- Keep `chatlas stats` for aggregate dataset-level reporting.
- It should report dataset freshness, provider coverage, counts, and artifact availability.
- It should not be the main surface for inspecting one resolved session.

## `export` Direction
- Keep `chatlas export` for materializing one selected session as a transcript or summary artifact.
- Export should operate on Chatlas session identity, not arbitrary filesystem paths.
- If direct file extraction remains useful, keep it outside the main Chatlas product surface.

## Implications For Current `chat session`
- `chat session` should not remain the long-term home of session browsing/query behavior.
- Its useful behavior should be reimplemented more naturally under Chatlas.
- After Chatlas reaches feature sufficiency, `chat session` can become:
- a thin compatibility facade over Chatlas, or
- a deprecated transitional surface to remove later
- The preferred long-term direction is to center user workflows on `chatlas`, not on `chat session`.

## Recommended Implementation Shape

### Phase 1. Make Chatlas Feature-Complete For Sessions
- Ensure Chatlas supports the core session jobs now handled by `chat session`.
- Build the query/expansion surface needed for day-to-day browsing and identity resolution.
- Keep export centered on dataset artifacts.

### Phase 2. Reduce `chat session` To Compatibility Or Diagnostics
- Remove it as an independent truth source.
- Make any remaining session-facing behavior delegate to Chatlas-backed resolution.
- Keep only provider-live debugging flows under `agentos chat`.

### Phase 3. Reorganize Code To Match The Boundary
- Separate provider specs and connector logic from Chatlas service logic.
- Keep raw ingestion under Chatlas.
- Keep normalization, derived artifacts, query, and export under Chatlas.
- Avoid a large mixed `chat core` that continues to blur live connector code with maintained dataset code.

## Tradeoffs
- Main benefit: one source of truth for sessions.
- Main benefit: stronger preservation-oriented workflow because queries depend on Chatlas freshness.
- Main benefit: simpler user mental model around where session data lives.
- Main cost: dataset freshness becomes an explicit operational concern.
- Main cost: ingestion failures must be surfaced clearly instead of hidden behind live fallbacks.

## Rejected Direction
- Keep both live-provider session queries and Chatlas-backed session queries as equal long-term backends.
- Reason: this creates permanent SSOT ambiguity and duplicated query logic.

## Open Follow-Up
- Decide whether `chat session` should become a temporary Chatlas-backed facade during migration or be phased out more aggressively once Chatlas reaches functional parity.
