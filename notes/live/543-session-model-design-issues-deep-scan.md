# Session.Model Design Issues — Deep Scan

Original deep scan of the experimental Session.Model export surface for
design-level issues in the canonical/native boundary, field consistency,
status vocabularies, and cross-provider uniformity.

Date: 2026-04-23
Refresh: 2026-04-25

Current implementation files:
- `src/agentos/chatlas/experimental/_codex.py`
- `src/agentos/chatlas/experimental/_copilot.py`
- `src/agentos/chatlas/experimental/_claude.py`
- `src/agentos/chatlas/experimental/_shared.py`
- `src/agentos/chatlas/experimental/_transcript.py`

Note: the original scan referenced the old monolithic path
`src/agentos/chatlas/experimental.py`. The detailed issue bodies below are
preserved as historical analysis, but their path/line references are stale.

## Refresh Summary (2026-04-25)

### Fixed in the current working tree
- A1, A2, A5, A6, A7: provider-specific model_run, event, and tool metadata
  moved under `native`.
- B1, B2: status vocabularies normalized (`running` for in-progress model runs;
  Codex tool status mapped to a closed canonical set).
- C3: reasoning trace entries now use canonical `content`.
- D1: Codex text blocks now preserve input/output origin.
- D2, D3, D4: canonical content blocks now cover tool calls/results and images;
  Copilot attachments no longer live only in `native`.
- E1, E2: Codex model-run message and reasoning attachment now works for
  multi-turn sessions by record span instead of single-run all-or-nothing
  heuristics.

### Corrected or narrowed claims
- A3 is narrower than originally written. `execution` is not Codex-only; Claude
  also emits it. The remaining concern is cross-provider `execution` shape
  divergence, not object existence.
- The original file path reference is stale because the implementation is now
  split by provider module.

### Still open after this fix pass
- A4: Copilot `model` remains canonical on tool_invocations while other
  providers do not emit it.
- B4: `source_refs` still use `record_index` for some providers and
  `event_index` for others.
- B5/C5: `provider` remains repeated on nested records such as model_runs and
  usage.
- C1/C2: turn-level and token-level field availability still differs across
  providers.
- E3: `tool_invocation_ref` vs `tool_invocation_refs` plurality is still mixed.
- H1, H2, H3: export-local IDs, failure detail placement, and
  `arguments_format: "raw_string"` were not addressed in this pass.

### Not re-audited in this refresh
- B3, B6, C4, F1, F2, F3, G1, G2, G3.

### Verification
- `uv run --group dev python -m pytest tests/test_chatlas_commands.py`
- Result: `54 passed`

---

## A. Canonical/Native Boundary Violations

### A1. Codex model_run fields promoted to canonical
`_codex_apply_turn_context_fields` (~line 2904-2928) promotes directly onto
model_run: `cwd`, `approval_policy`, `sandbox_policy`, `current_date`,
`timezone`, `truncation_policy`, `realtime_active`, `collaboration_mode`,
`reasoning_effort`. These are Codex session configuration. Copilot has no
equivalent. Should be under `native`.

### A2. Codex `model_provider` on model_run
~line 2873-2877. From `session_meta`. Copilot doesn't emit this field.

### A3. Codex `execution` sub-object on tool_invocations
~line 3328-3333. Contains `exit_code`, `stdout`, `stderr`,
`aggregated_output`, `formatted_output`, `parsed_cmd`, `process_id`, `source`,
`command`, `cwd`, `duration`. Copilot tool invocations have no `execution`.
Some fields like `exit_code` and `command` might be universal, but
`parsed_cmd`, `process_id`, `aggregated_output`, `formatted_output` are
Codex-specific.

### A4. Copilot `model` on tool_invocations
~line 1116-1118. Codex tool invocations don't have `model`. If canonical, it
should be consistently present or absent.

### A5. Copilot `interaction_id` on tool_invocations, events, model_runs
Promoted to canonical on tool_invocations (~line 1125), events (~line 682),
model_runs (~line 1508). This is a Copilot-specific correlation concept. Codex
has no equivalent. Should be under `native`.

### A6. Codex `model_context_window` on model_runs
~line 2892-2894. From `task_started` event data. Copilot doesn't emit this.

### A7. Codex `duration_ms` on model_runs
~line 2897-2899. From `task_complete` event. Copilot has `started_at`/`ended_at`
but no explicit duration field.

---

## B. Inconsistent Field Naming/Structure

### B1. model_run status vocabularies diverge
- Codex: `"completed"`, `"started"`, `"unknown"`
- Copilot: `"completed"`, `"running"`, `"unknown"`
- `"started"` vs `"running"` describe the same state.

### B2. tool_invocation status is open-ended for Codex
- Codex: passes through raw `status` string from `exec_command_end` before
  falling back to `"completed"` or `"requested"`. Can emit arbitrary values.
- Copilot: closed set `"completed"`, `"failed"`, `"requested"`.
- Canonical field should have a closed vocabulary.

### B3. tool_invocation native structure completely different
- Codex: `response_call_present`, `response_output_present`, `exec_end_present`,
  `record_indices` with keys `function_call`, `function_call_output`,
  `exec_command_end`.
- Copilot: `request_present`, `execution_start_present`,
  `execution_complete_present`, `event_indices` with keys `tool_request`,
  `tool.execution_start`, `tool.execution_complete`, plus raw payloads.
- Native is expected to diverge, but the boolean naming convention
  (`response_call_present` vs `request_present`) could be more consistent.

### B4. source_refs use different position field names
- Codex: `{"source_ref_id": ..., "record_index": ..., "line": ...}`
- Copilot: `{"source_ref_id": ..., "event_index": ..., "line": ...}`
- `record_index` vs `event_index` for the same concept. Should use one
  canonical key (e.g. `position` or `record_index`).

### B5. model_run `provider` field is redundant
- Both Codex and Copilot set `provider` on each model_run.
- Provider is already on the top-level session. A session cannot mix providers.

### B6. event `type` prefix convention
- Codex: `"codex.<payload_type>"` e.g. `"codex.task_started"`
- Copilot: `"copilot-cli.<event_type>"` e.g. `"copilot-cli.assistant.message"`
- Consistent pattern but undocumented as part of Session.Model.

---

## C. Missing Canonical Fields Across Providers

### C1. Codex tool_invocation `turn_id` from exec_command_end only
- Codex: from `exec_command_end` payload only. Missing if no exec_end record.
- Copilot: from any of the three tool evidence events.
- Same canonical field, inconsistent availability.

### C2. Copilot model_runs have `output_tokens`; Codex doesn't
- Copilot aggregates `outputTokens` from assistant messages within turn span.
- Codex has no per-model-run token counting.
- Absence in Codex is implicit (field missing), not explicit.

### C3. Reasoning trace content field names differ
- Copilot visible: `text`. Codex visible: `content`.
- Copilot opaque: `opaque_content`. Codex: no opaque concept.
- Both: `encrypted_content`.
- Codex also has `summary` which Copilot doesn't.
- Canonical reasoning entry should use consistent field names per visibility.

### C4. Clean transcript fallback messages missing `visibility`
- Clean transcript messages don't set `visibility` at all (~line 4021-4035).
- Codex and Copilot normalizers always set it. Inconsistency.

### C5. Usage `provider` field same redundancy as B5
- Copilot usage records include `"provider": "copilot-cli"`.
- Redundant with session-level provider.

---

## D. Content Model Gaps

### D1. Codex content blocks lose type granularity
- Raw content items have types `input_text`, `output_text`, `text` — all
  collapsed to `{"type": "text"}` (~line 3513-3526).
- The `input_text` vs `output_text` distinction carries semantic meaning
  (user-authored vs model-generated) that is lost.

### D2. No content block type for tool_use or tool_result
- Claude Code has `tool_use` and `tool_result` content items.
- Content model only has `text` and `unknown`.
- Claude Code normalizer will need these or everything becomes `unknown`.

### D3. Copilot attachments in native only
- `attachments` and `supportedNativeDocumentMimeTypes` preserved under `native`
  (~line 892-898).
- If agents support file attachments, needs a canonical content block type.

### D4. No canonical content block for images
- Claude Code supports `image` type in content arrays.
- Currently would map to `unknown`.

---

## E. Cross-Reference Consistency

### E1. Codex message_refs are all-or-nothing
- `_codex_model_run_message_refs`: if `single_model_run`, attach ALL messages.
  If not, attach NONE.
- Copilot: message_refs determined by event index ranges and parent chains.
- Codex approach is a heuristic shortcut that breaks for multi-turn sessions.

### E2. Codex reasoning_trace attachment is all-or-nothing
- Reasoning trace only attaches if `single_model_run` is True (~line 2969).
- Multiple model runs: reasoning floats unattached, only a warning emitted.
- Copilot attaches reasoning per-turn by event index ranges.

### E3. `tool_invocation_refs` (plural) vs `tool_invocation_ref` (singular)
- model_runs use `tool_invocation_refs` (plural, list of IDs).
- events use `tool_invocation_ref` (singular, single ID).
- Inconsistent plurality for the same cross-reference concept.

---

## F. Timestamp/Ordering Issues

### F1. Timestamp format not validated or normalized
- `_string_or_none` is used for timestamps — only checks non-empty string.
- No normalization to ISO 8601. Codex and Copilot could use different formats.
- Consumers cannot reliably sort across providers.

### F2. Event ordering relies on array position, not explicit sequence
- Events ordered by position in raw file. No explicit `sequence` field.
- Ordering is correct but implicit. Breaks if records are filtered or reordered.

### F3. Tool `started_at` fallback order differs between providers
- Codex: tries call_record -> exec_end -> output.
- Copilot: tries start -> request -> complete.
- Different preference order for the same concept.

---

## G. Status/Enum Value Issues

### G1. `visibility` values not documented as closed set
- Used values: `"conversation"`, `"context"`, `"unknown"`.
- Clean transcript fallback doesn't set visibility at all.
- No documentation of what each value means.

### G2. `coverage.status` values are ad-hoc
- Generic: `"normalized"`, `"missing"` (from `_coverage_status`).
- Codex-specific: `"event_only"`, `"no_raw_evidence"` (hardcoded).
- Not a documented enum.

### G3. Reasoning `visibility` values inconsistent across providers
- Codex: `"encrypted"`, `"visible"`, `"unknown"`.
- Copilot: `"visible"`, `"opaque"`, `"encrypted"`.
- Union is 4 values. No provider emits all of them.

---

## H. Additional Observations

### H1. IDs are export-local, not stable
- `message-N`, `tool-invocation-N`, `event-N`, `model-run-N`, `usage-N`,
  `reasoning-M-N` are all sequential per export run.
- Not stable across re-exports of the same session if normalization changes.

### H2. Tool failure detail in different canonical locations
- Copilot: `output.error` (~line 1262).
- Codex: `execution.stderr` and `execution.exit_code`.
- Two different canonical locations for the same concept.

### H3. Codex `input.arguments_format` is ad-hoc
- When JSON parsing fails, Codex adds `arguments_format: "raw_string"`
  (~line 3411).
- Copilot never does this. Provider-specific recovery path exposed as canonical.

---

## Current Status Snapshot

### Fixed
- A1, A2, A5, A6, A7
- B1, B2
- C3
- D1, D2, D3, D4
- E1, E2

### Open
- A4
- B4, B5/C5
- C1, C2
- E3
- H1, H2, H3

### Narrowed
- A3

### Not re-audited in this refresh
- B3, B6
- C4
- F1, F2, F3
- G1, G2, G3

---

## Related

- Session.Model concept: `notes/index/006-Session.Model.md`
- Implementation analysis: `notes/live/542-session-model-implementation-analysis.md`
- Architecture: `notes/live/534-chatlas-standard-chat-model.md`
- Standards research: `notes/live/540-agent-session-model-standards-research.md`
