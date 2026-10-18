# 897 — The Project's suite resolves its actions — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented.

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
<!-- tarav.breadcrumb 50e9a89a367b -->

A check must belong to something, because otherwise we do not know whether
it is no longer happening. The model is suite/check. If others want those
checks managed, for instance container Projects, it is done from the suites.
For now suites are attached only to Projects. Checks and POIs can be built
from many objects; this is about what a Project records as an action, and a
momentary check whose only footprint is printing needs none of it. The suite
is an organization of a Project's action system, not something fundamental
to POIs and checks. The question it answers: who can tell me whether this
check disappeared?
<!-- tarav.breadcrumb da57c9758a1c -->

The suite is something Projects have, identified from its Project, like
`<project>.suite`. It represents a set of checks. A check that is no longer
produced because it was removed from the code is no longer in the suite,
which is not very different from a check that is no longer triggered. The
suite is where we go to define the current set of active checks.
<!-- tarav.breadcrumb 8a6cedb128fa -->

A check that crashed is a result of the test, so the test is present. Some
checks are always created and run, others are not explicitly defined and can
occur once and never again; those are the ones that can be missing from the
suite. The two kinds are not tracked differently: they emerge. We run a
suite, we have the results, and we resolve the status of checks and actions.
<!-- tarav.breadcrumb acdeaf57127d -->

`project.checks.suite()` is the suite: the place where actions go to resolve
the current status of checks. The status must be clear when a check failed.
<!-- tarav.breadcrumb cb60022aa57d -->

The User asked for the request to be written and executed.
<!-- tarav.breadcrumb cb0d81e4b536 -->

About command output, decided just before: Tarav commands render their
output by default and `--json` dumps it; there is one model for both, and
the command decides what to present.
<!-- tarav.breadcrumb 172076a0f343 -->
<!-- tarav.breadcrumb 8dad8d01853c -->

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
`claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: done
(`poi-system.md`, daily note 2026-10-11).

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
- Start checkpoint: commit `0a2155f` (this note). 8 Breadcrumbs on it.
- Checks: `CheckSuite(owner=)`; a nested suite without an owner belongs to
  the suite that contains it. `CheckRun.add(result, owner=)`, `ran(owner)`,
  `groups()`. An owned suite that ran with no result still has a group, so
  a Project whose suite is now empty closes what it had. `CheckRun
  .incomplete()` is removed.
- Projects: `TaravProject.suite` (owner: `id`, `name`, `root`);
  `project.checks.run()` runs it; the root nests `child.suite`.
- Actions: `POIActions.resolve(check_run)` in two passes, first every
  Project's produced POIs, then every Project's actions that no suite of the
  run produced. `CHECK_FAILED` is the third situation. `GoneClosing` records
  `project`. `ActionRunStore.write()` skips a record that already says the
  same.
- Removed: `tarav.l1.actions.suites`, `tarav.l1.project.suite`,
  `tarav.l2.skw.suite`, the settling in the Skillware commands, the `suite`
  field of an action.
- Commands: `tarav check` prints "N raised now in M Project(s)". `tarav
  action` rows no longer carry `suite`; the `poi-action` view has `project`
  in place of `managed-by`.
- Also in this commit, implemented just before the request: `tarav action`
  and `tarav operator-context` print a readable summary by default and the
  full result with `--json`, both from one result; `tarav action list` has
  `--limit` for the summary.
- Error found by the real run and fixed: I had the run drop the old `suite`
  key from existing records. A record keeps unknown keys it was loaded
  with, so nothing changed on disk and the commit of "no changes" failed,
  which made a child's run print no actions line. The cleanup is removed;
  records opened under request 896 keep a `suite` key that nothing reads.
- Tests: 263 passed in the shared worktree; Ruff clean. New in
  `tests/test_actions_workflow.py`: a check that is present and failed
  leaves its action and says so; each Project resolves its own actions from
  its own suite (container run, child alone, container without the child);
  an action moves to the Project whose suite produces its POI; a run with no
  owned suite resolves nothing; the commands in both output modes.
- Real runs: `tarav check --project .` reported 51 POIs in 3 Projects and
  moved the 51 open actions from the root to `tarav-md`, the Project whose
  suite produces them. `tarav check --project tarav-md` alone then reported
  the same 51 with no change, and `tarav action list --project tarav-md`
  lists them. `tarav skw skills check` with a throwaway registry wrote
  nothing.
- Not verified on real data: a child-alone run closing an action, since no
  real situation was fixed (existing POIs are left as they are). The tests
  cover it.
- Not committed with this request, as before: `src/tarav/l2/tests/actions.py`
  and `tests/test_actions_pois.py`, adapted in the worktree.
- Product Breadcrumbs: 9 new in code (`checks/__init__.py` 3,
  `project/base.py` 1, `project/root.py` 1, `actions/pois.py` 3,
  `l3/check.py` 1), 4 in `tests/test_actions_workflow.py`, 3 in
  `ARCHITECTURE.md`; earlier in the day 2 each on the two command modules.
  Moved labels refreshed.
