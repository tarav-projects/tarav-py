# 736 — account monitor: auto-materialize as the `account-rotation` tick default

## Impl.Abstract

**Scope.** The monitor's `account-rotation` workflow currently sweeps
`capture_all_homes` + `rotate_all` on its periodic alarm and deliberately stops
short of writing homes; `materialize_all` runs only when the user presses `m`.
Make materialization part of the ordinary periodic tick, default it on, and give
the TUI a keystroke that toggles between the new **auto-materialize** mode and
the previous **manual-only** mode for the life of the session.

**Status.** Executed. All five slices landed; 2024 tests pass, project POI count
unchanged at its 33 baseline, changes uncommitted for review.

**Source context.** Chat of 2026-08-17. The user asked for materialization to
happen automatically as the `account-rotation` main tick, with an enable/disable
config and a key to toggle it. Two questions were resolved explicitly in that
chat: the default when nothing is configured is **auto**, and the keypress is
**session-only** (it does not survive a restart).

**Out of scope.**

- persisting the toggle across restarts — explicitly declined; the config
  document supplies the startup default and nothing writes back to it
- per-provider or per-account materialize policy; the sweep stays whole-provider
  as `providers_with_auth_methods()` defines it
- changing what `materialize_all` does, how drift is classified, or the
  `non-aligned homes` block
- the accounts-log schema and the `rotate`-primitive logging path
- making the `m` keystroke asynchronous

## Impl.Index

### Policy.Reversal

- [DC] note 668 established the opposite invariant — "automation freshens the
  registry, the human authorizes any home write with a keypress." This work
  reverses that policy deliberately at the user's direction; auto is one step
  more automatic and manual-only remains reachable, so the old behavior is
  preserved as a mode rather than deleted
- [CT] the reversal is confined to *when* `materialize_all` is called. It grants
  the periodic tick the same authority the `m` keystroke already had; it does
  not widen what a materialize sweep may write

### Mode.Ownership

- [DC] the mode lives on the `AccountRotationWorkflow` instance, not in
  `state.data["monitor_display"]`. The workflow is constructed once per monitor
  run from config and dies with the process, which is exactly the session-only
  lifetime the user asked for — no display-state key to normalize, no new
  `MonitorLoop` constructor parameter, no second place the default can disagree
- [CT] the toggle alarm is therefore an ordinary **workflow** alarm, not a
  display-only one like `io.usage-variant-toggle`. It must reach the workflow
  thread, so it must not be added to `_workflow_alarm_names`' display-only set
- [CT] waking every workflow on a toggle press is cheap: each workflow gates its
  own work on its own alarm names (`limits_tracking.py:150`,
  `auto_prime.py:113`), so an unrelated snapshot is a block re-render
- [PR] the mode is shown as a **row** inside the `account-rotation` block, never
  in the block title — `_apply_clock_feedback_to_visible_frame` (`loop.py:240`)
  overwrites that title from `data["workflow"]` and the alarm countdown on every
  visible tick

### Sweep.Unification

- [CT] the periodic branch and the `m` branch become one call. Today a snapshot
  carrying both `account-rotation.periodic` and `io.account-materialize` sweeps
  twice (`workflows/account_rotation.py:57` then `:59`); one call with
  `materialize = pressed or auto` is the same behavior minus the duplicate
- [DC] `materialize_sweep()` is deleted rather than kept. It is a one-line alias
  for `sweep_rotations(materialize=True)` whose docstring asserts a `m`-only
  semantic that stops being true here; leaving it would document the old policy
  from inside the new code
- [CT] the `requested → queued → running → done` status machine is unchanged and
  is now driven by auto sweeps too, so the `account-materialize` block and the
  top-row `materialize: running` indicator work in auto mode with no new code

### Config.Surface

- [CT] `agent.accounts.monitor` entries currently accept only `limits-tracking`
  and `auto-prime-zero-limits`; `config.py:78` rejects `account-rotation` by
  name and `builder.py:54` appends the workflow unconditionally, so the workflow
  has never had a config entry at all
- [DR] an `account-rotation` entry must skip `_load_targets`. That helper
  requires a non-empty `targets` array (`config.py:170`), and this workflow has
  no target list — it sweeps every provider with an auth method
- [DC] with no entry configured the workflow is still built, with
  `auto_materialize=True`. Absent config means auto, per the user's answer; an
  entry is only needed to start in manual-only mode
- [PS] several `account-rotation` entries across merged config documents is not
  a shape anyone asked for. First entry wins, matching how the other workflows
  refuse to instantiate twice, rather than inventing a merge rule for a boolean

## Execution.Plan

### Slice 1 — auto-materialize on the periodic tick

**Status.** Landed.

`src/tarav/agent/monitor/workflows/account_rotation.py`,
`src/tarav/agent/monitor/account_rotation.py`.

- `AccountRotationWorkflow.__init__(self, *, auto_materialize: bool = True,
  refresh_interval_sec: float = 60.0)`; `refresh_interval_sec` becomes an
  instance attribute so `_workflow_period_seconds` (`loop.py:520`) still reads it
- `loop()` collapses to one sweep: compute `should_sweep` from the startup /
  enter / periodic set as today, `pressed = trigger.fired(MONITOR_MATERIALIZE_ALARM)`,
  and when `should_sweep or pressed`, sweep once with
  `materialize = pressed or self.auto_materialize`; set the `running` state
  before and the summary payload after only when `materialize`
- delete `materialize_sweep` and its `__all__` entry

**Check.** `uv run pytest tests/test_agent_account_rotation_monitor.py`

**RED first** (`tests/test_agent_account_rotation_monitor.py`):

1. `test_periodic_sweep_materializes_by_default` — periodic alarm on a default
   workflow reconciles the drifted home and writes an `account-materialize`
   block reporting `materialized: 1`.
2. `test_manual_only_mode_periodic_sweep_leaves_home` —
   `AccountRotationWorkflow(auto_materialize=False)` on the same alarm rotates
   the active pointer but leaves the home file byte-identical, and adds no
   `account-materialize` block.
3. `test_manual_only_mode_still_materializes_on_keystroke` — the same
   manual-only workflow given `io.account-materialize` writes the home.

Existing tests calling `materialize_sweep()` move to
`sweep_rotations(materialize=True)`;
`test_workflow_loop_rotates_on_alarm_and_writes_block` asserts the old
registry-only tick and must be re-pointed at a manual-only workflow, since that
is now the mode it describes.

### Slice 2 — the toggle keystroke

**Status.** Landed.

`src/tarav/agent/monitor/clock.py`,
`src/tarav/agent/monitor/workflows/account_rotation.py`,
`src/tarav/agent/monitor/loop.py`,
`src/tarav/agent/commands/monitor.py`,
`src/tarav/agent/monitor/__init__.py`.

- `MONITOR_AUTO_MATERIALIZE_TOGGLE_ALARM = "io.auto-materialize-toggle"` in
  `clock.py`, exported from `monitor/__init__.py` beside the other io alarms
- the workflow flips `self.auto_materialize` when that alarm fires, before the
  sweep decision, and performs no sweep of its own on it
- `a` joins the input thread's key handling (`Enter`, `r`, `m` are taken)
- the marquee row (`loop.py:605`) gains `a auto/manual`

**Check.** `uv run pytest tests/test_agent_account_rotation_monitor.py
tests/test_agent_monitor_loop_render.py`

**RED first:**

4. `test_toggle_alarm_flips_mode_without_sweeping` — a snapshot carrying only
   the toggle alarm flips a default workflow to manual-only, leaves the home
   untouched, and leaves the active pointer unrotated; a second toggle restores
   auto.

### Slice 3 — config entry

**Status.** Landed.

`src/tarav/agent/monitor/models.py`, `src/tarav/agent/monitor/config.py`,
`src/tarav/agent/monitor/workflows/builder.py`,
`src/tarav/agent/monitor/workflows/account_rotation.py`.

- move `ACCOUNT_ROTATION_WORKFLOW` to `models.py` beside the other workflow-name
  constants and import it in the workflow module; keep the
  `workflows/__init__.py` re-export so importers are unaffected
- `load_monitor_workflow_configs` accepts the name, and for it reads
  `refresh_interval_sec` plus a strict boolean `auto_materialize` (default
  `True`, `CliError` on a non-boolean) with `targets=()`
- `build_monitor_workflows` constructs `AccountRotationWorkflow` from the first
  such config when present and from defaults when absent, keeping the workflow
  appended last as it is today

**Check.** `uv run pytest tests/test_agent_monitor_config.py
tests/test_agent_account_rotation_monitor.py`

**RED first** (`tests/test_agent_monitor_config.py`):

5. `test_account_rotation_config_can_disable_auto_materialize` — a config
   document with `{"workflow": "account-rotation", "auto_materialize": false}`
   and no `targets` loads and builds a workflow whose mode is manual-only.
6. `test_account_rotation_defaults_to_auto_materialize` — with no such entry,
   `build_monitor_workflows` still yields the workflow and its mode is auto.
7. `test_account_rotation_config_rejects_non_boolean_auto_materialize`.

### Slice 4 — mode visibility

**Status.** Landed.

`src/tarav/agent/monitor/account_rotation.py`,
`src/tarav/agent/monitor/workflows/account_rotation.py`.

- `rotation_block_rows` gains a leading mode row: `mode: auto-materialize` or
  `mode: manual-only — m to materialize`
- the block's `data` payload gains `"auto_materialize"` so the `--json` surface
  carries the mode

**Check.** `uv run pytest tests/test_agent_account_rotation_monitor.py`

**RED first:**

8. `test_block_reports_current_mode` — the block's first row names the active
   mode in both modes, and `block.data["auto_materialize"]` agrees.

### Slice 5 — surfaces and full suite

**Status.** Landed.

- `tarav-py/AGENTS.md`: the logging section's monitor bullet
  (`AGENTS.md:316-319`) states the sweep is drive-only and rotation-only; correct
  it and state the auto/manual mode, its config key, and the `a` keystroke.
  Required by that file's own first rule.

**Check.** `uv run pytest tests/` and `ruff check src tests`, plus
`tarav skw check --skill .` if the touched files are managed surfaces.

## Impl.Log

- [TS] execution was authorized by the `/tarav-hugentics --impl --dev --AUTO`
  invocation carrying both resolved defaults (auto; session-only)
- [DC] **auto mode empties the `non-aligned homes` block by construction, and the
  existing test suite proved it.** `test_workflow_shows_non_aligned_block_when_drift_present`
  failed on the full run: its startup-alarm frame now materializes, so the drift
  it seeds is reconciled before the block is written. This is correct behavior,
  not a regression — drift reporting and drift repair on the same tick cannot
  both be observed — so the test's shared `_render_frame` helper moved to
  manual-only, the mode in which drift survives to be reported. The consequence
  is user-visible enough to be worth stating in `AGENTS.md`: a standing entry in
  that block now means materialization *could not* fix it.
- [CT] collapsing the two sweep branches removed a latent double sweep: a
  snapshot carrying both the periodic and the materialize alarm previously ran
  `capture_all_homes` + `rotate_all` twice. That was reachable — pressing `m` on
  the same tick the periodic alarm fires — and is now one sweep.
- [PS] `ruff check src tests` reports one pre-existing `F401` in
  `src/tarav/skills/routing.py:18` (`local_storage_paths` imported but unused).
  It predates this work and is untouched by it; the touched surfaces lint clean.
- [PS] the implementation was not exercised against live accounts. A real
  `tarav agent accounts monitor --once` in the new default mode writes the
  operator's actual provider homes, so the verification here is the behavior
  suite plus an import-level check of the keystroke wiring. First real run is
  the user's.
