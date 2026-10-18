# 894 — Project POIs on actions: tracking is replaced — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented.

Replace the Project POI tracking store by the POI resolution action of
request 892, for real Projects: a check POI is an actionable POI, its action
lives in the central Record Registry, checks say when they are clear, and
`tarav check --project` hands its results to the Actions workflow.

Non-goals: blessings (request 895); Tarav Center (its own request); Directives;
hooks and chains; migrating the existing one-day-old tracking stores, which
are dropped.

## Design narrative

The User asked for the consequences of the day's design to be turned into
as many requests as needed and executed.
<!-- tarav.breadcrumb e1b238fb7d1c -->
<!-- tarav.breadcrumb ca092f0acadd -->

A tracked POI is an action triggered when the POI is first raised; the name
for now is an actionable POI. What is happening in a Project is asked as
"which actions are active?".
<!-- tarav.breadcrumb 9fc2b87d8568 -->
<!-- tarav.breadcrumb 71aaef9ccb5a -->

Everything is centralized: tracking moves out of the Project's folder.
<!-- tarav.breadcrumb aa8b4fd11da9 -->

The action instance follows the POI's identity; triggered again it stays
open, reopens, or is created. History is the Git history of the record.
<!-- tarav.breadcrumb 3b1476e7155f -->
<!-- tarav.breadcrumb 5d67a1b802d3 -->

Positive and negative results are modelled the same way, as POIs; positive
ones are suppressed by default, and a positive POI that closes an open action
is a signal worth showing. What to do with any POI is the caller's choice.
<!-- tarav.breadcrumb 27c7053af4d2 -->
<!-- tarav.breadcrumb b4e5c7255a32 -->

### Current behavior (observed 2026-10-09)

- `tarav.l1.poi_tracking`: `TrackablePOI` (a settings-carrying capability
  that `CheckPOI` extends), `POITracker`, status axes, `TrackRecordStore`,
  the `tracked-poi` Context view and resolver.
- `tarav.l2.project.tracking.open_tracker()` places the store in
  `<Project>/.tarav/poi-tracking/`; `tarav.l2.blessings.tracking` adds the
  blessing axis.
- `tarav.l3.check.report_project_checks()` retains, reports, tracks
  (`--tracking write|skip`) and renders; `CheckRun.clean()` counts every
  unblessed POI as not clean and ignores `failure`.
- `tarav poi tracking list` (`l3/poi_commands.py`) and
  `tarav context --view tracked-poi` read the store.
- `tests/test_poi_tracking.py` and parts of
  `tests/decisions/test_decisions_and_tracking.py` cover it.

### Agent choices (proposals, not User decisions)

- `CheckPOI` extends `ActionablePOI` in place of `TrackablePOI`; its action is
  the POI resolution action. A POI Type can still opt out.
- Every completed check that raises nothing yields the generic clear POI of
  request 892, naming the check and, when the check declares one, its subject.
  A check without a subject closes nothing, as an identity-less check cannot
  show "passed" today.
- `tarav check --project --actions write|skip` replaces `--tracking`. The run
  is handed to the Actions workflow; the POIs it returns for closed actions
  are shown.
- Callers choose by `failure`: `CheckRun.clean()`, the default report and the
  retained report consider failures only; `--include clear` shows the rest.
- `tarav poi tracking list` is replaced by `tarav action list`, and the
  `tracked-poi` view by a view of the POI's action.
- `tarav.l1.poi_tracking`, `tarav.l2.project.tracking` and the tracking axis of
  blessings are removed with their tests. `<Project>/.tarav/poi-tracking/`
  folders are left on disk and reported; they are not deleted by code.

### Open questions

- Which checks get a subject first. Proposed: the Project's own checks whose
  subject is evident (a file, a folder, a Type).
- Does the central registry need partitioning by Project now? Proposed: flat,
  with the Project in each record.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes:
`poi-system.md`, `operator-context.md`, `daily/2026-10-09.md`. Supporting session: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: design
discussion captured; implementation capture pending.

## Execution.Plan

1. Start checkpoint. `CheckPOI` actionable; clear POIs from completed checks;
   `failure`-aware `clean()`, report and retention; tests.
2. The hand-off in `report_project_checks`; `--actions`; shown closing
   signals; tests through the CLI with a temporary registry.
3. The action Context view and resolver; `tarav action list --project`;
   remove tracking code, command and tests.
4. Full suite, Ruff, a real `tarav check --project` on this workspace;
   Breadcrumbs; guidance and skill text; Wiki; completion commit.

## Impl.Log

- Designed 2026-10-09.
- Start checkpoint: commit `8fceeb7` (request 893). Files with other agents'
  uncommitted edits that this request also changes: `src/tarav/l3/check.py`,
  `src/tarav/l3/runtime.py`, `tests/kernel/test_object_record_contract.py`,
  `ARCHITECTURE.md`; only this request's hunks are committed from them.
- `ActionablePOI` moved to `tarav.l1.poi.actionable` (it names its Action Type
  as a string, so Checks do not import Actions); `CheckPOI` extends it in
  place of `TrackablePOI`; `ClearPOI` spins nothing.
- `POIActions.observe(pois, completed=, whole=, project=)`: an open action
  closes as `gone` when its check completed in the batch without raising it,
  matched by `subject_key`, else by `Check.identity`; with `whole`, a check
  Type that names neither closes its absent actions. Actions of another
  Project are never touched. A POI raised twice in one batch is one action.
- Agent choice, differing from the request text: completed checks are passed
  to `observe()` by the caller (`CheckRun.completed()`) and no clear POI is
  synthesized for every check. A check still raises `ClearPOI` when it has
  something to say. `CheckRun.findings()` leaves out POIs marked as not a
  failure, and `clean()` uses it.
- `tarav check --project --actions write|skip` replaces `--tracking`; the
  report prints the actions line and each `gone` signal; JSON carries
  `actions`. `TARAV_RECORDS` relocates the Record Registry, set by the test
  suite's `conftest.py`.
- `tarav.l1.actions.views`: `POIActionContext` and `POIActionResolver`
  (`tarav context --id <poi id or action id> --view poi-action`); the reported
  view's `track-record` entry is now `action`. `tarav action list --project`
  finds the nearest Project and shows each action's POI.
- Removed: `tarav.l1.poi_tracking`, `tarav.l2.project.tracking`,
  `tarav.l2.blessings.tracking`, `tarav.l3.poi_commands` (`tarav poi`),
  `tests/test_poi_tracking.py`, `CheckRun.track()` and `observations()`,
  `Project.poi_tracking()` (now `poi_actions()`).
- Tests: `tests/test_actions_workflow.py` has 16 (three new: the check
  command's hand-off across two Projects and with `skip`; a non-failure POI
  leaves the run clean; the action view). Full suite 259 passed in the shared
  worktree; Ruff clean. `tests/cli/test_check.py` is not in `testpaths` and
  already had three failures at HEAD.
- Real run on the root Project: 364 checks, 54 POIs with 52 identities; 52
  actions opened in `~/Documents/tarav/records/8f3394a6-.../`, one commit; a
  second run changed nothing; `tarav action list --project --state running`
  lists them and `tarav context --id <poi id> --view poi-action` opens one.
  Defect found there and fixed with a test: two POIs of one identity in a
  batch were counted as two openings.
- `AGENTS.md` updated through its Skillware source and compiled;
  `ARCHITECTURE.md` updated.
- Left on disk, not deleted by code: `.tarav/poi-tracking/` in the root and in
  `tarav-py`. Tarav Center's scripts import the removed tracker and are broken
  until its request 004.
- No real check declares a `subject_key` yet, so an action whose check
  identity includes what it found closes only when that check Type has none
  of its POIs left in a whole run, or never. That is the next thing to add
  per check.
