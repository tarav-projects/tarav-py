# 896 — Suites, closing records and the blessing as a closing — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented.

Reimplement blessings with the Actions primitives, and give "the situation
is gone" a clear meaning.

1. A **suite** is named by the caller of a check run. It manages the actions
   it opened and settles them after each run: an action whose POI the suite
   no longer produces closes as gone.
2. **Every closing produces a typed record.** An Action Type declares its
   closing paths; each path names the Type of the record it leaves.
3. A **Blessing** is the record of the path "closed although the situation
   still exists". It carries a reason and evidence and declares assertions.
4. **Reopening is decided by how the action was closed**, and the status of
   an action is a small vector: situation, action, closing.
5. The earlier blessing store, its records and its commands are removed.

Non-goals: Directives; hooks and chains; new suites beyond Projects and
Skillware packages; changes to the scoring system itself; migrating earlier
blessing records.

Follow-up request in another repository:
`vscode-tarav-center/notes/live/005-action-axes-and-blessing-impl-req.md`.

## Design narrative

### User decisions

The blessing code left beside dismissal by request 895 has to be
reimplemented with the new primitives.
<!-- tarav.breadcrumb aa735b651678 -->

An action is running and a blessing is just one way of closing it; it is not
different in kind from other closings. The action defines how it can be
closed. The POI can still appear: a blessed action is a suppressed one. The
blessing is a record, it can carry evidence or a reason, and so it can be
scored; that is why it hooks into the assertion system. A Blessing is a type
of closing constructor for a POI action.
<!-- tarav.breadcrumb de1fe4ddd2b4 -->

The scoring system is independent: it assigns scores to declared
assertions. Scores attach to assertions, and the Blessing, like any object,
declares assertions. The chain Situation, SituationCheck, SituationPOI,
SituationAction, SituationBlessing is one particular implementation; others
can come later. The word Blessing stays, defined mechanically: the action is
closed even though the situation still exists.
<!-- tarav.breadcrumb 266084a945ad -->

Closing an action produces a record of some Type; it is not a plain status.
An action can close automatically (a check passes) and can have several
closing paths, for instance the situation disappears, or it is blessed. An
action can be reopened, and that can depend on how it was closed. Status is
a vector with several axes, not one value.
<!-- tarav.breadcrumb bf16774289a7 -->

The User asked what the "subject" was. The agent had added a per-check
subject key in request 894 without approval, to tell "the check looked again
and found nothing" from "the check did not look".
<!-- tarav.breadcrumb 34185fabaa01 -->

A suite replaces that. A suite targets checks run on targets and has a
hardcoded UUID. Its meaning: if you run me, you are testing the same thing.
A situation has disappeared when the suite no longer detects it.
<!-- tarav.breadcrumb d01e90ba46ae -->

A suite can be very general, for instance one Projects suite. If it did not
produce the POI, the action is closed. No finer scoping is needed.
<!-- tarav.breadcrumb d8ce414098de -->

A check does not carry a suite. The caller names it: `tarav check` says
which suite the run is, and attaches it where documentation needs it. The
suite is like the operating system: it knows all the actions that belong to
it, and after a run it closes those that the results allow.
<!-- tarav.breadcrumb 9438d401c2cb -->

Identity is apart: an action's identity comes from its Type and its POI. The
suite is who manages the action.
<!-- tarav.breadcrumb 0a4700743d34 -->

The User asked to run this as a Develop pass.
<!-- tarav.breadcrumb 500491ddd147 -->

### Current behavior (observed 2026-10-11, `tarav-py` at `1688419`)

- `tarav.l1.actions`: `Exit(name, by)`; a run keeps `state`, `exit`,
  `output`, `closings` (attempts). `StepRunner.close` and `sweep` close runs.
- `tarav.l1.actions.pois`: `POIResolutionAction` with exits `gone` (loop)
  and `dismissed` (operator, `DismissalInput` with a reason). `POIActions
  .observe(pois, completed=, whole=, project=)` opens actions and closes
  them as gone by matching the owning check: `Check.subject_key`, else
  `Check.identity`, else "the whole suite ran". The reopen rule is two
  hard-coded lines.
- `tarav.l1.checks`: `Check.subject_key`, `Check.clear()`, `ClearPOI`,
  `CheckRun.completed()`; `clean()` and `report()` take both a blessing
  `store` and `actions`. A `CheckSuite` Type exists there already; it is a
  source of checks that can nest, with no identity of its own and no
  knowledge of actions.
- `tarav.l1.blessings`: `BlessablePOI`, `BlessingRecord` (a Decision),
  `BlessingAssessmentRecord` (a manually given score), `BlessingStore`.
  `tarav.l2.blessings`: two assertions on a blessing record, their cases and
  tribunal, the score vector read from the scoring repository, and an
  attention report used only by tests.
- Users of the store: Skillware packages (`.skw/blessings`, `tarav skw
  skills bless | assess-blessing`, `--blessing-status`), `ProjectDecisions
  .blessings()`, a `blessings` store in the runtime.
- Records accept unknown fields (`extra="allow"`), so existing action
  records load after fields are dropped.

### Agent choices (proposals, not User decisions)

- **Name.** The managing suite is `tarav.l1.actions.suites.Suite`
  (`Tarav.Actions.Suite`), separate from `CheckSuite`, which keeps composing
  checks. A suite Type carries the hardcoded UUID as its Type identity.
  `ProjectsSuite` and `SkillwareSuite` are the two first ones.
- **`Suite.settle(pois, target=, incomplete=(), complete=True)`.** It opens
  or reopens the action of each actionable POI, stamps `suite` and the
  target on the action, and records the situation as present. Then, among
  the actions it manages for that target and did not see: the situation
  becomes absent, and an open one closes as gone. Two guards: an action
  whose raising check Type is in `incomplete` (it crashed) is left as it
  is; with `complete=False` (not a run of the whole suite) nothing closes.
- **An unmanaged action is taken over** by the suite that next raises its
  POI. Actions opened before this request have no suite and are taken over
  on the next run when their POI is still raised; the others stay open.
- **Target** is the dictionary the caller gives (`id`, `name`, `root`); it
  is matched on `root`, as before.
- **Closing records.** `Closing` is a record Type (`id`, `run`, `exit`,
  `at`, `by`). `Exit` gains `closing`, the record Type its path leaves, and
  the record is kept on the run as `closing` (current state; earlier ones
  are in the registry's Git history). `Closing.reopens` says whether a POI
  raised again reopens the action: true for `GoneClosing`, false for a
  `Blessing`.
- **Axes** are plain fields on the run, each with one writer: `situation`
  (`present`, `absent`, set by the suite), `state` (the action, set by the
  closing paths), and `closing` (the record). `axes(run)` returns the three.
- **Blessing vocabulary replaces dismissal vocabulary**: exit `blessed`,
  `BlessingInput` (reason, support), `BlessablePOI` in the POI workflow (the
  one capability; `DismissablePOI` and the earlier `BlessablePOI` merge
  into it), `BlessingInputCheck`.
- **`Blessing`** (`Tarav.Blessings.Blessing`, in `tarav.l1.blessings`) keeps
  the actor (the session), the reason, the support and a snapshot of the
  POI. Its `assertions` and `score_vector` are composed from `l2` as today.
  The two assertions keep their logic; their subject is a reference to the
  Blessing.
- **Removed without replacement**: `BlessingAssessmentRecord` and `tarav skw
  skills assess-blessing` (a score typed by hand; the scoring system is
  where scores come from), `Check.subject_key`, `Check.clear()`, `ClearPOI`
  and `CheckRun.completed()` (nothing reads them once the suite closes
  actions).
- **Skillware.** `tarav skw skills check | build | deploy` settle the
  Skillware suite on the package. `bless` is removed: a Skillware POI is
  blessed like any other, with `tarav action close --exit blessed`.
- **Earlier blessing records are not migrated.** None exists in this
  workspace.

### Open questions

- When a blessed action's situation goes away and returns, the blessing
  still holds. The situation axis records that it was absent in between.
- Two suites raising the same POI share one action; the first manages it.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes:
`poi-system.md`, `operator-context.md`, `daily/`. Skill module:
`tarav-md/skills/tarav-pkg/references/step-actions.md`. Supporting session:
`claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: done
(`poi-system.md`, daily note 2026-10-11).

## Execution.Plan

1. Start checkpoint. Closing records, `Exit.closing`, axes; the runner and
   the sweep build closings. Tests.
2. `Suite`, `ProjectsSuite`; `tarav check --project` settles it. Remove
   `subject_key`, `clear()`, `ClearPOI`, `completed()`, identity matching.
   Tests; a real run on the root Project.
3. Blessing vocabulary and the `Blessing` record; `clean()` and reports read
   only actions; the action view and commands.
4. Assertions and attention on the `Blessing`; remove the store, its
   records, `ProjectDecisions.blessings()` and the runtime store; Skillware
   on its suite.
5. Full suite, Ruff, reinstall the CLI, Breadcrumbs, `ARCHITECTURE.md`,
   skill module, Wiki, completion commit.

## Impl.Log

- Designed 2026-10-11.
- Start checkpoint: commit `9b30df3` (this note). 10 Breadcrumbs on it, audit
  clean.
- Closing records: `Closing` (`Tarav.Actions.Closing`) with `fields()` and
  `reopens()`; `Exit.closing`; `close_run()` builds and validates the record
  and keeps it on the run as `closing`; `ActionRun.closing()` returns it as an
  object; `axes(run)`. A third taker, `suite`, joins `operator` and `loop`.
- Suites: `tarav.l1.actions.suites.Suite` with `settle`, `managed`,
  `manages`, `reference`. `ProjectsSuite` (`tarav.l1.project.suite`),
  `SkillwareSuite` (`tarav.l2.skw.suite`). `tarav check --project` settles
  the Projects suite, passing `CheckRun.incomplete()`.
- Removed: `Check.subject_key`, `Check.clear()`, `ClearPOI`,
  `CheckRun.completed()`, `POIActions.observe()`, the matching by check
  identity and the `whole` flag.
- Blessing: `tarav.l1.actions.blessing` holds `Blessing`, `BlessingInput`,
  `BlessingInputCheck` and its two POIs, all in the Blessings workflow.
  `BlessablePOI` is in `tarav.l1.poi.actionable`. `POIResolutionAction` has
  the paths `gone` (`GoneClosing`, by the suite) and `blessed` (`Blessing`, by
  an operator). `POIActions` reads: `of`, `standing`, `axes`, `blessing`,
  `blessing_standing`.
- Deviation from the design: the Blessing Types are defined in the Actions
  package, not in `tarav.l1.blessings`. Defining them there made the two
  packages import each other, which the architecture test forbids. They
  still belong to the Blessings workflow by their Type entity.
- Deviation: a Blessing is `Assertable` and not a `Decision`. The earlier
  record was a Decision subtype; a closing record is not an attributed
  Decision record in the Project's decisions folder.
- Assertions: `tarav.l2.blessings.assertions` takes a `Blessing`; the subject
  reference is `Tarav.Blessings.Blessing.Reference`. A Blessing validates the
  POI it keeps (identity matches Type and situation).
- Attention: `attention_report(collector, actions, repository)` reads the
  Blessing of each POI's action. Loss, stated: an action has one current
  Blessing, so counting several independent reviews of the same POI is gone
  (`review_count`, `independent_reviews`,
  `maximum_independent_reviews`). A supported and well scored Blessing defers
  three times longer, as one supported review did before.
- Removed: `BlessingStore`, `BlessingRecord`, `BlessingAssessmentRecord`,
  `ProjectDecisions.blessings()`, the runtime's `blessings` store, `tarav skw
  skills bless` and `assess-blessing`, a package's `.skw/blessings` store.
  `tarav skw skills check | build | deploy` settle the Skillware suite; an
  evaluation whose checks could not all run opens actions and closes none.
- `CheckRun.clean()` and `report()` take only `actions`; rows count `open` and
  `blessed`. `POICollector.report(actions=, blessing=)`.
- Commands: `tarav action types` shows each exit's closing Type; `list` rows
  carry `axes` and `suite`; `close` prints the closing record. The
  `poi-action` view has the entries `standing`, `poi`, `managed-by`,
  `closing`, `closings`, `acting`, `history`, `reported`.
- Tests: 259 passed in the shared worktree; Ruff clean. New
  `tests/blessing_bench.py` blesses a POI through the Actions workflow for the
  tests that used the store. `tests/test_actions_workflow.py` has 18 tests,
  among them: a suite closes only what it manages and only after a whole run;
  a blessed action stays closed and its situation axis moves; a Blessing
  declares assertions and no score is kept on it.
- Real run on the root Project (`tarav check --project .`): 51 POIs; the 51
  actions opened before this request were taken over by `Tarav.Project.Suite`
  and show `situation: present, action: open`. One action closed as gone by
  request 894 has no suite and stays as it is.
- Smoke run with a throwaway registry: `tarav skw skills check` on
  `tarav-md/skills/tarav-hugentics` opened 21 actions under `Tarav.SKW.Suite`.
- Known limit found: the Project's checks include the checks of its skill
  packages, so in a real Project a Skillware POI's action is managed by the
  Projects suite, and the Skillware suite leaves it alone. This is the "two
  suites raise the same POI" case of the open questions.
- Not committed with this request, as before: the actions test workflow
  (`src/tarav/l2/tests/actions.py`, `tests/test_actions_pois.py`), which is
  adapted in the worktree and waits for another agent's `l2/tests` package.
  In the worktree only, two entries naming the removed record Types were
  taken out of `RECORD_STATE_DEBT` in
  `tests/kernel/test_object_record_contract.py`, a list another agent added
  and has not committed.
- Product Breadcrumbs: 24 new on 15 surfaces (`actions/__init__.py` 2,
  `actions/blessing.py` 2, `actions/suites.py` 4, `actions/pois.py` 2,
  `project/suite.py` 1, `skw/suite.py` 1, `skw/skills.py` 1, `l3/check.py` 1,
  `blessings/assertions.py` 1, `checks/__init__.py` 1, `poi/actionable.py` 1,
  `tests/test_actions_workflow.py` 4, `tests/blessing_bench.py` 1,
  `l2/tests/actions.py` 1, `ARCHITECTURE.md` 3). Moved labels refreshed with
  `--refresh-positions`. `AGENTS.skw.json` has no Breadcrumb convention.
- `AGENTS.md` recompiled from its Skillware source; `ARCHITECTURE.md`,
  `l1/poi/README.md`, `l2/scoring/README.md` updated.
