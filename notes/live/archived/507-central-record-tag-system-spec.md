# Central Record-Tag System Spec

## Goal
Design a central, append-only tagging system for tape records that is:
- fast and simple to query now,
- auditable (all tagging attempts preserved),
- extensible for richer quality workflows over time.

## Scope
In scope:
- record-level tagging for entries stored in AgentOS tapes,
- provenance of all tag proposals/challenges/decisions,
- query surface for "find records by tag".
- tags for a record

Out of scope (for this phase):
- strict ontology management,
- automatic synonym collapsing,
- non-JSONL storage backends.

## Core Design Requirements
- Central tag memory: tags must be stored in one system-level tag ledger, not scattered per workflow.
- Record linkability: every tag event must reference a stable `record_ref` to the source record.
- Append-only provenance: no destructive edits; corrections are new events.
- Search-first UX: retrieving records by accepted tags must be fast and straightforward.
- Deterministic envelope: tag records must follow current tape entry envelope and validation rules.
- Replayability: current effective tags for a record must be derivable by replaying ordered events.
- Low-friction adoption: must work with existing `agentos tape` commands for MVP.

## System Responsibilities

### 1) Tag Ledger (SSOT)
A dedicated tape (or tape family) that stores tag events.
Responsibilities:
- persist all tag-related events,
- preserve full history,
- serve as source of truth for tag state derivation.

### 2) Tagging Workers (Agents/Skills)
Responsibilities:
- read target records,
- propose tags,
- optionally challenge proposals,
- emit decision events.

Modes:
- `quick`: propose only, then accept directly via decision policy.
- `quality`: proposer -> challenger -> decider event.
- `explore`: random sampled records, record-only context (no prior tags), then decision.

### 3) Tag State Resolver
A deterministic resolver that computes effective tag state per record from ledger events.
Responsibilities:
- fold events in timestamp/order sequence,
- expose `accepted/rejected/pending` states,
- produce current tag fingerprint per record.

### 4) Search/Index Projection
A derived read model optimized for lookup.
Responsibilities:
- build and refresh tag->record mappings,
- keep query surface simple for agents/CLI,
- remain reproducible from ledger source.

## Data Contract (Tag Events)
All tag events are normal tape entries with current envelope fields (`ts`, `writer`, `workflow`, `entry_type`, `refs`, `cargo`).

Required `cargo` fields for tag events:
- `record_ref`: stable pointer to tagged source record.
- `tag`: tag string (single tag per event for clean provenance).
- `status`: one of `proposed`, `challenged`, `accepted`, `rejected`.
- `source_mode`: one of `quick`, `quality`, `explore`.
- `evidence`: optional compact rationale or refs summary.
- `decision_of`: optional list of prior event ids/refs this event resolves.

Recommended event types:
- `tag.proposed`
- `tag.challenged`
- `tag.decision` (final accept/reject signal)

## Usage Flows

### Flow A: Quick Tagging (default MVP)
1. Select record(s) to tag.
2. Emit `tag.proposed` events.
3. Emit `tag.decision` events (accept/reject).
4. Resolver updates effective tag fingerprint.
5. Search uses accepted tags only.

### Flow B: Quality Tagging (adversarial)
1. Proposer emits `tag.proposed`.
2. Challenger emits `tag.challenged` for weak/conflicting tags.
3. Decider emits `tag.decision` with final status.
4. Resolver and index update from decisions.

### Flow C: Exploration Tagging (surface expansion)
1. Randomly sample records.
2. Tag with record-only context (no current tag visibility).
3. Emit `tag.proposed` with `source_mode=explore`.
4. Route through decision step before becoming searchable defaults.

## Query Semantics
Default query behavior:
- return records by `accepted` tags only.
- optional flags can include `proposed` or `challenged` for diagnostics.

Minimum query capabilities:
- `records by tag`
- `tags by record`
- `top tags (frequency)`
- `pending decisions`

## Governance and Quality
- No hard synonym canonicalization in phase 1.
- Agents should still read recent tag inventory + linked records before proposing.
- Duplicates/near-synonyms are tolerated initially and handled by decision policy + later cleanup waves.

## MVP Implementation Boundary
Phase 1 should deliver:
1. tag event schema and conventions,
2. one central tag ledger tape,
3. quick + quality + explore write flows,
4. deterministic resolver for effective tags,
5. basic query path over accepted tags.

Phase 1 should not require:
- ontology tooling,
- migration of historical tapes,
- advanced ranking/relevance models.

## Acceptance Criteria
1. Any tagged record has a reproducible event trail.
2. Effective tags can be recomputed from raw ledger.
3. Search by accepted tag works with current CLI workflows.
4. Exploration mode can inject novel tags without breaking query stability.
5. Quality mode can override quick/explore proposals via explicit decisions.

## Relaed workflows
- Use agents to autotag record
    - We can use a game framework
    - I give the agent a record, and the agent most propuse which tag should hit it on the tag system
        - that is, we can find if the propuse tag was used before on this record
        - we reapet 
- Evolution capacity: allow fresh random exploration tagging that ignores existing tags.