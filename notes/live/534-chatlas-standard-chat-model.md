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
- The current design direction is event-first:
  - canonical stored model should converge toward `session + sources + semantic events tape`
  - transcript, interaction, model-run, tool, reasoning, and usage surfaces should be projections over that tape
- See `notes/live/544-chatlas-event-first-standard-model.md` for the refined event-first contract and the cross-provider consensus event schema.

## Core Principle
- Provider-specific complexity should be concentrated, not eliminated.
- Raw provider payloads are the source evidence.
- `session.std.model` is the common operational surface.
- Derived artifacts are projections from the standard model where possible.
- Repeated raw-provider reads from normal services are a signal that the standard model probably lacks a concept.

## Canonical Surface Principle
- Canonical standard-model surfaces should be truthful and provider-neutral.
- Provider-specific expansions, prompt rewrites, and odd tool-result details should be preserved, but bounded, until the standard model has an explicit provider-neutral place for them.
- Do not promote provider-specific convenience fields into canonical fields unless they describe the same concept across providers.
- Prefer a conservative canonical field plus raw-artifact traceability (via `source_refs`) over a canonical field that implies fake precision. Canonical events do not carry a `native` field; raw provider data is always accessible via preserved raw artifacts.
- User-authored text and provider-expanded model input are different concepts: keep user-authored content canonical, and preserve provider-expanded prompt/input context as bounded provider evidence unless a future `model_input` or `prompt_context` surface is defined.
- Structured usage should be promoted when the provider exposes it as structured usage evidence, but aggregation boundaries must remain honest. Do not allocate session-level usage to model runs unless the raw data supports that allocation.
- Tool execution status and outputs should use structured provider fields first. Avoid parsing semi-structured terminal text into canonical fields until the provider evidence is reliable enough.

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
- Normalizers do not embed provider-native residue in canonical events. Raw data is traceable via `source_refs`.
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
- semantic events as the canonical ledger
- event producer and surface visibility
- event outcome for result and completion semantics
- interaction membership and execution membership
- transcript messages as a projection
- model runs as a projection
- typed content blocks
- reasoning or thinking data, including unavailable, redacted, opaque, and encrypted forms
- tool calls and tool results
- usage and cost
- runtime or agent events
- projection rules

## Design Rules
- Do not force all providers into a lowest-common-denominator transcript.
- Preserve provider-specific data in raw artifacts without requiring every downstream service to understand it.
- Raw artifacts are always accessible via `source_refs` on canonical events.
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
- Decide the normalized storage layout for the canonical event tape.
- Decide whether the standard model should live in one session JSONL stream or several linked normalized files.
- Decide how derived transcripts, runs, tools, reasoning, and usage should migrate from direct raw extraction to standard-model projections.
