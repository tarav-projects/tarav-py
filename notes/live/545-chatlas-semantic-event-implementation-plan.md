# Chatlas Semantic Event Implementation Plan

## Goal
- Move `agentos chatlas experimental export <session-id>` from provider-shaped event rows with canonical annotations to true semantic canonical events.
- Make `events[]` the source of truth for the experimental standard model.
- Rebuild transcript, run, tool, reasoning, and usage views from semantic events rather than from separate provider-specific extraction paths.

## Current State
- `notes/live/534-chatlas-standard-chat-model.md` defines the provider normalization boundary:

```text
provider raw artifacts
  -> provider normalizer
  -> session.std.model
  -> common Chatlas services
```

- `notes/live/544-chatlas-event-first-standard-model.md` defines the event-first contract.
- The experimental exporters currently add canonical fields to existing provider-shaped events:
  - `kind`
  - `producer`
  - `surfaces`
  - `interaction_ref`
  - `payload`
  - `outcome`
- That is useful as a bridge, but it is not the final shape because:
  - one raw record may contain several semantic facts
  - several raw records may contribute to one semantic fact
  - `payload` still often mirrors provider-shaped `data`
  - transitional `type`, `data`, and `native` still exist on event records

## Target State
- Provider normalizers emit a canonical semantic event tape.
- Each event represents one provider-neutral fact:
  - visible message
  - hidden context
  - reasoning
  - tool call
  - tool progress
  - tool result
  - model run start/end
  - session lifecycle/update
  - usage
  - metric
- Current projection arrays become views over the event tape:
  - `chat.messages`
  - `chat.model_runs`
  - `chat.tool_invocations`
  - `chat.reasoning_traces`
  - `chat.usage`
- `source_refs` preserves raw traceability. Canonical events should not embed provider-native residue.

## Reference Sessions
- Claude Code: `5dbf4437-633e-4039-a627-0459d85e9ecc`
- Copilot CLI: `d1d3f48b-4b29-4dfc-b551-5536b9677225`
- Codex: `019db5fd-7a73-7ae1-b5eb-901e62258dcb`
- Raw samples live under `dev/session-samples/`.

## Implementation Phases

### Phase 1: Shared Semantic Event Builder
Status: done in experimental code.

- Add shared helpers that create canonical events with one consistent shape.
- Centralize:
  - event id and sequence assignment
  - source reference normalization
  - producer construction
  - surfaces construction
  - outcome normalization
  - payload validation conventions
- Keep the first implementation private to `chatlas.experimental`.
- Do not change the CLI contract yet.

Acceptance:
- All provider normalizers can construct events without repeating event-shape boilerplate.
- Unit tests can assert event shape through a small shared expectation helper.

Implementation notes:
- Added a shared `_SemanticEventBuilder` under `src/agentos/chatlas/experimental/_shared.py`.
- Migrated Claude, Copilot, and Codex event loops to use the builder.
- Kept transitional `type`, `data`, and `native` fields for compatibility until Phase 6.
- The builder now guarantees the required canonical event fields, including an always-present `source_refs` list.

### Phase 2: Projection Builders Over Events
Status: done for shared helpers and the Copilot provider path.

- Add shared projection builders that derive current view arrays from events:
  - messages from `kind: "message"` and `surfaces.transcript == "visible"`
  - model runs from `run.start` / `run.end` and `model_run_ref`
  - tool invocations from `tool.call` / `tool.progress` / `tool.result` and `tool_invocation_ref`
  - reasoning traces from `kind: "reasoning"`
  - usage from `kind: "usage"`
- Keep provider-specific fallbacks only where semantic events are not yet complete.

Acceptance:
- Existing export shape is preserved at the envelope level.
- Projection outputs are generated from semantic events for at least one provider before expanding to all three.

Implementation notes:
- Added shared projection primitives under `src/agentos/chatlas/experimental/_shared.py`.
- Copilot now builds `messages`, `tool_invocations`, `model_runs`, and `usage` after `events[]`, using canonical events as the source input.
- Current Copilot projection intentionally preserves the existing experimental output shape; stricter transcript-only message policy should land after semantic splitting is complete.
- Real Copilot reference export matched pre-Phase-2 `messages`, `tool_invocations`, `model_runs`, `usage`, and `events` exactly.

### Phase 3: Claude Semantic Events First
- Convert Claude first because its raw records clearly expose mixed semantic content blocks.
- Split each Claude record into zero or more semantic events:
  - visible user text -> `message`
  - visible assistant text -> `message`
  - thinking block -> `reasoning`
  - tool use block -> `tool.call`
  - tool result block -> `tool.result`
  - progress hooks -> `tool.progress`
  - message usage -> `usage`
  - turn duration -> `metric`
- Preserve request-scoped model run semantics with `model_run_ref`.
- Keep `interaction_ref` assigned from the visible user request and propagated through tool/result/run events.

Acceptance:
- Claude reference export has no provider-shaped event records in `chat.events`.
- Claude projections can be rebuilt from events and match or improve current counts and content quality.
- Claude usage appears as `usage` events, not only as a side projection.

Implementation notes:
- Claude now emits semantic event units from raw records:
  - visible content -> `message`
  - thinking blocks -> `reasoning`
  - tool use blocks -> `tool.call`
  - tool result blocks -> `tool.result`
  - hook progress records -> `tool.progress`
  - `message.usage` payloads -> `usage`
- Claude `messages`, reasoning traces, and usage are now projected from canonical events.
- Claude `tool_invocations` and `model_runs` still use raw-backed grouping for request/tool correlation, then attach refs back onto events.
- `raw_canonical_candidate_count` for Claude now counts semantic evidence, so mixed records can legitimately produce more events than raw JSONL rows.
- Transitional `type` and `native` remain on Claude events for compatibility and span reconstruction; provider-shaped `data` is no longer emitted for Claude semantic events.

### Phase 4: Copilot Semantic Events
- Split Copilot records into semantic events:
  - `system.message` -> `context`
  - `user.message` -> `message`
  - assistant visible text -> `message`
  - assistant tool requests -> `tool.call`
  - reasoning text, opaque reasoning, and encrypted content -> `reasoning`
  - tool execution start/complete -> `tool.progress` / `tool.result`
  - assistant turn start/end -> `run.start` / `run.end`
  - shutdown metrics -> `usage`
- Use explicit surface states for opaque/encrypted reasoning.

Acceptance:
- Copilot mixed assistant records split into independent canonical events.
- Tool calls and tool results link through stable `tool_invocation_ref`.
- Session-level usage keeps honest scope.

### Phase 5: Codex Semantic Events
- Lift Codex evidence beyond current `event_msg` rows.
- Normalize:
  - developer/system/environment input -> `context`
  - user prompt -> `message`
  - assistant response text -> `message`
  - response reasoning items -> `reasoning`
  - function calls -> `tool.call`
  - function call outputs and exec completions -> `tool.result`
  - task started/completed -> `run.start` / `run.end`
  - token count records -> `metric` until reliable usage scope is available
- Avoid double-counting tool results when both function-call output and exec completion represent the same result.

Acceptance:
- Codex export represents response items that are currently missing from canonical events.
- Tool calls and outputs are linked, not just listed as terminal execution rows.
- Provider-expanded context is modeled as context, not user-authored transcript text.

### Phase 6: Remove Transitional Event Fields
- Once all three providers emit semantic events and projections are event-derived, remove transitional fields from `chat.events`:
  - `type`
  - `data`
  - `native`
- Keep raw access through `source_refs`.
- If a provider-specific detail has real canonical value, promote it into a provider-neutral payload field. Otherwise leave it in raw artifacts.

Acceptance:
- Canonical events match the contract in `544`.
- Normal export consumers no longer need provider event-row branches.
- Debug/raw export paths can still reach original raw artifacts.

### Phase 7: Regression Harness And Quality Report
- Add focused tests for each reference provider session.
- Add checks that:
  - every event has required canonical fields
  - sequence is stable and contiguous
  - every projection item links back to event ids or refs where applicable
  - every important raw semantic artifact is represented or explicitly reported unsupported
- Produce a small quality report for the three reference sessions after conversion.

Acceptance:
- `uv run python -m pytest tests/test_chatlas_commands.py -q` passes.
- `agentos chatlas experimental export <reference-session> --format json` passes for Claude, Copilot, and Codex.
- The report states remaining gaps rather than hiding them.

## Provider Order
1. Claude Code
2. Copilot CLI
3. Codex

Rationale:
- Claude gives the clearest pressure test for raw-record splitting.
- Copilot exercises opaque/encrypted reasoning and session-level usage.
- Codex exercises semantic lifting from response items and tool execution correlation.

## Non-Goals For This Pass
- Persist the standard model to the production Chatlas dataset.
- Change stable non-experimental CLI surfaces.
- Remove raw artifacts.
- Model full TUI layout state.
- Allocate aggregate usage to model runs when provider evidence does not support that allocation.

## Open Design Checks
- Exact payload shapes for `context`, `reasoning`, `tool.call`, `tool.result`, `usage`, and `metric`.
- Whether `event_id` should remain local sequence ids or become content-stable ids.
- Whether projection arrays should include full derived objects or only refs plus summary fields.
- How much unsupported evidence should be represented as `metric`, `session.update`, or normalization warnings.

## Immediate Next Step
- Start Phase 3 by splitting Claude raw records into true semantic events.
