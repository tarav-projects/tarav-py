# Chatlas Session Location Index Fields - impl-req

## Impl.Abstract

- **scope:** add session-location fields to Chatlas session index rows so `agentos chatlas query` can return meaningful `home` and `project_path` values
- **status:** implemented
- **source:** user request after investigating why `agentos chatlas query` returned `"home": null` and `"project_path": null`
- **target:** populate top-level `home` and `project_path` in `agentos.chatlas.session` index rows when the data is explicitly available
- **non-goals:** do not infer project paths from weak path heuristics for providers without explicit evidence; do not change `agentos chatlas query` row shape; do not add a broad metadata schema redesign

## Impl.Index

### Chatlas.Session.Location.Fields

- `home` is provider-instance metadata.
- `home` should be copied directly from `session.provider_instance.agent.home` into every session index row when the provider instance has a configured home.
- `project_path` is session metadata.
- `project_path` should be populated only when the provider-native session artifact explicitly records a project/cwd/workspace path.
- If the provider has no explicit project-path evidence, `project_path` should remain `null` or absent from the index row, which preserves the current honest-null behavior in `agentos chatlas query`.

#### appendix

Current evidence:

- `src/agentos/chatlas/delta_scan.py` already has `ChatlasProviderInstance.agent.home`.
- `agentos chatlas update --provider codex --verbose-mode quiet --output-mode json` reports configured instance homes such as `/Users/pereiro/.codex`.
- `agentos chatlas update --provider claude-code --verbose-mode quiet --output-mode json` reports configured instance home `/Users/pereiro/.claude`.
- `agentos chatlas update --provider copilot-cli --verbose-mode quiet --output-mode json` reports configured instance home `/Users/pereiro/.copilot`.
- `_session_index_row(...)` currently writes provider, instance, fingerprint, uri, session id, timestamps, artifacts, native metadata, and identity hash, but not `home` or `project_path`.
- `src/agentos/chatlas/query.py` already projects `home` and `project_path` from index row fields and returns `null` when absent.

#### meta

- status: accepted implementation target

### Provider.Location.Support

- `codex` has strong `project_path` support.
- Codex rollout files contain `session_meta.payload.cwd`.
- `CodexSessionRef` currently reads the rollout `session_meta` for the session id, but does not preserve `cwd`.
- The implementation should add `cwd` to `CodexSessionRef` and `CodexSession`, include it in `native_ref_metadata()`, and promote it to top-level `project_path` in the index row.

- `claude-code` has strong `project_path` support.
- Claude JSONL records contain top-level `cwd`.
- The implementation should read `cwd` from the first usable JSONL object when available, carry it through `ClaudeSessionRef` and `ClaudeSession`, include it in `native_ref_metadata()`, and promote it to top-level `project_path`.

- `copilot-cli` has strong `project_path` support.
- Copilot `events.jsonl` has `session.start.data.context.cwd` and often `session.start.data.context.gitRoot`.
- The implementation should prefer `gitRoot` as `project_path` when present, otherwise use `cwd`.
- The chosen value should be carried through `CopilotSessionRef` and `CopilotSession`, included in `native_ref_metadata()`, and promoted to top-level `project_path`.

- `pi` already has modeled `cwd`.
- `PiSessionRef.native_ref_metadata()` already includes `cwd` when present.
- The implementation should promote Pi `cwd` to top-level `project_path`.

- `gemini-cli`, `openclaw`, and `opencode` do not currently expose explicit project-path evidence through their session refs.
- Leave `project_path` unset/null for these providers until their raw schemas are explicitly inspected and modeled.

#### appendix

Provider evidence observed during investigation:

- Codex sample: rollout `session_meta.payload.cwd` contained `/Users/pereiro/projects/agentos-project`.
- Claude sample: first JSONL records contained top-level `cwd` such as `/Users/pereiro/projects/agentos-project`.
- Copilot sample: `session.start.data.context.cwd` and `gitRoot` were present.
- Pi source: `src/agentos/pi/session.py` already models `cwd` and emits it in native metadata.
- Gemini source: `src/agentos/gemini/session.py` reads `sessionId`, `lastUpdated`, and `startTime`; native metadata is empty.
- OpenClaw source: `src/agentos/openclaw/session.py` native metadata contains `session_keys` and `agent_id`, not cwd/project path.
- OpenCode source: `src/agentos/opencode/session.py` native metadata is empty.

#### meta

- status: provider report accepted

### Index.Row.Backfill.Semantics

- New index rows should include:
  - `home`: string when provider instance home is known, otherwise `null`
  - `project_path`: string when explicit provider session evidence is available, otherwise `null`
- The change should apply when `agentos chatlas update` derives or rewrites session index rows.
- Existing index rows will not gain these fields until their rows are rebuilt or refreshed.
- If the cache prevents unchanged sessions from being rederived, an implementer should either update the derivation signature so location-field changes cause a row rewrite, or document that a cache-disabled/session-index rebuild is required.
- Do not silently parse raw archived copies when the native session ref already has the source artifact available during index derivation.

#### appendix

Current local dataset includes historical rows where `home` and `project_path` are absent. The implementation should include tests against fresh indexing behavior rather than assuming existing local rows are already backfilled.

#### meta

- status: accepted operational semantics

## Execution.Plan

### Slice 1 - Add provider-instance home to session index rows

- update `_session_index_row(...)` in `src/agentos/chatlas/delta_scan.py`
- add top-level `home` using `str(session.provider_instance.agent.home)` when non-null, otherwise `None`
- keep `agentos chatlas query` projection unchanged
- path: provider config -> `ChatlasProviderInstance` -> session index row -> `agentos chatlas query` normalized row
- observable: newly indexed rows include `home`, and `agentos chatlas query` returns that value
- check: focused Chatlas test that indexes a configured provider instance with `home` and verifies both `chatlas index query` row and `chatlas query` normalized row
- status: implemented

### Slice 2 - Add Codex project_path extraction

- add `cwd` to `CodexSessionRef` and `CodexSession`
- read `session_meta.payload.cwd` in `read_codex_rollout_session_ref(...)`
- preserve `cwd` through merge and chatlas payload rehydration where applicable
- emit `cwd` in `native_ref_metadata()`
- promote Codex `cwd` to top-level `project_path` in `_session_index_row(...)`
- path: Codex rollout `session_meta.payload.cwd` -> Codex session ref -> session index row -> query row
- observable: newly indexed Codex sessions include `project_path`
- check: focused test using `_write_codex_rollout(...)` with a fixture cwd
- status: implemented

### Slice 3 - Add Claude project_path extraction

- add `cwd` to `ClaudeSessionRef` and `ClaudeSession`
- read top-level `cwd` from the first JSONL object when available in `read_claude_project_session(...)`
- preserve `cwd` through merge and chatlas payload rehydration where applicable
- emit `cwd` in `native_ref_metadata()`
- promote Claude `cwd` to top-level `project_path` in `_session_index_row(...)`
- path: Claude JSONL `cwd` -> Claude session ref -> session index row -> query row
- observable: newly indexed Claude sessions include `project_path`
- check: focused test with a Claude JSONL fixture containing `cwd`
- status: implemented

### Slice 4 - Add Copilot project_path extraction

- add `project_path` or equivalent internal field to `CopilotSessionRef` and `CopilotSession`
- read `session.start.data.context.gitRoot` from `events.jsonl` when present
- fall back to `session.start.data.context.cwd` when `gitRoot` is absent
- emit the selected value in `native_ref_metadata()`, preferably as `project_path`
- promote the selected value to top-level `project_path` in `_session_index_row(...)`
- path: Copilot `events.jsonl` session start context -> Copilot session ref -> session index row -> query row
- observable: newly indexed Copilot sessions include `project_path`
- check: focused test with `events.jsonl` containing both `cwd` and `gitRoot`, plus a fallback case if cheap
- status: implemented

### Slice 5 - Promote Pi cwd and keep unsupported providers honest

- add generic promotion helper in `delta_scan.py` that maps explicit provider metadata to `project_path`
- for Pi, map native `cwd` to `project_path`
- for Gemini, OpenClaw, and OpenCode, keep `project_path` as `None` unless new explicit evidence is added in the same slice
- avoid provider-specific path heuristics from archived raw paths
- path: provider session native metadata -> index promotion helper -> index/query row
- observable: Pi rows gain `project_path`; unsupported providers continue returning null
- check: focused unit/command tests for Pi promotion if existing fixtures make it cheap; otherwise helper-level coverage through synthetic provider/native rows
- status: implemented

### Slice 6 - Verify refresh behavior and installed CLI

- run focused Chatlas tests
- run the full test suite if focused tests pass
- reinstall editable CLI because the session index/query behavior changed:
  - `uv tool install --reinstall --editable .`
- smoke test one newly indexed or fixture-backed session when practical:
  - `agentos chatlas query --session-id <known-session-id>`
- if old cached rows do not backfill automatically, document the required rebuild command or update cache signature logic in the implementation
- observable: `agentos chatlas query` returns non-null `home` and `project_path` for supported provider sessions after refresh/rebuild
- check:
  - `uv run python -m pytest tests/test_chatlas_commands.py -q`
  - `uv run python -m pytest -q`
  - installed CLI smoke check
- status: implemented

## Impl.Log

- 2026-05-14: Created implementation request from the accepted design: index rows should capture provider-instance `home`, provider-explicit `project_path` for Codex, Claude, Copilot, and Pi, and leave unsupported providers null until explicit evidence exists.
- 2026-05-14: Implemented location indexing. `_session_index_row(...)` now emits top-level `home` and `project_path`; the derivation signature includes configured `home` so cached rows rederive; Codex and Claude preserve explicit `cwd`; Copilot preserves `gitRoot` with `cwd` fallback as `project_path`; Pi `cwd` is promoted through the shared row helper. Focused Chatlas tests and full test suite pass.
