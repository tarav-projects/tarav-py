# Chatlas Session Hashes And Sharded Index - impl-req

## Impl-Req State

Phase 5 complete; old single-index code assumptions are removed and the installed CLI has been refreshed.

## User Intent

Chatlas should keep the current simplified direction:

```text
provider raw artifacts -> provider normalizer -> session.std.model
```

The user wants the lightweight session index split across multiple files instead of one growing `index/sessions.index.jsonl` file. The split should be hash-based, but the hash should come from stable standard session identity/content, not from local provider instance data.

The standard session model should expose a standard session hash so other Chatlas services can use a provider-neutral identity/content surface rather than deriving their own local keys.

## Why This Exists

The current single-file index is simple, but it will become noisy as the dataset grows:

- every update can rewrite one large `sessions.index.jsonl`
- unrelated sessions produce merge/diff churn in the same file
- exact session lookup still scans the whole catalog
- there is no standard digest on the session model that downstream services can rely on

The accepted design is to add two explicit hashes:

- `session.identity_hash`: stable identity digest used for index sharding and lookup
- `session.content_hash`: canonical normalized-content digest used to detect model-content changes

These are separate because placement and change detection are different jobs.

## Current Situation

- Chatlas stores raw provider artifacts as the durable provider-native truth.
- Chatlas maintains a lightweight session catalog as shard files under `index/sessions/*.index.jsonl`.
- `agentos chatlas export <query>` builds the normalized session model in memory.
- The current model has canonical semantic events and `source_refs`, but it does not expose a standard identity hash or content hash.
- Provider instance information exists in the archive/index world, but the user does not want provider instance identity to determine standard session hashes.

## Requested Change

Add standard hashes to the session model envelope or session block:

```json
{
  "class": "agentos.chatlas.session_model",
  "schema_version": 1,
  "session": {
    "identity_hash": "sha256:...",
    "content_hash": "sha256:..."
  }
}
```

The exact placement can follow the current model structure, but both hashes must be first-class standard-model fields.

Define `identity_hash` from stable standard session identity fields. Use provider and provider-native session id, but do not include provider instance:

```json
{
  "schema": "agentos.chatlas.session_identity.v1",
  "provider": "codex",
  "provider_session_id": "019db5fd-7a73-7ae1-b5eb-901e62258dcb"
}
```

Define `content_hash` from canonical normalized model content. Start with the semantic `events[]` tape plus only the minimal stable metadata required to interpret those events:

```json
{
  "schema": "agentos.chatlas.session_content.v1",
  "events": [...]
}
```

Replace the single index file:

```text
index/sessions.index.jsonl
```

with sharded index files:

```text
index/sessions/
  00.index.jsonl
  01.index.jsonl
  ...
  ff.index.jsonl
```

Route each session index row by the first two hex characters of `session.identity_hash`:

```text
sha256:abcd... -> index/sessions/ab.index.jsonl
```

Only non-empty shard files need to exist.

Add an optional manifest if it keeps update/query code clearer:

```text
index/sessions.manifest.json
```

The manifest may record schema version, shard strategy, shard count, session count, generated time, and per-shard counts/content digests.

## Constraints And Invariants

- Do not include provider instance in `identity_hash`.
- Do not use the full mutable index record as the shard key.
- Do not use `content_hash` as the shard key.
- `identity_hash` must stay stable when a session gains more normalized events.
- `content_hash` should change when canonical normalized session content changes.
- Hash inputs must be canonicalized deterministically before hashing.
- Use explicit schema/version strings inside hash payloads so future changes can be intentional.
- Keep raw provider artifacts available through `source_refs`; hashes are not a replacement for auditability.
- Do not persist the full `session.std.model` yet.
- Do not add backward-compatibility aliases unless explicitly requested.
- Keep the command surface simple and aligned with the current Chatlas scope.

## Out Of Scope

- Cross-provider duplicate detection for the same human conversation.
- Content-addressed storage of raw artifacts.
- Persisting full normalized session models.
- Adding transcript or summary products back into Chatlas.
- Building secondary search indexes over event text.
- Using provider instance as a canonical identity component.

## Acceptance Signals

- `agentos chatlas export <query>` includes stable `identity_hash` and `content_hash` fields.
- Running export twice for unchanged raw data produces the same hashes.
- Adding/changing normalized events changes `content_hash` but does not change `identity_hash`.
- Chatlas update writes session index rows under `index/sessions/<prefix>.index.jsonl`.
- A session with `identity_hash: sha256:abcd...` is written to `index/sessions/ab.index.jsonl`.
- `index/sessions.index.jsonl` is outside the new design and should not be produced by Chatlas.
- `agentos chatlas query`, `agentos chatlas raw path`, `agentos chatlas raw export`, and `agentos chatlas export` work against the sharded index.
- Tests cover hash determinism, shard routing, and current command behavior.
- Existing reference sessions remain usable:
  - Claude Code: `5dbf4437-633e-4039-a627-0459d85e9ecc`
  - Copilot: `d1d3f48b-4b29-4dfc-b551-5536b9677225`
  - Codex: `019db5fd-7a73-7ae1-b5eb-901e62258dcb`

## Suggested Implementation Phases

1. **Define canonical hash helpers**
   - Add deterministic JSON canonicalization for hash payloads.
   - Add helpers for `sha256:` digest formatting.
   - Add tests proving key order and formatting do not affect digests.

2. **Add session identity/content hashes to the model**
   - Compute `identity_hash` from provider and provider-native session id.
   - Compute `content_hash` from canonical semantic session content.
   - Expose both fields in `chatlas export`.
   - Add tests for the three reference providers.

3. **Introduce sharded index writer/reader**
   - Replace the single-file writer with shard grouping by `identity_hash` prefix.
   - Write deterministic row ordering inside each shard.
   - Delete stale shard files that become empty or obsolete.
   - Add a manifest only if useful for simple verification/stats.

4. **Move query/raw/model commands onto the sharded reader**
   - Update all session-index loading paths to read `index/sessions/*.index.jsonl`.
   - Keep initial implementation as full shard scan unless an exact-hash lookup path is already easy.
   - Preserve strict one-session resolution for raw/model export commands.

5. **Clean up old single-index assumptions**
   - Remove constants, tests, help text, and manifest fields that refer to `index/sessions.index.jsonl`.
   - Refresh the installed CLI with `uv tool install --reinstall --editable .`.
   - Run focused Chatlas command tests.

## Relevant Files Or Surfaces

- `src/agentos/chatlas/core.py`
- `src/agentos/chatlas/commands.py`
- `src/agentos/chatlas/session_model/`
- `tests/test_chatlas_commands.py`
- `notes/live/544-chatlas-event-first-standard-model.md`
- `notes/live/547-chatlas-standard-model-contract.md`
- `notes/live/550-chatlas-simplified-session-model-surface-impl-req.md`
- `dev/session-samples/`

## Open Questions

- Should the content hash include only `events[]`, or should it also include stable session-level metadata such as provider and provider-native session id?
- Should the manifest be required in the first implementation, or deferred until stats/update reporting needs it?

## Related Impl-Reqs

- `notes/live/550-chatlas-simplified-session-model-surface-impl-req.md`

## End Log

- 2026-04-30: Created after the user accepted the design split between `session.identity_hash` for stable sharding and `session.content_hash` for normalized content change detection.
- 2026-04-30: Phase 1 complete. Added deterministic canonical JSON and `sha256:` digest helpers in `src/agentos/chatlas/session_model/_hashes.py`, with focused tests for key-order stability, compact UTF-8 canonicalization, digest formatting, and rejection of non-JSON numeric payloads.
- 2026-04-30: Phase 2 complete. `agentos chatlas export` now writes `session.identity_hash` from provider plus provider-native session id and `session.content_hash` from the canonical semantic event tape. Added coverage for deterministic repeated export and all three reference providers.
- 2026-04-30: Phase 3 complete. The session index now writes non-empty shard files under `index/sessions/<prefix>.index.jsonl`, routes rows by the first two hex characters of `identity_hash`, deletes stale shard files, and reads all shards through the shared session-index loader used by stats/query/raw/model commands.
- 2026-04-30: Removed the explicit old `index/sessions.index.jsonl` cleanup path from Phase 3 after user feedback. The code now implements only the sharded index design; any old single-file artifact should be removed manually, not handled by legacy-aware runtime logic.
- 2026-04-30: Phase 4 complete. `chatlas update` now reports `session_index_root` for the shard directory, session index query matching includes `identity_hash`, and tests verify `query`, `raw path`, `raw export`, and `export` work through identity-hash lookup over the sharded reader.
- 2026-04-30: Phase 5 complete. Renamed the internal index root constant for directory semantics, removed the unused shard-loader helper, updated query/raw/export help text to mention identity-hash lookup, refreshed the installed `agentos` CLI, and reran focused Chatlas tests plus command help smoke checks.
- 2026-04-30: Command surface adjustment after user feedback. Removed the `chatlas session-model export` subcommand and made the normalized standard session model available directly at `agentos chatlas export <query>`.
