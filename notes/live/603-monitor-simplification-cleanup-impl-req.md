# Monitor Simplification Cleanup - impl-req

## Impl.Abstract

- **scope:** simplify the `agentos agent accounts monitor` implementation by removing dead code, reducing untyped dict usage in favor of existing patterns, and clarifying the thread-safety contract — all without introducing new abstractions or expanding the API surface.
- **status:** draft.
- **source:** code review of the monitor package (`src/agentos/agent/monitor/`) after the background frame swap implementation (600-impl-req).
- **goal:** reduce cognitive load and maintenance surface. The monitor works correctly today; this is a cleanup pass focused on removing unnecessary complexity, not adding features.

## Impl.Index

### Current.State.Evidence

- Monitor package lives at `src/agentos/agent/monitor/` with 6 files: `__init__.py`, `models.py`, `loop.py`, `config.py`, `workflows.py`, `render.py`.
- `LimitsTrackingWorkflow` manages its internal state as nested `dict[str, object]` bags (`_workflow_state`, `_target_state`, `_target_states`). Keys like `"last_refresh_at_monotonic"`, `"refresh_count"`, `"status"` are accessed by string convention.
- `MonitorFrame.blocks` is `list[dict[str, object]]` — blocks are constructed by `monitor_block()` and consumed by convention-based key access (`block.get("title")`, `block.get("rows")`, etc.).
- `_format_seconds` at `workflows.py:487-490` is defined but never called anywhere in the codebase.
- `format_monitor_frame` (plain-text path) and `_monitor_render_rows` (Rich path) both walk the same frame/blocks/rows structure with near-identical traversal logic.
- `LimitsTrackingWorkflow._frame_block_index` caches a block position across frame swaps, guarded by a bounds check that falls through to `add_block`. The workflow runs once per frame, so `replace_block` is never actually needed.
- The frame-swap thread-safety invariant in `loop.py` is correct (Event-based handshake ensures exclusive access) but undocumented — the reasoning requires reading the full Event lifecycle across `_run_workflow_loop`, `_publish_working_frame_if_ready`, and `_start_workflow_cycle`.
- `_format_remaining_duration` maps 1-59 seconds to "1m" — acceptable for a monitor display.

### Simplification.Direction

- Remove dead code outright.
- Where untyped dicts cause the most friction (workflow target state), improve local clarity without storing non-JSON objects in `MonitorState.data`.
- Collapse `replace_block` / `_frame_block_index` tracking — always `add_block`.
- Extract the shared frame-walking logic so the plain-text and Rich paths share one traversal.
- Add a concise comment block documenting the thread-safety contract in `loop.py`.
- Do not introduce new public types, new modules, or new features.

### Out.Of.Scope

- Do not change `MonitorFrame.blocks` from `list[dict]` to a typed block dataclass — that would ripple through render, JSON serialization, and tests. The dict shape is stable and consumed in few places.
- Do not redesign `MonitorState.data` — it is a general-purpose bag intentionally.
- Do not change CLI flags, output format, or user-visible behavior.
- Do not add tests beyond what is needed to cover changed code paths.
- Do not touch `render.py` bar rendering internals (gradient, palette, cell math) — they are correct and self-contained.

## Execution.Plan

### Slice 1 - Remove Dead Code

Status: pending.

- Delete `_format_seconds` from `workflows.py`.
- Delete `replace_block` from `MonitorFrame` in `models.py`.
- Remove `_frame_block_index` field and all references from `LimitsTrackingWorkflow._write_frame_block` in `workflows.py` — always use `frame.add_block`.
- Update `__init__.py` exports if any removed symbols were exported.
- Check:
  - existing tests pass unchanged.

### Slice 2 - Tighten Workflow Target State Helpers

Status: pending.

- Keep `MonitorState.data` JSON-native. Do not store dataclass instances inside `state.data`, because `monitor_result_payload()` emits state directly through `json.dumps(...)`.
- Do not introduce `_TargetRefreshState` in this cleanup pass unless it is strictly local and converted back to plain dict before being stored.
- Prefer smaller helper functions around the existing target-state dict shape:
  - `_new_target_state(target) -> dict[str, object]`
  - `_target_refresh_count(target_state) -> int`
  - `_target_state_summary(target_state) -> dict[str, object]`
- Keep `_target_states` as `dict[str, object]` in `workflow_state["targets"]`.
- Keep JSON output structurally identical.
- Check:
  - existing tests pass unchanged.
  - `--once --json` output is structurally identical.

### Slice 3 - Deduplicate Frame Walking

Status: pending.

- Make `format_monitor_frame` (plain-text) use `_monitor_render_rows` from `render.py` internally, extracting `.text` from each render row.
- This removes the duplicated block/row traversal in `format_monitor_frame`.
- If `_monitor_render_rows` needs to become module-level visible (not underscore-prefixed), that is acceptable since both functions are in `render.py`.
- Check:
  - `format_monitor_frame` output is identical before and after.

### Slice 4 - Document Thread Safety Contract

Status: pending.

- Add a concise docstring or comment block to `MonitorLoop` class body (not per-method) explaining:
  - The workflow thread exclusively owns `working_frame` between `working_frame_available.set()` and `working_frame_ready.set()`.
  - The main thread exclusively owns `visible_frame` at all other times.
  - The swap in `_publish_working_frame_if_ready` is safe because it only runs after the workflow thread has released ownership by setting `working_frame_ready`.
  - No lock is needed because ownership is transferred, not shared.
- Keep the comment brief — 4-6 lines max.
- Check:
  - no functional change; tests pass.

### Slice 5 - Validation

Status: pending.

- Run focused tests:

```sh
uv run pytest tests/test_agent_account_registry_commands.py -q
```

- Run full suite if practical:

```sh
uv run pytest -q
```

- Refresh installed CLI:

```sh
uv tool install --reinstall --editable .
```

- Manual smoke:

```sh
agentos agent accounts monitor --once
agentos agent accounts monitor --once --json
```

## Impl.Log

- 2026-05-15: Drafted from code review discussion. Priority-ordered findings: thread-safety documentation gap, untyped workflow state dicts, untyped frame blocks (deferred — out of scope), duplicated frame walking, dead `_frame_block_index`/`replace_block` complexity, dead `_format_seconds`, minor readability items.
- 2026-05-15: Updated Slice 2 after review: do not store dataclasses in `MonitorState.data`, because monitor JSON serializes state directly. Cleanup should keep state JSON-native and only tighten helper boundaries.
