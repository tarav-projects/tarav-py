# 671 — accounts lifecycle event log (emit from all account primitives)

## Impl.Abstract

- **Scope:** add a dedicated, durable **accounts event log** and emit a lifecycle
  event from **every account primitive** — capture, activate, materialize, rotate —
  so both the CLI and (later) the monitor log uniformly. Logging lives in the
  primitive layer, per the FUNDAMENTAL rule "primitives are the source of truth; the
  CLI is just a consumer." Each `_all` sweep and each CLI handler inherits logging
  for free because they call the per-item primitive.
- **Log file:** `~/.agentos/agent/accounts-log/YYYYMMDD.jsonl` (daily roll, UTC),
  one JSON object per line. Append is **best-effort** — it never raises into the
  caller (mirrors `monitor_log.append_monitor_log_event`).
- **Secret-free:** events carry only `ref_id` / `artifact_id` (content hashes) and
  identifiers — never `Auth.Data`. Same rule as everywhere else in the account
  system.
- **Emit only on real effect** — never on a preview:
  - `capture_home`: emit `capture` only when `is_new and not dry_run` (a real
    capture-log append). Payload `{ref_id, artifact_id}`.
  - `activate`: emit `activate` (always commits; no dry-run). Payload `{ref_id}`.
  - `materialize_account`: emit `materialize` only when `status == "materialized"`
    (an actual home write) — not on `aligned`/`check`/`skipped`. Payload
    `{active_ref, captured_ref}`.
  - `rotate`: emit `rotate` only when `changed and not dry_run`. Payload
    `{previous_active, new_active}`.
- **Status:** COMPLETE.
- **Source context:** this session's logging research (see `agentos-py/AGENTS.md` →
  "Logging System"). User directive: do the `~/.agentos/agent/accounts-log/…` file,
  for all account primitives; **integrate the monitor into it later**.
- **Out of scope (this iteration):**
  - **Monitor integration.** Do not touch `monitor/account_rotation.py` or the
    monitor sweep's existing `append_monitor_log_event(event=account_rotation,…)`.
    Note: because the monitor sweep calls `rotate_all → rotate`, monitor-driven
    rotations *will* now also land in the accounts log via the primitive — that is
    desired. The monitor keeps its own monitor-log line for now; de-duplicating /
    fully routing the monitor through this log is the deferred follow-up.
  - **A reader CLI** (`agentos accounts log` tail/query). Deliberately deferred —
    this iteration is the write side only. Flag as the obvious next follow-up so the
    log does not stay write-only like monitor-log.
  - Folding the existing activity-log / monitor-log stacks into one shared event-log
    primitive (the broader unification) — deferred.

## Impl.Index

### Block A: the accounts-log append primitive
- Current state (`Hard.Evidence`): `monitor_log.py`
  (`src/agentos/agent/monitor_log.py`) is the closest existing pattern — a dated
  JSONL appender: `append_monitor_log_event(*, event, payload, …) -> Path | None`,
  daily `YYYYMMDD.jsonl`, schema `{schema_version, class, recorded_at, event, …,
  payload}`, best-effort `try/except → None`, serialize-before-open. Account
  primitives live under `src/agentos/agent/{capture,activation,materialization,
  rotation}.py`; each has a frozen `*Result` dataclass carrying exactly the ids the
  events need (`CaptureResult.is_new/ref_id/artifact_id`,
  `ActivateResult.ref_id`, `MaterializeResult.status/active_ref/captured_ref`,
  `RotateResult.changed/skipped/previous_active/new_active`).
- Decision: new module `src/agentos/agent/accounts_log.py` with
  `accounts_log_dir() -> ~/.agentos/agent/accounts-log` and
  `append_account_event(*, event, provider, account, method, payload=None,
  home=None) -> Path | None`. Schema mirrors monitor-log for consistency:
  `{schema_version, class="agentos.agent.accounts-log", recorded_at (ISO-Z), event,
  provider, account, method, home, payload}`. Best-effort: serialize first, then
  `mkdir`+append; any exception → return `None` (never crash a primitive). Reuse the
  monitor-log helpers' style (do not import its private helpers — keep this module
  self-contained, it is a sibling not a subtype).

### Block B: emit from each primitive (on real effect only)
- Current state (`Hard.Evidence`): the four primitives and their effect gates —
  `capture_home` appends only when `is_new and not dry_run`
  (`capture.py:50`); `activate` always calls `set_active` then returns
  (`activation.py:25`); `materialize_account` returns a `status` discriminating the
  real-write case (`materialization.py:34`); `rotate` sets `changed` true only when
  it moved the active pointer for a non-dry run (`rotation.py:41`).
- Decision: add one `append_account_event(...)` call inside each per-item primitive
  at its real-effect branch (the four gates above). Because the sweeps
  (`capture_all_homes`, `materialize_all`, `rotate_all`) and the CLI handlers all
  funnel through these per-item primitives, no call site outside the primitives
  changes. Payloads as listed in `Impl.Abstract`. Never emit on `dry_run`/`check`/no
  effect.

### Block C: keep AGENTS.md truthful
- Current state (`Hard.Evidence`): `agentos-py/AGENTS.md` → "Logging System" lists
  three mechanisms and, under "Known gaps"/"Direction", describes the accounts log as
  not-yet-existing.
- Decision: update that section — add the accounts-log as a fourth, real mechanism
  (path/schema/writers), and move "emit lifecycle events from the primitives" from
  *direction* to *done*, leaving the monitor-integration and reader-CLI items as the
  remaining open follow-ups. (House rule: update AGENTS.md when the system changes.)

## Execution.Plan

Vertical slices, test-first (`RED.GREEN.Test.Suite`). Reach an observable endpoint
fast: Slice 1 makes the appender real and tested; Slices 2–5 wire one primitive each
(each independently observable by reading the day's JSONL); Slice 6 is the doc sync.
`No.Regression`: add only the behavior tests below.

### Slice 1 — the append primitive (Block A)
- Changes: create `accounts_log.py` with `accounts_log_dir` +
  `append_account_event`.
- Path: any caller → dated JSONL line.
- Observable result: calling `append_account_event(event="x", provider="codex",
  account="jp", method="file", payload={"a":1})` writes one parseable line under
  `accounts_log_dir()` with the schema fields; an unserializable payload returns
  `None` and writes nothing (no partial line).
- Check (RED→GREEN): new `tests/test_agent_accounts_log.py` — assert the written
  record round-trips (event/provider/account/method/payload present, `recorded_at`
  ISO-Z, daily filename), and best-effort: a bad payload (`{"x": object()}`) →
  `None`. RED before the module exists.

### Slice 2 — rotate emits (Block B)
- Changes: in `rotation.rotate`, after a real pointer move (`changed and not
  dry_run`), `append_account_event(event="rotate", …, payload={previous_active,
  new_active})`.
- Path: `agent accounts rotate` and `rotate_all` (monitor + CLI) → accounts log.
- Observable result: a rotate that changes the active ref writes one `rotate` line;
  a `dry_run` rotate or a no-op writes nothing.
- Check (RED→GREEN): in the test module, seed a stale active + a fresher capture,
  call `rotate`, assert exactly one `rotate` event with the right prev/new; call with
  `dry_run=True` (fresh env) and assert no event. Follow the registry/seed pattern in
  `tests/test_agent_rotation.py`.

### Slice 3 — capture emits (Block B)
- Changes: in `capture.capture_home`, inside the `is_new and not dry_run` branch,
  emit `capture` with `{ref_id, artifact_id}`.
- Observable result: a first-time capture of a home writes one `capture` line; a
  repeat capture (already in the capture log) or a `dry_run` writes nothing.
- Check (RED→GREEN): seed a home, `capture_home` once → one event; call again → no
  new event; `dry_run=True` → no event. Pattern from
  `tests/test_agent_account_status_report.py` / capture tests.

### Slice 4 — activate emits (Block B)
- Changes: in `activation.activate`, after `set_active`, emit `activate` with
  `{ref_id}`.
- Observable result: an `activate` call writes one `activate` line carrying the
  resolved ref id.
- Check (RED→GREEN): seed a capture, `activate(provider, account, method, prefix)`,
  assert one `activate` event with that `ref_id`.

### Slice 5 — materialize emits (Block B)
- Changes: in `materialization.materialize_account`, only on the
  `status == "materialized"` branch, emit `materialize` with `{active_ref,
  captured_ref}`.
- Observable result: a materialize that writes a home emits one `materialize` line;
  an `aligned`/`check`/`skipped` outcome emits nothing.
- Check (RED→GREEN): drifted home + active set → materialize → one event; same with
  `check=True` → no event; an already-aligned home → no event. Pattern from
  `tests/test_agent_materialization.py`.

### Slice 6 — AGENTS.md sync (Block C)
- Changes: update the "Logging System" section per Block C.
- Observable result: AGENTS.md lists the accounts-log as a real mechanism; the
  primitive-emit item is no longer under "Direction".
- Check: doc-only; no test. Verify by re-reading the section.

### Risks / deviation triggers
- **Emit placement:** the call must sit *inside* the real-effect gate, not before it
  — logging a capture/rotate/materialize that did not actually persist is a defect.
  If a primitive's effect gate is not a single clear branch, stop rather than guess.
- **Best-effort contract:** `append_account_event` must never raise into a primitive
  (a logging failure cannot break capture/rotate/etc.). Mirror monitor-log's
  `try/except → None`.
- **Secrets:** payloads carry ids only. If any field would embed `Auth.Data`, stop.
- **Interim double-log:** monitor rotations will now appear in *both* accounts-log
  (via the rotate primitive) and monitor-log (via the untouched sweep). Expected;
  do not "fix" it here — that is the deferred monitor-integration follow-up.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- Each of capture/activate/materialize/rotate writes exactly one accounts-log line
  on a real effect, and nothing on a preview/no-op.
- `agentos-py/AGENTS.md` "Logging System" reflects the new mechanism.

## Impl.Log

- All six slices done test-first (RED→GREEN). Suite 210→219 (+9 tests), lint clean.
- No deviations from the plan. Emits sit inside each primitive's real-effect gate
  (`rotate`: `changed and not dry_run`; `capture_home`: `is_new and not dry_run`;
  `materialize_account`: the `status="materialized"` branch; `activate`: after
  `set_active`). No call site outside the primitives changed.
- Decision in open space: all behavior tests live in one self-contained module
  (`tests/test_agent_accounts_log.py`) using the codex JWT seed pattern, so the emit
  tests don't depend on other test modules' fixtures.
- No circular import: `accounts_log` depends only on `_core.project`.
