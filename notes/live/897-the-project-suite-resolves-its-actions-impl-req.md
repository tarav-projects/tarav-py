# 897 — The Project's suite resolves its actions — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: designed.

Request 896 added a separate suite Type that manages POI actions, stamped
with the Project a command started from. This request replaces it:

1. The suite is the Project's own set of checks, `<project>.suite`, which is
   the existing check suite of the Project, identified by its Project.
2. A run of a suite keeps which Project each result belongs to. A container
   Project's run goes through its children's suites.
3. The Actions code resolves each Project's actions from that Project's
   results. A run on a child alone resolves the same actions.
4. The situation axis says plainly when an action's check is present and
   failed.
5. `Tarav.Actions.Suite`, `ProjectsSuite` and `SkillwareSuite` are removed.
   `tarav skw skills check` records no action.

Also carried by this request's commit: the readable default output and
`--json` of the action and operator-context commands, implemented just
before it and not yet committed.

Non-goals: suites for anything but Projects; other closing paths; Directives.

Follow-up in another repository:
`vscode-tarav-center/notes/live/006-actions-of-the-owning-project-impl-req.md`.

## Design narrative

### User decisions

The agent explained that an action had one manager and one target, the
Project a command started from, so a run on a child alone closed nothing.
<!-- tarav.breadcrumb 50e9a89a367bd319df95e392129df4ed2705f2cf8bdbead7241efc89e82cd300 -->

A check must belong to something, because otherwise we do not know whether
it is no longer happening. The model is suite/check. If others want those
checks managed, for instance container Projects, it is done from the suites.
For now suites are attached only to Projects. Checks and POIs can be built
from many objects; this is about what a Project records as an action, and a
momentary check whose only footprint is printing needs none of it. The suite
is an organization of a Project's action system, not something fundamental
to POIs and checks. The question it answers: who can tell me whether this
check disappeared?
<!-- tarav.breadcrumb da57c9758a1cfef6939c0f302aacb0f3d3f5006872e84a35d2e3496fe02b6b81 -->

The suite is something Projects have, identified from its Project, like
`<project>.suite`. It represents a set of checks. A check that is no longer
produced because it was removed from the code is no longer in the suite,
which is not very different from a check that is no longer triggered. The
suite is where we go to define the current set of active checks.
<!-- tarav.breadcrumb 8a6cedb128fa888e39b066cc57e85276f699daee5fc1d0097064814997f8d0fe -->

A check that crashed is a result of the test, so the test is present. Some
checks are always created and run, others are not explicitly defined and can
occur once and never again; those are the ones that can be missing from the
suite. The two kinds are not tracked differently: they emerge. We run a
suite, we have the results, and we resolve the status of checks and actions.
<!-- tarav.breadcrumb acdeaf57127d02b4a59f638ad35969fdb6ba240d5edbecbfd61aa0e4d13ce3c4 -->

`project.checks.suite()` is the suite: the place where actions go to resolve
the current status of checks. The status must be clear when a check failed.
<!-- tarav.breadcrumb cb60022aa57df47999552ac488631cbc5647e151f9b93296fe243c31634b22d4 -->

The User asked for the request to be written and executed.
<!-- tarav.breadcrumb cb0d81e4b536b7fa2e72962f0aea0542fe0ba6063c8fc41e5e3c5630bbb59a95 -->

About command output, decided just before: Tarav commands render their
output by default and `--json` dumps it; there is one model for both, and
the command decides what to present.
<!-- tarav.breadcrumb 172076a0f343a0ed666f5600452a5c7d0d82b288656ed2fcd54536b71fa59255 -->
<!-- tarav.breadcrumb 8dad8d01853c69283145d54227bd6aad9b7258cd30bd1183147a897b7431d975 -->

### Current behavior (`tarav-py` at `7f74882`)

- `tarav.l1.actions.suites.Suite.settle(pois, target=, incomplete=,
  complete=)`; `ProjectsSuite`, `SkillwareSuite`. An action stores `suite`
  and `project` (the target), and a suite leaves alone an action of another
  suite or target.
- `tarav.l1.checks.CheckSuite` holds checks and nested suites.
  `CheckSuite.run()` flattens every result into one `CheckRun`.
- `TaravProject.Checks.suite()` builds the Project's suite; subclasses wrap
  it (`Project`, `PythonPackageProject`, `DocsProject`, `RootProject`). The
  root nests `child.checks.suite()` for a child that shares its environment;
  another child runs in its own environment through one `ChildProjectCheck`.
- On the root Project, 51 open actions carry the root as their Project.

### Agent choices (proposals, not User decisions)

- **Owner on the suite.** `CheckSuite` takes an optional `owner`: a plain
  description of whose suite it is. For a Project it is `id`, `name`, `root`.
  The checks code gives it no meaning. A nested suite without an owner
  belongs to the suite that contains it.
- **`TaravProject.suite`** is the Project's check suite with the Project as
  owner. `project.checks.run()` runs it, and the root nests `child.suite`.
- **`CheckRun` keeps the owner of each result**: `groups()` returns the
  results per owner. Results with no owner are momentary.
- **`POIActions.resolve(check_run)`** replaces `Suite.settle`: for each
  owning Project in the run it opens or reopens the actions of its POIs,
  and among that Project's actions whose POI was not produced it closes the
  open ones as gone, unless a check of the Type that raised it is present in
  that Project's results and did not complete.
- **An action belongs to the Project whose suite produces its POI.** An
  action found under another Project is moved to it in the normal run; this
  is how the 51 existing actions reach their owning Projects.
- **Situation axis**: `present`, `absent`, `check failed`.
- **A child that runs in its own environment** is seen by the root as one
  check of the root; the child's own actions are resolved by the child's own
  run, not by the root's.
- `GoneClosing` records the Project in place of the suite.

### Open questions

- A Project removed from its container, or a check moved to another
  Project's suite, leaves actions that no run resolves until that POI is
  produced again elsewhere.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes:
`poi-system.md`, `daily/2026-10-11.md`. Skill module:
`tarav-md/skills/tarav-pkg/references/step-actions.md`. Supporting session:
`claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: pending.

## Execution.Plan

1. Start checkpoint. `CheckSuite.owner`, `CheckRun.groups()`,
   `TaravProject.suite`, the root nesting `child.suite`. Tests.
2. `POIActions.resolve()`; remove the three suite Types and the Skillware
   settling; `check failed`; commands and the action view. Tests.
3. A real run on the root Project and on a child alone.
4. Full suite, Ruff, reinstall the CLI, Breadcrumbs, `ARCHITECTURE.md`,
   `AGENTS.md` source, skill module, Wiki, completion commit.

## Impl.Log

- Designed 2026-10-11.
