# Chatlas Codex Raw Normalizer Plan

## Goal
- Add the first provider-raw normalizer for `agentos chatlas experimental export <query>`.
- Target provider: `codex`.
- Input: Codex rollout JSONL backing artifact.
- Output: in-memory `agentos.chatlas.experimental.session_model`.
- Keep this read-only. Do not materialize `normalized/`, `derived/`, or any new persistent artifact yet.

This is the first concrete implementation of the boundary:

```text
provider raw artifact
  -> provider raw normalizer
  -> session.std.model projection
  -> common Chatlas services
```

## Current State
- `agentos chatlas experimental export <query>` exists.
- The exporter currently uses the clean transcript fallback.
- Clean fallback fills `chat.messages` with user/assistant text only.
- `chat.model_runs`, `chat.tool_invocations`, and `chat.events` are still empty.
- For Codex sessions, this loses the replay/tool/reasoning structure that exists in the rollout JSONL.

Current implementation anchor:
- `src/agentos/chatlas/experimental.py`
- `tests/test_chatlas_commands.py`
- Generic plan note: `notes/live/535-chatlas-experimental-session-model-plan.md`

## Progress Notes
- Phase 1 is implemented: the experimental builder now dispatches through an internal provider-normalization boundary.
- Phase 2 is implemented for Codex: the Codex path validates the primary backing artifact as a rollout JSONL and loads raw records with record index, line number, timestamp, record type, payload, and source refs.
- Codex raw parsing warnings are surfaced through `normalization.warnings`.
- Phase 3 is implemented for Codex: `response_item.message` records now populate `chat.messages`.
- Codex messages preserve full raw text, source refs with record index/line, visibility tags, and native content-type metadata.
- Developer/system/context-like messages are preserved with `visibility: "context"` instead of being filtered out.
- Unknown Codex message content item types are preserved as `{"type": "unknown", "native": ...}` blocks with warnings.
- For Codex rollout sessions, `normalization.normalizer` now reports `codex.raw_rollout.experimental.v1` and `normalization.source_mode` reports `codex_raw_rollout` when raw messages are present.
- The clean transcript fallback remains available when raw rollout parsing succeeds but no `response_item.message` records are available.
- Phase 4 is implemented for Codex: `response_item.function_call`, `response_item.function_call_output`, and `event_msg.exec_command_end` records are joined by `call_id` into `chat.tool_invocations`.
- Codex tool invocations preserve parsed input arguments, provider output text, shell execution metadata, source refs for all joined records, and native presence/record-index flags.
- Incomplete tool joins remain visible through warnings for missing call/output/exec-end records; invalid JSON arguments are preserved as raw strings with warnings.
- `tool_invocations` is removed from `normalization.unsupported_concepts` when at least one invocation is normalized.
- Phase 5 is implemented for Codex: every `event_msg` record now populates `chat.events`.
- Codex events preserve normalized event type names, timestamps, source refs, payload data, and native record metadata.
- `event_msg.exec_command_end` events link to `chat.tool_invocations` by `call_id` through `tool_invocation_ref`.
- Tool invocations now receive `event_refs` when related events exist.
- `events` is removed from `normalization.unsupported_concepts` when at least one event is normalized.
- Phase 6 is implemented for Codex: `turn_context`, task lifecycle events, and `response_item.reasoning` now populate `chat.model_runs`.
- Codex model runs preserve model/provider metadata, reasoning effort, cwd, sandbox/approval context, lifecycle bounds, message/tool/event refs, and reasoning traces.
- Encrypted reasoning is preserved as encrypted evidence with source refs and is not treated as visible reasoning text.
- Large or sensitive `turn_context` instruction/summary fields are not copied into the standard model; only safe collaboration-mode settings are exposed.
- `model_runs` is removed from `normalization.unsupported_concepts` when at least one run is normalized.
- Phase 7 is implemented for Codex: `normalization` now includes structured `counts`, `raw_counts`, `coverage`, and `deferred_concepts`.
- Codex raw metadata reports record counts by raw record type, `response_item` payload type, and `event_msg` payload type.
- Coverage metadata compares raw evidence counts against normalized `messages`, `model_runs`, `tool_invocations`, `events`, and reasoning traces.
- Token-count events remain preserved under `chat.events`; the first-class `usage` projection is marked as deferred through `unsupported_concepts` and `deferred_concepts` when token-count evidence exists.
- Count-oriented warnings are emitted when raw evidence is only partially normalized or when stable usage/cost projection is deferred.

## Raw Codex Evidence

From session `019db5fd-7a73-7ae1-b5eb-901e62258dcb`, the Codex rollout includes:
- 168 JSONL records.
- Record types:
  - `session_meta`: 1
  - `turn_context`: 1
  - `response_item`: 104
  - `event_msg`: 62
- `response_item` payload types:
  - `message`: 7
  - `reasoning`: 7
  - `function_call`: 45
  - `function_call_output`: 45
- `event_msg` payload types:
  - `user_message`: 1
  - `agent_message`: 4
  - `exec_command_end`: 45
  - `token_count`: 10
  - `task_started`: 1
  - `task_complete`: 1

The clean fallback currently emits only 5 messages for that session and no tools/events/model runs, so Codex raw normalization should be the next implementation step.

## Normalizer Contract

Add an internal Codex normalizer behind the experimental builder:

```text
_build_experimental_session_model(session)
  -> _normalize_provider_raw(session, sources)
    -> _normalize_codex_raw_rollout(session, sources)
    -> fallback: _experimental_clean_transcript_messages(...)
```

The Codex normalizer should return the same conceptual payload the clean fallback returns, but richer:

```python
{
    "messages": [...],
    "model_runs": [...],
    "tool_invocations": [...],
    "events": [...],
    "source_mode": "codex_raw_rollout",
    "warnings": [...],
    "unsupported_concepts": [...],
}
```

Provider-specific logic stays inside this boundary. Callers should only see the standard experimental model.

## MVP Output Requirements

For Codex rollout sessions, populate:
- `chat.messages` from `response_item.message`.
- `chat.model_runs` from `turn_context` plus task lifecycle evidence.
- `chat.tool_invocations` by joining `function_call`, `function_call_output`, and `exec_command_end` by `call_id`.
- `chat.events` from `event_msg` records.
- Reasoning trace from `response_item.reasoning`, attached to the best model run.
- Source references that point back to the rollout source and record line/index.

Keep raw evidence recoverable by:
- preserving `source_refs` on every normalized object,
- carrying selected provider-native identifiers such as `call_id` and `turn_id`,
- keeping raw rollout data available through `sources`,
- adding warnings instead of silently dropping unsupported fields.

## Proposed Shapes

These are experimental shapes. They are allowed to change before the model is stabilized.

### Messages

```jsonc
{
  "message_id": "message-1",
  "role": "user",
  "timestamp": "2026-04-22T16:20:12.288Z",
  "visibility": "conversation",
  "content": [
    {
      "type": "text",
      "text": "..."
    }
  ],
  "source_refs": [
    {
      "source_ref_id": "source-1",
      "record_index": 3,
      "line": 3
    }
  ],
  "native": {
    "record_type": "response_item",
    "payload_type": "message",
    "content_type": "input_text"
  }
}
```

Visibility guidance:
- `conversation`: human/assistant conversation text.
- `context`: provider/platform/developer/context records that should be preserved but not shown in a default clean transcript.
- `unknown`: records where Chatlas cannot confidently classify visibility.

The raw Codex normalizer should not throw away text. Presentation layers can later choose whether to hide `context` messages.

### Model Runs

```jsonc
{
  "model_run_id": "model-run-1",
  "provider": "codex",
  "model_provider": "openai",
  "model": "gpt-5.4",
  "reasoning_effort": "xhigh",
  "turn_id": "...",
  "started_at": "...",
  "ended_at": "...",
  "status": "completed",
  "message_refs": ["message-1", "message-2"],
  "tool_invocation_refs": ["tool-invocation-1"],
  "event_refs": ["event-1"],
  "reasoning_trace": [
    {
      "reasoning_id": "reasoning-1",
      "timestamp": "...",
      "visibility": "encrypted",
      "encrypted_content": "...",
      "summary": [],
      "content": [],
      "source_refs": [...]
    }
  ],
  "native": {
    "turn_context_present": true
  }
}
```

Model-run rules:
- Prefer one model run per `turn_context`.
- Attach records by `turn_id` when available.
- If no `turn_context` exists, create an inferred run only when the session has model-scoped records, and emit a warning.
- Do not invent precise boundaries when the raw data does not support them.

### Tool Invocations

```jsonc
{
  "tool_invocation_id": "tool-invocation-1",
  "call_id": "...",
  "tool_name": "exec_command",
  "status": "completed",
  "started_at": "...",
  "ended_at": "...",
  "input": {
    "arguments": {}
  },
  "output": {
    "content": "..."
  },
  "execution": {
    "command": "...",
    "cwd": "...",
    "exit_code": 0,
    "duration": 1.23,
    "stdout": "...",
    "stderr": "..."
  },
  "source_refs": [...],
  "native": {
    "response_call_present": true,
    "response_output_present": true,
    "exec_end_present": true
  }
}
```

Tool-linking rules:
- Use `call_id` as the join key.
- Emit a tool invocation even if only one side exists.
- Add warnings for unmatched calls, unmatched outputs, duplicate `call_id`s, or invalid argument JSON.
- Parse `arguments` as JSON when possible; keep the original string when parsing fails.
- Prefer `exec_command_end` fields for shell execution metadata.

### Events

```jsonc
{
  "event_id": "event-1",
  "type": "codex.exec_command_end",
  "timestamp": "...",
  "turn_id": "...",
  "tool_invocation_ref": "tool-invocation-1",
  "source_refs": [...],
  "native": {
    "payload_type": "exec_command_end"
  }
}
```

Event rules:
- Preserve `event_msg` records as replay evidence.
- Link `exec_command_end` events to tool invocations by `call_id`.
- Keep `agent_message` and `user_message` events as replay events, not canonical messages, because `response_item.message` is the better message source.
- Preserve `token_count`, `task_started`, and `task_complete` events.

## Reasoning Policy

Codex reasoning records may contain encrypted content. The normalizer should:
- preserve visible `summary` and `content` when present,
- preserve encrypted reasoning as encrypted evidence when present,
- mark encrypted items with `visibility: "encrypted"`,
- avoid claiming encrypted reasoning is human-readable,
- attach reasoning to `model_runs[].reasoning_trace`,
- add a warning if reasoning records exist but cannot be attached to a model run.

## Implementation Phases

### Phase 1. Add A Provider Normalization Result
- Introduce an internal result shape in `src/agentos/chatlas/experimental.py`.
- Replace the direct clean-fallback call in `_build_experimental_session_model`.
- Dispatch on `session["provider"]`.
- Use Codex raw normalizer only when the primary backing artifact is a readable rollout JSONL.
- Keep the clean transcript fallback for unsupported providers and failure cases.

### Phase 2. Add Codex Raw Record Loader
- Read the primary backing artifact line by line.
- Parse JSON objects with `record_index`, `line`, `timestamp`, `type`, and `payload`.
- Skip invalid JSONL lines with warnings.
- Preserve source references with line/index information.
- Reuse or mirror Codex rollout validation from `agentos.chat.extractors.codex` without coupling to the clean extractor output.

### Phase 3. Normalize Messages
- Convert `response_item.message` records into `chat.messages`.
- Preserve `role` from Codex where possible.
- Map `input_text` and `output_text` to `{ "type": "text" }` blocks.
- Map unknown content item types to `{ "type": "unknown", "native": ... }`.
- Mark developer/platform/context-like messages as `visibility: "context"`.
- Mark normal user and assistant conversation records as `visibility: "conversation"`.
- Preserve native role/content type metadata.

### Phase 4. Normalize Tool Invocations
- Index `response_item.function_call` by `call_id`.
- Index `response_item.function_call_output` by `call_id`.
- Index `event_msg.exec_command_end` by `call_id`.
- Build one `chat.tool_invocations[]` entry per observed `call_id`.
- Attach all source refs for that call id.
- Link related event ids to the tool invocation.
- Emit warnings for incomplete or conflicting join groups.

### Phase 5. Normalize Events
- Convert every `event_msg` into `chat.events`.
- Use type names like `codex.task_started`, `codex.token_count`, and `codex.exec_command_end`.
- Include selected structured fields directly when they are provider-neutral enough.
- Put provider-specific residue under `native`.
- Link events to model runs and tool invocations when possible.

### Phase 6. Normalize Model Runs And Reasoning
- Build model runs from `turn_context`.
- Populate model/provider/reasoning-effort/cwd/sandbox/approval metadata from `turn_context`.
- Use `task_started` and `task_complete` to set status and bounds when available.
- Attach message, tool, event, and reasoning references.
- Convert `response_item.reasoning` into `reasoning_trace`.
- Preserve encrypted reasoning explicitly instead of dropping it.

### Phase 7. Update Normalization Metadata
- Set `normalization.source_mode` to `codex_raw_rollout`.
- Set `normalization.normalizer` to `codex.raw_rollout.experimental.v1`.
- Remove `messages`, `tool_invocations`, `events`, and `model_runs` from `unsupported_concepts` when populated.
- Add residual unsupported concepts only for known missing surfaces, such as stable usage/cost modeling if not yet implemented.
- Include count-oriented warnings when raw concepts were present but partially normalized.

### Phase 8. Tests
- Extend Codex test fixtures with:
  - one user message,
  - one assistant message,
  - one reasoning record,
  - one `function_call`,
  - one `function_call_output`,
  - one `exec_command_end`,
  - one `token_count`,
  - task start/complete records,
  - one context/developer message.
- Assert:
  - `source_mode == "codex_raw_rollout"`,
  - messages are populated from raw records,
  - context messages are preserved with `visibility: "context"`,
  - tool calls/results/exec events join by `call_id`,
  - reasoning trace preserves encrypted evidence,
  - events include lifecycle and token-count records,
  - clean fallback still works for unsupported providers or missing artifacts.

### Phase 9. Real Session Verification
- Refresh the editable CLI after code changes:

```sh
uv tool install --reinstall --editable .
```

- Run the focused test file:

```sh
uv run pytest tests/test_chatlas_commands.py -q
```

- Re-export the known session:

```sh
agentos chatlas experimental export 019db5fd-7a73-7ae1-b5eb-901e62258dcb --provider codex
```

- Expected high-level result for that session:
  - `normalization.source_mode == "codex_raw_rollout"`
  - `chat.messages` includes the 7 raw `response_item.message` records, with visibility tags.
  - `chat.tool_invocations` includes 45 joined invocations.
  - `chat.events` includes 62 replay events.
  - `chat.model_runs` includes the Codex turn context.
  - `model_runs[].reasoning_trace` includes 7 reasoning records.
  - Clean transcript fallback warnings are gone.

## Open Decisions
- Whether encrypted reasoning should be emitted inline in the standard model by default, or represented by source refs plus a hash. Initial recommendation: emit it inline in this experimental local export, clearly marked as encrypted.
- Whether developer/context messages should live in `chat.messages` or a separate context collection. Initial recommendation: keep them in `chat.messages` with `visibility: "context"` so no text is lost.
- Whether `agent_message` and `user_message` events should also create messages. Initial recommendation: keep them as events to avoid duplicates, and use `response_item.message` as canonical messages.
- Whether usage/token counts deserve a first-class `usage` surface now. Initial recommendation: keep token-count events in `chat.events` first; promote to `usage` after comparing more providers.

## Acceptance Criteria
- Codex raw rollout sessions no longer rely on clean transcript fallback when raw parsing succeeds.
- The experimental export exposes messages, tools, events, model-run metadata, and reasoning evidence for Codex.
- Tool calls are joined by `call_id` and incomplete joins are visible through warnings.
- Raw evidence remains traceable through source refs.
- No storage format is changed.
- Focused tests pass.
