# Chatlas Export Index Selection - impl-req

## Impl-Req State

Implemented: `agentos chatlas export` now selects through the Chatlas session index, reads copied Chatlas raw artifacts, and preserves the separate `agentos chatlas query` stub boundary.

## User Intent

Reimplement `agentos chatlas export` on top of the new Chatlas session index selection path.

The important boundary is:

- `agentos chatlas index query`
  - cheap selector over `index/sessions/**/*.jsonl`
  - identity/session metadata lookup
  - used internally by commands that need to select one or more sessions
  - no raw/native/cache reads
- `agentos chatlas export`
  - uses index query for selection
  - then reads copied Chatlas raw artifacts referenced by the selected index row
  - produces session content/model views
- `agentos chatlas query`
  - future richer/deeper query surface
  - can include full-text, transcript/content search, broader matching, provider-specific derived fields, expensive scans, ranking, etc.
  - it can call/index-query as its first filter stage, but it is not the default selector for other commands

## Why This Exists

The Chatlas update redesign makes the session index the first durable product. Commands that need to select a session should use that index as a cheap metadata selector instead of depending on the future, broader `chatlas query` surface.

`agentos chatlas export` is the next command to restore because it validates the intended pipeline:

```text
index selection -> copied Chatlas raw artifact -> session model view
```

## Current Situation

`agentos chatlas index query` exists and reads only `~/Documents/chatlas/index/sessions/**/*.jsonl`.

`agentos chatlas export` is still present in the CLI, but its active implementation is stubbed:

- CLI surface: `src/agentos/chatlas/commands.py`
- Stub export function: `src/agentos/chatlas/session_model/_model.py`
- Export view projection already exists in `src/agentos/chatlas/session_model/_views.py`
- Provider normalizers already exist for `codex`, `claude-code`, and `copilot-cli`

The old export implementation exists only under `_DEPRECATED/chatlas-update-v1/` as reference material. It must not be imported or revived as runtime code.

## Requested Change

Reimplement `agentos chatlas export` so it:

- resolves the requested session through the new index-selection path
- requires exactly one selected index row
- reads copied Chatlas raw artifacts referenced by that selected index row
- produces the existing session model view payloads
- keeps `agentos chatlas query` stubbed and separate

The current CLI shape can remain:

```sh
agentos chatlas export <query> --provider codex --view zip-transcript --format json
```

For the first slice, `<query>` should behave as a selector over index fields:

- exact `uri`
- exact `identity_hash`
- exact `session_id`
- case-insensitive `display_name` contains as fallback

`--provider` should restrict the index selection.

## Constraints And Invariants

- Use index query semantics for export selection.
- Do not call the future/general `chatlas_query(...)` selector from export.
- Do not read native provider homes during selection or export.
- Do not read `cache/session-index-derivations-v1/`.
- Read only copied Chatlas raw artifacts already referenced by the selected index row.
- Do not import or revive `_DEPRECATED/chatlas-update-v1`.
- Keep `agentos chatlas query` as a separate explicit stub.
- Keep `--format json` as the only supported export format for now.
- Keep existing `--view` choices: `full`, `transcript`, `user`, `replay`, `events`, `zip-transcript`.
- First implementation may support only providers with active session-model normalizers: `codex`, `claude-code`, and `copilot-cli`.
- Unsupported providers should fail clearly rather than returning partial or misleading exports.

## Out Of Scope

- Reimplementing `agentos chatlas query`.
- Full-text search.
- Ranking or fuzzy matching.
- Exporting raw artifact files.
- Adding non-JSON export formats.
- Adding option-only export selection fields.
- Implementing new provider normalizers for `gemini-cli`, `opencode`, `pi`, or `openclaw`.

## Acceptance Signals

- `agentos chatlas export <session-id> --view full --format json` returns an `agentos.chatlas.session_model` payload for a supported provider.
- `agentos chatlas export <session-id> --view zip-transcript --format json` returns an `agentos.chatlas.zip_transcript` payload.
- Export works after the native provider artifact is removed, as long as the copied Chatlas raw artifact and index row remain.
- `--provider` restricts selection.
- Zero matches fail with a clear error.
- Multiple matches fail with a clear error listing candidate identities.
- Unsupported providers fail with a clear unsupported-provider error.
- Tests prove export does not require native provider homes after the index and copied raw artifacts exist.
- Tests prove `agentos chatlas query` remains the explicit stub.
- Runtime code does not import `_DEPRECATED`.

## Implementation Shape

Slice 1: Index-backed selection for export.

- Add a small internal helper that selects one index row for an export query.
- Reuse `chatlas_index_query` or the lower-level index query runtime rather than `chatlas_query`.
- Implement exact id/hash/URI matching first, then display-name contains fallback.
- Add tests for zero, one, and multiple selected rows.

Slice 2: Restore supported-provider session model export.

- Reconnect `chatlas_export_session_model` to build a session model from the selected index row.
- Use the active provider session payload helpers and normalizers for `codex`, `claude-code`, and `copilot-cli`.
- Apply existing `_project_session_model_view(...)`.
- Add a Codex fixture test for `full` and `zip-transcript`.

Slice 3: Boundary and lifecycle tests.

- Prove export still works after deleting the native Codex artifact that originally produced the copied Chatlas raw artifact.
- Prove `chatlas query` remains stubbed.
- Prove `_DEPRECATED` is not imported by runtime code.
- Run focused and full test suites.

## Relevant Files Or Surfaces

- `src/agentos/chatlas/commands.py`
- `src/agentos/chatlas/core.py`
- `src/agentos/chatlas/index_query.py`
- `src/agentos/chatlas/session_model/_model.py`
- `src/agentos/chatlas/session_model/_views.py`
- `src/agentos/chatlas/session_model/_codex.py`
- `src/agentos/chatlas/session_model/_claude.py`
- `src/agentos/chatlas/session_model/_copilot.py`
- `tests/test_chatlas_commands.py`
- `notes/live/580-chatlas-index-query-command-impl-req.md`

## Open Questions

- Should export later grow option-only selection fields mirroring `agentos chatlas index query`? Recommended: not in this first implementation.
- Should display-name fallback be allowed when it matches more than one row? Recommended: fail clearly and ask for a stronger selector.

## Related Impl-Reqs

- `notes/live/576-chatlas-update-v1-deprecation-stub-impl-req.md`
- `notes/live/579-chatlas-delta-scan-impl-req.md`
- `notes/live/580-chatlas-index-query-command-impl-req.md`

## End Log

- 2026-05-12: Created implementation request for reimplementing `agentos chatlas export` on top of index-query selection and copied Chatlas raw artifacts.
- 2026-05-12: Implemented index-backed export selection and supported-provider session model export in `src/agentos/chatlas/session_model/_model.py`, with lazy package export wiring in `src/agentos/chatlas/session_model/__init__.py` and CLI behavior tests in `tests/test_chatlas_commands.py`. Verified with `uv run ruff check src/agentos/chatlas/session_model/__init__.py src/agentos/chatlas/session_model/_model.py tests/test_chatlas_commands.py`, `uv run pytest tests/test_chatlas_commands.py -q`, `uv run pytest -q`, `git diff --check`, `uv tool install --reinstall --editable .`, and installed-command smoke checks for export help, missing export selection, and the separate `chatlas query` stub.
