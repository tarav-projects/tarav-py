# 626 — agent subsystem cleanup — Impl.Req

## Impl.Abstract

| Field | Value |
|---|---|
| Status | done |
| Scope | Consolidate duplicated helpers across extractors, remove dead code, replace provider dispatch chains with registry lookups, deduplicate monitor helpers |
| Source | Full codebase audit (6 parallel agents, 46 findings) — in-chat session |
| Target package | `agentos-py` (`agentos.agent`) |

### Intent

The `agentos.agent` subsystem (~10.5K lines, 31 files) has accumulated DRY violations, dead code, and dispatch patterns that should use existing registries. The most impactful issues:

1. `_string_or_none()` / `_string_or_empty()` defined 8+ times across extractors and account modules with behavioral inconsistency
2. Dead wrapper functions in 4 extractor files — refactoring artifacts with zero callers
3. Dead functions in `sessions.py` (`_glob_paths`, `_update_time_bounds`, `_find_session_for_provider`)
4. `_backing_artifact_is_extractable()` in `sessions.py` re-implements a 7-way provider dispatch that `extractors/__init__.py` already handles via `_PROVIDER_SESSION_EXTRACTORS` registry
5. `_cell_offset_to_text_index()` duplicated identically between `monitor/models.py` and `monitor/render.py`
6. Manual dataclass reconstruction instead of `dataclasses.replace()` in `config.py` and `commands.py`
7. Unused `format_json_output` in `_cli_common.py`

This impl-req covers Tier A (mechanical, low-risk) and selected Tier B (dispatch tables, monitor dedup) work. It deliberately excludes:
- AgentConfig/AgentBase consolidation (needs design session — changes core abstractions)
- SessionSource/BackingArtifact merge (same)
- `workflows.py` decomposition (1396 lines, separate design session)
- `sessions.py` restructuring (ProviderAgentContext redesign)
- `config.py` provider defaults registry (5 functions, separate concern)
- `MonitorLoop` decomposition

### Key design decisions

- **Extractor helpers go in `extractors/common.py`**: existing shared module for the package. Add `_string_or_none`, `_string_or_empty`, `format_turns_output` there. These are extractor-internal.
- **Account module `_string_or_none` imports from `session_utils.string_or_none`**: the account modules use a strip+reject variant that matches `session_utils.string_or_none` exactly. No new module needed.
- **`_backing_artifact_is_extractable` uses `_PROVIDER_SESSION_EXTRACTORS`**: the registry in `extractors/__init__.py` already maps provider → probe function. The sessions.py 7-way if-chain is a redundant parallel dispatch.
- **`_cell_offset_to_text_index` canonical home is `monitor/models.py`**: `render.py` imports from there.

## Impl.Index

### Block: extractor helper consolidation

`_string_or_none` and `_string_or_empty` are defined locally in `copilot_cli.py`, `gemini_cli.py`, `openclaw.py`, and `pi.py`. All are identical within their behavioral group:

- `_string_or_none(value)`: returns `value` if `isinstance(value, str) and value`, else `None` — strict, no strip
- `_string_or_empty(value)`: returns `str(value)` if value is str, else `""` — always returns a string

These belong in `extractors/common.py` alongside existing `DialogTurn`, `format_turns_jsonl`, `format_turns_markdown`.

Additionally, the output format dispatch (`if output_format == "markdown": ... else: ...`) is repeated in all 8 extractors. A `format_turns_output(turns, output_format)` helper eliminates this.

### Block: dead extractor wrapper functions

5 thin wrappers with zero callers (confirmed by grep — only the `def` line matches):

- `copilot_cli.py:125`: `_load_copilot_events` wraps `load_copilot_cli_events`
- `gemini_cli.py:113`: `_load_gemini_session_data` wraps `load_gemini_cli_session_data`
- `opencode.py:226`: `_load_opencode_messages` wraps `load_opencode_session_messages`
- `opencode.py:137`: `_resolve_opencode_db_path` wraps `resolve_opencode_db_path`
- `openclaw.py:129`: `_load_openclaw_records` wraps `load_openclaw_session_records`

### Block: dead code in sessions.py

3 functions defined but never called (grep confirms only the `def` line matches):

- `_find_session_for_provider()` at line 751
- `_update_time_bounds()` at line 1301
- `_glob_paths()` at line 1339

### Block: sessions.py extractable dispatch

`_backing_artifact_is_extractable()` (line 935) is a 7-way `if session.provider == "..."` chain that lazy-imports each extractor's `is_*_session_path` function. This duplicates what `_PROVIDER_SESSION_EXTRACTORS` in `extractors/__init__.py` already provides — a dict mapping provider name → `ProviderSessionExtractorSpec` with a `probe_artifact_path` field.

The replacement: look up the provider in the registry, call `probe_artifact_path(path)`. If no entry, return `False`. This collapses ~30 lines into ~5.

Import consideration: `sessions.py` currently avoids importing from `extractors/__init__.py` to prevent circular imports (extractors/__init__.py imports from sessions.py at line 8). The solution is to expose a minimal lookup function from extractors that does not trigger the full import chain, or to use a late import inside the function body (same pattern currently used).

### Block: account module _string_or_none

`account_registry.py:316-319` and `account_usage_fallback.py:71-74` both define:
```python
def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
```

This is identical to `session_utils.string_or_none` (line 127), which strips and rejects empty. Replace both with an import from `session_utils`.

### Block: monitor _cell_offset_to_text_index

Identical function at `monitor/models.py:270-284` and `monitor/render.py:364-378`. Keep the `models.py` copy, import in `render.py`.

### Block: dataclasses.replace() usage

Two locations manually reconstruct frozen dataclasses instead of using `replace()`:

- `config.py:812-822`: `default_agent_ping_config_with_model()` — manually copies all fields of `AgentPingConfig` to override `model`. Should use `replace(config, model=model)`.
- `commands.py:182-189`: ping command reconstructs `AgentCommandConfig` to override model. Should use `replace(command_config, model=agent.ping.model)`.

### Block: unused format_json_output

`_cli_common.py:43-46` defines `format_json_output` and exports it in `__all__`. Grep confirms no callers anywhere in the codebase — all command functions use `json.dumps(payload, indent=2, sort_keys=True)` directly. Remove the function and its `__all__` entry.

## Execution.Plan

### Slice 1 — Add shared helpers to `extractors/common.py`

**What changes**: Add `_string_or_none`, `_string_or_empty`, and `format_turns_output` to `extractors/common.py`.

**Files**:
- `agentos-py/src/agentos/agent/extractors/common.py` — add 3 functions

**Observable result**: `from agentos.agent.extractors.common import _string_or_none, _string_or_empty, format_turns_output` works.

**Validation**: Import check in Python REPL.

### Slice 2 — Migrate extractor callers to `common.py`

**What changes**: Replace local `_string_or_none` and `_string_or_empty` definitions in 4 extractor files with imports from `common.py`. Replace output format dispatch with `format_turns_output` call in all 8 extractors (7 provider files + potentially common patterns).

**Files** (each gets import swap + definition deletion):
- `extractors/copilot_cli.py` — delete `_string_or_none` (line 281), `_string_or_empty` (line 287), add import
- `extractors/gemini_cli.py` — delete `_string_or_empty` (line 321), add import
- `extractors/openclaw.py` — delete `_string_or_empty` (line 249), add import
- `extractors/pi.py` — delete `_string_or_none` (line 352), `_string_or_empty` (line 358), add import
- All 8 extractor files — replace format dispatch with `format_turns_output` call

**Observable result**: `grep -r "def _string_or_none\|def _string_or_empty" src/agentos/agent/extractors/` returns only `common.py`.

**Validation**: `uv run python -c "from agentos.agent.extractors import extract_chat_session"` succeeds.

### Slice 3 — Delete dead extractor wrapper functions

**What changes**: Remove 5 unused wrapper functions from extractor files.

**Files**:
- `extractors/copilot_cli.py` — delete `_load_copilot_events` (line 125)
- `extractors/gemini_cli.py` — delete `_load_gemini_session_data` (line 113)
- `extractors/opencode.py` — delete `_load_opencode_messages` (line 226), `_resolve_opencode_db_path` (line 137)
- `extractors/openclaw.py` — delete `_load_openclaw_records` (line 129)

**Observable result**: `grep -r "def _load_copilot_events\|def _load_gemini_session_data\|def _load_opencode_messages\|def _load_openclaw_records\|def _resolve_opencode_db_path" src/agentos/agent/extractors/` returns no matches.

**Validation**: Same import check as Slice 2.

### Slice 4 — Delete dead code in sessions.py and _cli_common.py

**What changes**: Remove 3 dead functions from `sessions.py` and 1 dead function from `_cli_common.py`.

**Files**:
- `sessions.py` — delete `_find_session_for_provider` (line 751), `_update_time_bounds` (line 1301), `_glob_paths` (line 1339)
- `_cli_common.py` — delete `format_json_output` (line 43), remove from `__all__`

**Observable result**: Grep confirms no remaining definitions. No remaining references to these functions.

**Validation**: `uv run python -c "from agentos.agent.sessions import find_chat_session"` succeeds.

### Slice 5 — Migrate `_string_or_none` in account modules

**What changes**: Replace local `_string_or_none` definitions in `account_registry.py` and `account_usage_fallback.py` with imports from `session_utils.string_or_none`.

**Files**:
- `account_registry.py` — delete local `_string_or_none` (line 316), add `from agentos.agent.session_utils import string_or_none`, update call sites to use `string_or_none` (no underscore prefix)
- `account_usage_fallback.py` — same pattern (line 71)

**Observable result**: `grep -r "def _string_or_none" src/agentos/agent/` returns no matches (only `session_utils.string_or_none` exists).

**Validation**: `uv run python -c "from agentos.agent.account_registry import load_links"` succeeds.

### Slice 6 — Replace extractable dispatch with registry lookup

**What changes**: Replace the 7-way if-chain in `_backing_artifact_is_extractable()` (sessions.py:935) with a lookup into `_PROVIDER_SESSION_EXTRACTORS` from `extractors/__init__.py`.

Since `extractors/__init__.py` imports from `sessions.py` (line 8), a direct top-level import would create a cycle. Use a late import inside the function body (same pattern the current code already uses for each extractor).

**Files**:
- `sessions.py` — rewrite `_backing_artifact_is_extractable()` to ~5 lines

**Observable result**: `sessions.py` no longer imports individual `is_*_session_path` functions.

**Validation**: `uv run python -c "from agentos.agent.sessions import find_chat_session"` succeeds.

### Slice 7 — Deduplicate `_cell_offset_to_text_index` in monitor

**What changes**: Delete `_cell_offset_to_text_index` from `monitor/render.py`, import from `monitor/models.py`.

**Files**:
- `monitor/render.py` — delete function (line 364-378), add import from `monitor.models`

**Observable result**: `grep -r "def _cell_offset_to_text_index" src/agentos/agent/monitor/` returns only `models.py`.

**Validation**: `uv run python -c "from agentos.agent.monitor import run_monitor_loop"` succeeds (or equivalent top-level import).

### Slice 8 — Use `dataclasses.replace()` for dataclass overrides

**What changes**: Replace manual field-by-field reconstruction with `replace()` calls.

**Files**:
- `config.py` — simplify `default_agent_ping_config_with_model()` (line 812-822) to use `replace(config, model=model)`
- `commands.py` — simplify ping model override (line 182-189) to use `replace(command_config, model=agent.ping.model)`

**Observable result**: No manual AgentPingConfig or AgentCommandConfig constructor calls for field overrides.

**Validation**: `uv run python -c "from agentos.agent.config import default_agent_ping_config_with_model"` succeeds.

### Risks

- **Import cycles (Slice 6)**: `sessions.py` ↔ `extractors/__init__.py`. Mitigated by using a late import inside the function body, matching the existing pattern.
- **`string_or_none` behavioral drift (Slice 5)**: Account modules use a strip variant. `session_utils.string_or_none` also strips. Confirmed identical behavior. Low risk.
- **Extractor `format_turns_output` (Slice 2)**: Touches all 8 extractor files. Mechanical but wide. Each change is a 2-line replacement — low complexity per file.

### Out of scope

- AgentConfig/AgentBase consolidation (core abstraction change, needs design session)
- SessionSource/BackingArtifact merge (same)
- `workflows.py` decomposition (1396 lines, separate design session)
- `sessions.py` ProviderAgentContext redesign (redundant derived fields)
- `config.py` provider defaults registry (5 if-chain functions → data-driven)
- Workflow state management base class extraction
- `MonitorLoop` decomposition
- `commands.py` provider dispatch consolidation (register/link/status)
- `agent_config_from_config_entry()` decomposition (211 lines)

## Impl.Log

### 2026-05-21 — all 8 slices executed

- **Slice 1**: Added `_string_or_none`, `_string_or_empty`, `format_turns_output` to `extractors/common.py`.
- **Slice 2**: Migrated all 7 extractor files — replaced `format_turns_jsonl`/`format_turns_markdown` imports with `format_turns_output`, replaced 3-line dispatch with single call. Deleted local `_string_or_none`/`_string_or_empty` from `copilot_cli.py`, `gemini_cli.py`, `openclaw.py`, `pi.py`.
- **Slice 3**: Deleted 5 dead wrapper functions from `copilot_cli.py`, `gemini_cli.py`, `opencode.py` (2), `openclaw.py`.
- **Slice 4**: Deleted `_find_session_for_provider`, `_update_time_bounds`, `_glob_paths` from `sessions.py`. Deleted `format_json_output` from `_cli_common.py` and removed from `__all__`.
- **Slice 5**: Replaced `_string_or_none` in `account_registry.py` and `account_usage_fallback.py` with `session_utils.string_or_none` import.
- **Slice 6**: Replaced 7-way provider dispatch in `_backing_artifact_is_extractable()` with `_PROVIDER_SESSION_EXTRACTORS` registry lookup (~37 lines → 8 lines). Late import preserves circular import safety.
- **Slice 7**: Deleted duplicate `_cell_offset_to_text_index` from `monitor/render.py`, now imports from `monitor/models.py`.
- **Slice 8**: Replaced manual dataclass reconstruction with `dataclasses.replace()` in `config.py` and `commands.py`.

**Deviations**: The impl-req mentioned "all 8 extractors" for the format dispatch but there are 7 provider extractor files. Applied to all 7. No other deviations.

**No remaining work.**
