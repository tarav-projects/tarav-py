# 898 — The Project composes its checks and its actions — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented.

Request 897 made the check code carry the Project: a suite had an owner, a
run grouped its results by owner, and one function of the Actions code read
those groups and did everything. The command `tarav check` was the only place
where checks and actions met. This request puts the Project in the middle:

1. `project.checks` only runs the checks and returns the results. It knows
   nothing about actions.
2. `project.actions` only handles the actions registered under the Project.
   It takes results, registers the actions of POIs it sees for the first
   time, and passes the results to each registered action. It never runs a
   check.
3. Each Action Type decides what a run of the checks means for one of its
   actions. The loop of the Project knows nothing about POIs.
4. One method of the Project, `project.status()`, composes the two: run the
   checks, hand the results to the actions. A container does the same for
   itself and asks each child Project to do it for itself.
5. The command `tarav project status` runs that method. It is the command an
   agent runs repeatedly. `tarav check` only runs the checks.
6. Removed: `project.suite`, the owner of a `CheckSuite`, the groups of a
   `CheckRun`, the `actions` argument of `CheckRun.report` and `clean`, and
   `POIActions.resolve`.

Non-goals: a subscription mechanism for hooks; a cache of the last run;
actions that do not come from POIs; a child in its own Python environment
(it stays one check of the root, as before); Directives.

Follow-up in another repository:
`vscode-tarav-center/notes/live/007-one-project-call-for-status-impl-req.md`.

## Design narrative

### User decisions

The user restated the model to align on it. The Project is the object that
the actions are attached to. Open actions are like open issues: typed,
persistent across sessions, registered under a Project. A check or a POI as
an object is distinct from what is done with it. They doubted that the suite
is needed as a concept; what is needed is that the machinery of the actions
can tell whether a situation is happening now, and that something knows how
to run the checks again in an equivalent context.
<!-- tarav.breadcrumb 8cb0c4d036d6 -->

The agent answered that the Project is that runner, and that request 897 had
carried the Project through the check code as an owner, which is the wrong
position. The user agreed: registering actions is something about the
Project, and that is what makes the integration of checks, results and
actions necessary. Objects may hold builders of other objects; a further
layer integrates them with larger systems. The Project runs a loop that
gives the check results to every registered action, and each action does
what it needs: ignore them, close itself, or change its status.
<!-- tarav.breadcrumb 0aeb23ca2476 -->

Builders on objects are a modeling pattern to use when it fits, not a rule;
redundant paths are allowed. The user asked for a clear picture of the
actors and whether the arrangement is balanced.
<!-- tarav.breadcrumb 34f41714deb0 -->

`project.suite` is to be eliminated. A cache of a run, if ever needed, goes
inside `project.checks`.
<!-- tarav.breadcrumb 82da1ff17e35 -->

`project.checks` holds the checks of a Project, can run the checks of
subprojects, and only runs checks. Its results are passed to the action
workflow to update any action and, in the same way, to start any action.
<!-- tarav.breadcrumb c9a3f8f4771a -->

The separation comes first and a compound command later; `project actions`
is a bad name for something that also runs checks; one command is needed
that an agent can run repeatedly.
<!-- tarav.breadcrumb 665a994e2bb7 -->

Do the split in the code and use `tarav project status` for now.
<!-- tarav.breadcrumb 3e71bda5133d -->

### Current behavior (inspected)

- `TaravProject.suite` (`l1/project/base.py`) wraps `project.checks.suite()`
  in a `CheckSuite` with `owner` = the Project identity.
  `Checks.run()` runs it.
- `RootProject._child_checks` (`l2/project/root.py`) nests each child's
  `suite`, so one run holds the results of all Projects, grouped by owner
  (`CheckRun.owners`, `suites`, `ran()`, `groups()`).
- `POIActions.resolve(check_run)` (`l1/actions/pois.py`) reads the groups and
  opens, reopens, moves, marks and closes actions. It holds the POI rules,
  among them matching a failed check by its Type.
- `l3/check.py` calls `project.checks.run()`, then `POIActions().resolve(run)`,
  then `run.report(actions=…)` and `run.clean(actions=…)`. The extension's
  script repeats the first two calls.
- The exit taker of `gone` is named `suite`.

### Proposals of the agent

These were described to the user in the discussion at the level of the
actors; the names and details below are the agent's.

**Checks.** `CheckSuite` loses `owner`. `CheckRun` loses `owners`, `suites`,
`ran()`, `groups()` and the `owner` argument of `add()`. `report()` takes an
optional `label` function and counts each row's POIs under the labels it
returns, in `row["standing"]`; the check code gives the labels no meaning.
`clean()` means every check completed and there is no finding.

**Project checks.** `project.checks.suite()` stays the whole set, with the
subprojects for a container. `project.checks.own()` is the part that belongs
to this Project alone; for a root it leaves out the children that load in
this process. `project.members()` are those child Projects (none by default).

**Action Types.** `Action.on_checks(run, update)` is what a Type does with
the results of its Project's checks for one registered action. It returns a
name for the change it made, or `None`. The base ignores the results.
`update` carries the check run, the Project identity, the time, a list for
signals and a memo that a Type can use to index the results once.

`POIResolutionAction.on_checks` holds the POI rules: my POI is among the
results (present; reopen when the closing says so); my check did not
complete (check failed; stay as I am); otherwise absent, and close as gone
when open. `POIResolutionAction.opened(poi, …)` builds the action of a POI.

**Project actions.** `ProjectActions` (`l1/actions/project.py`), reached as
`project.actions`:

- `list()`: the actions registered under the Project.
- `start(run)`: for each POI in the results that names an Action Type,
  register its action under this Project when it is not registered here: a
  new one is built by its Type, one registered under another Project moves.
- `refresh(run)`: pass the results to every registered action, open or
  closed.
- `update(run)`: `start`, then `refresh`, then write and commit. Returns the
  counts and the signals.

`POIActions` keeps only its reading methods.

**Composition.** `project.status(on_result=None)` returns a `ProjectStatus`:
the Project, its own check run, what its actions did, and the statuses of its
members. `ProjectStatus.run()` is one `CheckRun` with every result, for the
report; `acted()` adds up the counts.

**Exit taker.** `suite` is renamed `project`: the Project closes an action as
gone. Records written before keep `by: suite` as plain data.

**Commands.** `tarav check` loses `--actions` and prints only the checks'
report. `tarav project status --project [PATH]` takes the same report
options, labels each row's POIs `open` or `blessed`, prints the actions line,
and exits 0 when every check completed and every finding is blessed.
Agent instructions that say `tarav check` change to the new command.

### Alternatives considered

- Hide the update inside `project.checks.run()`: rejected, running checks is
  also used only to look.
- Two commands, checks then actions: the second needs the results of the
  first, so it would need a cache or run the checks itself.
- A general hook that subsystems subscribe to: left for later; a plain call
  in the composing method is the hook for now.

### Open questions

- A child in its own Python environment is still one check of the root, so
  the root's status does not update that child's actions.
- The loop visits closed actions too; with a long history it may need a
  limit.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md`, root
`tarav-md/notes/wiki/`. Relevant notes: `poi-system.md`,
`daily/2026-10-11.md`. Supporting chat: session `abd0372d` above.
Capture status: done (`poi-system.md`, section "The Project composes its checks
and its actions"; daily 2026-10-11).

## Execution.Plan

1. Checks: remove owner and groups; `label` in `report`; plain `clean`.
2. Actions: `on_checks`, the builder, `ProjectActions`; remove `resolve`;
   rename the taker.
3. Project: `checks.own()`, `members()`, `actions`, `status()`; remove
   `suite`; the root splits its children.
4. Commands: plain `tarav check`; `tarav project status`.
5. Tests rewritten for the new arrangement; full suite and Ruff.
6. Agent instructions and skills; real run on the root Project.
7. Extension request 007; Wiki capture.

## Impl.Log

- Design written from the discussion of 2026-10-11.
- Implemented as planned. One change to the plan: the root's full set of
  checks keeps the children in their listed order; only `own()` leaves the
  loadable ones out.
- `Project.poi_actions()` removed; `project.actions.list()` replaces it.
- Checks: Ruff clean; `uv run pytest` 266 passed (the configured test paths).
  `tests/cli/test_check.py` is outside those paths: three of its tests
  already fail on the previous commit and a fourth fails with another
  agent's uncommitted change; none is caused by this request.
- Real run: `tarav project status --project .` reported 51 actions raised in
  3 Projects, nothing opened, reopened or closed; the same for `tarav-md`
  alone. `tarav check --project .` printed no actions line.
- Instructions: `AGENTS.skw.json` of the root, `tarav-md` and `tarav-py`
  name `tarav project status`; `ARCHITECTURE.md` and the skill module
  `step-actions.md` updated.
- Breadcrumbs: submitted on `l1/actions/__init__.py`, `pois.py`,
  `project.py`, `l1/project/base.py`, `status.py`, `l2/project/root.py`,
  `l3/check.py`, `tests/test_actions_workflow.py`,
  `tests/test_project_tree.py`; positions refreshed on the moved code.
  Breadcrumbs of removed code (`resolve`, `groups`, `poi_actions`) went
  with it.
- Not committed with this request: `src/tarav/l2/tests/actions.py` and
  `tests/test_actions_pois.py`, updated to the new calls, still wait for
  another agent's `l2/tests` package.

