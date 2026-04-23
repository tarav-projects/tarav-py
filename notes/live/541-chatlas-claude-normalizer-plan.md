# Chatlas Claude Normalizer Plan

## Goal
- Implement a provider-specific raw normalizer for `claude-code` in `agentos chatlas experimental export`.
- Project Claude raw session artifacts into the experimental standard model at the provider boundary:

```text
claude raw session artifact
  -> claude provider normalizer
  -> session.std.model
```

Normalizer id:

```text
claude-code.raw_session.experimental.v1
```

Source mode:

```text
claude_code_raw_session
```

## Reference Session
- Primary example session:
  - `5dbf4437-633e-4039-a627-0459d85e9ecc`
- Artifact:
  - `~/.claude/projects/-Users-pereiro-projects-agentos-project-agentos/5dbf4437-633e-4039-a627-0459d85e9ecc.jsonl`

Observed raw shape in the example session:
- `42` raw records
- `1` real human prompt
- `12` assistant records
- `10` user records total
- `9` assistant `tool_use` content blocks
- `9` user `tool_result` content blocks
- `18` progress records (`PreToolUse` / `PostToolUse`)
- `1` assistant `thinking` content block
- `4` distinct `requestId` values

## Progress Notes
- Phase 1 is implemented.
- Phase 3 is implemented.
- Phase 4 is implemented.
- `agentos chatlas experimental export <claude-session>` now dispatches `claude-code` to `claude-code.raw_session.experimental.v1`.
- Claude currently loads the raw session artifact, preserves raw record structure in-memory, reports raw counts and coverage, and returns explicit deferred concepts.
- Claude now normalizes visible `chat.messages[]` from user string content and assistant text blocks.
- Claude now normalizes `chat.events[]` from the raw record stream.
- `last-prompt` artifact residue is intentionally excluded from canonical events and remains visible through raw counts/warnings.
- Normalized Claude tool invocations, model runs, reasoning, and usage remain intentionally deferred to later phases.

## Design Commitments
- Keep canonical surfaces truthful and provider-neutral.
- Preserve Claude-specific residue in bounded `native` fields.
- Do not represent `tool_result` protocol records as visible user chat messages.
- Do not represent `tool_use`-only or `thinking`-only assistant records as visible assistant chat messages.
- Use structured provider evidence first:
  - `toolUseResult` for tool execution output
  - `message.usage` for usage
  - `requestId` for model-run grouping
- Preserve raw provenance with source refs on normalized records.

## Proposed Claude Mapping

### Messages
- Normalize the real human prompt as one canonical user message.
- Normalize assistant `content[].type == "text"` blocks as visible assistant messages.
- Exclude these from visible `chat.messages`:
  - assistant `thinking`-only records
  - assistant `tool_use`-only records
  - user `tool_result` records

Expected visible messages for the reference session:
- `1` user message
- `2` assistant messages
- total: `3`

### Tool Invocations
- Join tool evidence by Claude `tool_use.id`.
- Request evidence:
  - assistant `content[].type == "tool_use"`
- Result evidence:
  - user `content[].type == "tool_result"`
  - top-level `toolUseResult`
- Runtime evidence:
  - `progress` records with `toolUseID`

Canonical fields:
- `call_id`
- `tool_name`
- `status`
- `started_at`
- `ended_at`
- `input`
- `output`
- `execution`
- `model`
- `request_id`
- `message_id`
- `event_refs`
- `source_refs`

Expected tool invocations for the reference session:
- `9`

### Model Runs
- Group Claude runs primarily by `requestId`.
- Use `message.id` as bounded native/supporting evidence, not the primary run key.
- Treat `stop_reason == "tool_use"` as a completed run that yielded tool requests, not as an incomplete run.
- Attach:
  - visible message refs
  - tool invocation refs
  - event refs
  - reasoning trace
  - usage

Expected model runs for the reference session:
- `4`

### Reasoning
- Normalize assistant `content[].type == "thinking"` into `model_runs[].reasoning_trace[]`.
- Use:
  - `visibility: "visible"` when `thinking` text is present
- Preserve Claude `signature` and any provider-only reasoning metadata under `native`.

Expected reasoning trace entries for the reference session:
- `1`

### Usage
- Promote Claude `message.usage` into `chat.usage[]`.
- Use `scope: "model_run"` because the evidence is attached to request/message records, not just session shutdown state.
- Preserve provider cache fields and related usage residue under `native`.
- Do not invent session totals unless we decide to derive them explicitly.

Expected usage records for the reference session:
- `4`

### Events
- Normalize raw records into `chat.events[]` where they provide replay or provenance value.
- Include at least:
  - assistant records
  - user records
  - progress records
  - system records that reflect runtime session behavior
- Keep redundant artifact residue such as `last-prompt` out of canonical events unless needed for diagnostics.

## Implementation Phases

### Phase 1. Loader And Dispatch
- Add `claude-code` dispatch in `src/agentos/chatlas/experimental.py`.
- Add a Claude raw session loader that preserves:
  - raw record index
  - line number
  - uuid
  - parent uuid
  - timestamp
  - top-level record type
  - message payload
  - progress payload
  - tool result payload
  - source refs
- Validate the artifact with the existing Claude extractor helper.
- Emit parse warnings for invalid JSON or unsupported record shapes.

### Phase 2. Raw Counts And Metadata
- Add Claude raw-count reporting and normalization metadata.
- Track at least:
  - raw record count
  - raw visible-message evidence count
  - raw tool-use count
  - raw tool-result count
  - raw progress count
  - raw reasoning evidence count
  - raw usage evidence count
  - distinct request count

### Phase 3. Events
- Normalize replay-oriented raw records into `chat.events[]`.
- Promote useful cross-links:
  - `call_id`
  - `request_id`
  - `message_id`
  - `parent_uuid`
  - `tool_invocation_ref`
  - `model_run_ref`
- Preserve raw payload fragments under `data` and `native`.

### Phase 4. Messages
- Normalize visible chat messages only.
- Keep Claude protocol/tool plumbing out of visible `chat.messages`.
- Preserve message ids, request ids, stop reason, model, and related provider metadata under `native`.

### Phase 5. Tool Invocations
- Build one normalized tool invocation per `tool_use.id`.
- Join assistant tool request, tool result, and progress evidence.
- Prefer `toolUseResult` for structured execution output.
- Add warnings for incomplete tool groups.

### Phase 6. Model Runs
- Build one model run per `requestId`.
- Derive run timestamps from the grouped raw records.
- Attach message refs, tool refs, and event refs.
- Normalize run status with Claude-specific rules.

### Phase 7. Reasoning And Usage
- Promote `thinking` blocks into `reasoning_trace`.
- Promote per-request `message.usage` into `chat.usage[]`.
- Keep provider-only cache/accounting fields bounded under `native`.

### Phase 8. Coverage, Warnings, And Tests
- Add count-oriented warnings when raw evidence exceeds normalized coverage.
- Add fixture coverage for:
  - text messages
  - thinking blocks
  - tool_use/tool_result pairs
  - progress records
  - usage
- Add a real-session smoke check for:
  - `5dbf4437-633e-4039-a627-0459d85e9ecc`

## Initial Smoke Expectations
- `messages: 3`
- `tool_invocations: 9`
- `model_runs: 4`
- `reasoning_traces: 1`
- `usage: 4`

These are working expectations for the current reference session, not a cross-provider contract.

## Open Decisions
- Whether to keep all assistant raw records as events, or exclude purely redundant duplicates.
- Whether to emit a derived session-scoped usage summary in addition to run-scoped usage.
- Whether some Claude `system` records belong in canonical events or only in bounded metadata.
