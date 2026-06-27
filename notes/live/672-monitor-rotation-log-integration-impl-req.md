# 672 — monitor reads the accounts-log; remove rotation-display redundancy

## Impl.Abstract

- **Scope:** make the monitor's rotation display a consumer of the durable
  **accounts-log** (671), and delete the parallel paths that duplicated it. Today a
  rotation is recorded in **three** places: (1) an in-memory ring the TUI renders
  (`account_rotation_recent`, dies with the TUI), (2) a `monitor-log`
  `account_rotation` line (write-only), and (3) — since 671 — the accounts-log via
  the `rotate` primitive. The accounts-log is the durable source of truth; the other
  two are redundant. Collapse to **one source (accounts-log), one reader (the TUI
  block), zero duplication**.
- **Realignment / `No.Legacy`:** this corrects the seam left by 671, which scoped
  monitor integration out ("we integrate the monitor into it later"). 668 built the
  ring + monitor-log line *before* the accounts-log existed; now that it exists, those
  are dead/duplicate paths and must be **removed**, not kept behind both.
  Clarification: `monitor-log` itself is **not** legacy — it keeps its operational
  events (`monitor_start`, `workflow_error`, `config_stale`). Only its
  `account_rotation` line is redundant and goes.
- **End state:**
  - The `account-rotation` TUI block (last-5 rotations) reads `event="rotate"` records
    from the accounts-log (newest-first), via a new programmatic reader.
  - The in-state ring and its machinery
    (`ACCOUNT_ROTATION_RECENT_KEY`, `push_recent`, `recent_from_state`,
    `record_events`, `RotationEvent`) are deleted.
  - `sweep_rotations` / `materialize_sweep` just **drive** the lifecycle primitives
    (capture→rotate[→materialize]); rotation logging already happens inside the
    `rotate` primitive. The `monitor-log` `account_rotation` write is removed.
- **Status:** COMPLETE.
- **Source context:** session discussion on logging redundancy; builds on 671
  (accounts-log) and 668 (the original monitor rotation display). See
  `agentos-py/AGENTS.md` → "Logging System".
- **Out of scope:**
  - The **`agentos accounts log` reader CLI** — this adds a *programmatic* reader
    (consumed by the monitor); the user-facing command stays a separate deferred
    follow-up. (Keep that gap noted in AGENTS.md.)
  - The non-aligned-homes block (670) — untouched.
  - Folding the activity-log / monitor-log stacks into one shared primitive — the
    broader deferred unification.
  - Changing what counts as a rotation, the sweep cadence, the `m` keystroke
    semantics, or the rotation rank.

## Impl.Index

### Block A: a programmatic accounts-log reader
- Current state (`Hard.Evidence`): `accounts_log.py` is write-only —
  `append_account_event` + `accounts_log_dir`, no reader (`src/agentos/agent/
  accounts_log.py`). The log is daily-rolled `YYYYMMDD.jsonl`; a `rotate` record is
  `{…, event:"rotate", provider, account, method, payload:{previous_active,
  new_active}, recorded_at}` (671).
- Decision: add `read_recent_events(*, event: str | None = None, limit: int = 5)
  -> list[dict]` to `accounts_log.py`. Scan the dated files **newest filename
  first** (dates sort lexically), reading each file's lines and collecting matching
  records **newest-first**, stopping once `limit` is reached (so "last 5" can span a
  day boundary). Best-effort: missing dir / unreadable / malformed line → skip,
  never raise. Returns plain dicts (the parsed JSON records).

### Block B: the TUI rotation block reads the log
- Current state (`Hard.Evidence`): `AccountRotationWorkflow._write_block`
  (`workflows.py:1199`) renders `rotation_block_rows(recent_from_state(state))`;
  `rotation_block_rows` (`account_rotation.py:160`) consumes ring dicts shaped
  `{ts, provider, account, method, prev, new}`. The workflow `loop`
  (`workflows.py:1186`) calls `record_events(state, sweep_rotations(materialize=
  False))` on the sweep alarms.
- Decision: `_write_block` renders
  `rotation_block_rows(read_recent_events(event="rotate", limit=5))`. Reshape
  `rotation_block_rows` to consume **accounts-log `rotate` records** (read
  `recorded_at`, `provider`, `account`, `method`, and `payload.previous_active/
  new_active`) — same visible row format (`<ts>  <provider> acct/method
  prev→new`, newest-first, `(no rotations yet)` when empty). The reader already
  returns newest-first, so drop the `reversed(...)`. The workflow `loop` still
  drives the sweep on its alarms, but no longer records to state.

### Block C: remove the redundant paths (`No.Legacy`)
- Current state (`Hard.Evidence`): `account_rotation.py` holds the ring machinery
  (`ACCOUNT_ROTATION_RECENT_KEY`, `push_recent`, `recent_from_state`,
  `record_events`, `RotationEvent`) and `sweep_rotations` writes the duplicate
  `append_monitor_log_event(event="account_rotation", …)` (`account_rotation.py:59`).
  Consumers of the sweep return / state: the workflow `loop`
  (`record_events(...)`), and `loop.py:214` (`materialize_sweep(self.state)`, return
  **discarded**).
- Decision: delete the ring machinery and `RotationEvent`; remove the
  `append_monitor_log_event(event="account_rotation")` call (and its now-unused
  import if nothing else in the module uses it). `sweep_rotations(*, materialize)`
  and `materialize_sweep()` become **drive-only** (no return needed for display, no
  `state` needed) — keep per-provider best-effort isolation. Update both callers:
  the workflow `loop` just calls `sweep_rotations(materialize=False)`; `loop.py`
  calls `materialize_sweep()`. Remove the now-unused `utc_now_iso` / `MonitorState`
  imports as applicable. Any test asserting on the removed surfaces is updated to
  assert against the accounts-log (the new source of truth) or `R.active_ref`.

### Block D: keep AGENTS.md truthful
- Current state (`Hard.Evidence`): AGENTS.md "Logging System" lists the
  monitor-integration redundancy as a known gap and the accounts-log reader as a
  follow-up.
- Decision: move "monitor reads the accounts-log / redundancy removed" from *gap* to
  *done*; state monitor-log now carries only operational events; keep the
  `agentos accounts log` **reader CLI** as the remaining open follow-up. (House rule:
  AGENTS.md ships with the change.)

## Execution.Plan

Test-first (`RED.GREEN.Test.Suite`). Reach the observable endpoint fast: Slice 1
makes the reader real; Slice 2 puts logged rotations on screen (end-to-end);
Slice 3 removes the duplication; Slice 4 syncs the doc. `No.Regression`: add only the
behavior tests named; rewrite (don't accrete) the tests that covered removed paths.

### Slice 1 — accounts-log reader (Block A)
- Changes: add `read_recent_events` to `accounts_log.py`.
- Path: dated JSONL files → newest-first filtered records.
- Observable result: with several `rotate` and `capture` events written across
  files, `read_recent_events(event="rotate", limit=2)` returns the two most-recent
  `rotate` records, newest-first; `event=None` returns the most-recent of any kind;
  a missing log dir returns `[]`.
- Check (RED→GREEN): extend `tests/test_agent_accounts_log.py` — append N `rotate`
  events (and a `capture`), assert the reader's filter, limit, and newest-first
  order; assert `[]` on a fresh env. RED before the function exists.

### Slice 2 — TUI block renders logged rotations (Block B)
- Changes: rewire `_write_block` to the reader; reshape `rotation_block_rows` to the
  accounts-log record shape.
- Path: monitor frame render ← accounts-log.
- Observable result: after a real sweep rotation, the `account-rotation` block shows
  a row carrying the account (`acct/method`) and the new ref id; with no rotations it
  shows `(no rotations yet)`.
- Check (RED→GREEN): update the workflow-render test in
  `tests/test_agent_account_rotation_monitor.py` so the block assertion is satisfied
  by a rotation that was *logged* (not ring-recorded). RED while `_write_block` still
  reads the ring (the ring is no longer populated once Slice 3 lands — sequence Slice
  2's test to assert the log-sourced row). Keep the "home untouched / active moved"
  assertions.

### Slice 3 — delete the redundant paths (Block C)
- Changes: remove ring machinery + `RotationEvent` + the `monitor-log`
  `account_rotation` write; make `sweep_rotations` / `materialize_sweep` drive-only;
  update the two callers and the obsolete tests.
- Path: monitor sweep + keystroke.
- Observable result: a sweep rotation still moves the active pointer and still
  appears in the TUI block (via the log), but **nothing** is written to `monitor-log`
  for it, and `state.data` has no `account_rotation_recent` key.
- Check (RED→GREEN): replace `test_push_recent_truncates_to_five` and the
  `recent_from_state`/`record_events` assertions with: (a) a test that a sweep writes
  a `rotate` accounts-log record and **no** `monitor-log` `account_rotation` line;
  (b) the existing `R.active_ref == fresher` / home-untouched assertions stay green.
  Full suite must pass with the deleted symbols gone (import errors are the RED).

### Slice 4 — AGENTS.md sync (Block D)
- Changes: update "Logging System" per Block D.
- Observable result: the doc reflects the monitor reading the accounts-log and the
  monitor-log carrying only operational events; the reader-CLI remains the open gap.
- Check: doc-only; re-read the section.

### Risks / deviation triggers
- **Record-shape drift:** `rotation_block_rows` must read the accounts-log keys
  (`recorded_at`, `payload.previous_active/new_active`), not the old ring keys. A row
  showing blanks means the shape mapping is wrong — fix before proceeding.
- **Cross-day tail:** "last 5" may span dated files; the reader must walk files
  newest-first, not just today's. If only today's file is read, a day-boundary loses
  history.
- **Keystroke path:** `loop.py:214` discards the `materialize_sweep` return — safe to
  drop the return, but confirm no other caller depends on it.
- **Per-provider isolation:** keep the `try/except continue` around each provider in
  `sweep_rotations`; logging now lives in the primitive but the sweep must still not
  crash a tick.
- **Scope guard:** do not add the `agentos accounts log` CLI here; do not touch the
  non-aligned-homes block or sweep cadence.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- A monitor sweep rotation appears in the TUI block sourced from the accounts-log,
  writes a `rotate` accounts-log record, and writes **no** `monitor-log`
  `account_rotation` line.
- The ring symbols (`ACCOUNT_ROTATION_RECENT_KEY`, `push_recent`,
  `recent_from_state`, `record_events`, `RotationEvent`) no longer exist.
- `agentos-py/AGENTS.md` "Logging System" reflects the integration.

## Impl.Log

- All four slices done test-first (RED→GREEN). Suite 219→221, lint clean. Slices 2+3
  were implemented together (removing the ring breaks `_write_block`, so the rewire
  and the deletion land in one coherent step), each still RED→GREEN at the test level.
- Removed (No.Legacy): `RotationEvent`, `ACCOUNT_ROTATION_RECENT_KEY`, `push_recent`,
  `recent_from_state`, `record_events`, and the `monitor-log` `account_rotation`
  write. `sweep_rotations(*, materialize) -> None` and `materialize_sweep() -> None`
  are drive-only; `loop.py` keystroke and the workflow `loop` updated accordingly.
- Tests covering removed paths were rewritten to assert against the accounts-log
  (`read_recent_events`) / `R.active_ref`; `test_push_recent_truncates_to_five` was
  deleted (reader limit is covered in `test_agent_accounts_log.py`); added
  `test_sweep_writes_no_monitor_log_rotation_line` to pin the de-duplication.
- Verified no lingering references to the removed symbols across src/tests.
