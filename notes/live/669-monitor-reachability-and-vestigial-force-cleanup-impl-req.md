# 669 — fix account-rotation reachability + drop vestigial materialize `--force`

## Impl.Abstract

- **Scope (cleanup):** fix one integration gap and remove one dead CLI flag, both
  surfaced by a general scan of the account system.
  - **A. Integration — the always-on account-rotation workflow is unreachable
    without unrelated config.** `build_monitor_loop` raises
    `CliError("…must configure at least one workflow")` when there are zero workflow
    *configs* (`config.py:147`), but the `AccountRotationWorkflow` (668) is
    config-free and appended **unconditionally inside** `build_monitor_workflows`.
    So the monitor refuses to start — and account-rotation never runs — unless a
    limits-tracking config happens to exist. Make the monitor runnable with zero
    configs (account-rotation is always present), with an empty-safe config
    fingerprint.
  - **B. Legacy — vestigial `--force` on `accounts materialize`.** The
    `materialize` subparser declares `--force` (`commands.py:~961`) but the handler
    stopped reading `args.force` in the 665 extraction — a declared flag that does
    nothing. Remove it. (The identically-named `--force` on `sessions copy` is real,
    used at `commands.py:717` — leave it.)
- **Status:** COMPLETE.
- **Source context:** `hugentics-codebase-cleaner` general scan (this session),
  after the monitor work (668) and the materialize extraction (665). Cleanup
  constraints: narrow, module-local, replace don't wrap.
- **Out of scope:** the deliberately-commented auto-prime branch in
  `build_monitor_workflows` (the user disconnected it on purpose at session start —
  not legacy); any change to account-rotation behavior, `materialize` semantics, or
  the monitor config schema.

## Impl.Index

### Block A: the monitor must start when only the always-on workflow exists
- Current state (`Hard.Evidence`): `build_monitor_loop` (`config.py:140`) →
  `configs = load_monitor_workflow_configs(...)`; `if not configs: raise CliError`;
  then `MonitorLoop(workflows=build_monitor_workflows(configs),
  config_fingerprint=configs[0].config_fingerprint, …)`. `build_monitor_workflows`
  (`workflows.py:1213`) now always appends `AccountRotationWorkflow()`, so the
  returned tuple is never empty. `MonitorLoop` accepts `config_fingerprint=None`
  (`loop.py:68`, handled by `_check_config_fingerprint`, `loop.py:394`);
  `monitor_config_fingerprint(start_path=…)` is empty-safe (hashes empty documents).
  No test pins the raise or calls `build_monitor_loop`.
- Decision: drop the `if not configs: raise`. The loop always has at least
  account-rotation, so "at least one workflow" is now always true and the guard is
  stale/wrong. Replace the fingerprint source so it does not index an empty
  `configs`: use `configs[0].config_fingerprint if configs else
  monitor_config_fingerprint(start_path=start_path)` (the loader is already
  `monitor_config_fingerprint`, so this stays consistent). Result: running the
  monitor with no limits-tracking config starts and shows the (empty)
  `account-rotation` block.

### Block B: remove the no-op `--force` from materialize
- Current state (`Hard.Evidence`): `accounts_materialize_parser.add_argument(
  "--force", …)` exists; `_cmd_agent_accounts_materialize` /
  `materialize_account` never read `force` (since 665). Two tests
  (`test_agent_accounts_materialize.py:35`, `test_codex_accounts_materialize.py:48`)
  pass `force=False` in the handler `Namespace` purely as leftover.
- Decision: delete the `--force` argument from the materialize subparser, and drop
  the now-meaningless `force=False` from those two test `Namespace`s. `No.Legacy`:
  the CLI should not advertise a flag it ignores.

## Execution.Plan

Two independent slices, each behaviour-preserving except the one intended change.
Verification is the existing suite (monitor-config + materialize coverage) plus a
new focused check for Block A. `No.Regression`: add only the Block-A behavior test.

### Slice 1 — monitor runnable with zero configs (Block A)
- Changes: in `build_monitor_loop`, remove the empty-configs `raise` and make the
  fingerprint empty-safe (per Block A).
- Path: `build_monitor_loop(start_path=…)` with no workflow config documents.
- Observable result: it returns a `MonitorLoop` whose workflows include
  `AccountRotationWorkflow` (no `CliError`); with configs present, behavior is
  unchanged.
- Check (RED→GREEN): new test (e.g. in a monitor-config test module) — call
  `build_monitor_loop` against a start path with no monitor workflow config and
  assert it returns a loop containing the `account-rotation` workflow (RED today:
  raises `CliError`). Keep/confirm an existing-config case still builds.

### Slice 2 — drop vestigial `--force` (Block B)
- Changes: remove the `--force` arg from the materialize subparser; drop
  `force=False` from the two materialize handler tests' `Namespace`s.
- Path: `agent accounts materialize …` arg parsing.
- Observable result: `agent accounts materialize --help` no longer lists `--force`;
  materialize still works (check / real / aligned paths unchanged).
- Check (RED→GREEN): the existing materialize tests stay green after dropping the
  `force` field (they never exercised it). Optionally assert the parser rejects
  `--force` — but the minimal, sufficient check is the green suite with `force`
  removed from the Namespaces. No new behavior to test.

### Risks / deviation triggers
- **Block A fingerprint:** must not `IndexError` on empty `configs`; route through
  `monitor_config_fingerprint` when empty. Confirm `_check_config_fingerprint`
  tolerates the value (it already handles `None` and a loader).
- **Do not touch** the commented auto-prime branch (intentional disconnect) or the
  real `sessions copy --force`.
- **Scope guard:** if removing the `raise` surfaces another caller that depended on
  it (none found), stop rather than widen.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- `build_monitor_loop` returns a loop (with account-rotation) given zero configs.
- `agent accounts materialize --help` does not advertise `--force`.

## Impl.Log

- Both slices done. Suite 205→206 (+1 reachability test), lint clean.
- Block A: `CliError` import stays (still used by ~25 other validators in
  `config.py`). The empty-configs fingerprint routes through
  `monitor_config_fingerprint` (empty-safe); `MonitorLoop` tolerated it.
- Block B verified live: `agent accounts materialize --help` no longer advertises
  `--force`; the two materialize handler tests stay green with `force` dropped from
  their `Namespace`s.
- Left untouched per scope: the intentionally-commented auto-prime branch and the
  real `sessions copy --force`.
