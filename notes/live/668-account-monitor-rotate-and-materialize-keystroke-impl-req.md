# 668 — account monitor: auto-rotate workflow + `m`→materialize keystroke + 5-row log

## Impl.Abstract

- **Scope:** bring the account lifecycle into the monitor, with home writes kept
  manual.
  - **Auto-rotate workflow** (periodic, ~60s): each fire sweeps all providers with
    `capture_all_homes` + `rotate_all` — **registry-only, never writes a home.**
  - **`m` keystroke** → `rotate --materialize`: the full reconcile
    (`capture_all_homes` + `rotate_all` + `materialize_all`), which **does** write
    homes. Runs inline on the input/UI thread (it is fast; keeping it simple).
  - **5-row rotation log** in the TUI: a small block showing the last ~5 rotations
    that actually changed the active pointer (`ts · provider · account/method ·
    prev→new`). Fed by both the auto workflow and the `m` action.
- **Status:** READY.
- **Source context:** design discussion (this session). Separation of concerns:
  automation freshens the *pool/active* (safe), the human authorizes any *home*
  write with a keypress. Builds on the lifecycle primitives (capture 660, rotation
  661, materialization 664) and the drift labels (666). The monitor currently runs
  only limits-tracking (auto-prime commented in `build_monitor_workflows`,
  `workflows.py:1176`).
- **Out of scope:** automatic materialization; a real `agentos accounts` log
  subsystem (the event store here is deliberately throwaway — see the log block —
  to be revisited later); per-account/per-target monitor config (the workflow
  sweeps all providers via the primitives, it has no target list); making `m`
  async.

## Impl.Index

### Block: a pure rotation-sweep + recent-ring + block module
- Evidence: the lifecycle primitives are ready — `capture.capture_all_homes`,
  `rotation.rotate_all` (returns `RotateResult` with `changed`/`previous_active`/
  `new_active`), `materialization.materialize_all`;
  `auth_method_registry.providers_with_auth_methods()` is the sweep set.
  `monitor_log.append_monitor_log_event` (`monitor_log.py:19`) is a write-only,
  best-effort dated-JSONL audit sink (no reader).
- Decision: new `monitor/account_rotation.py` holding the framework-free heart:
  - `RotationEvent` (frozen): `ts, provider, account, method, prev, new`.
  - `sweep_rotations(*, materialize: bool) -> list[RotationEvent]` — per provider in
    `providers_with_auth_methods()`: `capture_all_homes`; `rotate_all` → collect the
    `changed` results as `RotationEvent`s; if `materialize`, `materialize_all`.
    Best-effort per provider (one provider's error must not abort the sweep). Each
    changed event is also written via `append_monitor_log_event(event=
    "account_rotation", …)` for durable audit (best-effort; display never depends on
    it).
  - `push_recent(recent: list[dict], events, *, limit=5) -> list[dict]` — append and
    keep the last `limit`. The display ring (the log file has no reader, so the
    5-row view is in-state).
  - `render_rotation_block(recent) -> dict` — a frame block (title
    `account-rotation`) of up to 5 rows, `(no rotations yet)` when empty.
- Why the in-state ring: `append_monitor_log_event` can't be read back; the "5 rows"
  come from a small list kept in `MonitorState`. This is the "very very simple"
  store — append to the existing audit log + a 5-item in-memory ring. No new file
  format, no pruning, no reader.

### Block: the auto workflow consumes the sweep (rotate only)
- Evidence: a monitor workflow is a class with `name`, `periodic_alarm_name`,
  `refresh_interval_sec`, `setup(state, frame)`, `loop(state, frame, trigger)` that
  writes a block into `frame` (`LimitsTrackingWorkflow`, `workflows.py:97`).
  `build_monitor_workflows` (`workflows.py:1165`) maps config→workflow.
  Fixed-period alarms are armed from `refresh_interval_sec` via
  `_arm_fixed_periodic_alarm`/`_workflow_period_seconds` (`loop.py:441,467`) — the
  auto-prime analog.
- Decision: `AccountRotationWorkflow` (name `account-rotation`,
  `periodic_alarm_name = ACCOUNT_ROTATION_PERIODIC_ALARM` added in `clock.py`,
  `refresh_interval_sec = 60` fixed). `loop`: when its periodic alarm (or
  startup/enter) fired → `events = sweep_rotations(materialize=False)`,
  `push_recent` into the state ring, `render_rotation_block` into the frame.
  `setup`: write the empty block.
- Decision (simplification): build it **unconditionally** in
  `build_monitor_workflows` (no per-target config; the sweep is global), and arm
  `ACCOUNT_ROTATION_PERIODIC_ALARM` at startup through the existing fixed-periodic
  arming path. This avoids a monitor-config schema change — the interval is a fixed
  default now, tunable later.

### Block: the `m` keystroke triggers a materialize sweep
- Evidence: the input thread maps chars → `loop.set_alarm(NAME)`
  (`commands.py:665`; Enter→re-prime, `r`→usage toggle); `_apply_display_alarms`
  (`loop.py:205`) runs the action when `snapshot.fired(NAME)`.
- Decision: add `MONITOR_MATERIALIZE_ALARM` (`clock.py`, a one-shot display alarm
  like the toggle). Map `m` in the input thread
  (`elif char.lower() == "m": loop.set_alarm(MONITOR_MATERIALIZE_ALARM)`). Handle it
  in `_apply_display_alarms`: `events = sweep_rotations(materialize=True)` then
  `push_recent` into the same state ring. Inline on the UI thread (accepted: fast,
  simple). The block reflects any new rotations on the next render.
- Note: `m` writes homes via `materialize_all`; if it causes no active-pointer
  change (pool already at head) there is simply no new rotation row — correct, the
  log is *rotation* events, not materialize events.

## Execution.Plan

Ordering: the framework-free module first (fully unit-testable, the heart), then the
periodic workflow that consumes it, then the keystroke. Each slice
`RED.GREEN.Test.Suite`, test-first. Mirror `test_agent_monitor_auto_prime.py` /
`test_agent_monitor_log.py` for monitor-framework test setup.

### Slice 1 — `monitor/account_rotation.py` (sweep + ring + block)
- Changes: add `RotationEvent`, `sweep_rotations`, `push_recent`,
  `render_rotation_block`.
- Path: lifecycle primitives → events → ring → block.
- Observable result: over a seeded pool where the active ref is stale and a fresher
  ref exists, `sweep_rotations(materialize=False)` returns one `RotationEvent`
  (`prev→new`) and activates the head **without** touching homes;
  `push_recent` keeps only the last 5; `render_rotation_block` renders the rows
  (and `(no rotations yet)` when empty).
- Check (RED→GREEN): new `tests/test_agent_account_rotation_monitor.py` — seed a
  codex account/home + a fresher captured ref (per the `test_agent_accounts_rotate`
  fixtures); assert the returned event, that `active_ref` moved, and that the home
  file is unchanged (no materialize); a `materialize=True` case writes the home;
  `push_recent` truncation; block shape. RED before the module exists.

### Slice 2 — `AccountRotationWorkflow` + wiring + periodic alarm
- Changes: add `ACCOUNT_ROTATION_PERIODIC_ALARM` (`clock.py`), the workflow class
  (`workflows.py`), build it unconditionally in `build_monitor_workflows`, and arm
  its fixed periodic alarm at startup (`loop.py`).
- Path: `loop` tick with the periodic alarm fired → sweep (no materialize) → block.
- Observable result: a monitor frame after a fired `ACCOUNT_ROTATION_PERIODIC_ALARM`
  contains an `account-rotation` block listing the rotation just performed; no home
  was written.
- Check (RED→GREEN): extend the monitor test — drive a `loop` with the alarm fired
  over a seeded stale pool; assert the frame block exists with the expected row and
  that `active_ref` advanced. Mirror the auto-prime workflow test harness. RED
  before the workflow is built.

### Slice 3 — `m` keystroke → materialize sweep
- Changes: add `MONITOR_MATERIALIZE_ALARM` (`clock.py`); map `m` in the input thread
  (`commands.py`); handle the fired alarm in `_apply_display_alarms` (`loop.py`)
  calling `sweep_rotations(materialize=True)` + `push_recent`.
- Path: keypress → `set_alarm` → `_apply_display_alarms` → materialize sweep.
- Observable result: firing `MONITOR_MATERIALIZE_ALARM` materializes the active ref
  into a stale home (home file updated) and records any rotation row.
- Check (RED→GREEN): extend the monitor test — invoke the loop's display-alarm
  handler with `MONITOR_MATERIALIZE_ALARM` fired over a seeded stale home; assert
  the home file now holds the active payload and the ring recorded the event. The
  raw stdin→alarm char mapping is thin glue (mirrors the untested `r` mapping) —
  cover the handler, not termios.

### Risks / deviation triggers
- **Keychain cost:** claude `capture_all_homes` shells out to `security` per home;
  fine at 60s, would not be at a tight interval. Do not lower the period.
- **Per-provider isolation:** `sweep_rotations` must wrap each provider so one
  provider's capture/keychain failure can neither abort the sweep nor crash the
  monitor tick / keystroke. Best-effort, like the rest of the monitor.
- **Inline `m`:** accepted to block the UI briefly. If a real materialize sweep is
  ever slow enough to freeze rendering noticeably, that is the trigger to move it
  off-thread (out of scope now).
- **Display vs audit:** the 5-row view reads the in-state ring, never the JSONL
  file; `append_monitor_log_event` is best-effort audit only. Do not make the block
  depend on reading the log back.
- **No home writes on the auto path:** the workflow must call `rotate_all` only —
  never `materialize_all`. Materialization belongs solely to the `m` path.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- The `account-rotation` block renders in a monitor frame (e.g. a `--once`/single
  frame render shows it, empty when no rotations).
- Auto path leaves homes untouched (a home can read `drift:home-older` after an
  auto-rotate); only `m` writes homes.
- `sweep_rotations` is the one place the lifecycle primitives are driven for the
  monitor; the workflow and the keystroke handler are thin consumers.

## Impl.Log

- (executer fills in)
