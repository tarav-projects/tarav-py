# 895 — Dismissal replaces blessings — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: partly implemented. Dismissal is in place for Project POIs; the
blessing code is not removed (see Impl.Log).

A blessing becomes the dismissal close path of the POI's action. The separate
blessing mechanism (store, records, capability, attention schedule, Project
decisions folder for blessings) is replaced by dismissing the action, with a
reason and an attributed operator.

Non-goals: graded dismissal with scoring thresholds; other close paths such
as "provided"; Directives; Tarav Center.

## Design narrative

The User asked for the consequences of the day's design to be turned into
as many requests as needed and executed.
<!-- tarav.breadcrumb 54d64105d3d2 -->
<!-- tarav.breadcrumb 64a8a02277d1 -->

A blessing answers a specific question about a POI; its general meaning is
that the POI's claim is attenuated or dismissed, an overrule of the check.
<!-- tarav.breadcrumb 6cbc87f5a27e -->
<!-- tarav.breadcrumb 2988467a6903 -->

A POI can be resolved in several typed ways and dismissal is the softest; the
word "blessing" need not survive, and the design is free of earlier inertia.
<!-- tarav.breadcrumb 860aedf41ce6 -->
<!-- tarav.breadcrumb fee84f8f2342 -->

A blessing is a way to finish the action a POI started.
<!-- tarav.breadcrumb 179d173b6699 -->

### Current behavior (observed 2026-10-09)

- `tarav.l1.blessings`: `BlessablePOI`, `BlessingRecord` (a `Decision`),
  `BlessingAssessmentRecord`, `BlessingStore` (`bless`, `assess`, `standing`).
- `tarav.l2.blessings`: assertions and score vectors for blessings, the
  attention report, the tracking axis.
- `tarav.l2.project.decisions.ProjectDecisions.blessings()` keeps a Project's
  blessings in `<Project>/.tarav/decisions/`. No Project in this workspace
  holds a blessing record.
- Users: `l2/skw/pois.py`, `l2/skw/skills.py`, `l1/skw/presentation.py`,
  `l2/tests/scoring.py`, `CheckRun.clean()` and `_standing()`, and tests under
  `tests/scoring/`, `tests/decisions/`, `tests/test_poi_*.py`,
  `tests/test_skw_poi.py`.

### Agent choices (proposals, not User decisions)

- "Can this POI be dismissed?" is a property of its Action Type: the
  resolution action offers `dismissed` unless the Type says otherwise. The
  `BlessablePOI` capability becomes `DismissablePOI`, read by the action.
- A dismissal is recorded in the action's record: who, when, the reason, and
  the operator's input as taken from the Operator Context.
- `CheckRun.clean()` and the reports ask the Actions workflow whether a POI's
  action is dismissed, where they asked the blessing store.
- Assessment of a dismissal by assertions and scores is kept as a later
  request; the present assessment and attention code is removed with its
  tests, and that loss is stated in the Impl.Log.
- The Decisions workflow keeps its `Decision` Type; only the blessing
  subtypes leave it.

### Open questions

- Is losing blessing assessment and the attention schedule acceptable until a
  graded dismissal is designed? If not, this request stops after putting
  dismissal in place and leaves the blessing code beside it.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes:
`poi-system.md`, `decisions.md`, `daily/2026-10-09.md`. Supporting session: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: design
discussion captured; implementation capture pending.

## Execution.Plan

1. Start checkpoint. `DismissablePOI`; dismissal data in the action record;
   `tarav action do --operation dismiss` for a Project POI; tests.
2. `clean()`, reports and Skillware presentation read dismissal.
3. Remove the blessing workflow, its Project store method and tests, or stop
   here if the open question says so.
4. Full suite, Ruff, a live dismissal on this workspace; Breadcrumbs;
   guidance and skill text; Wiki; completion commit.

## Impl.Log

- Designed 2026-10-09.
- Start checkpoint: commit `1c1fc53` (request 894).
- Done, steps 1 and 2:
  - `DismissablePOI` in `tarav.l1.poi.actionable`; `BlessablePOI` extends it,
    so every Type that could be blessed can have its action dismissed.
  - The action's record keeps whether its POI allows dismissal;
    `DismissalReasonCheck` raises `DismissalNotPermitted` otherwise. Records
    opened before this get the field on their next trigger.
  - `POIActions.standing(poi)`; `CheckRun.clean(actions=)` and
    `report(actions=)` treat a dismissed finding as settled, and rows carry a
    `dismissed` count that the text renderer shows when it is not zero.
  - `tarav check --project` reads dismissals for its report and its exit
    code, also with `--actions skip`. Reading never creates the registry
    (`ActionRunStore.exists()`).
- Tests: one new in `tests/test_actions_workflow.py` (a plain `CheckPOI` is
  refused, a dismissable one is dismissed, the report shows it, and a run
  whose only finding is dismissed exits 0). Full suite 260 passed in the
  shared worktree; Ruff clean.
- Real run on the root after compiling `AGENTS.md` from its source in request
  894: the action of `Tarav.Project.Agents.Product.Drift` closed as `gone` and
  the report printed the signal. No real POI was dismissed, by the standing
  rule not to settle existing POIs.
- Not done, step 3, and why. The blessing workflow is not only the Project's:
  Skillware packages have their own blessing store (`.skw/blessings`) and
  commands (`tarav skw skills ... bless`, `assess-blessing`, POI listings by
  blessing status), and blessings carry assessments with assertions and
  scores and an attention schedule. Removing them now would delete scored
  assessment with nothing to replace it, since graded dismissal is not
  designed. That is the case the request's open question set aside. What
  remains for a later request: Skillware packages on POI actions, a scored
  grade of dismissal, then removal of `tarav.l1.blessings`,
  `tarav.l2.blessings` and `ProjectDecisions.blessings()`.
- No blessing record exists in this workspace, so nothing needs migrating.
