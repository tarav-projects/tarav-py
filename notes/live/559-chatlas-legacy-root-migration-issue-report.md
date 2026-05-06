# Chatlas Legacy Root Migration Compatibility - issue-report

## Status

Resolved: Chatlas default-root resolution now resolves `~/Documents/chatlas` directly and no longer performs automatic legacy-root migration from `AGENTOS_HOME/chatlas`.

## Problem

`agentos chatlas` default-root resolution still checks for a legacy Chatlas root under `AGENTOS_HOME/chatlas` and moves it to the current default root under `~/Documents/chatlas` when the current root does not exist.

This behavior is observable in `src/agentos/chatlas/core.py`: `_resolve_chatlas_root()` calls `_migrate_legacy_chatlas_root_if_needed()` for every command path that uses the implicit default Chatlas root.

The compatibility behavior is also locked in by `tests/test_chatlas_commands.py::test_chatlas_stats_migrates_legacy_default_chatlas_root`.

## Expected Behavior

If the one-time migration from the old default root to `~/Documents/chatlas` is complete, default Chatlas root resolution should resolve the current default root directly and should not include runtime compatibility migration from `AGENTOS_HOME/chatlas`.

If legacy-root migration is still required, that requirement should be explicitly documented as current behavior rather than left as implicit compatibility code.

## Reproduction

Relevant code path:

1. `agentos chatlas stats`, `agentos chatlas update`, and other commands call Chatlas functions without passing `--chatlas-root`.
2. Those functions call `_resolve_chatlas_root(None)`.
3. `_resolve_chatlas_root()` resolves `default_chatlas_root()` and then calls `_migrate_legacy_chatlas_root_if_needed(resolved_default_root)`.
4. `_migrate_legacy_chatlas_root_if_needed()` inspects `agentos_home_dir() / "chatlas"` and may move that directory to `~/Documents/chatlas`.

Relevant test:

```sh
uv run pytest tests/test_chatlas_commands.py -k migrates_legacy_default_chatlas_root
```

Local state checked on 2026-05-06:

- `/Users/pereiro/Documents/chatlas` exists.
- `/Users/pereiro/.agentos/chatlas` does not exist.

## Context

`agentos-py/AGENTS.md` says not to add backward-compatibility aliases or compatibility layers unless explicitly requested, and to prefer clean namespace and interface changes over preserving legacy command paths.

Archived Chatlas planning says the current default Chatlas root should be `~/Documents/chatlas`. The archived implementation TODO also records that existing default Chatlas repos should migrate from `~/.agentos/chatlas` to `~/Documents/chatlas`, which explains why the compatibility path was originally introduced.

The issue is that the migration path now remains in normal runtime root resolution rather than as a bounded migration step.

## Relevant Files Or Surfaces

- `src/agentos/chatlas/core.py`
- `tests/test_chatlas_commands.py`
- `notes/live/archived/518-chatlas-implementation-plan.md`
- `notes/live/archived/519-chatlas-implementation-todo.md`
- `AGENTS.md`

## Root Cause (if known)

The Chatlas root moved from `AGENTOS_HOME/chatlas` to `~/Documents/chatlas`. A migration helper was added so existing default Chatlas repositories could be moved automatically. That helper remains wired into default root resolution after the migration appears complete locally.

## Suggested Fix (if known)

Resolved by treating legacy default-root migration as unsupported stale compatibility behavior.

Completed changes: `_legacy_default_chatlas_root()`, `_migrate_legacy_chatlas_root_if_needed()`, the call from `_resolve_chatlas_root()`, and the dedicated migration regression test were removed.

## Open Questions

- Resolved: no maintained local legacy root was found.
- Resolved: no implicit or one-shot legacy migration command is being kept.
- Resolved: `~/Documents/chatlas` is treated as the only default root.

## End Log

- 2026-05-06: Issue report created after stale-code review found the runtime compatibility path in Chatlas root resolution.
- 2026-05-06: Resolved by removing automatic legacy-root migration from Chatlas default-root resolution and deleting the dedicated compatibility regression test.
