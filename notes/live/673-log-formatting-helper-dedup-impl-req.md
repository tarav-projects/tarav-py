# 673 — de-duplicate the JSONL-log formatting helpers (cleanup)

## Impl.Abstract

- **Scope (cleanup):** remove repeated-knowledge duplication in the append-log
  formatting helpers. `_iso_z` (format a `datetime` as ISO-Z) and `_home_str`
  (stringify a home path) are defined **byte-identically** in both
  `src/agentos/agent/monitor_log.py` and `src/agentos/agent/accounts_log.py`, and
  `_core/clock.py:utc_now_iso` hand-rolls the same ISO-Z formatting inline. Centralize
  each piece of knowledge in one place and have the consumers use it.
- **Decision:**
  - Add `iso_z(value: datetime) -> str` to `_core/clock.py` (UTC, microseconds
    dropped, `+00:00`→`Z`), and redefine `utc_now_iso()` as `iso_z(now)` so the two
    share one formatter.
  - Add a shared home-path stringifier to `_core/project.py` (home/path is that
    module's domain); both log modules use it.
  - Delete the duplicated `_iso_z` / `_home_str` from both log modules and call the
    shared helpers.
- **Status:** COMPLETE.
- **Source context:** `hugentics-codebase-cleaner` scan (this session), after the
  accounts-log work (671) and monitor integration (672). Cleanup constraints: stay
  narrow, module-local, replace don't wrap.
- **Out of scope (do NOT touch):**
  - The **event-log mechanisms** themselves — schemas, dated-file roll, dir layout,
    and the `append_*` APIs. Folding the activity/monitor/accounts JSONL *stacks*
    into one shared event-log primitive is the user's explicitly deferred
    unification — this cleanup only de-dups two formatting helpers.
  - `project_command_log.record_activity_event` and the activity log.
  - Any change to what gets logged, when, or by whom.

## Impl.Index

### Block A: one ISO-Z formatter in `_core/clock.py`
- Current state (`Hard.Evidence`): `clock.py:utc_now_iso` =
  `datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00",
  "Z")`. `monitor_log._iso_z` / `accounts_log._iso_z` =
  `value.astimezone(UTC).isoformat().replace("+00:00","Z")` (no microsecond strip).
  Both produce a `…Z` string; they differ only in microsecond handling.
- Decision: introduce `iso_z(value: datetime) -> str` in `clock.py` that normalizes
  to UTC, **drops microseconds**, and `Z`-formats; redefine `utc_now_iso()` to
  `iso_z(datetime.now(timezone.utc))`. The log modules format their single
  already-captured `now` via `iso_z(now)` (keeps the filename and `recorded_at`
  derived from the **same** timestamp — no second `now()` call). Net behavior change:
  the two append logs' `recorded_at` now drops sub-second precision, matching the
  house-wide `utc_now_iso` convention. `utc_now_iso()` output is unchanged.

### Block B: one home-path stringifier in `_core/project.py`
- Current state (`Hard.Evidence`): `_home_str(home) -> str | None` is identical in
  both log modules — `None`→`None`, else `str(Path(home).expanduser())` with a
  `str(home)` fallback on error. `_core/project.py` already owns the agentos
  home/path domain (`agentos_home_dir`).
- Decision: add a shared `home_path_str(home: Path | str | None) -> str | None` to
  `_core/project.py` with the same semantics; both log modules import and use it and
  drop their local copies.

## Execution.Plan

Two behavior-preserving slices (except the intended microsecond drop in the two
logs). Verification = the existing suite (`utc_now_iso` is used by ~8 modules; the
log tests cover the helpers) plus a focused `iso_z` check. `No.Regression`: add only
the one `iso_z` unit check; do not add tests for unchanged behavior.

### Slice 1 — shared `iso_z` (Block A)
- Changes: add `iso_z` to `clock.py`; redefine `utc_now_iso` via it; switch both log
  modules to `iso_z(now)` and delete their `_iso_z`.
- Path: `append_monitor_log_event` / `append_account_event` → `recorded_at`.
- Observable result: both append logs still write a `…Z` `recorded_at` derived from
  the same datetime used for the daily filename; `utc_now_iso()` is unchanged.
- Check (RED→GREEN): add a unit test for `iso_z` (a fixed aware datetime → expected
  `…Z`, microseconds dropped); RED before `iso_z` exists. Confirm the existing
  `tests/test_agent_monitor_log.py` and `tests/test_agent_accounts_log.py` stay green
  (they assert the `Z` suffix / round-trip, not microseconds).

### Slice 2 — shared `home_path_str` (Block B)
- Changes: add `home_path_str` to `_core/project.py`; both log modules import it and
  delete their `_home_str`.
- Path: the `home=` argument of both append functions.
- Observable result: a `home` passed to either append function is stored as the same
  expanded string as before; `None` stays `None`.
- Check (RED→GREEN): the existing log tests that exercise the `home` field stay
  green; if none asserts it directly, the `accounts_log` `capture`/`materialize`
  emit tests (which pass `home=`) cover the path. No new test needed beyond green.

### Risks / deviation triggers
- **Microsecond drop:** if any test pins sub-second precision in a log
  `recorded_at`, that is the intended change — update that assertion, do not revert.
  If something *functional* depends on sub-second ordering (nothing found), stop.
- **Single-`now` discipline:** keep deriving the filename and `recorded_at` from one
  captured `now` in each append function — do not introduce a second `now()` call.
- **Scope guard (hard boundary):** do not touch the append APIs, schemas, dirs, the
  activity log, or begin any cross-stack log unification. A change that reshapes those
  aborts the run.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- `_iso_z` and `_home_str` no longer exist in either log module; `iso_z` /
  `home_path_str` exist once in `_core` and are the only definitions.
- `utc_now_iso()` behavior unchanged.

## Impl.Log

- (empty — not started)
