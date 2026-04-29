# Chatlas Standard Model Contract

## Purpose
- Define the current target contract for `agentos.chatlas.experimental.session_model`.
- Make the standard model provider-neutral end to end.
- Keep provider-native data in raw artifacts, reachable through `source_refs`.
- Give later code changes a concrete contract to implement and test against.

## Status
- Contract status: experimental.
- Schema version: `1`.
- This contract describes the target standard-model shape for the current experimental work.
- The current exporter already conforms for `chat.events[]` on the main provider-neutral boundary.
- Current projection arrays still expose some `native` fields; those are contract deviations to remove in the provider-neutral cleanup plan.

## Core Rule

```text
standard model = provider-neutral facts
raw artifacts = provider-native truth
source_refs = bridge between them
```

The standard model must not embed provider-native blobs just because the normalizer has access to them. If a consumer needs provider-native details, it should resolve `source_refs` against the preserved raw artifact.

## Envelope
Required top-level fields:
- `class`: must be `agentos.chatlas.experimental.session_model`
- `schema_version`: integer, currently `1`
- `experimental`: boolean, currently `true`
- `session`: provider-neutral session identity
- `agent_instance`: provider and configured instance identity
- `sources`: raw source descriptors
- `chat`: event tape plus export-time projection views
- `normalization`: normalizer metadata, coverage, warnings, and explicit gaps

Top-level fields must not include raw provider records.

## Session
`session` identifies the conversation in provider-neutral Chatlas terms.

Allowed fields:
- `uri`
- `provider`
- `instance`
- `provider_instance_fingerprint`
- `session_id`
- `display_name`
- `display_name_field`
- `created_at`
- `updated_at`

Current deviation:
- Existing Chatlas session rows may carry `native`. This belongs to the existing dataset layer, not to the long-term standard session model. The standard contract should not require or depend on it.

## Agent Instance
`agent_instance` identifies the configured provider instance that produced the session.

Allowed fields:
- `provider_family`
- `instance`
- `provider_instance_fingerprint`

This is canonical identity metadata, not raw provider payload.

## Sources
`sources[]` describes raw artifacts retained by Chatlas.

Required fields:
- `source_ref_id`

Allowed fields:
- `role`
- `storage_kind`
- `path`
- `locator`
- `extractable`

Rules:
- `source_ref_id` is the stable id referenced by `source_refs`.
- A source descriptor may identify a raw JSONL file, transcript artifact, or other retained source.
- A source descriptor does not inline full raw artifact contents.

## Source Refs
`source_refs[]` connects a standard record to raw evidence.

Required field:
- `source_ref_id`

Allowed locator fields:
- `line`
- `record_index`
- `event_index`
- `content_index`
- `request_index`

Rules:
- `source_ref_id` must refer to one entry in `sources[]`.
- Line-oriented raw artifacts should include `line` when available.
- Provider records should include `record_index` or `event_index` when available.
- Nested provider evidence should use `content_index` or `request_index` when needed.
- Source refs should identify evidence precisely enough that a debug resolver can recover the native payload.

## Chat
`chat` contains:
- `events`: canonical semantic event tape
- `messages`: transcript projection
- `model_runs`: execution-unit projection
- `tool_invocations`: tool lifecycle projection
- `usage`: usage projection

Current export note:
- Projections are included in the experimental export for inspection.
- Long-term storage should converge toward storing `session`, `sources`, `events`, and `normalization`, then deriving projections from events.

## Events
`chat.events[]` is the canonical ledger and source of truth.

Required fields on every event:
- `event_id`
- `sequence`
- `kind`
- `producer`
- `surfaces`
- `interaction_ref`
- `payload`
- `source_refs`

Allowed optional fields:
- `timestamp`
- `outcome`
- `model_run_ref`
- `tool_invocation_ref`
- `call_id`
- `turn_id`
- `request_id`
- `message_id`

Fields not allowed:
- `type`
- `data`
- `native`
- raw provider transport envelopes
- raw provider parent ids
- raw provider event ids

Current deviations to audit:
- Some events may still carry provider-shaped correlation helpers such as `parent_uuid`, `content_index`, or `request_index` as top-level fields. These should be promoted only if neutral, otherwise moved into `source_refs` or removed.

### Event Ids And Sequence
- `event_id` is currently local to the export and sequence-based: `event-1`, `event-2`, etc.
- `sequence` must be contiguous and 1-based.
- Event ids must be unique within one session model.
- Content-stable event ids are deferred until storage direction is decided.

### Producer
`producer` answers who generated the event in canonical terms.

Required field:
- `type`

Allowed `type` values:
- `user`
- `assistant`
- `tool`
- `system`
- `provider`

Allowed optional field:
- `name`

Provider transport roles should be mapped into these canonical producer types.

### Surfaces
`surfaces` answers where the event belongs.

Required fields:
- `transcript`
- `replay`
- `debug`
- `model_input`

Allowed values:
- `visible`
- `hidden`
- `opaque`
- `encrypted`
- `unavailable`

Rules:
- `transcript` controls normal human transcript visibility.
- `replay` controls whether the event belongs in an agent replay.
- `debug` controls whether the event belongs in debug inspection.
- `model_input` controls whether the event represents content sent back into a model.
- Surfaces are not full TUI state.

### Outcomes
`outcome` should be used for completion/result semantics.

Allowed values:
- `ok`
- `error`
- `interrupted`
- `cancelled`

Rules:
- Tool failures are `kind: tool.result` with `outcome: error`.
- Do not create a separate canonical `tool.error` kind.

## Event Kinds And Payloads

### `message`
Represents visible or contextual message content.

Required payload fields:
- `role`
- `content`

Allowed payload fields:
- `visibility`
- `phase`
- `output_tokens`

Rules:
- `role` is provider-neutral, for example `user`, `assistant`, `system`, or `developer`.
- `content` is a list of content items.
- Normal transcript messages should have `surfaces.transcript: visible`.
- Provider-expanded prompt/context content should usually be `context`, not a user-authored transcript `message`.

### `context`
Represents hidden or contextual input that is significant but not user-authored transcript text.

Required payload fields:
- `context_type`

Allowed payload fields:
- `role`
- `content`
- `visibility`
- `cwd`
- `model`
- `current_date`
- `timezone`
- `approval_policy`
- `sandbox_policy`
- `reasoning_effort`
- `collaboration_mode`
- `truncation_policy`
- `realtime_active`
- `turn_id`

Rules:
- Context should preserve canonical meaning without copying full provider prompt envelopes.
- Large provider-specific prompt expansion should remain recoverable through `source_refs`.

### `reasoning`
Represents reasoning evidence exposed by the provider.

Required payload fields:
- `visibility`

Allowed payload fields:
- `content`
- `summary`
- `signature`

Rules:
- `visibility` should be one of `visible`, `opaque`, `encrypted`, or `unavailable`.
- Encrypted or opaque reasoning should not be decoded or invented.
- Provider-specific encrypted payload structure should remain in raw artifacts unless the encrypted blob itself is the canonical evidence.

### `tool.call`
Represents a tool request.

Required payload fields:
- `call_id`
- `tool_name`
- `input`

Rules:
- `call_id` links call/progress/result events.
- `tool_invocation_ref` links to the tool invocation projection when available.
- `input` should be a provider-neutral argument object when parseable, or a clear raw-string representation when not parseable.

### `tool.progress`
Represents tool lifecycle progress that is meaningful for replay/debug but is not the final result.

Required payload fields:
- `call_id`

Allowed payload fields:
- `tool_name`
- `phase`
- `input`
- `command`
- `cwd`
- `process_id`
- `duration`
- `exit_code`
- `stdout`
- `stderr`
- `aggregated_output`
- `formatted_output`
- `result_source`

Rules:
- Progress events may be transcript-hidden but replay/debug-visible.
- Avoid copying provider hook payloads unless promoted to neutral progress fields.

### `tool.result`
Represents the result of a tool call.

Required payload fields:
- `call_id`

Allowed payload fields:
- `content`
- `output`
- `execution`
- `is_error`
- `success`
- `result_source`
- `model`

Rules:
- Use `outcome` for result status.
- Tool errors are represented as `tool.result` with `outcome: error`.
- Avoid double-counting final result evidence when provider emits both model-visible output and execution-complete records.

### `run.start`
Represents the start of a model execution unit.

Allowed payload fields:
- `turn_id`
- `started_at`
- `model_context_window`
- `collaboration_mode_kind`

Rules:
- `model_run_ref` should identify the projected model run when available.
- A model run is provider execution truth, not necessarily one visible transcript turn.

### `run.end`
Represents the end of a model execution unit.

Allowed payload fields:
- `turn_id`
- `completed_at`
- `duration_ms`
- `last_agent_message`

Rules:
- `outcome` should describe completion state when known.
- `model_run_ref` should identify the projected model run when available.

### `usage`
Represents token, request, or billing evidence when scope is honest.

Required payload fields:
- `provider`
- `scope`

Allowed payload fields:
- `model`
- `model_run_ref`
- `request_id`
- `input_tokens`
- `output_tokens`
- `cache_read_tokens`
- `cache_write_tokens`
- `reasoning_tokens`
- `request_count`
- `provider_billing_units`

Rules:
- `scope` must be `model_run` or `session`.
- Do not allocate aggregate session usage to model runs without provider evidence.
- If usage evidence exists but scope is unclear, preserve it as `metric` and report `usage` as deferred.

### `metric`
Represents important evidence that is not yet a canonical first-class projection.

Allowed payload fields:
- `subtype`
- `duration_ms`
- `info`
- `rate_limits`
- `is_meta`

Rules:
- Metrics are acceptable for preserving evidence without overclaiming semantics.
- Codex token-count rows currently remain `metric` events until usage scope can be represented truthfully.

### `session.start`
Represents session start metadata.

Required payload fields:
- `session_id`

Allowed payload fields:
- `update_type`
- `producer`
- `source`
- `originator`
- `cli_version`
- `cwd`
- `model_provider`

### `session.update`
Represents session-level state changes.

Required payload fields:
- `update_type`

Allowed payload fields:
- `model`
- `new_model`

### `session.end`
Represents session shutdown/end evidence.

Allowed payload fields:
- `shutdown_type`
- `current_model`

## Content Items
Content items should be provider-neutral.

Common content item fields:
- `type`
- `text`
- `origin`

Allowed `type` values for now:
- `text`
- `unknown`

Rules:
- Text content should use `type: text`.
- Unknown structured content may use `type: unknown` with a small provider-neutral summary.
- Full native content payloads should stay in raw artifacts.

Current deviation:
- Some content items currently carry `native` for unknown/provider-specific content. Phase 4 should remove this from the standard model or move it behind a debug resolver.

## Projections
Projection arrays are views over `events[]`. They exist in experimental exports for analysis, but they should be rebuildable and deletable.

General projection rules:
- Projection records must use provider-neutral fields.
- Projection records should link back to events with `event_refs` when applicable.
- Projection records should be traceable to raw evidence through `event_refs` and/or `source_refs`.
- Projection records must not expose `native` in the target contract.

### Messages
Required fields:
- `message_id`
- `role`
- `visibility`
- `content`

Allowed fields:
- `timestamp`
- `source_refs`
- `event_refs`

Rules:
- `messages[]` is the transcript/context projection, not the full execution truth.
- Visible conversation messages should be reconstructible from `events[]` where `kind: message` and `surfaces.transcript: visible`.

### Model Runs
Required fields:
- `model_run_id`
- `provider`
- `status`

Allowed fields:
- `model`
- `turn_id`
- `request_id`
- `started_at`
- `ended_at`
- `output_tokens`
- `message_refs`
- `tool_invocation_refs`
- `event_refs`
- `source_refs`
- `reasoning_trace`

Rules:
- Model runs represent provider execution units.
- They are not transcript turns.
- Claude model runs are request-scoped.
- Copilot model runs are assistant-turn scoped.
- Codex model runs are rollout/model-execution scoped.

### Tool Invocations
Required fields:
- `tool_invocation_id`
- `call_id`
- `tool_name`
- `status`

Allowed fields:
- `started_at`
- `ended_at`
- `turn_id`
- `request_id`
- `message_id`
- `model`
- `input`
- `output`
- `execution`
- `event_refs`
- `source_refs`

Rules:
- Tool invocations summarize `tool.call`, `tool.progress`, and `tool.result` events.
- `status` should be provider-neutral, for example `requested`, `running`, `completed`, `failed`, `interrupted`, or `cancelled`.

### Reasoning Traces
Reasoning traces may be represented:
- inline on `model_runs[].reasoning_trace`
- later as a top-level projection if needed

Required fields per reasoning trace item:
- `reasoning_id`
- `visibility`

Allowed fields:
- `content`
- `timestamp`
- `source_refs`
- `event_refs`

Rules:
- Reasoning trace items must not expose provider-native encrypted or opaque envelopes.
- The original evidence remains reachable through `source_refs`.

### Usage
Required fields:
- `usage_id`
- `scope`
- `provider`

Allowed fields:
- `model`
- `model_run_ref`
- `input_tokens`
- `output_tokens`
- `cache_read_tokens`
- `cache_write_tokens`
- `reasoning_tokens`
- `request_count`
- `provider_billing_units`
- `timestamp`
- `source_refs`
- `event_refs`

Rules:
- Usage scope must be honest.
- Model-run scoped usage should link to `model_run_ref`.
- Session-scoped usage must not be forced onto model runs.

## Normalization
`normalization` reports how the standard model was built.

Required fields:
- `provider`
- `normalizer`
- `version`
- `source_mode`
- `warnings`
- `unsupported_concepts`

Allowed fields:
- `counts`
- `raw_counts`
- `coverage`
- `deferred_concepts`

Rules:
- `unsupported_concepts` should state concepts the model cannot currently provide.
- `deferred_concepts` should state concepts intentionally postponed because evidence or scope is insufficient.
- Coverage should distinguish missing raw evidence from deferred normalization.
- Warnings should explain lossy or partial normalization decisions.

## Known Current Deviations
- Projection records still expose `native`.
- Some unknown content items still expose `native`.
- Some event top-level fields may be provider correlation helpers rather than neutral canonical fields.
- Some projection construction still uses provider-specific grouping logic instead of shared event-only projection helpers.

These deviations are the implementation targets for `notes/live/546-chatlas-provider-neutral-standard-model-plan.md`.

## Contract Test Direction
Future contract tests should assert:
- no `native` anywhere in `chat.events[]` or projection records
- no `type` or `data` on events
- no raw provider event type fields on standard records
- every `source_ref_id` resolves to `sources[]`
- every `event_ref` resolves to `chat.events[]`
- every `model_run_ref` resolves to `chat.model_runs[]`
- every `tool_invocation_ref` resolves to `chat.tool_invocations[]`
- expected unsupported/deferred concepts are explicit
