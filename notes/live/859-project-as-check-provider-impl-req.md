# 859 — The Project is a CheckProvider

<!-- tarav.sessions
64298cbc = claude-code:9da4cef5-68b7-4d17-8a06-1351ca51e82f @64298cbc8db2e7aa971e0828653c07bcb483cfed40931fdf87d5abe7ce1c60b3
-->

## Impl.Abstract

Knowledge.Surface: wiki
Alignment.Mode: Interactive
Status: ready (Develop).

Revise [858](858-project-checks-entry-point-impl-req.md): the Project's checks
live in `checks()`, because `TaravProject` is an ordinary `CheckProvider`;
`TaravProject.check()` is removed. `CheckProvider.checks` becomes a method
returning an iterable (typically a generator). `tarav check --project` runs
the Project's checks one by one and prints each result as it arrives.

Non-goals: hooks; selection or profiles; changing `run_checks()`; any
concrete Project's checks (g70203's placeholder is g70203 request 535).

## Design narrative

### User decisions

The User preferred a method to a property: callers do not expect reading a
property to take ten minutes.
<!-- tarav.breadcrumb a7dd82d9f1192ed7f3126bfe792784678ccdc8fa2b7d9cbc3d02e82ad2c8fb1f -->

Returning a generator is good design: it returns quickly, and the checks run
only if the caller runs them.
<!-- tarav.breadcrumb 7244c5ae69aa39236eba44f03c5f5db5ab2c1192a0c7763acf57722631be8d73 -->

`project.check()` is rejected — one letter away from `checks` — so
`project.checks()` is the place for a Project's checks, and a command-line
interface runs them; its name is open ("run checks" to be explicit).
<!-- tarav.breadcrumb 9bbf131b3449711f4aa0d9c247a52cd43d782ed6edc2f8e56c948521f283f495 -->

All that is happening: the Project is a check provider, and there is a CLI to
run its checks.
<!-- tarav.breadcrumb b2ee28b6fdda20123080246a5ac386296f8f28f16cf2fe2878ef6f6f78d2a7cb -->

Make sure the Tarav Project base class is a CheckProvider, then propagate it to
g70203, with at least a placeholder if migrating its checks is too difficult.
<!-- tarav.breadcrumb aec64f90d9dd4b0b039347dc771988fb081292adf29daff6bd89092fa8e58452 -->

Hooks were discussed and dropped: with a generator, any caller's loop body is
its hook.

### Current behavior (858, commit `6cb0f33`)

`TaravProject.check()` returns `CheckResult`s and the base raises;
`CheckProvider.checks` is a property on `CheckProvider`, `SkwSkill`,
`Workspace`, `Command` and the test example; callers use `x.checks`
(`workspaces/commands.py`, `tests/test_workspaces.py`, `tests/test_skw_poi.py`,
`tests/test_checks_workflow.py`). No other repository uses Tarav's
`CheckProvider`.

### Design

1. `CheckProvider.checks()` is a method; the base raises
   `NotImplementedError` naming the provider Type. Every provider and caller
   moves to `checks()`.
2. `TaravProject(TaravEntity, LoadingProfile, CheckProvider)`; `check()` is
   removed. A Project subtype overrides `checks()`.
3. `tarav check --project [PATH] [--json]` keeps its name and harness launch.
   `report_project_checks` iterates `project.checks()`, runs each Check,
   turns an exception raised by a Check into a `failed` `CheckResult` with
   the exception as reason, and prints each result as it arrives (text) or
   the `check_report()` at the end (`--json`). Exit 0 when all completed
   without POIs, 1 otherwise, 2 when the Project declares no checks.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki: `tarav-md/notes/wiki/checks-workflow.md`
("Project checks: one entry point"). Downstream: g70203 request 535
(`g70203-project/g70203-md/notes/live/535-project-checks-placeholder-impl-req.md`).
Supporting chat: session `9da4cef5-68b7-4d17-8a06-1351ca51e82f` (alias
`64298cbc`).

## Execution.Plan

1. `l1/checks`: `CheckProvider.checks()` method.
2. Providers and callers: `l2/skw/skills.py`, `l1/cli/__init__.py`,
   `l1/workspaces/model.py`, `l1/workspaces/commands.py`, tests.
3. `l1/project/base.py`: subclass `CheckProvider`; remove `check()`.
4. `l3/check.py`: stream over `checks()`, exception → `failed`.
5. `tests/cli/test_check.py` updated; AGENTS.md and ARCHITECTURE.md updated.
6. Verify: focused tests, full suite, ruff, tool reinstall, md-library smoke.

## Impl.Log

- 2026-10-03 Design: written from the discussion after 858.
