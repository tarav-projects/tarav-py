# Chatlas Update V1 Deprecation And Stub - impl-req

## Impl-Req State

Implemented as the first migration slice: the old Chatlas update-era runtime is archived as dead reference and the live command surface is stubbed.

## User Intent

Move the current Chatlas update implementation out of runtime code and into a dead reference area, then replace the live command surface with explicit mocks/stubs so the new system can be reimplemented cleanly.

## Why This Exists

The current `chatlas update` implementation has grown into a monolithic workflow that mixes raw mirroring, session discovery, index materialization, cache management, git finalization, manifest writing, and CLI reporting. The redesign should not preserve that structure as legacy runtime code. The old code should remain available only as reference while the new phase-based implementation is built.

## Current Situation

Runtime Chatlas code currently lives under `src/agentos/chatlas/`.

Important current surfaces:

- `src/agentos/chatlas/commands.py` registers the CLI and calls runtime functions.
- `src/agentos/chatlas/core.py` owns most command behavior, including `chatlas_update`, query, stats, raw path/export, index shard helpers, and cache helpers.
- `src/agentos/chatlas/raw.py` owns raw archive mirroring and raw scan cache behavior.
- `src/agentos/chatlas/session_model/` depends on Chatlas query/session selection behavior for export.
- Tests in `tests/test_chatlas_commands.py` encode the old behavior heavily.

The package build includes only `src/agentos`, so a top-level `agentos-py/_DEPRECATED/` directory is outside the shipped package.

## Requested Change

Implement a demolition/stub slice with three outcomes:

1. Move or copy the current Chatlas update-era implementation into `agentos-py/_DEPRECATED/chatlas-update-v1/` as dead reference code.
2. Remove runtime dependencies from `src/agentos/chatlas` to the moved code.
3. Replace the live Chatlas command handlers with explicit stub/mock behavior that preserves the command surface shape while making clear that the backend is under reimplementation.

`_DEPRECATED` is dead code. It must not be imported, packaged, tested, or used as a fallback.

## Constraints And Invariants

- Do not create compatibility bridges from `src/agentos/chatlas` into `_DEPRECATED`.
- Do not make `_DEPRECATED` importable package code.
- Do not keep the old `chatlas update` implementation callable from the live CLI.
- Keep the top-level `agentos chatlas` command registered.
- Preserve parser shape for existing Chatlas subcommands where practical, especially `chatlas update` flags.
- Stub payloads must be explicit and deterministic.
- Stub behavior should be easy to assert in tests.
- The slice should be small enough that the next implementation can start from clean live modules.

## Out Of Scope

- Reimplementing `index-only`.
- Rebuilding raw mirroring.
- Rebuilding query, stats, raw export, or standard-model export.
- Migrating old tests to the new full behavior.
- Designing the final session index schema.
- Adding runtime fallback to old code.

## Acceptance Signals

- `agentos chatlas update --output-mode=json` exits successfully and emits a deterministic stub payload.
- `agentos chatlas update` without JSON remains quiet or emits only intentional stub progress according to existing `--verbose-mode` behavior.
- The live `src/agentos/chatlas` runtime does not import from `_DEPRECATED`.
- `_DEPRECATED/chatlas-update-v1/` contains the old implementation reference and a short README explaining that it is dead code.
- Focused tests prove the stub command surface.
- A search for `_DEPRECATED` under `src/agentos` returns no runtime imports.

## Implementation Shape

### Slice 1: Archive Old Code As Dead Reference

Create:

- `_DEPRECATED/chatlas-update-v1/README.md`
- `_DEPRECATED/chatlas-update-v1/src/agentos/chatlas/...` or another clearly labeled source mirror

Copy the old Chatlas runtime files needed as reference. At minimum include:

- `src/agentos/chatlas/commands.py`
- `src/agentos/chatlas/core.py`
- `src/agentos/chatlas/raw.py`
- `src/agentos/chatlas/_cache_io.py`
- `src/agentos/chatlas/session_model/` if export/query coupling makes it useful as reference

The README must state that the directory is dead reference code and must not be imported.

Observable check:

- Files exist under `_DEPRECATED/chatlas-update-v1/`.
- `rg "_DEPRECATED" src/agentos` finds no runtime imports.

### Slice 2: Replace Live Chatlas Runtime With Stubs

Keep `src/agentos/chatlas/__init__.py` and `src/agentos/chatlas/commands.py` as the live command entry. Replace handler behavior so current Chatlas commands return explicit stub payloads.

Minimum required stub:

- `agentos chatlas update`

Recommended stub payload shape for JSON:

```json
{
  "status": "stubbed",
  "command": "chatlas update",
  "reason": "chatlas update is under reimplementation",
  "phase": null,
  "selection": {
    "providers": null
  }
}
```

The exact payload may differ, but it must be stable and clearly identify the command as stubbed.

Observable check:

- `agentos chatlas update --output-mode=json` returns the stub payload.
- `agentos chatlas update --provider codex --output-mode=json` includes the selected provider in the stub payload.

### Slice 3: Stabilize Imports During Rebuild

Decide which old public imports should remain as stubs and which should fail clearly.

Likely keep as live stubs:

- `agentos.chatlas.commands.register_chatlas_commands`
- `agentos.chatlas.core.chatlas_update`

Likely replace with clear `CliError` or stub payload functions:

- `chatlas_query`
- `chatlas_stats`
- `chatlas_raw_paths`
- `chatlas_raw_export`
- `chatlas_export_session_model`

Keep pure utility modules only if they are genuinely independent and still needed by other tests, such as session hash helpers. Do not keep old orchestration code just to satisfy old tests.

Observable check:

- CLI import succeeds.
- `agentos --help` still lists `chatlas`.
- Commands fail or stub intentionally, not through import errors.

### Slice 4: Test The Demolition Boundary

Add focused tests rather than preserving old behavior tests.

Suggested tests:

- `test_chatlas_update_stub_json_payload`
- `test_chatlas_update_stub_preserves_provider_selection`
- `test_chatlas_update_stub_respects_quiet_verbose_mode`
- `test_chatlas_runtime_does_not_import_deprecated_code`

Old behavior-heavy tests should be skipped, rewritten, or moved in a later test-cleanup slice. Do not contort the stubs to satisfy old update behavior assertions.

## Relevant Files Or Surfaces

- `src/agentos/cli.py`
- `src/agentos/chatlas/__init__.py`
- `src/agentos/chatlas/commands.py`
- `src/agentos/chatlas/core.py`
- `src/agentos/chatlas/raw.py`
- `src/agentos/chatlas/session_model/`
- `tests/test_chatlas_commands.py`
- `tests/test_chatlas_session_hashes.py`
- `_DEPRECATED/chatlas-update-v1/`
- `notes/live/575-chatlas-update-workflow-split-design-summary.md`

## Open Questions

- Should non-update Chatlas subcommands return stub payloads with exit code `0`, or should they fail with a clear `CliError` until reimplemented?
- Should the old behavior tests be moved under `_DEPRECATED` as reference, or simply replaced by new contract tests?
- Should `chatlas update --phase index-only` be introduced in this stub slice or left for the first real reimplementation slice?

## Related Impl-Reqs

- `notes/live/575-chatlas-update-workflow-split-design-summary.md`

## End Log

- 2026-05-11: Created to capture the first Chatlas update redesign migration slice: archive old implementation as dead reference, sever runtime use, and stub the live command surface.
- 2026-05-11: Implemented the slice. Archived old Chatlas runtime under `_DEPRECATED/chatlas-update-v1/`, replaced live Chatlas update/query/stats/raw/export runtime behavior with explicit stubs, replaced impacted command tests with stub-boundary tests, verified no `_DEPRECATED` imports under `src/agentos`, refreshed the editable CLI, and checked `agentos chatlas update --output-mode=json`.
