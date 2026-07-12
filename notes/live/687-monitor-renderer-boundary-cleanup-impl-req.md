# 687 — monitor renderer boundary cleanup

## Impl.Abstract

- **Scope:** narrow cleanup of `src/agentos/agent/monitor/` after the materialize-trigger hardening work.
- **Target:** monitor loop, account-rotation monitor helpers, and renderer-row/block usage.
- **Status:** implemented.
- **Source:** `$hugentics-codebase-cleaner --AUTO`, target monitor and renderer systems.
- **Out of scope:** changing monitor behavior, redesigning workflow scheduling, changing CLI flags, adding new renderer primitives, or broad formatting cleanup.

## Impl.Index

### Cleanup.Theme.Workflow.Priority.Boundary

- `MonitorLoop._workflows_for_snapshot` currently knows the literal workflow name `"account-rotation"` to prioritize materialization.
- That leaks a workflow implementation detail into the generic loop.
- Better local boundary: workflows may optionally expose a `priority_for_snapshot(snapshot)` method; the loop asks for a priority without knowing workflow names.

### Cleanup.Theme.Materialize.State.Knowledge

- Materialize monitor state currently repeats loose strings and key names across `loop.py`, `workflows/account_rotation.py`, and `account_rotation.py`.
- The repeated knowledge is small but sensitive: `account_materialize`, `requested`, `queued`, `running`, and top-row visibility rules.
- Better local boundary: centralize these constants/helpers in the account-rotation monitor helper module and use them from both loop and workflow code.

### Cleanup.Theme.Renderer.Model.Use

- `account-materialize` display should remain built from monitor row/block model objects (`MonitorInfoRow`, `MonitorTextRow`, `MonitorFrame.add_block`).
- Cleanup should clarify row construction and visible-result filtering without bypassing `render.py` or adding print-style rendering.

### Cleanup.Theme.Render.Order.Boundary

- Materialize responsiveness requires `account-rotation` to execute before `limits-tracking` when the `m` alarm fires.
- Visual block order should not depend on execution order.
- Better local boundary: renderer/payload emission should apply canonical block ordering while leaving the underlying `MonitorFrame.blocks` append order intact.

## Execution.Plan

### Vertical.Slice 1 — Workflow priority protocol

- **Status:** complete.
- **Target:** `src/agentos/agent/monitor/loop.py`, `src/agentos/agent/monitor/workflows/account_rotation.py`, `tests/test_agent_monitor_loop_render.py`.
- **Change:** add an optional priority hook to the monitor workflow protocol and replace literal `"account-rotation"` sorting with hook-based ordering.
- **Check:** update the existing priority test to prove the hook, not a name literal, controls ordering.
- **Acceptance:** no workflow name literal remains in `loop.py` for materialize priority.

### Vertical.Slice 2 — Materialize state helpers

- **Status:** complete.
- **Target:** `src/agentos/agent/monitor/account_rotation.py`, `src/agentos/agent/monitor/loop.py`, `src/agentos/agent/monitor/workflows/account_rotation.py`.
- **Change:** centralize materialize state key/status constants and state payload helpers.
- **Check:** existing requested/queued/running/done monitor tests still pass.
- **Acceptance:** `loop.py` and workflow code no longer hand-build `account_materialize` dicts or repeat active status sets.

### Vertical.Slice 3 — Materialize block row cleanup

- **Status:** complete.
- **Target:** `src/agentos/agent/monitor/account_rotation.py`, `tests/test_agent_account_rotation_monitor.py`.
- **Change:** make visible-result filtering and summary row construction clearer through small module-local helpers/constants.
- **Check:** existing test continues proving aligned rows are not rendered and drift/action rows are rendered.
- **Acceptance:** behavior unchanged; renderer rows remain typed monitor rows.

### Vertical.Slice 4 — Verification

- **Status:** complete.
- **Checks:** `uv run pytest tests/test_agent_monitor_loop_render.py tests/test_agent_account_rotation_monitor.py`; `uv run ruff check src/agentos/agent/monitor tests/test_agent_monitor_loop_render.py tests/test_agent_account_rotation_monitor.py`.
- **Acceptance:** targeted tests and lint pass; diff remains scoped to monitor/renderer cleanup plus this Impl.Req.

### Vertical.Slice 5 — Canonical visual block order

- **Status:** complete.
- **Target:** `src/agentos/agent/monitor/render.py`, `tests/test_agent_monitor_loop_render.py`.
- **Change:** sort known monitor blocks at the renderer/payload boundary so visual order is stable even when materialize execution prioritizes account-rotation.
- **Check:** add a regression test where `account-rotation` and `account-materialize` are appended before `limits-tracking`, but render/payload order still shows `limits-tracking`, `account-rotation`, then `account-materialize`.
- **Acceptance:** workflow execution priority remains unchanged; `MonitorFrame.blocks` remains append-owned by workflows; printed and payload block order are canonical.

## Impl.Log

- **Pre-cleanup checkpoint:** `ab58c85 fix: harden monitor materialize trigger`.
- **Execution checkpoint:** `d7b7019 chore: monitor cleanup execution checkpoint`.
- **Decision:** `--AUTO` skips cleaner's ordinary confirmation checkpoint; proceed with the scoped cleanup Impl.Req.
- **Deviation:** follow-up `$agentos-hugentics-impl --exec --AUTO` requested execution of the visual-order fix without an explicit commit authorization; repo AGENTS says commits are user-gated, so no new execution checkpoint commit was created.
- **Implemented:** monitor workflow materialize priority now uses an optional workflow hook instead of a hard-coded workflow name in `loop.py`.
- **Implemented:** materialize state keys/status strings/top-row status membership now live in the account-rotation monitor helper module.
- **Implemented:** materialize block row rendering now uses small module-local helpers for count rows and visible action-result filtering.
- **Implemented:** renderer/payload emission now applies canonical block order for known monitor blocks, decoupling visual order from workflow execution order.
- **Verified:** `uv run pytest tests/test_agent_monitor_loop_render.py tests/test_agent_account_rotation_monitor.py` — 24 passed.
- **Verified:** `uv run ruff check src/agentos/agent/monitor tests/test_agent_monitor_loop_render.py tests/test_agent_account_rotation_monitor.py` — passed.
- **Verified:** `uv run pytest tests/test_agent_monitor_loop_render.py tests/test_agent_account_rotation_monitor.py` — 25 passed.
- **Verified:** `uv run python -m py_compile src/agentos/agent/monitor/render.py` — passed.
- **Verified:** `uv run ruff check src/agentos/agent/monitor tests/test_agent_monitor_loop_render.py tests/test_agent_account_rotation_monitor.py` — passed.
