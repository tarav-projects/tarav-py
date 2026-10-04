# 858 — Project checks entry point

<!-- tarav.sessions
64298cbc = claude-code:9da4cef5-68b7-4d17-8a06-1351ca51e82f @64298cbc8db2e7aa971e0828653c07bcb483cfed40931fdf87d5abe7ce1c60b3
-->

## Impl.Abstract

Knowledge.Surface: wiki
Alignment.Mode: Interactive
Status: ready (Develop: design then execute in the same invocation).

Establish one standard entry point for a Project's checks: every
`TaravProject` has a `check()` method that a Project subtype implements by
running its checks with Tarav's existing Check, CheckResult and POI
primitives; `tarav check --project [PATH]` runs it in the Project's own
harness environment and reports the results.

The only semantic: whatever the Project's `check()` runs is what runs when
someone asks for the Project's checks.

Non-goals: a check registry or declaration format; selection, profiles or
cost classes for heavy checks; wrapping pytest; attention, tracked-POI
reconciliation or blessings in the report; implementing `check()` for any
concrete Project (md-library, g70203); renaming `tarav test` (an unrelated
CLI smoke test).

## Design narrative

### User direction

The User wants a standard way of running a project's tests, analogous to the
source and tests folders of a programming language, but more general than
testing code: these are the checks of the whole project. The Project class
should have an entry point that runs whatever was put there. Linter, checker
and test mean more or less the same thing to the User; the only semantic for
now is that this entry point runs when someone asks for the project's checks.
<!-- tarav.breadcrumb 21f4e6352977f16d87b1ff9e929f190057c795c1083d3ac18acc28fab6f7a6bd -->

This is Tarav-level, not specific to g70203.
<!-- tarav.breadcrumb 2d06173e832534f5fb9f1f1854f8a21ed676ff6035f884baaa56fc48d2487723 -->

Every Project class has a check method that subtypes implement; the
implementation runs the checks and may use every primitive Tarav already has
for checks and POIs. It is an entry point to establish now. The User chose
the name "project checks", not "project tests", called it simple to
implement, and asked for this request to be designed and executed through
the Develop path.
<!-- tarav.breadcrumb e8e0abaddc2eaf0ab0e3d0162009e88f0f248861cc1dcdd5cc93a47fa958ee22 -->
<!-- tarav.breadcrumb 7f8164ba52ed2e5c0c558a4a274dce1f0ac27c4d98194e01e41ff8f286c435c8 -->

### Naming (agent rationale, accepted by the User)

A Check is the unit: it runs and reports POIs (`tarav.l1.checks`). A linter is
a runner that selects, orders and reports checks; a test is a check run by a
framework at development time. "Check" therefore names the umbrella, and the
existing `tarav test` smoke-test command keeps "test" from being a clear name.

### Current behavior (inspected 2026-10-03)

- `tarav.l1.project.base.TaravProject` is the minimal Project base;
  `tarav.l2.project.Project` the featured subtype; concrete Projects (e.g.
  md-library's `MdLibraryProject`) subclass `TaravProject`.
- `tarav.l1.checks`: `Check.run() -> CheckResult` (status `completed`,
  `incomplete` or `failed`; `pois()`); `run_checks(checks)`; `CheckPOI`;
  `CheckProvider.checks`.
- A Project's own Types are only known inside its harness environment.
  `tarav.l3.project.harness.run(path=, code=)` launches the Project package's
  `__main__` (`main(project_type=...)`), which binds the trusted Type, loads
  the marker and executes code with `project` in scope. md-library's
  `__main__` already does this. `tarav run --project` deliberately does not
  inject a Project.

### Design

1. `TaravProject.check(self) -> tuple[CheckResult, ...]`. The base raises
   `NotImplementedError` naming the Project Type: a subtype must implement
   it. No default checks.
2. `tarav.l1.checks.check_report(results) -> dict`: plain, JSON-ready data
   per result (Check Type name, status, reason, POIs via `as_dict()`) and
   totals. Shared by the CLI and any caller.
3. `tarav check --project [PATH] [--json]` (l3): requires `--project`,
   resolves the Project, and launches `harness.run(path=..., code=...)` whose
   code calls `project.check()`, prints the report (text or JSON) and exits
   0 when every result completed with no POIs, 1 otherwise. A Project
   without a harness, or whose Type does not implement `check()`, fails with
   a clear error.

The exit code informs callers; it does not block anything.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant
notes: `checks-workflow.md`, `projects.md`, `tarav-harness.md`. Supporting
chat: Claude Code session `9da4cef5-68b7-4d17-8a06-1351ca51e82f` (alias
`64298cbc`). First consumers: md-library (`MdLibraryProject`) and g70203
(once it declares a typed harness).

## Execution.Plan

1. `TaravProject.check()` in `src/tarav/l1/project/base.py`.
2. `check_report()` in `src/tarav/l1/checks/__init__.py`.
3. `src/tarav/l3/check.py` with `register_check_command`, registered in
   `tarav.l3.runtime` beside `run`.
4. Tests (`tests/cli/test_check.py`): base raises; a subtype's results
   render through `check_report`; the CLI passes the Project path and code
   to the harness runner and returns its exit code; the generated code,
   executed with a stub Project, prints the report and exits 0/1 correctly.
5. Docs: `AGENTS.md` Project model bullet, `ARCHITECTURE.md` Project section.
6. Verify: focused tests, ruff, configured suite; reinstall the tool;
   smoke `tarav check --project` against md-library (expected: clear
   "does not implement check()" error, read-only).

## Impl.Log

- 2026-10-03 Design: written after inspecting the Project base, Checks
  primitives, the harness launch path and the `run` CLI.
