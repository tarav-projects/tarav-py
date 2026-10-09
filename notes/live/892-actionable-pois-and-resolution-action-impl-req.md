# 892 — Actionable POIs and the POI resolution action — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Design.
Status: ready for the User's review; not executed.

Rebuild the Actions example of request 891 on the model the discussion
reached: a POI is only an event, and an actionable POI spins one action, the
POI resolution action, which stays open until one of its close paths is met.
Dismissal (what was called blessing) is one close path. This is tried on the
actions test workflow only.

Non-goals: replacing the Project POI tracking store (`tarav.l1.poi_tracking`)
or the Project's blessings and decisions; changing `tarav check`; hooks for
other workflows' actions; chains between actions; grades of dismissal and
scoring; changes to Tarav Center.

## Design narrative

### User decisions

A blessing answers a specific question about a POI, and the types should carry
that semantic. Its general meaning is that the POI's claim is attenuated or
dismissed, an overrule of the check.
<!-- tarav.breadcrumb 848aa3b4b7e8594ecdd1adedc88b7a34df000000de5d0695a376e73c22792640 -->
<!-- tarav.breadcrumb c128b7897e8f00d7d1ca09dbb8e4c7439c5c6dc2c3ebdfa004f064a94dfd6d06 -->

More generally a POI can be resolved in typed ways: the situation was changed,
something the POI asks for was done, or it was dismissed. The word "blessing"
need not be kept.
<!-- tarav.breadcrumb 1c7b053efd891d419c29581ab494b6bbb3567fbf7b76ffabd65449bc083d1632 -->

A POI is only the event of a situation being raised. It can activate an
action, and a blessing is a way to finish that action.
<!-- tarav.breadcrumb ae56f759003a95ba68a0e635e8949886474232d23e1fee1cfb15f9a05343dc7a -->

A tracked POI is an action triggered when the POI is first raised and closed
automatically when a later check no longer raises it. An action has several
close paths, as a program has. Earlier designs need not be kept.
<!-- tarav.breadcrumb c9b6ee7279d88c0f213e292e2fbc45d8f2bf7d25c6f1e9f34e1b24072606f1cc -->

One action per POI. Other workflows may later attach their own independent
actions, and actions may close when others close.
<!-- tarav.breadcrumb c74fa25ad8915f73b54ceedf526df69d4c8e8d3530ed07401328aae083e878a2 -->

The POI that spins an action is, for now, an actionable POI. A loop owned by
the Actions workflow asks each running action whether a close path is met and
closes it if so; that is preferred to hooking into the checks.
<!-- tarav.breadcrumb 5b89eacbcdb76899c10af83df17e48eb83dfbb0888357fd075a98545341bea31 -->

### Current behavior (after request 891)

- `tarav.l1.actions`: `StepAction` has one set of closing tests; a run ends
  with exit `ok` or `error`; only an operator closes it, through `StepRunner`,
  and every command takes an input from the Operator Context.
- `tarav.l2.actions.blessing`: `BlessingAction` writes a `BlessingRecord` in a
  `BlessingStore` from inside a run; `BlessedThroughAction` and
  `UnharnessedBlessingCheck` detect blessings made outside one.
- `tarav.l2.tests.actions` (uncommitted, beside another agent's uncommitted
  test workflows package): text files, `TestMarkerCheck`, `TestMarkerPOI`,
  `TestBlessingAction`.
- `tarav.l1.poi_tracking`: `TrackablePOI`, and a tracker that a check run's
  results are handed to (`CheckRun.track(into=...)`); checks never write to it.

### Agent choices (proposals, not User decisions)

- **Close paths on the Step action.** A `StepAction` declares named exits.
  Each exit has its tests and says who may take it: an operator, the loop, or
  both. A run records the exit it closed by, with what that exit recorded.
  `error` remains for an aborted run or a failed opening. The single closing
  test of request 891 becomes the one exit of an action that declares no
  other.
- **`ActionablePOI`**, a POI capability in the Actions workflow: the POI Type
  names the Action Type it spins, by default the POI resolution action.
- **`POIResolutionAction`** (root of the actions that follow a POI). Its input
  is the POI event as raised, kept in the run; no operator is needed to open
  it. Exits:
  - `gone`: taken by the loop when the POI's check completed and did not
    raise it. A check without an identity can never show this, as today.
  - `dismissed`: taken by an operator, whose input (a reason) comes from the
    Operator Context. The dismissal is recorded in the run itself; no separate
    blessing record is written.
- **Opening and the loop.** The Actions workflow is handed a check run's
  results, as the tracker is today: it opens a run for each actionable POI
  that has no running or dismissed run for its identity, and takes `gone` for
  running runs whose POI was not raised. A separate `sweep` asks every running
  action for exits the loop may take. `tarav action sweep` exposes it.
- **Identity and recurrence.** A run is keyed to the POI identity (Type and
  situation). A dismissed POI that is still raised keeps its closed run. A
  POI raised again after `gone` opens a new run; the history is the runs.
- **Listings show the exit**, so `gone` and `dismissed` are never confused.
- **The example.** `TestMarkerPOI` becomes an actionable POI; the test
  workflow's check results are handed to the Actions workflow; the blessing
  bundle and `TestBlessingAction` are removed, with `BlessedThroughAction`
  and `UnharnessedBlessingCheck`, which no longer have a case: a dismissal
  cannot exist outside a run.
- **Commits in batches**: one registry commit per hand-off or sweep, not per
  run.

### Open questions

- Names: "actionable POI", "resolution action", "dismissed", "gone".
- Does `dismissed` require a reason in this first version, or is the bare
  overrule allowed? Proposed: a reason is required.
- Should the `provided` kind of exit (the POI asks for data) be in the
  example? Proposed: not yet.
- When the Project's tracking and blessings move onto this, which records are
  migrated and what does Tarav Center read? A later request.
- Is the test workflow's check handed to Actions by the test itself, or
  through a small Project-like provider?

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes:
`poi-system.md` (section "A POI is an event; what follows it is an action"),
`operator-context.md`, `daily/2026-10-09.md`. Supporting session:
`claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: done for
the design discussion.

## Execution.Plan

1. Exits on `StepAction` and `ActionRun`; `StepRunner.close` takes an exit;
   request 891's tests adapted.
2. `ActionablePOI`, `POIResolutionAction`, the hand-off from check results,
   the sweep, `tarav action sweep`; listings show exits; batch commits.
3. The test workflow on it; tests: a POI opens a run; a second check run opens
   none; fixing the file closes by `gone`; dismissal closes by `dismissed` and
   stays closed while raised; a changed file opens a new run; a returning
   situation opens a new run.
4. Remove the blessing bundle; update the skill module, `ARCHITECTURE.md`,
   Breadcrumbs, Wiki; completion commits. The test-workflow part still waits
   for the test workflows package to be committed.

## Impl.Log

- Designed 2026-10-09. Not executed.
