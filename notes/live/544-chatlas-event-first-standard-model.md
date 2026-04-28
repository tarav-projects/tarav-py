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
- The persisted canonical model should converge toward:
  - session metadata
  - source metadata
  - a semantic `events` tape
- The model should not treat literal TUI state as a canonical cross-provider concept.
- Instead, the model should represent presentation semantics on normalized events:
  - who produced the event
  - what kind of event it is
  - where it should be visible
- The standard model should represent execution truth and presentation truth as linked but separate concerns.
- `messages[]`, `interactions[]`, `model_runs[]`, `tool_invocations[]`, `reasoning_traces[]`, and `usage[]` should be treated as runtime views over the event tape.

## Core Questions
- For every provider artifact, the normalizer should answer:
  1. What happened?
  2. Who produced it?
  3. Where is it visible?
  4. Which execution unit does it belong to?
  5. Which user-level interaction does it belong to?

## Core Concepts

### 1. Events
- `events[]` is the atomic normalized ledger and the main source of truth.
- Events should be semantic units, not raw-record copies.
- One raw provider record may normalize into many canonical events.
- One canonical event may join several raw provider records when they represent one semantic fact.
- Each meaningful provider artifact should normalize into one or more events when it has replay, audit, transcript, or execution value.
- An event should carry at least:
  - `event_id`
  - `sequence`
  - `kind`
  - `producer`
  - `surfaces`
  - `timestamp` or stable order
  - `interaction_ref`
  - `payload`
  - `source_refs`
- These refs should be present when applicable:
  - `model_run_ref`
  - `tool_invocation_ref`

Example event shape:

```json
{
  "event_id": "event-12",
  "sequence": 12,
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
  "interaction_ref": "interaction-1",
  "model_run_ref": "run-2",
  "tool_invocation_ref": "tool-4",
  "payload": {},
  "source_refs": []
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
- `model_runs[]` is a projection that represents provider execution units.
- These are not transcript turns.
- Examples:
  - Claude: grouped by `requestId`
  - Copilot: grouped by assistant turn start/end evidence
  - Codex: grouped by rollout/model execution evidence

### 5. Interactions
- `interactions[]` is a projection that represents user-level conversation units.
- This is the closest thing to what a human experiences as one request/response episode.
- Interaction membership should be reconstructible from `events[]`.
- The clean way to guarantee that is to put `interaction_ref` on events.
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

## Stored Model And Views
- The intended storage split is:
  1. canonical stored model:
     - `session`
     - `sources`
     - `events`
  2. runtime or cached views:
     - `messages`
     - `interactions`
     - `model_runs`
     - `tool_invocations`
     - `reasoning_traces`
     - `usage`
- This keeps one source of truth and makes projections deletable and rebuildable.

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

## Cross-Provider Consensus Schema

### Canonical Event Shape
- A minimal consensus event shape across Codex, Copilot, and Claude is:

```json
{
  "event_id": "event-17",
  "sequence": 17,
  "timestamp": "2026-04-23T20:25:57.286Z",
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
  "interaction_ref": "interaction-1",
  "model_run_ref": "run-2",
  "tool_invocation_ref": "tool-4",
  "outcome": "ok",
  "payload": {},
  "source_refs": ["raw/claude/5dbf4437/record-3", "raw/claude/5dbf4437/record-4"]
}
```

Required fields:
- `event_id`
- `sequence`
- `kind`
- `producer`
- `surfaces`
- `interaction_ref`
- `payload`
- `source_refs`

Optional when applicable:
- `timestamp`
- `model_run_ref`
- `tool_invocation_ref`
- `outcome`

Note: there is no `native` field on canonical events. Raw provider data is always available via `source_refs` pointing back to the preserved raw artifacts. The canonical event tape should be self-contained for canonical meaning without embedding provider-native residue.

### Event Outcome
- Result or completion events may carry `outcome`.
- Initial outcome values:
  - `ok`
  - `error`
  - `interrupted`
  - `cancelled`
- Use `outcome` instead of multiplying event kinds for success and failure variants.
- Examples:
  - a failed tool execution is `kind: "tool.result"` with `outcome: "error"`
  - an interrupted tool execution is `kind: "tool.result"` with `outcome: "interrupted"`
  - a failed model run is `kind: "run.end"` with `outcome: "error"`

### Consensus Event Kinds
- The smallest useful cross-provider kind set is:
  - `message`
  - `context`
  - `reasoning`
  - `tool.call`
  - `tool.result`
  - `tool.progress`
  - `run.start`
  - `run.end`
  - `session.start`
  - `session.end`
  - `session.update`
  - `usage`
  - `metric`
  - `error`

Notes:
- Tool execution failures are represented as `kind: "tool.result"` with `outcome: "error"`.
- `error` is reserved for standalone non-result errors that cannot be modeled as a failed `tool.result`, `run.end`, or `session.end`.
- `metric` exists for raw evidence such as Codex `token_count` or Claude `turn_duration` that is not structured token/cost data with a known scope. Normalizers are responsible for the metric-vs-usage boundary: `usage` = structured token/cost data with known scope (per-run or per-session); `metric` = everything else (latency, counts, internal telemetry).
- `context` covers model-visible non-transcript input such as developer/system input or injected environment context.

### Consensus Producer Types
- Canonical producers should use:
  - `user`
  - `assistant`
  - `tool`
  - `system`
  - `provider`

### Consensus Surfaces
- Initial cross-provider surfaces:
  - `transcript`
  - `replay`
  - `debug`
  - `model_input`

Initial surface states:
  - `visible`
  - `hidden`
  - `opaque`
  - `encrypted`

### Provider Mapping Pressure Test
- Claude requires semantic splitting:
  - one raw message record may contain visible text, `thinking`, `tool_use`, `tool_result`, and usage evidence
- Copilot requires semantic splitting:
  - one `assistant.message` may contain visible text, tool requests, and multiple reasoning forms
- Codex requires semantic lifting:
  - important evidence lives outside current `event_msg` records, including `response_item.reasoning`, `response_item.function_call`, and `response_item.function_call_output`

Conclusion:
- the canonical event tape cannot be a thin rename of current provider event rows
- it must normalize semantic units

### Initial Provider Mapping
- Claude:
  - user text -> `message`
  - assistant text -> `message`
  - `thinking` -> `reasoning`
  - `tool_use` -> `tool.call`
  - `tool_result` -> `tool.result`
  - `PreToolUse` / `PostToolUse` -> `tool.progress`
  - `tool_result` with `is_error: true` -> `tool.result` with `outcome: "error"`
  - `message.usage` -> `usage`
  - `turn_duration` -> `metric`
- Copilot:
  - `system.message` -> `context`
  - `user.message` -> `message`
  - assistant text -> `message`
  - assistant `toolRequests[]` -> `tool.call`
  - `reasoningText` / `reasoningOpaque` / `encryptedContent` -> `reasoning`
  - `tool.execution_start` -> `tool.progress`
  - `tool.execution_complete` -> `tool.result` with `outcome` from completion success/failure evidence
  - `assistant.turn_start` / `assistant.turn_end` -> `run.start` / `run.end`
  - session lifecycle or config changes -> `session.*`
  - `session.shutdown.modelMetrics` -> `usage`
- Codex:
  - developer/system input -> `context`
  - visible user prompt -> `message`
  - visible assistant text -> `message`
  - `response_item.reasoning` -> `reasoning`
  - `response_item.function_call` -> `tool.call`
  - `response_item.function_call_output` and `exec_command_end` -> `tool.result` with `outcome` from execution evidence
  - `task_started` / `task_complete` -> `run.start` / `run.end`
  - `token_count` -> `metric`

## Streaming and Delta Assembly
- Normalizers must assemble streaming deltas into a single final-state canonical event.
- Intermediate streaming records (partial content blocks, incremental chunks) should not appear as separate events in the canonical tape.
- The assembled event's `source_refs` should list all raw records that contributed to it, preserving full provenance to the streaming sequence.
- This keeps the event tape semantic while the raw archive retains the full transport-level detail (timing, chunk boundaries) if needed.

## Sequence Ordering
- `sequence` is a normalizer-assigned global order number.
- Normalizers should follow the order of the raw artifact as closely as possible.
- When raw records lack timestamps or arrive out of order, the raw artifact's own ordering is authoritative.
- No additional causal-graph or parallel-branch tracking is required at the canonical level.

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
- On disk, Chatlas should be able to persist just the event tape plus session/source metadata and rebuild the rest.

## Non-Goals
- Model arbitrary UI widget state.
- Model app-specific layout or panel behavior.
- Force every provider into exactly the same transcript shape.

## Suggested Next Steps
1. Update the standard-model note to reference the event-first direction and the canonical event tape.
2. Evolve the experimental schema so normalized events carry canonical `kind`, `producer`, `surfaces`, and `interaction_ref`.
3. Redesign provider exports so raw records split or merge into semantic events where needed.
4. Rebuild `messages`, `interactions`, `model_runs`, `tool_invocations`, `reasoning_traces`, and `usage` as projections over semantic events.
