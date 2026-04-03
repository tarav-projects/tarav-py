# Chatlas Implementation Plan

## Goal
- Implement `Chatlas` as a first-class `agentos` subsystem.
- Keep `Chatlas` focused on maintained chat data and public consumption surfaces.
- Reuse existing `agentos` chat provider/session/archive machinery instead of creating a parallel stack.

## Accepted Architecture
- `agentos chat ...` stays provider-facing.
- `agentos chatlas ...` becomes dataset-facing.
- `Chatlas` owns chat data artifacts and projections.
- `Chatlas` does not own telemetry gathering, account usage refresh, or generic provider operations.
- The current `chat archive` concept is absorbed as the `raw/` layer inside `Chatlas`.

## Existing Code Anchors
- `src/agentos/chat/commands.py`
- `src/agentos/chat/archive.py`
- `src/agentos/chat/core.py`
- `src/agentos/chat/providers.py`

## Storage Contract Direction
- Default Chatlas root should live under `~/.agentos/chatlas`.
- Chatlas should be git-backed.
- Checked-in SSOT should stay text-friendly and append-friendly.
- Local query databases or indexes should be generated from the checked-in dataset rather than becoming the primary source of truth.

## Target Dataset Layout
- `raw/`: provider-native archived chat artifacts.
- `normalized/`: canonical cross-provider records.
- `derived/`: transcripts, summaries, indexes, and related projections.
- `manifests/`: update runs, lineage, schema versions, source fingerprints, and checkpoint metadata.

## Canonical Entity Direction
- `source_artifact`
- `session`
- `message`
- `transcript`
- `summary`

## Modeling Rules
- Reuse the existing canonical `agentos chat session` model wherever possible.
- Keep provider-native fields under `native`.
- Make normalized records traceable back to source artifacts and provider instances.
- Keep derived outputs reproducible from `raw/` plus `normalized/`.

## Command Surface Direction
- `agentos chatlas update`
- `agentos chatlas stats`
- `agentos chatlas query`
- `agentos chatlas export`

## Execution Plan

### Phase 1. Create the Subsystem Skeleton
- Add a new package at `src/agentos/chatlas/`.
- Add `commands.py` under `src/agentos/chatlas/`.
- Register a top-level `chatlas` CLI in `src/agentos/cli.py`.
- Wire initial command verbs.
- `update`
- `stats`
- `query`
- `export`

### Phase 2. Define the Chatlas Storage Contract
- Define the default Chatlas root path.
- Define the folder layout under the Chatlas root.
- Define one manifest schema for update runs.
- Define lineage fields linking normalized data back to raw artifacts.
- Write these contracts down before expanding provider coverage.

### Phase 3. Implement Raw Ingestion
- Extract reusable archive planning and mirroring behavior from `src/agentos/chat/archive.py`.
- Retarget archive output from the old generic archive root into `Chatlas/raw`.
- Reuse current provider-family/provider-instance and include/exclude behavior initially.
- Add a migration path so `agentos chat archive` can delegate to the Chatlas raw layer during transition.

### Phase 4. Implement Normalization
- Build a normalization pipeline that reads imported raw artifacts and emits canonical records into `normalized/`.
- Start with currently supported providers and extractors.
- Reuse existing session resolution and dialog extraction logic from `src/agentos/chat/core.py` and `src/agentos/chat/extractors/`.
- Emit append-friendly text outputs such as JSONL.

### Phase 5. Implement Derived Projections
- Generate clean transcript views from normalized data.
- Generate several summary levels over the same sessions.
- Generate local query databases or indexes as rebuildable artifacts.
- Keep derived outputs deterministic from the underlying dataset inputs.

### Phase 6. Add Public Service Surfaces
- `agentos chatlas stats`: dataset counts, freshness, provider coverage, checkpoint state.
- `agentos chatlas query`: provider-agnostic lookup over normalized records.
- `agentos chatlas export`: transcript and structured export surfaces.
- Start with simple output formats such as `json` and `markdown`.

### Phase 7. Migrate Existing Surfaces Carefully
- Keep `agentos chat session` intact during the initial Chatlas rollout.
- Keep `agentos chat accounts` outside the Chatlas boundary.
- Gradually phase out `agentos chat archive` by delegating it to Chatlas update behavior.
- Decide later whether `agentos chat session` should remain provider-live, become Chatlas-backed, or support both modes.

### Phase 8. Add Tests and Fixtures
- Add tests for CLI registration.
- Add tests for Chatlas layout creation.
- Add tests for raw ingestion and manifest generation.
- Add tests for normalization and derived outputs.
- Add one end-to-end fixture run across a small multi-provider sample.

### Phase 9. Refresh Docs and Notes
- Document the split between `agentos chat` and `agentos chatlas`.
- Document the Chatlas data contract before advertising it for third-party consumption.
- Keep the public format stable only after the storage contract and normalized schema are settled.

## First Change Set
- Add `src/agentos/chatlas/commands.py`.
- Register `agentos chatlas` in `src/agentos/cli.py`.
- Implement `agentos chatlas update` with raw-layer behavior only.
- Create `raw/` and `manifests/` under the Chatlas root.
- Reuse archive provider-instance resolution from `src/agentos/chat/archive.py`.
- Emit one manifest per update run.
- Keep normalization, query, and export out of the first slice.
- Add tests proving raw imports land in the Chatlas layout and are checkpointed correctly.

## Rationale for the First Slice
- It creates a real subsystem quickly.
- It preserves the accepted service boundary.
- It avoids mixing CLI birth, archive migration, normalized schema design, and query-engine work into one patch.
- It gives a stable base for later normalization and public-consumption work.

## Open Follow-Ups
- Finalize the canonical normalized entity schemas.
- Decide the exact manifest schema.
- Decide which raw artifacts are public versus private/local-only.
- Decide whether local query databases are checked in or always generated.
