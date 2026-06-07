# Impl.Req — Agent CLI JSON output centralization + tmp_folder dead-dir removal

## Impl.Abstract

- **Scope**: Two narrow code-hygiene cleanups under `src/agentos/`.
- **Source**: Hugentics-codebase-cleaner pass on `main` (clean tree at commit `5c8bec2`).
- **Status**: Drafted. Gated mode, autoapproved by the user. Hand straight to `impl.executer.agent` after writing.
- **Backward compatibility**: not a goal. JSON output for the affected CLI commands already uses `indent=2, sort_keys=True`; behavior is preserved.

## Impl.Index

### Block: `format_json_output` is dead and duplicated

- `src/agentos/agent/_cli_common.py:43` defines `format_json_output(payload) -> json.dumps(payload, indent=2)`.
- `Hard.Evidence`: `grep -rn format_json_output src/agentos/` returns only the definition + `__all__`. Zero call sites in `src/` and `tests/`.
- `src/agentos/agent/commands.py` has **9** identical `print(json.dumps(payload, indent=2, sort_keys=True))` sites: lines 77, 367, 385, 399, 413, 528, 598, 605, 689.
- The helper's current `indent=2` (no `sort_keys`) does not match the in-use convention; reusing it as-is would silently change CLI output.
- Decision: change the helper to `json.dumps(payload, indent=2, sort_keys=True)` (the de-facto convention in `commands.py`) and route the 9 sites through it.

### Block: `src/agentos/tmp_folder/` is an empty package directory

- `find src/agentos/tmp_folder -type f` returns only stale `__pycache__/*.pyc`.
- No source files; not tracked by git.
- `grep -rn "agentos.tmp_folder\|from agentos import tmp_folder" src/ tests/` returns no hits. The live tmp-folder code is `src/agentos/utils/tmp_folder.py` (unrelated).
- Decision: delete the directory tree on disk.

## Execution.Plan

### Slice 1 — Centralize CLI JSON output

- **Changes**:
  - `src/agentos/agent/_cli_common.py`: change `format_json_output` body to `return json.dumps(payload, indent=2, sort_keys=True)`. Move `import json` to module scope (cheap, removes lazy-import nit).
  - `src/agentos/agent/commands.py`: import `format_json_output` from `._cli_common`. Replace each of the 9 `print(json.dumps(payload, indent=2, sort_keys=True))` lines with `print(format_json_output(payload))`. Do not touch `_agent_profile_template` (uses `indent=2` without sort_keys + appended `"\n"` — different formatting contract).
- **Path through system**: CLI JSON output paths in `agent` subcommands (list, profiles, sessions, etc.).
- **Observable result**: Identical JSON output for the affected commands; no duplicated `json.dumps(... indent=2, sort_keys=True)` literals in `commands.py`; the helper has callers.
- **Check**: `grep -n "json.dumps(payload, indent=2, sort_keys=True)" src/agentos/agent/commands.py` returns nothing. `grep -n format_json_output src/agentos/agent/commands.py` returns 9 call sites + 1 import.

### Slice 2 — Remove dead `tmp_folder` package directory

- **Changes**: `rm -rf src/agentos/tmp_folder` (only contains `__pycache__`; not git-tracked, so no commit hunk for the deletion itself).
- **Observable result**: Directory no longer present; nothing imports it.
- **Check**: `ls src/agentos/tmp_folder` errors with "No such file or directory". `python -c "import agentos.utils.tmp_folder"` still succeeds (unrelated live module).

### Final verification

- Run `uv run pytest` (full suite — the affected JSON-emitting commands are exercised by `tests/test_agent_profiles.py` and adjacent tests).
- If the full suite is too slow, fall back to `uv run pytest tests/test_agent_profiles.py tests/test_agent_account_events.py tests/test_codex_account_reconcile.py tests/test_agent_run_account_preflight.py`.

### Risks / deviation triggers

- If any test asserts exact stdout JSON for the affected commands with a different ordering, it must already pass (output unchanged). If a test fails after slice 1, that's an unexpected divergence — abort and report.
- If `grep` discovers an import of `agentos.tmp_folder` outside `src/` / `tests/` (e.g. in `dev/`, `notes/`), do not delete; abort slice 2 and surface.

### Acceptance signals

- `grep` checks above pass.
- `uv run pytest` (or the focused subset) is green.
- Two clean per-slice commits (semantic, conventional) on top of the executer's pre-execution checkpoint commit.

## Impl.Log

- (executer fills in)
