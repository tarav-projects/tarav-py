# Chatlas Export Views - impl-req

## Impl-Req State

Implemented in code; export views now project filtered standard session models from `agentos chatlas export` without introducing a second export model.

## User Intent

`agentos chatlas export` currently emits the full normalized standard session model. That is useful, but verbose for callers that only need a smaller surface such as visible messages, user requests, replay, or the canonical event tape.

The user wants minimal processing built into export so callers do not each need to post-process the full model. The accepted principle is:

```text
session.std.model is the source
export views are projections
raw provider data is not parsed by view code
export views are filtered standard models, not new models
```

## Why This Exists

Chatlas should remain simple:

```text
raw provider artifacts -> provider normalizer -> session.std.model -> export views
```

Without export views, every downstream caller has to understand the full standard model and reimplement the same filtering rules. With views, callers can ask for common projections while still consuming the same standard-model envelope and vocabulary.

The important boundary is that views are not new domain models. They are filtered standard models.

## Current Situation

- `agentos chatlas export <query>` emits the full `agentos.chatlas.session_model`.
- The session model contains `session`, `agent_instance`, `sources`, `chat`, and `normalization`.
- `chat.events[]` is the canonical semantic tape.
- `chat.messages`, `chat.model_runs`, `chat.tool_invocations`, and `chat.usage` are standard projections.
- Raw artifacts remain available separately through `agentos chatlas raw path` and `agentos chatlas raw export`.
- The durable design rule now lives in `notes/index/007-Chatlas.Standard.Model.Contract.md`.

## Requested Change

Add `--view` to `agentos chatlas export`:

```text
agentos chatlas export <query> --view full
agentos chatlas export <query> --view transcript
agentos chatlas export <query> --view user
agentos chatlas export <query> --view replay
agentos chatlas export <query> --view events
```

`full` should be the default and should preserve the current output shape.

MVP views:

```text
full        full current session model
transcript  visible user/assistant messages only
user        visible user-authored messages only
replay      visible messages + tool calls, but not full tool results
events      canonical event tape only, with session identity/header
```

All views must return a standard session model envelope:

```json
{
  "class": "agentos.chatlas.session_model",
  "schema_version": 1,
  "view": "transcript",
  "session": {},
  "agent_instance": {},
  "sources": [],
  "chat": {},
  "normalization": {}
}
```

Do not create a separate `agentos.chatlas.export_view` class.

## View Semantics

### `full`

- Return the current full standard session model.
- Include `view: "full"` only if this does not cause unnecessary churn in current tests/consumers; otherwise leave `full` exactly unchanged and add `view` only to filtered views.

### `transcript`

- Keep visible conversation messages.
- Include user and assistant messages.
- Exclude hidden context, reasoning, metrics, tool calls, and tool results.
- Prefer deriving from `chat.events[]` with `kind: message` and `surfaces.transcript: visible`; using existing `chat.messages` is acceptable if it is already a standard projection over events and preserves refs.

### `user`

- Keep visible user-authored messages only.
- Useful for extracting task/request history.
- Exclude assistant, tools, reasoning, hidden context, and provider-expanded prompt/context.

### `replay`

- Keep visible messages plus lightweight tool-call records.
- Include enough tool-call data to understand what was invoked: name, input/arguments when already standardized, event/tool refs, timestamp/outcome when available.
- Exclude full tool result payloads by default.
- Do not parse raw command output text to synthesize summaries.

### `events`

- Keep session/header/source metadata plus canonical `chat.events`.
- Drop or empty derived projections such as `messages`, `model_runs`, `tool_invocations`, and `usage`, unless keeping them is necessary for schema consistency.
- Preserve enough `sources` for existing `source_refs` to remain resolvable.

## Constraints And Invariants

- Views must be derived from the standard model, not provider raw artifacts.
- Views must keep the `agentos.chatlas.session_model` envelope and standard vocabulary.
- Views may omit sections, omit records, or filter arrays.
- Views must not introduce a parallel export-view schema.
- Views must not parse provider-native raw artifacts directly.
- Raw data remains available through `source_refs`, `raw path`, and `raw export`.
- `full` must remain the default export behavior.
- Keep `--format json` as the only format for this change.
- Do not reintroduce transcript or summary materialization.
- Do not persist view outputs.
- Do not add backward-compatibility aliases or legacy command paths.

## Out Of Scope

- Text, Markdown, or JSONL export formats.
- Persisted derived transcript/summary files.
- LLM-generated summaries.
- Raw-provider parsing inside view builders.
- Complex replay summarization or command-output summarization.
- UI work.

## Acceptance Signals

- `agentos chatlas export <query>` still emits the full standard model by default.
- `agentos chatlas export <query> --view full` emits the full standard model.
- `--view transcript` emits a standard-model envelope containing only visible user/assistant transcript messages.
- `--view user` emits a standard-model envelope containing only visible user-authored messages.
- `--view replay` emits a standard-model envelope with visible messages and lightweight tool-call records, excluding full tool results.
- `--view events` emits a standard-model envelope centered on `chat.events`.
- Filtered views do not expose a new top-level class.
- View builders do not read or parse raw artifacts.
- Existing reference sessions remain usable:
  - Claude Code: `5dbf4437-633e-4039-a627-0459d85e9ecc`
  - Copilot: `d1d3f48b-4b29-4dfc-b551-5536b9677225`
  - Codex: `019db5fd-7a73-7ae1-b5eb-901e62258dcb`

## Suggested Implementation Phases

1. **Add export view option**
   - Add `--view {full,transcript,user,replay,events}` to `agentos chatlas export`.
   - Default to `full`.
   - Keep `--format json`.

2. **Add view projection helpers**
   - Build helpers in `src/agentos/chatlas/session_model/`.
   - Accept a fully built standard session model and return a filtered standard session model.
   - Do not call raw loaders or provider normalizers from view helpers.

3. **Implement `transcript` and `user`**
   - Filter visible message records/events.
   - Preserve relevant `session`, `agent_instance`, `sources`, and `normalization`.
   - Keep source/event refs valid where present.

4. **Implement `events`**
   - Preserve canonical events and required header/source metadata.
   - Empty or omit derived projections according to the least surprising current model shape.

5. **Implement `replay`**
   - Include visible messages plus lightweight tool-call records/events.
   - Exclude full tool result payloads.
   - Keep implementation conservative; no raw text parsing or generated summaries.

6. **Verification and docs**
   - Add focused command tests for each view.
   - Test at least one reference session per provider where practical.
   - Refresh installed CLI with `uv tool install --reinstall --editable .`.
   - Update this impl-req end log after implementation.

## Relevant Files Or Surfaces

- `src/agentos/chatlas/commands.py`
- `src/agentos/chatlas/session_model/`
- `tests/test_chatlas_commands.py`
- `tests/test_chatlas_session_hashes.py`
- `notes/index/007-Chatlas.Standard.Model.Contract.md`
- `notes/live/553-chatlas-session-hashes-sharded-index-impl-req.md`
- `dev/session-samples/`

## Open Questions

- Should filtered views include `view: "<name>"` at the top level, or should view identity live only in `normalization`/metadata to keep the envelope smaller?
- For filtered views, should empty projection arrays be present for schema regularity, or omitted for compactness?

## Related Impl-Reqs

- `notes/live/553-chatlas-session-hashes-sharded-index-impl-req.md`

## End Log

- 2026-05-01: Created after the user accepted MVP export views: `full`, `transcript`, `user`, `replay`, and `events`, with the invariant that views are filtered standard models rather than new models.
- 2026-05-01: Implemented `agentos chatlas export --view {full,transcript,user,replay,events}` with `full` as the default. View projections live in `src/agentos/chatlas/session_model/_views.py` and are derived from the built standard session model rather than provider raw artifacts. Focused tests cover default export and explicit `--view full`, Codex `transcript`/`user`/`events`, Claude `replay`, and Copilot `transcript`. Installed CLI refreshed with `uv tool install --reinstall --editable .`.
