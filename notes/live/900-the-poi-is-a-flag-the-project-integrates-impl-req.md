# 900 — The POI is a flag; the Project integrates — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented.

A POI used to be the thing that persisted, and machinery grew around it: a
store of every printed POI, blessing asked through POI listings, a reader of
actions that belongs to no Project. Now the action persists. This request
makes the POI what it is, a momentary flag between detecting and working,
and moves what integrates several workflows to the Project.

1. The store of reported POIs is removed, with its Context view, its
   resolver, the check that proved it worked, the `context` render level and
   the hint POI listings printed.
2. POI listings know nothing of actions: no blessing or standing in them.
   `tarav skw skills` loses `--blessing-status`. The blessing attention
   report is deleted.
3. The reader of actions that belongs to no Project is removed; what is
   needed is on `project.actions`.
4. `tarav status` prints action ids, and its result depends only on actions.
   `tarav context --id <id>` finds an action by its id or by the id of its
   POI, without naming a view.
5. The existing action records are deleted and reopened, because an action
   now keeps what its POI's Type says about it.

Non-goals: moving the capability markers `ActionablePOI` and `BlessablePOI`;
`POI.throw()`; an inbox for occurrences; Directives.

Follow-up in another repository:
`vscode-tarav-center/notes/live/009-open-an-action-by-its-id-impl-req.md`.

## Design narrative

### User decisions

The status hint named a POI and a view. The interface must be more action
centric: POI actions are one type of action, and what the status lists are
open actions. An `--id` should find the object, an action or a POI.
<!-- tarav.breadcrumb 0d22dad7770b -->

The context workflow is independent and receives a contextualizer, a view
for instance. The status only promotes how the agent can go further.
<!-- tarav.breadcrumb f7c15836181b -->

It is useful to say which system consumes the POIs. A linter can use the POI
system without hooking into the Project's status; there the POI has another
escalation path, maybe only printing. The Project status is closely
integrated with the Project's actions and checks, and its checks escalate to
actions by design.
<!-- tarav.breadcrumb 9feb4d22d402 -->

The user then questioned printing as a path of its own: what is the point of
a POI if not to demand action, and should all execution not go through
actions, which are how agents are harnessed on specific steps.
<!-- tarav.breadcrumb e1d4a84132e7 -->

Settled as fundamental: a POI is a flag, a notification. It can be escalated
by starting an action; actions can also start without a POI; actions are the
unit of work in Tarav. An action needs a place to be registered and a way to
end, which a bare POI does not have. Printing is only how a person looks at
checks directly.
<!-- tarav.breadcrumb bfb0c9920634 -->

The POI is the interface between detecting and working. The store of
reported POIs must go, at least for now: make a simple system first and
test what is really needed. A POI is momentary and owns nothing.
<!-- tarav.breadcrumb 90cdfb857d9a -->

`POI.throw()` stays: it is conceptually clean. Blessing through POIs and the
attention report are probably to be removed from POI. A Type can still
declare capabilities: the caller triggers one, but an object can say what
it can do.
<!-- tarav.breadcrumb 406f09ed039a -->

Complex things such as blessing and filtering are modeled only at the level
of a Project or a similar system, because they integrate several workflows
and primitives. Objects may hold parts of the integration, but it is
managed by something larger and well defined: the Project, for now.
<!-- tarav.breadcrumb eae6d230e2d5 -->

Commit the pending work, then write this request and build it.
<!-- tarav.breadcrumb b37bcfd5bcb6 -->

### Current behavior (inspected)

- `tarav.l1.poi.reporting`: `ReportedPOIStore` writes every printed POI to
  `~/.tarav/check-reports/`; `ReportedPOI`, `ReportedPOIContext` and
  `ReportedPOIResolver` open one by id; `context_instruction()` is the hint
  listings print. Five commands write to the store.
- `POIContextRoundTripCheck` (`l1/checks/poi_contract.py`) proves a printed
  id opens from the store.
- `POICollector.report(actions=, blessing=)` and
  `POIActions.blessing_standing` put blessing into POI listings;
  `tarav skw skills` filters on it. `l2/blessings/attention.py` is called
  only by its tests.
- `POIActions` (`l1/actions/pois.py`) reads actions by POI for anyone.
- `tarav context --id <action-id>` finds nothing without `--view poi-action`.
- The status is settled when every finding is blessed, read from POIs.

### Proposals of the agent

**POI.** `tarav.l1.poi.reporting` is removed. What it knew about one POI
moves to the object: `IdentifiedPOI.describe()` returns its message,
situation and evidence, its Type and the Type of its check with where each
is defined, and the Type's notes. Renderers lose the `context` level and the
hint. `POICollector.report` loses `actions` and `blessing`.

The notification helpers stay: the audit called two of them unused, but
`emit_notification` delivers through them.

**Action.** An action that follows a POI keeps `describe()` of its POI in
`event.source`, so what the POI's Type says is read from the action. An
`ActionRun` contributes its own entries to its Context, and its Action Type
adds what is specific to it (`Action.context_entries`). `ActionResolver`
finds an action by its id or by its POI's id for any view. The view
`poi-action` is removed.

**Project.** `project.actions` gains `of(poi)`, `standing(poi)` and
`blessing(poi)`. `POIActions` is removed.

**Status.** Settled means every check that ran completed and no action is
open. Change lines carry action ids; the hint is
`tarav context --id <action-id>`. The check report inside `--json` no
longer labels POIs as open or blessed.

**Consumers.** `tarav check`, `tarav skw skills`, the breadcrumbs and the
Diagram commands only print.

**Data.** The action records are deleted and reopened; the files in
`~/.tarav/check-reports/` are deleted.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md`, root
`tarav-md/notes/wiki/`. Relevant notes: `poi-system.md`,
`daily/2026-10-12.md`. Supporting chat: session `abd0372d` above.
Capture status: done (`poi-system.md`, section "The POI is a flag; the Project
integrates"; daily 2026-10-12).

## Execution.Plan

1. POI: remove reporting, add `describe()`, simplify renderers and collector.
2. Actions: `event.source`, Context entries, `ActionResolver`, fold the
   reader into `project.actions`.
3. Consumers: check, status, SKW skills, breadcrumbs, Diagram commands;
   delete the attention report and the round-trip check.
4. Tests; full suite and Ruff.
5. Delete the data; real runs.
6. Instructions and architecture text; extension request 009; Wiki capture.

## Impl.Log

- Design written from the discussion of 2026-10-12.
- Implemented as planned, with these additions:
  - The check report lost its `label` option and its `context_example`
    key: nothing used them once the status stopped labelling POIs.
  - `ProjectActions.of(project)` became `for_project(project)`, because
    `of(poi)` is now the lookup of a POI's action.
  - The view `poi-action` is removed and not renamed: the action's own
    Context does its work.
- Checks: Ruff clean; `uv run pytest` 289 passed. `tests/scoring/
  test_blessing_attention.py` and one architecture test went with the
  attention report.
- Data: the action records were deleted and the deletion committed in the
  registry; the 250 files of `~/.tarav/check-reports/` were deleted.
- Real runs on the root: `tarav status --project .` opened 51 actions and
  listed the first 20 with their ids; a second run changed nothing;
  `tarav context --id 4e3b5daa-6888` opened the action with its entries.
- Instructions: the canonical Tarav System Prompt now points at the action;
  the three agents files were regenerated; `ARCHITECTURE.md`, the POI and
  scoring READMEs and `step-actions.md` updated.
- Not committed with this request: `src/tarav/l2/tests/actions.py` and
  `tests/test_actions_pois.py` still wait for another agent's package.

