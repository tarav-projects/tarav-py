# Chatlas Provider-Neutral Standard Model Plan

## Goal
- Make the whole Chatlas standard session model provider-neutral.
- Keep native/provider-specific truth in raw artifacts.
- Use `source_refs` as the bridge from standard records back to raw evidence.
- Ensure normal Chatlas services can consume the standard model without parsing provider formats.

## Context
- `notes/live/534-chatlas-standard-chat-model.md` established the normalization boundary:

```text
provider raw artifacts
  -> provider normalizer
  -> session.std.model
  -> common Chatlas services
```

- `notes/live/544-chatlas-event-first-standard-model.md` established that `events[]` is the central canonical concept.
- `notes/live/545-chatlas-semantic-event-implementation-plan.md` implemented semantic event tapes for the three reference providers:
  - Claude Code: `5dbf4437-633e-4039-a627-0459d85e9ecc`
  - Copilot CLI: `d1d3f48b-4b29-4dfc-b551-5536b9677225`
  - Codex: `019db5fd-7a73-7ae1-b5eb-901e62258dcb`
- Phase 7 proved the current experimental export can produce semantic events for all three reference sessions.

The next issue is model cleanliness:
- `chat.events[]` is now close to provider-neutral.
- Some projection records still carry provider-shaped `native` payloads.
- Several provider normalizers still include provider-specific grouping logic in projection construction.
- The event and projection schemas are still implicit Python dict shapes, not a written standard contract.

## Accepted Direction
- The standard model should be provider-neutral end to end.
- If a consumer wants native/provider-specific details, it should follow `source_refs` to the raw artifact.
- The standard model should not copy native provider payloads just because they are available.
- Provider facts should be promoted into the standard model only when they can be expressed as provider-neutral facts.

Working rule:

```text
standard model = provider-neutral facts
raw artifacts = provider-native truth
source_refs = bridge between them
```

## Canonical Boundary

### Standard Model
The standard model may contain:
- provider-neutral session identity and timestamps
- provider-neutral source metadata
- semantic events
- provider-neutral projection views over events
- explicit unsupported/deferred concept reports

The standard model should not contain:
- raw provider event types
- raw provider transport envelopes
- provider-specific parent ids unless promoted into a neutral relationship
- raw provider message JSON
- raw tool hook payloads when they are only provider implementation detail
- `native` blobs as normal model fields

### Raw Artifacts
Raw artifacts remain the durable provider-native truth:
- full JSONL records
- provider transport event ids
- original message/block shapes
- hook payloads
- provider-specific metadata
- fields not yet understood by the standard model

### Source Refs
`source_refs` must be strong enough to recover raw facts:
- `source_ref_id`
- line number when line-oriented
- record or event index when available
- content/request indices when a semantic event came from a nested raw block

If a canonical record needs to justify itself, it should point back to source refs instead of embedding native payloads.

## Promotion Rule
A provider field may enter the standard model only when it answers a provider-neutral question.

Examples:
- Claude `requestId` can support `model_run_ref` or a neutral `request_id` field when it identifies an execution unit.
- Copilot encrypted reasoning becomes a `reasoning` event with `visibility: encrypted`, not a Copilot-specific encrypted payload shape.
- Codex `token_count` is preserved as a `metric` event until usage scope can be represented truthfully.

Non-examples:
- raw `parentId`
- raw provider event type strings
- complete raw message envelopes
- exact hook command payloads when only useful for provider debugging
- provider-specific nested usage blobs when already projected into neutral token fields

## Target Stored Shape
The long-term stored standard model should converge toward:

```text
session
sources
events
normalization
```

Projection arrays are views:
- `messages`
- `interactions`
- `model_runs`
- `tool_invocations`
- `reasoning_traces`
- `usage`

During the experimental phase, exports may keep projections in the JSON output for inspection, but they should be rebuildable from `events[]` plus `sources[]`.

## Implementation Plan

### Phase 1: Write The Current Standard Contract
Status: done.

- Add a written contract for the experimental standard model.
- Define required fields for:
  - envelope
  - `session`
  - `sources`
  - `chat.events[]`
  - projection arrays
  - `normalization`
- Define the allowed event kinds and minimal payload shape for each kind:
  - `message`
  - `context`
  - `reasoning`
  - `tool.call`
  - `tool.progress`
  - `tool.result`
  - `run.start`
  - `run.end`
  - `usage`
  - `metric`
  - `session.start`
  - `session.update`
  - `session.end`
- Explicitly state that standard model records should not expose `native`.

Acceptance:
- The contract is clear enough that tests can assert against it.
- The contract distinguishes canonical fields from debug/raw evidence.

Implementation notes:
- Added `notes/live/547-chatlas-standard-model-contract.md`.
- The contract defines the provider-neutral envelope, session, source, event, projection, content, and normalization shapes.
- The contract explicitly treats `native` in projections as a current deviation, not a standard-model field.
- The contract records source refs as the bridge back to provider-native raw artifacts.

### Phase 2: Audit Provider-Neutral Leaks
Status: done.

- Inspect current experimental exports for the three reference sessions.
- Identify every provider-shaped field still present outside raw artifacts.
- Classify each leak:
  - promote to neutral field
  - replace with `source_refs`
  - move to a debug-only resolver surface
  - drop from standard output
- Pay special attention to projection-level `native` fields.

Acceptance:
- Produce a small inventory of fields to remove, promote, or defer.
- No provider-specific field is removed without preserving raw traceability through `source_refs`.

Implementation notes:
- Added `notes/live/549-chatlas-provider-neutral-leak-audit.md`.
- The audit was generated from the three checked-in reference-session samples.
- Main leak classes:
  - projection-level `native`
  - `session.native`
  - event top-level source locators/correlation helpers
  - Claude hook progress payload details
  - Copilot raw usage aggregate payload
  - Codex tool progress aliases
- The audit recommends strengthening source refs before deleting `native` from projections.

### Phase 3: Strengthen Source Refs As The Native Bridge
Status: done.

- Make `source_refs` consistent across providers and projections.
- Ensure nested semantic evidence can be located precisely:
  - Claude content block indexes
  - Copilot event/request indexes
  - Codex record indexes and response item positions
- Decide whether projection records should carry their own `source_refs` or derive them entirely from `event_refs`.
- Add shared helpers for source-ref validation.

Acceptance:
- Every event has source refs when raw evidence exists.
- Every projection record can trace back to raw evidence through either `event_refs` or direct `source_refs`.
- Removing `native` does not make raw recovery materially worse.

Implementation notes:
- Added `_standard_model_traceability_errors` in `src/agentos/chatlas/experimental/_shared.py`.
- The validator checks:
  - every event has non-empty source refs
  - every source ref points to a known `sources[]` entry
  - every source ref has at least one locator field
  - every locator value is a positive integer
  - every projection record has either `source_refs` or `event_refs`
  - every `event_ref` resolves to an event that itself has source refs
  - nested `model_runs[].reasoning_trace[]` items remain traceable
- The three reference-session exports now run through this validator in the current-contract harness.
- Decision for now: keep direct `source_refs` on projections while also validating `event_refs`. Direct projection source refs are redundant in some cases, but useful during the transition away from `native`.

### Phase 4: Remove `native` From Standard Projections
Status: done.

- Remove `native` from:
  - `messages`
  - `model_runs`
  - `tool_invocations`
  - `reasoning_traces`
  - `usage`
- Promote only the neutral parts that normal consumers need.
- Keep provider-specific details in raw artifacts.
- If needed, add a separate debug-only function later that resolves source refs and displays native context.

Acceptance:
- Experimental export standard-model projections no longer include `native`.
- Existing useful neutral data remains available through explicit canonical fields.
- Tests assert absence of `native` across standard events and projections.

Implementation notes:
- The experimental export boundary now strips `native` recursively from:
  - `session`
  - `chat.messages`
  - `chat.model_runs`
  - `chat.tool_invocations`
  - `chat.usage`
- Provider normalizers may still use internal native scratch data while grouping events into projections, but the exported standard model no longer exposes it on those surfaces.
- Unknown content item native payloads are also removed from projection output; raw recovery depends on `source_refs`.
- The current-contract reference harness now rejects `native` recursively in session and projection surfaces.
- Existing projection source refs/event refs continue to pass the Phase 3 traceability validator.

### Phase 5: Make Projection Builders More Shared
Status: done.

- Move more projection construction into shared event-driven helpers.
- Keep provider-specific logic only where it belongs:
  - raw artifact parsing
  - event normalization
  - assigning provider-derived refs during normalization when required
- Avoid provider-specific parsing inside normal Chatlas services.

Acceptance:
- Provider normalizers primarily emit semantic events.
- Projection construction reads semantic events instead of raw provider payloads.
- Any provider-specific projection logic is documented as temporary or justified by unavoidable correlation evidence.

Implementation notes:
- Added shared `_project_reasoning_trace_from_events` in `src/agentos/chatlas/experimental/_shared.py`.
- Claude, Copilot, and Codex now use the shared reasoning projection helper.
- Provider-specific code now only supplies the event inclusion rule:
  - Claude filters reasoning events by raw record span.
  - Copilot filters reasoning events by raw event-index span.
  - Codex projects all reasoning events, then attaches them to model runs with existing span/turn logic.
- Removed dead Copilot fallback code that projected reasoning from provider-shaped assistant-message payloads. Reasoning is now expected to be split into semantic `reasoning` events first.

### Phase 6: Add Contract Tests
Status: pending.

- Extend the reference-session harness to check:
  - no `native` in standard model records
  - no provider raw event-type fields in standard model records
  - all projection refs resolve
  - all source refs point to known sources
  - expected unsupported/deferred concepts are explicit
- Keep these tests focused on the current contract, not legacy compatibility.

Acceptance:
- Reference sessions pass contract tests for Claude Code, Copilot CLI, and Codex.
- Codex usage remains explicitly deferred until usage scope is reliable.

### Phase 7: Decide Storage Direction
Status: pending.

- Decide when `session.std.model` becomes a persisted Chatlas artifact rather than only an experimental export.
- Decide whether stored artifacts contain only:
  - `session`
  - `sources`
  - `events`
  - `normalization`
- Decide whether projections are runtime-only, cached, or exported on demand.

Acceptance:
- Storage strategy preserves the event tape as source of truth.
- Views remain rebuildable and deletable.
- Raw artifacts remain available for audit/debug/recovery.

## Non-Goals
- Do not remove raw artifacts.
- Do not add backward-compatibility aliases for legacy event shapes.
- Do not make provider-specific native fields canonical.
- Do not model full TUI layout state.
- Do not allocate usage to model runs when provider evidence does not support that allocation.

## Open Questions
- Should projection records keep direct `source_refs`, or should they rely only on `event_refs`?
- Should debug/raw resolution be a separate command, for example `agentos chatlas experimental raw-ref ...`?
- Should `event_id` stay local sequence-based in experimental exports, or become stable/content-addressed before persistence?
- How strict should the schema be while the model is still experimental?

## Immediate Next Step
- Start Phase 6 by tightening contract tests around provider-neutral standard-model records.
