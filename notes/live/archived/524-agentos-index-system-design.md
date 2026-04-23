---
title: Agentos Index System Design
date: 2026-04-07
status: draft
---

# Agentos Index System Design

## Goal

Define `agentos-index` as a useful `Tape.System` where agents can store structured data about subjects for later use.

This is not limited to computation reuse. Agents may use the index to leave tags, notes, assertions, judgments, links, coordination markers, and computed results.

## Core Framing

- `agentos-index` is a shared memory and lookup surface for agents.
- It is a system built on tapes, not a separate storage philosophy.
- `agentos` should provide infrastructure and protocols.
- Agents and agentic apps should define the semantics they need on top.
- Useful recurring patterns can be offered as stdlib systems, but they should not become mandatory ontology for all users.
- The MVP should focus on one global `agentos` index first, not on per-project indexes.

## MVP Scope

- Phase 1 should use one global index root under `agentos` home.
- In current `agentos` path terms, this means starting from the global `indexes` area under `~/.agentos/`.
- Project-local index roots are deferred.
- Cross-scope discovery is deferred.
- This keeps the first implementation focused on the data model, tape layout, projection model, and query surface.

## Why This Exists

- Agents should not keep redefining where reusable agent-side data should live.
- Agents should not keep inventing ad hoc file and folder conventions for later lookup.
- There should be one standard place to start when asking:
  - what do we know about this subject?
  - has an agent already said something about it?
  - has some work already been done?
  - where is the related result or artifact?
- The system should make cross-agent reuse cheap without forcing one application-level meaning model.

## System Boundary

`agentos-index` should define infrastructure, not application semantics.

Core responsibilities:

- subject addressing and linking through stable refs
- append-only canonical storage on tapes
- projection and materialized-projection patterns for current-state reads
- deterministic query surfaces
- standard storage modes for inline values, managed objects, and external refs

For the MVP, storage-root discovery is intentionally trivial:

- there is one global `agentos-index` home
- agents look there first
- project-local discovery can be added later if it proves useful

Out of scope for the core:

- a universal ontology for all agent data
- one mandatory vocabulary for tags, claims, notes, or computations
- app-specific conflict policy, trust policy, or ranking policy
- forcing all large artifacts to live inside the index

## Data Posture

The generic mental model is:

- an agent attaches an entry to a subject
- the entry has a kind
- the entry carries payload and provenance
- the system makes that data discoverable and queryable later

The core does not need one giant universal schema beyond the infrastructure contract. Different index systems can define different entry kinds and payload shapes as long as they use the shared discovery, ref, tape, and query conventions.

## Storage Modes

The index should support three basic storage modes:

- `inline`
  - small structured values live directly in index records
- `managed-object`
  - the index system owns the stored object and keeps a stable pointer to it
- `external-ref`
  - the record points to data owned by another system

This lets the same system handle both small annotations and larger artifacts without forcing one storage pattern.

## Relationship To StdLib And Apps

The layering should be:

- core `agentos-index`
  - infrastructure and protocol
- stdlib index systems
  - reusable systems that are broadly useful
- app and agent systems
  - custom semantics built on the protocol

Examples of plausible stdlib systems:

- a tag system
- a computation reuse system
- a work-claim or lease system
- a generic annotation system

These are useful default systems, not the definition of indexing itself.

## MVP Usage Cases

### Chat Session Summary Cache

- subject: a `chatlas` session ref
- key: `prompt + parameters -> result`
- value: an inline summary, a managed object, or an external ref to the produced summary
- query: has this summary request already been resolved for this session

This is especially useful for repeated chat-session summarization work, where multiple agents may want the same derived summary.

### Chatlas Session Tags

- subject: a `chatlas` session ref
- entry: one or more tags attached to the session
- query: all `chatlas` sessions with a given tag

This gives agents a reusable scoping surface for later search, summarization, and filtering workflows.

## Example Usage

### Session Tags

- subject: a chat session ref
- entry: tag `research`
- query: all sessions tagged `research`

### Session Notes

- subject: a chat session ref
- entry: short note or assertion about the session
- query: what has already been said about this session

### Summary Reuse

- subject: a session ref or a derived computation key
- entry: summary metadata, inline summary, or pointer to a summary artifact
- query: has this already been produced, and where is it

### Work Coordination

- subject: a computation key or task subject
- entry: in-progress marker or lease
- query: is some other agent already working on this

## Recommended Architecture

`agentos-index` should follow the general `Tape.MutableSystem` posture:

- canonical history is append-only
- current usable state is derived through projection
- materialized projections are allowed
- materialized projections are non-canonical and rebuildable

This keeps the system aligned with the broader tape language and avoids in-place mutable state.

## Design Position

- `agentos-index` is not only for computations.
- `agentos-index` is not only an external-reference catalog.
- `agentos-index` is a place where agents can leave structured data about something for later use.
- `agentos` provides the infrastructure.
- semantics belong to stdlib systems and to the apps and agents that build on top.

## Open Direction

The likely direction is:

- first, one shared global `agentos-index` surface
- later, possibly multiple named index systems under that surface
- only after that, reconsider project-local or multi-root discovery if real usage demands it
