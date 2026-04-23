# Chatlas Standard Chat Model

## Goal
- Define the architectural direction for a standard Chatlas chat model.
- Make Chatlas services prefer one normalized session model instead of parsing provider-specific raw formats throughout the codebase.
- Concentrate provider-specific normalization work at one boundary:

```text
provider raw artifacts
  -> provider normalizer
  -> session.std.model
  -> common Chatlas services
```

## Accepted Direction
- Chatlas keeps provider-native raw data.
- Chatlas exposes provider-native raw data for audit, debugging, migration, and recovery.
- Chatlas normalizes raw provider data into a standard model before normal service consumption.
- Chatlas services should prefer `session.std.model` for query, export, summary, transcript, replay, search, and future UI surfaces.
- Provider-specific logic should be concentrated in provider normalizers, not spread across downstream Chatlas services.
- This is a strong architectural preference, not an absolute ban: raw access remains valid when the standard model is intentionally insufficient.

## Core Principle
- Provider-specific complexity should be concentrated, not eliminated.
- Raw provider payloads are the source evidence.
- `session.std.model` is the common operational surface.
- Derived artifacts are projections from the standard model where possible.
- Repeated raw-provider reads from normal services are a signal that the standard model probably lacks a concept.

## Boundary

### Before The Boundary
- Discover provider sessions.
- Preserve raw provider artifacts.
- Parse provider-native payloads.
- Interpret provider-specific message, event, reasoning, tool-call, usage, and session structures.
- Attach source references from normalized records back to raw artifacts.
- Report normalization gaps explicitly.

### At The Boundary
- Each provider normalizer converts raw session data into `session.std.model`.
- Normalizers may carry provider-specific metadata under bounded extension fields.
- Normalizers should preserve provenance so every important standard record can be traced back to raw source data when possible.

### After The Boundary
- Chatlas query, stats, export, summaries, transcript generation, replay export, search, and future presentation layers consume `session.std.model` by default.
- Services may still read raw data for diagnostics, audits, migrations, recovery, or explicit raw/export workflows.
- If a normal product path needs raw data repeatedly, prefer extending `session.std.model` instead of adding another provider-specific branch.

## Current State
- Chatlas already has the service-layer shape:
- `raw/`: provider-native archived chat artifacts
- `normalized/`: current normalized session rows
- `derived/`: transcripts, summaries, indexes, and similar projections
- `manifests/`: update runs, lineage, schema versions, and source fingerprints
- Current normalized output is mainly session identity and backing-artifact metadata.
- Current transcript rendering still depends on provider extractors reading primary raw backing artifacts.
- The next architectural move is to make richer chat content normalization explicit instead of treating clean transcript extraction as the only normalized content path.

## Standard Model Scope
- The concrete schema will be defined later.
- The model should cover the fundamental parts of an agent chat, not just clean user/assistant turns.
- Expected concept areas:
- session identity and lineage
- raw source references
- messages
- typed content blocks
- model runs
- reasoning or thinking data, including unavailable, redacted, and opaque forms
- tool calls
- tool results
- replay and streaming events
- usage and cost
- runtime or agent events
- visibility and projection rules

## Design Rules
- Do not force all providers into a lowest-common-denominator transcript.
- Preserve provider-specific data without requiring every downstream service to understand it.
- Keep extension data bounded and clearly marked as provider-specific.
- Prefer additive schema evolution over rewriting raw artifacts.
- Keep raw and standard records linked by stable source references.
- Treat clean transcripts, summaries, and search indexes as views over the standard model whenever possible.

## Non-Goals For This Note
- Define the full `session.std.model` schema.
- Implement the normalizers.
- Change the `agentos chatlas` CLI surface.
- Remove raw access.
- Make downstream raw access impossible.

## Open Follow-Ups
- Define the first `session.std.model` schema.
- Decide the normalized storage layout for messages, replay events, tool calls, and model runs.
- Decide whether the standard model should live in one session JSONL stream or several linked normalized files.
- Decide which provider-specific extension fields are allowed in normalized records.
- Decide how derived transcripts should migrate from direct raw extraction to standard-model projections.
