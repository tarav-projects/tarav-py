# Session.Model Implementation Analysis

Analysis of `src/agentos/chatlas/experimental.py` (4,313 lines) against the
Session.Model concept defined in `notes/index/006-Session.Model.md`.

Date: 2026-04-23

---

## Adapter Maturity

| Provider | Loader | Messages | Tools | Events | Model Runs | Reasoning | Usage |
|----------|--------|----------|-------|--------|------------|-----------|-------|
| Codex | Complete | Yes | Yes (by `call_id`) | Yes | Yes (turn_context + inferred) | Yes | Deferred |
| Copilot CLI | Complete | Yes | Yes (by `toolCallId`) | Yes | Yes (turn_start/end) | Yes (visible/opaque/encrypted) | Yes (modelMetrics) |
| Claude Code | Loader only | No | No | No | No | No | No |

Claude Code has the raw loader (`_ClaudeRawRecord`, `_ClaudeRawSession`) and raw
counts analysis but returns empty lists for all normalization surfaces.

---

## Strengths

### Provenance
Every normalized record links back to raw source via `source_refs` with line
numbers. Rare and valuable for audit and debugging.

### Native extension discipline
Provider-specific data is consistently bounded under `native`, never leaking
into canonical fields without justification.

### Honesty about gaps
`unsupported_concepts`, `deferred_concepts`, and per-surface `coverage` metadata
tell consumers exactly what the normalizer could not do and why.

### Tool invocation joining
Both Codex (function_call -> function_call_output -> exec_command_end) and
Copilot (toolRequest -> execution_start -> execution_complete) correctly join
multi-record tool lifecycles by call ID.

### Rich normalization metadata
Raw counts vs. normalized counts, coverage status per surface, warnings. Useful
for trust and debugging.

---

## Issues and Improvement Opportunities

### 1. Single-file monolith

4,300 lines in one file with 3 provider normalizers, all raw loaders, and all
helpers. Providers share zero normalization code beyond tiny utilities.

**Suggestion:** Split into a package:

```
chatlas/experimental/
  __init__.py          # re-export chatlas_experimental_export_session_model
  _model.py            # _ExperimentalNormalizationResult, envelope builder
  _codex.py            # Codex loader + normalizer
  _copilot.py          # Copilot loader + normalizer
  _claude.py           # Claude Code loader + normalizer
  _shared.py           # _string_or_none, _dedupe_dicts, source_ref helpers
  _transcript.py       # clean transcript fallback
```

### 2. Claude Code normalizer is empty (biggest functional gap)

The raw loader parses `uuid`, `parentUuid`, `message`, `data`, `toolUseResult`.
Raw counts detect visible messages, tool_use, tool_result, thinking blocks,
usage payloads, and distinct request IDs. But no normalized output is produced.

Claude Code's JSONL has `message.role`, `message.content[]` (with type
text/tool_use/tool_result/thinking), `message.usage`, and request-scoped
grouping. The raw record already has all the fields needed.

**This is the most impactful next step** — implementing the Claude Code
normalizer validates Session.Model across 3 providers.

### 3. No typed output schema

The entire normalized output is `dict[str, object]`. No dataclasses or
TypedDicts for the output model — only for raw input records.

Consequences:
- No IDE autocompletion or type checking for consumers.
- The "schema" is implicit in the code that constructs dicts.
- Fields can be silently misspelled or omitted.

**Suggestion:** Define typed dataclasses for canonical output surfaces:
`SessionModelMessage`, `SessionModelToolInvocation`, `SessionModelRun`,
`SessionModelEvent`, `SessionModelUsage`. Keep `native` as `dict[str, object]`.

### 4. Codex-specific fields leak into model_run canonical surface

In `_codex_apply_turn_context_fields`, fields like `cwd`, `approval_policy`,
`sandbox_policy`, `truncation_policy`, `realtime_active`, `collaboration_mode`
are promoted directly onto the model_run dict. These are not provider-neutral
concepts that Copilot or Claude Code share.

**Suggestion:** Move under `model_run["native"]` or introduce a bounded
`session_context` sub-object, unless these are canonicalized as universal.

### 5. Repetitive normalization metadata/coverage code

Three nearly identical metadata functions and three nearly identical coverage
functions. Same pattern, only raw count field names differ.

**Suggestion:** Extract a shared metadata builder that takes a provider-specific
coverage function as a parameter.

### 6. Warning accumulation mixes progress and problems

Warnings mix operational progress ("codex raw rollout parsed: 42 records") with
actual issues ("codex message record 5 has no role"). Different audiences.

**Suggestion:** Separate `warnings` (issues) from `info` (operational status).
Or add a severity/category field.

### 7. Visibility field inconsistency

- Codex: heuristic prefix matching (`_CODEX_CONTEXT_MESSAGE_PREFIXES`).
- Copilot: structural (event type `system.message` -> context).
- Claude Code: will need a third approach.

The Codex heuristic is fragile — a user message starting with `<INSTRUCTIONS>`
would be misclassified.

**Suggestion:** Document as known limitation. Consider
`visibility_confidence` or `visibility_source` in `native`.

### 8. Missing content types beyond text

Content blocks support `text` and `unknown`. Agents produce images, file
references, code blocks with language annotations — all collapse into either
`text` or `unknown`.

**Suggestion:** Add `image`, `file`, and `code` content block types to the
canonical model as they appear in real sessions.

### 9. No session-level context metadata

The `session` payload captures identity (URI, provider, timestamps) but nothing
about project context — working directory, git state, project name, system
prompt summary. These are universal concepts across coding agents.

Some of this exists in Codex's `session_meta` but stays under `model_run.native`.

**Suggestion:** Add a `session.context` surface for session-scoped configuration
(cwd, project, agent version, system prompt hash).

### 10. No explicit ordering/sequencing

Messages use `message_id: "message-N"` which implies order, but there is no
explicit `sequence` field. Consumers must rely on array index or parse the ID.

**Suggestion:** Add `sequence: int` to messages, tool invocations, and events
for unambiguous ordering even after filtering or reordering.

---

## Priority Recommendations

1. **Implement Claude Code normalizer** — biggest impact, validates Session.Model
   across 3 providers. Raw loader and counts already exist.
2. **Define typed output schema** — formalize Session.Model as dataclasses. Turns
   an implicit convention into a real contract.
3. **Split into package** — natural refactor, each provider is independent. Makes
   the codebase maintainable as more providers arrive.
4. **Move Codex-specific model_run fields to native** — keeps canonical surface clean.
5. **Add session context surface** — captures universal session metadata.

---

## Related

- Session.Model concept: `notes/index/006-Session.Model.md`
- Architecture: `notes/live/534-chatlas-standard-chat-model.md`
- Implementation plan: `notes/live/538-chatlas-provider-normalizers-plan.md`
- Standards research: `notes/live/540-agent-session-model-standards-research.md`
- Implementation: `src/agentos/chatlas/experimental.py`
