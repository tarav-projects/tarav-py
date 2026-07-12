# 686 — monitor materialize keystroke robustness

## Impl.Abstract

- **Scope:** make `agentos agent accounts monitor` handle `m` materialization robustly when workflow work is already active, surface visible materialize status through monitor renderer rows/blocks, and report materialize sweep results instead of silently swallowing them.
- **Source:** user-reported intermittent stale/no-feedback behavior when pressing `m`; local diagnosis found the monitor uses a single pending workflow snapshot slot that can be overwritten by later workflow alarms.
- **Status:** implemented.
- **Out of scope:** redesigning account registry semantics, changing `agentos agent accounts materialize` CLI flags, changing provider credential formats, or adding a user-facing accounts-log CLI.

## Impl.Index

### Current.Monitor.M.Path

- `agentos-py/src/agentos/agent/commands/monitor.py` maps `m` to `MONITOR_MATERIALIZE_ALARM`.
- `agentos-py/src/agentos/agent/monitor/loop.py` currently stores one pending `MonitorClockSnapshot` in `_pending_workflow_snapshot`.
- A later workflow alarm can replace an unconsumed materialize snapshot before the workflow thread takes it.
- `agentos-py/src/agentos/agent/monitor/workflows/account_rotation.py` only writes homes when the received trigger includes `MONITOR_MATERIALIZE_ALARM`.

### Materialize.Semantic.Difference

- Direct `agentos agent accounts materialize` calls `materialize_account(provider, account, method, home)` and returns one explicit `MaterializeResult`.
- Monitor `m` calls `materialize_sweep()`, which runs `capture_all_homes`, `rotate_all`, and `materialize_all` across providers with auth methods.
- `materialize_all` can return `aligned` or `skipped` results; current monitor code discards them.
- `sweep_rotations` currently catches all provider exceptions and continues without exposing status.

### Renderer.Constraint

- Visual additions should use existing monitor renderer model surfaces: typed row objects and monitor blocks.
- Use `MonitorTextRow`/`MonitorInfoRow` and `MonitorFrame.add_block`; do not print from workflow code or bypass `render.py`.

## Execution.Plan

### Vertical.Slice 1 — Merge pending workflow alarms

- **Status:** complete.
- **Target:** `src/agentos/agent/monitor/loop.py`, `tests/test_agent_monitor_loop_render.py`.
- **Behavior:** if a workflow snapshot is pending and another workflow alarm fires before consumption, the pending snapshot keeps both alarm names instead of replacing the earlier one.
- **RED check:** add a loop-level test that simulates `MONITOR_MATERIALIZE_ALARM` pending and `ACCOUNT_ROTATION_PERIODIC_ALARM` arriving before consumption; assert both are delivered.
- **GREEN implementation:** change pending snapshot handling to merge fired alarms while preserving a sensible latest tick/alarm snapshot.
- **Acceptance:** materialize alarm cannot be lost to a later periodic alarm.

### Vertical.Slice 2 — Return materialize sweep results

- **Status:** complete.
- **Target:** `src/agentos/agent/monitor/account_rotation.py`, `tests/test_agent_account_rotation_monitor.py`.
- **Behavior:** materialize sweep returns provider-scoped result records for materialized/aligned/skipped/error outcomes instead of returning `None`.
- **RED check:** add test for a skipped home and a provider error/status result without relying on printed output.
- **GREEN implementation:** introduce a small monitor-owned result dataclass or JSON-shaped dict list; preserve best-effort provider isolation but record failures.
- **Acceptance:** caller can count `materialized`, `aligned`, `skipped`, and `error` results.

### Vertical.Slice 3 — Render visible `m` acknowledgement/status

- **Status:** complete.
- **Target:** `src/agentos/agent/monitor/workflows/account_rotation.py`, `src/agentos/agent/monitor/workflows/state.py` if needed, monitor render tests.
- **Behavior:** pressing `m` produces a visible monitor block/status using renderer model rows: requested/running/done/skipped/failed.
- **RED check:** workflow test fires `MONITOR_MATERIALIZE_ALARM` and asserts an `account-materialize` block appears with status/count rows.
- **GREEN implementation:** store latest materialize summary in `MonitorState.data` and write a monitor block with `MonitorInfoRow`/`MonitorTextRow`.
- **Acceptance:** monitor frame exposes materialize result in normal text and JSON render paths.

### Vertical.Slice 4 — Verification and docs touch

- **Status:** complete.
- **Target:** targeted tests and `AGENTS.md` only if documented subsystem behavior changes.
- **Checks:** `uv run pytest tests/test_agent_monitor_loop_render.py tests/test_agent_account_rotation_monitor.py`.
- **Acceptance:** targeted tests pass, diff is scoped, Impl.Req status/log updated.

## Impl.Log

- **Deviation:** execution module asks for a checkpoint commit before edits. Project AGENTS policy says commits are user-gated and the user did not explicitly request a commit. Proceeding without a checkpoint commit and leaving changes uncommitted for review.
- **Implemented:** pending workflow snapshots now merge fired alarm names instead of replacing earlier unconsumed alarms.
- **Implemented:** monitor materialize sweeps now return per-home/per-provider result records, including skipped homes and provider errors.
- **Implemented:** monitor `m` now exposes requested/running state in top rows and a post-sweep `account-materialize` block using monitor row/block renderer model surfaces.
- **Follow-up implemented:** `requested` is now only the immediate keypress acknowledgement; after the materialize alarm is queued for the workflow thread, the top-row state becomes `queued`, avoiding a misleading permanent `requested` line while account data fetching is active.
- **Follow-up correction:** `account-materialize` now renders only materialize-relevant outcomes (`materialized`, `skipped`, `error`) and no longer lists aligned homes or aligned counts.
- **Follow-up correction:** materialize-triggered workflow cycles prioritize the `account-rotation` workflow before limits/auto-prime work, so a merged materialize+periodic trigger writes homes before slow account-data refresh. This does not interrupt a workflow already mid-fetch when `m` is pressed.
- **Verified:** `uv run pytest tests/test_agent_monitor_loop_render.py tests/test_agent_account_rotation_monitor.py` — 21 passed.
- **Verified:** `uv run ruff check src/agentos/agent/monitor tests/test_agent_monitor_loop_render.py tests/test_agent_account_rotation_monitor.py` — passed.
- **Re-verified after queued-state follow-up:** `uv run pytest tests/test_agent_monitor_loop_render.py tests/test_agent_account_rotation_monitor.py` — 22 passed.
- **Re-verified after queued-state follow-up:** `uv run ruff check src/agentos/agent/monitor tests/test_agent_monitor_loop_render.py tests/test_agent_account_rotation_monitor.py` — passed.
- **Re-verified after display/priority correction:** `uv run pytest tests/test_agent_monitor_loop_render.py tests/test_agent_account_rotation_monitor.py` — 24 passed.
- **Re-verified after display/priority correction:** `uv run ruff check src/agentos/agent/monitor tests/test_agent_monitor_loop_render.py tests/test_agent_account_rotation_monitor.py` — passed.
