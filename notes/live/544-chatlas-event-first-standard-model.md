# Chatlas Event-First Standard Model

## Goal
- Refine the standard Chatlas session model so it can express provider execution truth and transcript truth without forcing them into the same shape.
- Keep provider normalization concentrated at the provider boundary while making the standard model honest about:
  - what happened
  - who produced it
  - what the user saw
  - what the provider executed
  - how those things relate

## Relationship To Earlier Direction
- This note extends the standard-model direction in `notes/live/534-chatlas-standard-chat-model.md`.
- The earlier direction remains valid:

```text
provider raw artifacts
  -> provider normalizer
  -> session.std.model
  -> common Chatlas services
```

- The refinement here is that the standard model should be event-first.
- Transcript-visible messages are not the only truth.
- Model runs are not the same thing as transcript turns.

## Accepted Direction
- The most central concept in the standard model is `event`.
- The model should not treat literal TUI state as a canonical cross-provider concept.
- Instead, the model should represent presentation semantics on normalized events:
  - who produced the event
  - what kind of event it is
  - where it should be visible
- The standard model should represent execution truth and presentation truth as linked but separate concerns.

## Core Questions
- For every provider artifact, the normalizer should answer:
  1. What happened?
  2. Who produced it?
  3. Where is it visible?
  4. Which execution unit does it belong to?
  5. Which user-level interaction does it belong to?

## Core Concepts

### 1. Events
- `events[]` is the atomic normalized ledger.
- Each meaningful provider artifact should normalize into one or more events when it has replay, audit, transcript, or execution value.
- An event should carry at least:
  - `event_id`
  - `kind`
  - `producer`
  - `surfaces`
  - `timestamp` or stable order
  - `content`
  - `interaction_ref`
  - `model_run_ref`
  - `tool_invocation_ref`
  - `native`
  - `source_refs`

Example event shape:

```json
{
  "event_id": "event-12",
  "kind": "tool.result",
  "producer": {
    "type": "tool",
    "name": "bash"
  },
  "surfaces": {
    "transcript": "hidden",
    "replay": "visible",
    "debug": "visible",
    "model_input": "visible"
  },
  "model_run_ref": "run-2",
  "tool_invocation_ref": "tool-4"
}
```

### 2. Producer
- `producer` answers who generated the event in canonical terms.
- This must be separate from provider transport roles.
- Expected producer families:
  - `user`
  - `assistant`
  - `tool`
  - `system`
  - `provider`

This matters because raw transport roles are often misleading.

### 3. Surfaces
- `surfaces` answers where the event belongs.
- This is not full app/TUI state.
- It is a bounded presentation contract.
- Initial surfaces to support:
  - `transcript`
  - `replay`
  - `debug`
  - `model_input`

Expected values are small and explicit, such as:
  - `visible`
  - `hidden`
  - `opaque`
  - `encrypted`

### 4. Model Runs
- `model_runs[]` represents provider execution units.
- These are not transcript turns.
- Examples:
  - Claude: grouped by `requestId`
  - Copilot: grouped by assistant turn start/end evidence
  - Codex: grouped by rollout/model execution evidence

### 5. Interactions
- `interactions[]` represents user-level conversation units.
- This is the closest thing to what a human experiences as one request/response episode.
- One interaction may contain:
  - one user message
  - multiple model runs
  - multiple tool invocations
  - multiple hidden events
  - one or more visible assistant messages

### 6. Messages
- `messages[]` is a transcript projection.
- Messages are visible transcript items, not the full execution truth.
- Messages should be derived from events and linked back to them.

### 7. Tool Invocations
- `tool_invocations[]` is a structured summary over related tool events.
- It should collect request, progress, result, and execution residue in one place.

### 8. Reasoning Traces
- `reasoning_traces[]` is a structured summary over reasoning events.
- Visibility may differ by provider:
  - visible
  - opaque
  - encrypted
  - unavailable

### 9. Usage
- `usage[]` is a structured summary over usage evidence.
- Usage must keep honest scope boundaries:
  - model-run scoped when raw evidence is model-run scoped
  - session scoped when raw evidence is only session scoped

## Why This Structure Is Needed

### Claude Example
Reference session:
- `5dbf4437-633e-4039-a627-0459d85e9ecc`

Visible transcript:
1. user prompt
2. assistant short acknowledgement
3. assistant final report

Execution reality:
- `4` model runs
- `9` tool invocations
- `1` reasoning block
- many progress events

This means:
- transcript truth and execution truth are different
- both are valid
- neither should be forced to pretend to be the other

### Copilot Example
Reference session:
- `d1d3f48b-4b29-4dfc-b551-5536b9677225`

Copilot includes:
- visible assistant messages
- hidden or opaque reasoning evidence
- tool execution start/complete records
- usage from shutdown metrics

This fits the same model if events carry:
- canonical producer
- surfaces
- execution refs

### Codex Example
Reference session:
- `019db5fd-7a73-7ae1-b5eb-901e62258dcb`

Codex may include provider-expanded context such as environment or instruction input.

That context:
- is not human-authored user text
- may not belong in the visible transcript
- may still be visible to the model as input evidence

So the model needs a way to express:
- system-produced context
- hidden from transcript
- visible in model input / debug / replay

## Key Design Rule
- Keep transcript roles separate from canonical producers.
- Keep provider transport structure separate from canonical event meaning.
- Keep execution grouping separate from visible transcript grouping.

In practice:
- a raw `user` record can canonically be a `tool.result`
- a raw assistant record can canonically be a hidden `reasoning` event
- a system/provider artifact can canonically be `context.input`

## Practical Consequences
- `events[]` should be the strongest source of truth.
- `messages[]` should be treated as a transcript projection.
- `model_runs[]` should be treated as execution grouping.
- `interactions[]` should be treated as user-level grouping.
- `tool_invocations[]`, `reasoning_traces[]`, and `usage[]` should be structured summaries linked back to events and runs.

## Non-Goals
- Model arbitrary UI widget state.
- Model app-specific layout or panel behavior.
- Remove bounded `native` provider residue.
- Force every provider into exactly the same transcript shape.

## Suggested Next Steps
1. Update the standard-model note to reference the event-first direction.
2. Evolve the experimental schema so normalized events carry canonical `producer` and `surfaces`.
3. Decide whether `interactions[]` should be introduced immediately or after `events[]` gains `producer` and `surfaces`.
4. Re-check Claude, Copilot, and Codex exports against this event-first contract.
