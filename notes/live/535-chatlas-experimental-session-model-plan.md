# Chatlas Experimental Session Model Plan

## Goal
- Implement a read-only experimental export path for the future Chatlas standard session model.
- Use it to inspect real cross-provider outputs before committing to permanent normalized storage.
- Keep the experiment isolated under an `experimental` command namespace.

Target command:

```sh
agentos chatlas experimental export <query>
```

`<query>` uses normal Chatlas session resolution. A native session id is one valid query, but the command should also support URI, display name, fingerprint, and native-field matches through the same selection model as `chatlas export`.

## Accepted Direction
- The command is a read-only projection.
- It does not rewrite `normalized/`.
- It does not change existing `chatlas query`, `chatlas export`, summaries, or derived transcript behavior.
- It builds one experimental `Chatlas.Session.Model` JSON object for one resolved session.
- The first implementation should be useful for output inspection, not treated as a stable public schema.

## Progress Notes
- Phase 1 is implemented: `agentos chatlas experimental export <query>` exists and emits the experimental JSON envelope.
- Phase 4 clean transcript fallback is implemented: `chat.messages` is populated from existing clean extractor JSONL output.
- Current fallback source mode is `clean_transcript_fallback`.
- `model_runs`, `tool_invocations`, and `events` remain empty arrays with normalization warnings.
- The implementation remains read-only and does not change `normalized/` or `derived/` storage.
- Detailed Codex raw normalizer plan: `notes/live/536-chatlas-codex-normalizer-plan.md`.

## Architecture

```text
normalized session row
  + raw backing artifacts
  + provider normalizer
  -> experimental Chatlas.Session.Model JSON
```

The experiment should exercise the target long-term boundary:

```text
provider raw artifacts
  -> provider normalizer
  -> session.std.model
  -> common Chatlas services
```

For the MVP, the standard model is emitted on demand instead of materialized as a dataset artifact.

## Command Surface

### Initial Command

```sh
agentos chatlas experimental export <query>
```

Default output:
- JSON
- one session only
- pretty formatted through the existing JSON output helper

Suggested first options:
- `--provider <provider>`: same semantics as existing `chatlas export`
- `--format json`: only JSON for the MVP
- `--include-raw-fragments`: optional later, not in the first slice
- `--strict`: optional later, fail on normalization warnings instead of emitting them

### Namespace Rationale
- `experimental` keeps the unstable schema out of the stable `chatlas export --kind ...` contract.
- It lets us compare provider outputs before deciding storage layout.
- It makes it clear that downstream tools should not yet depend on the shape.

## MVP Output Shape

```jsonc
{
  "class": "agentos.chatlas.experimental.session_model",
  "schema_version": 1,
  "experimental": true,
  "session": {},
  "agent_instance": {},
  "sources": [],
  "chat": {
    "messages": [],
    "model_runs": [],
    "tool_invocations": [],
    "events": []
  },
  "normalization": {
    "provider": "codex",
    "normalizer": "codex.v1",
    "warnings": []
  }
}
```

## MVP Model Content

### `session`
- `uri`
- `provider`
- `instance`
- `provider_instance_fingerprint`
- `session_id`
- `display_name`
- `display_name_field`
- `created_at`
- `updated_at`
- `native`

This is mostly copied from the existing normalized session row.

### `agent_instance`
- `provider_family`
- `instance`
- `provider_instance_fingerprint`
- optional `instance_id` when available
- optional `label` when available
- optional `default_model` when available
- optional `anchors` or `homes` when available and safe to expose

This should reference the existing canonical `ProviderInstance` concepts instead of creating a second instance model. The experimental model should not copy every runtime setting into each session by default.

### `sources`
- `source_ref_id`
- `role`
- `storage_kind`
- `path`
- `locator`
- `extractable`

This is based on existing `backing_artifacts`, with stable ids added so messages and events can point back to source evidence.

### `chat.messages`
- `message_id`
- `role`
- `timestamp`
- `content`
- `source_refs`
- optional `native`

MVP content blocks:
- `text`
- `thinking`
- `tool_call`
- `tool_result`
- `image`
- `error`
- `unknown`

The first slice may only produce `text` blocks for providers where the current extractor exposes only clean transcript turns. The model should still reserve the richer block vocabulary from the start.

### `chat.model_runs`
- Keep as an empty array unless the provider normalizer can identify model-run boundaries.
- Do not invent model runs from weak evidence.
- Add warnings when the provider likely has model-run data that is not yet normalized.

### `chat.tool_invocations`
- Keep as an empty array unless tool call/result ids can be linked reliably.
- If a provider exposes tool calls only as serialized text in the current extractor, keep them as message content and emit a warning.

### `chat.events`
- Keep as an empty array for the first slice unless replay events are directly available.
- The field exists to keep the output shape aligned with the future replay model.

### `normalization`
- provider family
- normalizer id
- normalizer version
- source mode, such as `clean_transcript_fallback` or `provider_raw`
- warnings
- unsupported concepts

Warnings are part of the MVP. They make incomplete provider coverage visible without blocking inspection.

## Provider / Instance Integration

### Existing Concepts To Reuse
- `ProviderFamily`: canonical provider family identity.
- `ProviderInstance`: canonical configured instance identity.
- `provider_instance_fingerprint`: stable instance identity in session rows.
- `ChatSession`: logical cross-provider session identity.
- `BackingArtifact`: provider-native raw evidence for a session.

### Rule
- The experimental session model references provider and instance identity.
- Provider and instance configuration remain owned by the canonical agent/provider registry.
- Chat content normalizers consume provider/session/source data but should not become another instance registry.

### Practical MVP
- Build `agent_instance` from the normalized row first.
- If the resolved `ProviderInstance` is available during export, enrich `agent_instance` with safe summary fields.
- Do not block the MVP on perfect instance enrichment.

## Code Anchors
- CLI registration: `src/agentos/chatlas/commands.py`
- Stable Chatlas APIs: `src/agentos/chatlas/core.py`
- Raw mirroring/provider support: `src/agentos/chatlas/raw.py`
- Provider/instance model: `src/agentos/chat/providers.py`
- Session/backing artifact model: `src/agentos/chat/sessions.py`
- Existing extractor fallback: `src/agentos/chat/extractors/`
- Tests: `tests/test_chatlas_commands.py`

## Implementation Plan

### Phase 1. Add Experimental CLI Namespace
- Add `experimental` as a subparser under `agentos chatlas`.
- Add `experimental export <query>`.
- Keep supported format to `json` only.
- Reuse provider filtering from stable export.
- Route to a new internal API such as `chatlas_experimental_export_session_model(...)`.

### Phase 2. Add Experimental Core Module
- Add `src/agentos/chatlas/experimental.py`.
- Keep experimental model-building code out of the stable `core.py` path where possible.
- Reuse stable helpers from `core.py` for:
- resolving one normalized session
- loading Chatlas root
- selecting normalized sessions
- rendering JSON consistently

If current helper visibility makes reuse awkward, first extract small stable helper functions rather than duplicating query logic.

### Phase 3. Define The MVP Builder
- Build the top-level envelope.
- Copy `session` from the normalized session row.
- Build `sources` from backing artifacts.
- Build minimal `agent_instance`.
- Build `normalization` metadata.
- Emit empty `model_runs`, `tool_invocations`, and `events` arrays initially.

### Phase 4. Add Clean Transcript Fallback Normalizer
- Use current extractors as a fallback to produce `chat.messages` from clean transcript turns.
- Convert each turn into one message with one `text` content block.
- Attach coarse source refs back to the primary backing artifact.
- Mark normalization source mode as `clean_transcript_fallback`.
- Emit warnings that replay/tool/reasoning structure may be missing.

This gives immediate cross-provider output without pretending the result is complete.

### Phase 5. Add First Provider-Raw Normalizer
- Pick one provider with rich raw structure and good local fixtures.
- Candidate order:
- `pi`, because it already has typed content blocks in its raw session shape.
- `copilot-cli`, because raw events include tool execution and assistant/tool events.
- `codex`, because it is central to Agentos usage.
- Add provider-specific normalization behind a small dispatch table.
- Keep the provider normalizer internal to the experimental module at first unless it grows.

### Phase 6. Compare Outputs
- Run the command across several providers.
- Inspect:
- message ordering
- timestamp quality
- source refs
- reasoning representation
- tool-call/result linking
- instance/provider identity quality
- normalization warnings
- Update the schema before any storage materialization.

### Phase 7. Decide Storage Direction
- Only after inspecting real output, decide whether `session.std.model` should be materialized as:
- one JSON file per session
- one JSONL stream per session
- several linked normalized files such as messages/model_runs/events
- or generated only on demand for longer.

## First Change Set
- Add `agentos chatlas experimental export <query>`.
- Add `src/agentos/chatlas/experimental.py`.
- Emit the MVP envelope.
- Populate `session`, `agent_instance`, `sources`, `chat.messages`, and `normalization`.
- Use clean transcript fallback for messages.
- Add tests for:
- CLI registration
- exact query resolution
- JSON envelope shape
- source refs
- fallback text messages
- provider filter behavior

## Acceptance Criteria
- Existing `agentos chatlas` commands continue to behave unchanged.
- The new command returns valid JSON for one resolved session.
- The command errors clearly on no match or ambiguous match.
- Output includes session identity, provider/instance identity, source artifacts, messages, empty future arrays, and normalization warnings.
- Tests cover the experimental command without requiring live provider homes.
- No persistent `normalized/` or `derived/` storage format changes are made.

## Deferred Items
- Permanent `session.std.model` storage.
- Migration of `chatlas export --kind transcript`.
- Replay event reconstruction.
- Full tool invocation linking across all providers.
- Full reasoning/thinking preservation across all providers.
- UI or presentation changes.
- Raw fragment embedding in the experimental JSON.

## Open Questions
- Should the experimental model use `agent_instance` or just `instance` as the top-level key?
- Should message ids be stable content hashes, source-position ids, or generated sequence ids for the MVP?
- Should source refs use raw dataset-relative paths instead of absolute paths in the emitted JSON?
- Which provider should be the first provider-raw normalizer after the clean transcript fallback?
