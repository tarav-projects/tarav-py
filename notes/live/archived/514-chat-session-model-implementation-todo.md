# Chat Session Model Implementation TODO

## Goal
- Implement the accepted `agentos chat session` model from `513-chat-session-model-design.md`.
- Migrate `list`, `find`, and `stats` to a session-first schema.
- Preserve `extract` behavior while aligning it with the new resolver/session model.

## Checklist
- [x] Introduce internal session-model helpers for:
- [x] canonical session rows
- [x] backing artifacts
- [x] query match payloads
- [x] Migrate shared session serialization away from flat provider-native top-level fields.
- [x] Replace `primary_artifact_path` / `canonical_finding_count` output with:
- [x] `primary_backing_artifact`
- [x] `backing_artifact_count`
- [x] Move provider-native summary fields under `native`.
- [x] Add `created_at` derivation to session rows where possible.
- [x] Update `list` output envelope to:
- [x] include `selection`
- [x] include `expansions`
- [x] emit new session rows
- [x] keep card output working against the new row shape
- [x] Update `find` default behavior to return `sessions`, not `findings`.
- [x] Add `find --artifacts`.
- [x] Keep `find --grep` as search-evidence mode and separate it from canonical backing artifacts.
- [x] Define a `search_finding` payload for grep hits.
- [x] Update `stats` inventory mode to use the new envelope and counts.
- [x] Update `stats <query>` to return:
- [x] `selection`
- [x] `session`
- [x] `stats`
- [x] Decide compatibility policy for provider diagnostics:
- [x] keep behind an opt-in flag
- [ ] or preserve temporarily in JSON output during migration
- [x] Update tests for:
- [x] list
- [x] find
- [x] stats
- [x] extract compatibility where session shape changes affect resolver behavior
- [x] Run targeted chat command tests.
- [x] Run the full `agentos` test suite if targeted tests pass cleanly.

## Progress Notes
- Design captured in `513-chat-session-model-design.md`.
- Accepted command surface keeps the current command count flat and makes `find` a session-first query view.
- Implementation complete in code and tests.
- Provider diagnostics moved behind the existing `--full-output` flag as `provider_diagnostics`.
- Verified with:
- `uv run pytest tests/test_chat_commands.py tests/test_chat_extract_commands.py -q`
- `uv run pytest -q`
