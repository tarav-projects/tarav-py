# 894 — Project POIs on actions: tracking is replaced — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: ready, after request 892.

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
<!-- tarav.breadcrumb e1b238fb7d1c658ae1ba8070e4ee048fd59a4fd38f96e1ef6e4b713ce12723e4 -->
<!-- tarav.breadcrumb ca092f0acadd49686ecd414d6f3ffef214c9504797d081b423e78e1ef475b39b -->

A tracked POI is an action triggered when the POI is first raised; the name
for now is an actionable POI. What is happening in a Project is asked as
"which actions are active?".
<!-- tarav.breadcrumb 9fc2b87d85688f228b71776ebeb4a0a214a278feeaeeb0712dbbbd1122b1a868 -->
<!-- tarav.breadcrumb 71aaef9ccb5ad237166a65f15f933170fcc0df10abd6d1ef34e9fce309e0492c -->

Everything is centralized: tracking moves out of the Project's folder.
<!-- tarav.breadcrumb aa8b4fd11da9807d3237b8ed35ffc57f94062703436dd5b4d9c0b87beac08ae2 -->

The action instance follows the POI's identity; triggered again it stays
open, reopens, or is created. History is the Git history of the record.
<!-- tarav.breadcrumb 3b1476e7155fe81631d6bbf5ef02e8b73df6dd69823fdd751992b8dddbaad591 -->
<!-- tarav.breadcrumb 5d67a1b802d3b9853035134d9526fe4dc63d066397df2700d336039d516c4f4a -->

Positive and negative results are modelled the same way, as POIs; positive
ones are suppressed by default, and a positive POI that closes an open action
is a signal worth showing. What to do with any POI is the caller's choice.
<!-- tarav.breadcrumb 27c7053af4d28afd741b4b40ed9d05d0c823612886ac8c248b93e59827414cfd -->
<!-- tarav.breadcrumb b4e5c7255a3242347813ba71f86f9746f3944c250d607ec43ac90b346e6c9c58 -->

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
