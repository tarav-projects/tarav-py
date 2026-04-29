# Chatlas Provider-Neutral Leak Audit

## Goal
- Audit current `agentos.chatlas.experimental.session_model` exports against the provider-neutral contract in `547`.
- Identify provider-shaped fields still present outside raw artifacts.
- Classify each field as:
  - promote to a neutral field
  - replace with `source_refs` or `event_refs`
  - move behind a debug/raw resolver
  - drop from standard output

## Inputs
Reference exports were generated from checked-in samples under `dev/session-samples/`:
- Claude Code: `5dbf4437-633e-4039-a627-0459d85e9ecc`
- Copilot CLI: `d1d3f48b-4b29-4dfc-b551-5536b9677225`
- Codex: `019db5fd-7a73-7ae1-b5eb-901e62258dcb`

The scan checked:
- `native` fields across the standard model
- event top-level fields outside the contract
- event payload keys outside the contract
- source-ref coverage needed to remove native fields without losing raw traceability

## Summary
The event tape is close to the provider-neutral boundary, but the export is not fully provider-neutral yet.

Main leak classes:
1. Projection records still expose `native`.
2. `session.native` is still copied from the existing Chatlas dataset layer.
3. Some event top-level fields are raw locator/correlation helpers.
4. Some event payload fields are provider-specific debug residue.
5. Some provider facts need neutral promotion rather than direct copying.

## Counts From Reference Exports

Claude Code:
- `messages=3`
- `model_runs=4`
- `tool_invocations=9`
- `events=53`
- `usage=12`
- `reasoning_traces=1`
- unsupported concepts: none

Copilot CLI:
- `messages=4`
- `model_runs=3`
- `tool_invocations=2`
- `events=25`
- `usage=1`
- `reasoning_traces=5`
- unsupported concepts: none

Codex:
- `messages=7`
- `model_runs=1`
- `tool_invocations=45`
- `events=163`
- `usage=0`
- `reasoning_traces=7`
- unsupported concepts: `usage`

## Leak Inventory

### 1. Projection `native`
Status: remove from standard projections.

Observed:

Claude:
- `chat.messages[*].native`: 3
- `chat.model_runs[*].native`: 4
- `chat.tool_invocations[*].native`: 9
- `chat.model_runs[*].reasoning_trace[*].native`: 1
- `chat.usage[*].native`: 12

Copilot:
- `chat.messages[*].native`: 4
- `chat.model_runs[*].native`: 3
- `chat.tool_invocations[*].native`: 2
- `chat.model_runs[*].reasoning_trace[*].native`: 5
- `chat.usage[*].native`: 1

Codex:
- `chat.messages[*].native`: 7
- `chat.model_runs[*].native`: 1
- `chat.tool_invocations[*].native`: 45
- `chat.model_runs[*].reasoning_trace[*].native`: 7

Decision:
- Remove these from standard projections.
- Keep neutral fields already present:
  - ids
  - timestamps
  - status
  - model
  - request/turn ids when neutral
  - input/output/execution summaries
  - token fields
  - `event_refs`
  - `source_refs`
- Raw details currently inside `native` should be recovered through `source_refs`.

Traceability impact:
- Low, assuming `source_refs` and `event_refs` stay complete.
- Most `native` fields duplicate source indexes, raw records, or provider event payloads.

### 2. `session.native`
Status: remove from standard model envelope.

Observed:
- `session.native`: 1 per provider reference export.

Decision:
- Do not include `session.native` in the standard model.
- Keep native session metadata in the underlying Chatlas dataset row or raw artifacts.
- Promote only neutral fields such as `session_id`, `display_name`, `created_at`, and `updated_at`.

Traceability impact:
- Low.
- The session has backing artifacts and source descriptors.

### 3. Event Top-Level Locator/Correlation Fields
Status: move source locators into `source_refs`; drop raw provider correlations unless neutral.

Observed:

Claude:
- `parent_uuid`: 52 events
- `content_index`: 19 events

Copilot:
- `request_index`: 2 events

Codex:
- no extra event top-level keys in the reference export.

Decisions:
- `content_index`: source locator. Keep only in `source_refs`.
- `request_index`: source locator. Keep only in `source_refs`.
- `parent_uuid`: raw Claude message correlation id. Drop from standard events unless a provider-neutral relationship is explicitly needed. Current `interaction_ref`, `model_run_ref`, `tool_invocation_ref`, and source refs are the standard relationships.

Traceability impact:
- Low for `content_index` and `request_index`; those already belong in source refs.
- Medium for `parent_uuid`; before dropping it, verify model-run/tool/message refs preserve all standard relationships needed by projections.

### 4. Claude Tool Progress Payload
Status: partially promote, mostly move to debug/raw.

Observed extra payload keys:
- `tool.progress.progress_type`: 18
- `tool.progress.hook_event`: 18
- `tool.progress.hook_name`: 18

Related field to review:
- `tool.progress.command` currently contains the Claude hook command, not the user-requested tool command.

Decisions:
- Promote `progress_type` to neutral `phase` if it can be normalized to values like `pre_tool_use` and `post_tool_use`.
- Drop `hook_event` and `hook_name` from standard output; keep recoverable through source refs.
- Review `command` for Claude hook progress. The canonical tool command already exists in the `tool.call` input. Hook implementation commands are provider/debug detail and should not be confused with the user's tool execution command.

Traceability impact:
- Low.
- Source refs point back to the hook progress records.

### 5. Copilot Interaction Id Payloads
Status: replace with canonical refs.

Observed extra payload keys:
- `run.start.interaction_id`: 3
- `tool.result.interaction_id`: 2

Decision:
- Drop provider/raw interaction ids from payloads.
- Use canonical `interaction_ref` for standard interaction grouping.
- If the raw Copilot interaction id is needed for debugging, resolve it through source refs.

Traceability impact:
- Low.
- Standard grouping already uses `interaction_ref`.

### 6. Copilot Usage Payload
Status: split into neutral usage fields, metrics, and raw-only data.

Observed extra payload keys:
- `usage.model_metrics`: 1
- `usage.current_model`: 1
- `usage.total_premium_requests`: 1
- `usage.total_api_duration_ms`: 1
- `usage.current_tokens`: 1
- `usage.system_tokens`: 1
- `usage.conversation_tokens`: 1
- `usage.tool_definitions_tokens`: 1
- `usage.code_changes`: 1

Decisions:
- `model_metrics`: raw provider aggregate blob. Do not expose directly.
- `current_model`: promote to neutral `model` where appropriate.
- `total_premium_requests`: represent as `provider_billing_units` if scoped clearly.
- `total_api_duration_ms`: preserve as `metric` or neutral duration field, not usage.
- `current_tokens`, `system_tokens`, `conversation_tokens`, `tool_definitions_tokens`: prompt-composition counters. Preserve as `metric` unless the usage contract gains explicit fields for context composition.
- `code_changes`: not usage. Preserve as `metric` or debug-only raw evidence.

Traceability impact:
- Medium.
- The usage projection already exposes neutral token and billing fields, but source refs must remain precise before dropping the raw `model_metrics` blob.

### 7. Codex Tool Progress Payload
Status: promote or rename neutral execution fields.

Observed extra payload keys:
- `tool.progress.parsed_cmd`: 45
- `tool.progress.source`: 45

Decisions:
- `parsed_cmd`: duplicate command structure. Promote to a single neutral field, likely `command`, and remove the provider-shaped alias.
- `source`: provider/event origin label. Use `result_source` when it describes semantic result flow; otherwise drop and keep raw evidence through source refs.

Traceability impact:
- Low.
- Codex tool progress events already include command/output fields and source refs.

### 8. Unknown Content Item Native Payloads
Status: remove from standard content items.

Observed in reference exports:
- Not present in the three reference-session exports.

Known from tests/current code:
- Unknown content items can currently carry `native`.

Decision:
- Replace unknown content `native` with a small neutral placeholder or summary.
- Keep full raw content recoverable through source refs.

Traceability impact:
- Medium for unknown structured content.
- Before removing, ensure the containing message/event has source refs precise enough to recover the raw content item.

## Not Leaks
These are acceptable standard-model fields:
- `provider` as provider family identity
- `source_ref_id`
- `event_id`
- `sequence`
- `content[*].type` for standard content item type
- `producer.type`
- `request_id` when used as a neutral execution request identity
- `turn_id` when used as a neutral execution turn identity
- `call_id` when used to link tool call/progress/result

## Recommended Cleanup Order
1. Strengthen and validate source refs before deleting projection `native`.
2. Remove event top-level source locator fields already duplicated in source refs.
3. Remove raw provider correlation ids from event payloads.
4. Normalize Claude hook progress payloads.
5. Normalize Copilot usage payloads into usage plus metrics.
6. Normalize Codex tool progress aliases.
7. Remove `native` from projections and session envelope.
8. Add contract tests that reject provider-native fields in standard output.

## Phase 3 Inputs
Phase 3 should focus on source refs because every removal depends on traceability:
- Confirm every event source ref points to a known source.
- Confirm every projection can recover raw evidence through direct `source_refs` or `event_refs`.
- Decide whether projection records should keep direct `source_refs` once `event_refs` are complete.
- Add shared validators before deleting `native`.

## Open Checks
- Whether Claude hook progress should remain `tool.progress` or become a lower-priority `metric`.
- Whether Copilot prompt-composition counters deserve dedicated usage fields or should stay as metrics.
- Whether Codex `parsed_cmd` should be represented as `command` on the event or only inside `execution` on the tool invocation projection.
