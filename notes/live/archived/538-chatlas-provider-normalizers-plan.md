# Chatlas Provider Normalizers Plan

## Goal
- Move the experimental standard model toward a real provider-normalizer architecture.
- Update the existing Codex normalizer only where the shared model contract requires it.
- Implement a Copilot CLI raw-events normalizer for `agentos chatlas experimental export`.

Target boundary:

```text
provider raw artifacts
  -> provider normalizer
  -> session.std.model
```

## Current State
- `agentos chatlas experimental export <query>` exists.
- The experimental command now errors when a provider has no provider-specific raw normalizer.
- Codex has the first raw normalizer: `codex.raw_rollout.experimental.v1`.
- Copilot CLI now has an experimental raw-events normalizer: `copilot-cli.raw_events.experimental.v1`.
- Copilot currently normalizes messages, events, and tool invocations; model runs, reasoning traces, and usage remain deferred.
- The canonical surface rule is documented in `notes/live/534-chatlas-standard-chat-model.md`.

## Progress Notes
- Phase 1 shared contract slice is implemented.
- The experimental normalization result now includes `usage`.
- The experimental JSON envelope now emits `chat.usage`.
- Codex emits `chat.usage: []` while preserving token-count records under `chat.events`.
- Normalization counts and generic coverage now include usage counts.
- Chatlas command tests cover the new empty usage surface for Codex.
- Copilot Phase 1 loader is implemented.
- The experimental builder now dispatches `copilot-cli` to `copilot-cli.raw_events.experimental.v1`.
- Copilot raw event loading preserves event index, line number, event id, parent id, timestamp, event type, data object, and source refs internally.
- Copilot Phase 1 emits raw event counts, event-type counts, parse-warning counts, and evidence counts for reasoning, usage, and cost.
- Copilot raw counts now also track assistant `toolRequests` as tool-call evidence.
- Unsupported providers still fail explicitly; tests now cover that path with `pi`.
- Copilot Phase 2 events are implemented.
- The Copilot normalizer now emits one `chat.events[]` record per raw event.
- Copilot events use `copilot-cli.<raw event type>` type names and preserve raw event data, timestamps, source refs, and native event metadata.
- Copilot events promote `turn_id`, `call_id`, and `interaction_id` when those identifiers are present.
- Copilot event coverage now reports normalized event counts instead of treating events as unsupported.
- Copilot Phase 3 messages are implemented.
- `system.message` records normalize to context messages.
- `user.message.content` normalizes as canonical user-authored conversation content, while `transformedContent` stays under `native.transformed_content`.
- Non-empty `assistant.message.content` normalizes as assistant conversation content.
- Empty assistant messages that only carry tool requests remain represented through events until Phase 4 creates tool invocations.
- Copilot message native metadata preserves provider message ids, request ids, phases, output tokens, tool requests, interaction ids, and reasoning/encrypted evidence when present.
- Copilot Phase 4 tool invocations are implemented.
- Copilot now joins `assistant.message.toolRequests`, `tool.execution_start`, and `tool.execution_complete` by `toolCallId`.
- `chat.tool_invocations[]` now emits canonical tool name, status, timestamps, input arguments, output content, model, interaction id, event refs, and source refs.
- Copilot tool execution events now link back to `tool_invocation_ref` in `chat.events`.
- Real-session smoke for `d1d3f48b-4b29-4dfc-b551-5536b9677225` now yields 2 normalized tool invocations and 18 normalized events.
- Copilot Phase 5 model runs are implemented.
- Copilot now builds one `chat.model_runs[]` record per `assistant.turn_start` / `assistant.turn_end` span, keyed by `turnId`.
- Model runs attach message refs, tool invocation refs, event refs, output tokens, and the current model chosen from structured session model-change evidence.
- Real-session smoke for `d1d3f48b-4b29-4dfc-b551-5536b9677225` now yields 3 normalized model runs.
- Copilot Phase 6 reasoning is implemented.
- `assistant.message.reasoningText`, `reasoningOpaque`, and `encryptedContent` now normalize into `model_runs[].reasoning_trace` as separate entries with truthful `visibility` values: `visible`, `opaque`, and `encrypted`.
- Reasoning evidence that cannot be attached to a normalized turn now emits a warning and remains preserved in `messages/events/native`.
- Real-session smoke for `d1d3f48b-4b29-4dfc-b551-5536b9677225` now yields 5 normalized reasoning-trace entries across 3 model runs.
- Copilot Phase 7 usage is implemented.
- `session.shutdown.data.modelMetrics` now normalizes into `chat.usage[]` with one session-scoped record per model key.
- Copilot request cost now lands in `usage.provider_billing_units` as bounded provider-specific billing evidence instead of remaining a deferred standalone cost surface.
- Session-level shutdown token counters remain preserved under `usage[].native.session_token_counters`.
- Real-session smoke for `d1d3f48b-4b29-4dfc-b551-5536b9677225` now yields 1 normalized usage record and no remaining unsupported Copilot MVP surfaces.

## Design Commitments
- Normalizers preserve raw evidence with source refs.
- Canonical fields should be truthful and provider-neutral.
- Provider-specific residue belongs in bounded `native` data until a provider-neutral surface exists.
- Do not invent precision. If raw data is aggregate, keep it aggregate.
- Do not parse semi-structured terminal text into canonical fields unless the provider exposes reliable structured evidence.

## Shared Model Adjustment

### Add `chat.usage`
- Add a top-level experimental chat surface:

```jsonc
{
  "chat": {
    "messages": [],
    "model_runs": [],
    "tool_invocations": [],
    "events": [],
    "usage": []
  }
}
```

Rationale:
- Usage and cost are already part of the standard model scope.
- Copilot exposes structured aggregate usage in `session.shutdown.modelMetrics`.
- Codex token-count evidence exists, but its stable projection is still deferred.

Initial usage record shape:

```jsonc
{
  "usage_id": "usage-1",
  "scope": "session",
  "provider": "copilot-cli",
  "model": "gpt-5.4",
  "input_tokens": 65285,
  "output_tokens": 978,
  "cache_read_tokens": 41472,
  "cache_write_tokens": 0,
  "reasoning_tokens": 401,
  "request_count": 3,
  "provider_billing_units": {
    "kind": "copilot_premium_request_cost",
    "value": 1
  },
  "source_refs": [...]
}
```

Rules:
- Use `scope: "session"` for aggregate usage.
- Use `scope: "model_run"` only when the raw data is truly per run.
- Do not distribute session-level usage across model runs.
- Cost-like fields stay provider-specific unless they have a provider-neutral unit.

### Adapter Result Contract
- Extend `_ExperimentalNormalizationResult` with `usage`.
- Keep all provider normalizers returning the same normalized surfaces:
  - `messages`
  - `model_runs`
  - `tool_invocations`
  - `events`
  - `usage`
  - `normalizer`
  - `source_mode`
  - `warnings`
  - `unsupported_concepts`
  - `metadata`

## Codex Adapter Updates

### Required
- Add `usage=[]` to Codex normalizer results until stable Codex usage projection is implemented.
- Keep Codex `token_count` records preserved under `chat.events`.
- Keep `usage` in `unsupported_concepts` and `deferred_concepts` when `token_count` evidence exists but no first-class usage is emitted.
- Update normalization counts and coverage to include `usage`.
- Update tests to expect the new `chat.usage` field.

### Optional Cleanup
- Consider renaming internal functions from provider-specific "raw rollout" wording into a clearer adapter boundary later, but do not block Copilot on this.
- Keep the existing Codex source refs and reasoning behavior unchanged.

## Copilot Adapter MVP

Normalizer id:

```text
copilot-cli.raw_events.experimental.v1
```

Source mode:

```text
copilot_cli_raw_events
```

Primary artifact:
- `events.jsonl` under `.copilot/session-state/<session-id>/events.jsonl`
- Legacy flat `.jsonl` sessions should be accepted if existing Copilot extractor already recognizes them.

### Phase 1. Loader
- Add a Copilot raw event loader that preserves:
  - event index
  - line number
  - event id
  - parent id
  - timestamp
  - event type
  - data object
  - source refs
- Surface invalid JSON and non-object lines as normalization warnings.
- Validate that the artifact belongs to Copilot using the existing Copilot extractor helper or equivalent embedded `session.start` evidence.

### Phase 2. Events
- Normalize every raw Copilot event into `chat.events`.
- Event type format: `copilot-cli.<raw type>`, for example `copilot-cli.tool.execution_complete`.
- Preserve raw event data under `data`, excluding only fields already promoted if useful.
- Include `native` with event id, parent id, event type, record index, and line.
- Link tool events to `tool_invocation_ref` when possible.
- Link turn events to `model_run_ref` when possible.

### Phase 3. Messages
- Normalize `system.message` as a context message.
- Normalize `user.message.content` as canonical user-authored conversation content.
- Preserve `user.message.transformedContent` under `native.transformed_content`, not canonical content.
- Normalize `assistant.message.content` as assistant conversation content when non-empty.
- Do not create a visible assistant message for an empty `assistant.message` whose purpose is only tool request emission.
- Preserve assistant message ids, request ids, phases, output token counts, tool request summaries, encrypted content, and opaque reasoning evidence in `native`.

Expected for session `d1d3f48b-4b29-4dfc-b551-5536b9677225`:
- 1 context system message.
- 1 conversation user message.
- 2 visible assistant messages.
- 1 empty tool-request-only assistant event represented through tools/events, not a visible message.

### Phase 4. Tool Invocations
- Join by `toolCallId`.
- Use `assistant.message.data.toolRequests`, `tool.execution_start`, and `tool.execution_complete` as evidence.
- Emit one `tool_invocation` per observed `toolCallId`.
- Canonical fields:
  - `call_id`
  - `tool_name`
  - `status`: `completed`, `failed`, or `requested`
  - `started_at`
  - `ended_at`
  - `input.arguments`
  - `output.content`
  - `output.detailed_content`
  - `model`
  - `interaction_id`
  - `event_refs`
  - `source_refs`
- For `bash`, put command arguments in `input.arguments`; do not parse exit status from result text.
- Preserve `toolTelemetry`, raw result, and request metadata under `native`.

### Phase 5. Model Runs
- Build one model run per `assistant.turn_start` / `assistant.turn_end` pair.
- Use `turnId` as the join key.
- Attach:
  - messages by parent-chain and interaction id where reliable
  - tool invocations by event parent-chain and interaction id
  - events by turn boundaries, parent-chain, or turn id
  - reasoning traces from assistant messages inside the turn
- Model:
  - Prefer `session.model_change.data.newModel`.
  - Fall back to `session.shutdown.data.currentModel`.
- Status:
  - `completed` when matching turn end exists.
  - `running` or `unknown` when turn start has no end.
- Per-run usage:
  - Attach `output_tokens` from `assistant.message.outputTokens`.
  - Do not attach aggregate input/reasoning/cache tokens.

### Phase 6. Reasoning
- Normalize visible `assistant.message.reasoningText` into `model_runs[].reasoning_trace` with `visibility: "visible"`.
- Preserve `reasoningOpaque` and `encryptedContent` as opaque/encrypted evidence with source refs.
- Do not present opaque/encrypted reasoning as readable text.
- If reasoning evidence exists but cannot be attached to a model run, emit a warning and preserve it in the most conservative place available.

### Phase 7. Usage
- Normalize `session.shutdown.data.modelMetrics` into `chat.usage`.
- Emit one usage record per model key under `modelMetrics` when the payload has the nested shape:

```jsonc
{
  "modelMetrics": {
    "gpt-5.4": {
      "requests": {"count": 3, "cost": 1},
      "usage": {
        "inputTokens": 65285,
        "outputTokens": 978,
        "cacheReadTokens": 41472,
        "cacheWriteTokens": 0,
        "reasoningTokens": 401
      }
    }
  }
}
```

- If Copilot emits a flatter `modelMetrics` shape, preserve it under `native` and emit a warning unless a safe mapping is obvious.
- Include session-level token counters from shutdown as native evidence unless they map cleanly.

### Phase 8. Normalization Metadata
- Add Copilot `raw_counts`:
  - total events
  - counts by event type
  - parse warning count
- Add Copilot coverage:
  - messages
  - model_runs
  - tool_invocations
  - events
  - reasoning
  - usage
  - cost
- Warnings should report actual gaps, not routine progress.
- Use `unsupported_concepts` only for missing standard surfaces with raw evidence or intentionally deferred concepts.

### Phase 9. Tests
- Add focused fixture tests in `tests/test_chatlas_commands.py`.
- Test missing provider normalizer remains true for a different unsupported provider.
- Replace the current Copilot missing-normalizer test with a successful Copilot export once the normalizer lands.
- Assertions for Copilot fixture:
  - `source_mode == "copilot_cli_raw_events"`
  - messages include system context, user text, and visible assistant text
  - transformed user content is preserved in `native`, not canonical content
  - tool calls join by `toolCallId`
  - model runs join by `turnId`
  - visible and opaque reasoning evidence is represented correctly
  - usage is emitted from `session.shutdown.modelMetrics`
  - no terminal-result exit-code parsing is performed

### Phase 10. Real Session Smoke
- Reinstall CLI after behavior changes:

```sh
uv tool install --reinstall --editable .
```

- Smoke command:

```sh
agentos chatlas experimental export d1d3f48b-4b29-4dfc-b551-5536b9677225 --format json
```

Expected high-level counts after MVP:

```jsonc
{
  "messages": 4,
  "model_runs": 3,
  "tool_invocations": 2,
  "events": 18,
  "usage": 1
}
```

Reasoning traces should be at least 2 if both opaque/encrypted assistant reasoning records are counted, with one visible reasoning text record attached to the final model run.

## Acceptance Criteria
- Unsupported providers fail explicitly.
- Codex exports still pass existing behavior, with `chat.usage: []` added.
- Copilot session `d1d3f48b-4b29-4dfc-b551-5536b9677225` exports without fallback.
- Copilot output does not lose raw evidence needed for audit or future migration.
- Copilot output does not promote transformed prompt input, aggregate usage, or parsed terminal text into misleading canonical fields.
- `uv run pytest tests/test_chatlas_commands.py -q` passes.
