# 891 — Actions workflow: Step action MVP, tried on a test workflow — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented.

A minimal viable Actions workflow: a base Action Type, a Step action (an
opening test, the agent's work, closing tests), the action run as a recorded
instance, and the minimal Operator Context that feeds it. It is tried on a
new test workflow that produces POIs and has their blessing controlled by an
action.

Non-goals: Directives; conditioning `context()` or Project checks on an
operator; pipelines of steps; moving POI tracking or Project decisions to the
central place; a blessing action for real Projects; Context views for runs;
request 888's wider scope, which this request supersedes in its minimal part.

## Design narrative

### User decisions

Design the action workflow and let the Operator Context emerge from it.
Blessing a POI is an action: a Type represents what blessing a POI means, and
holds state and validation tests.
<!-- tarav.breadcrumb a42bc22a73f1 -->

There is a blessing action that is the root of all actions aiming to bless.
<!-- tarav.breadcrumb f7f9fd56d4ce -->

POIs, checks, situations and now actions are typed objects that relate to
each other; actions can be narrowly specialized, for instance to bless only
one Type of POI. Agents interact through well-defined objects, with checks to
detect deviation early.
<!-- tarav.breadcrumb 4d66d491eadf -->

Not everything must be an action, and nothing says work must be action-free
either. Tarav is expressive: it provides elemental primitives and packaged
bundles, and a bundle may require its parts, as a `CheckPOI` requires its
check.
<!-- tarav.breadcrumb 1e222280e044 -->
<!-- tarav.breadcrumb a4050fcd1e80 -->
<!-- tarav.breadcrumb d6a4e8ca01ef -->
<!-- tarav.breadcrumb 47813e78cfef -->

The action workflow starts with base Types that have almost no
functionality. An action has an identity as a Type and as an instance, like
a program and a process. Runs can be asked of the Project by state: running,
stopped, stopped with an error. Every action is linked to a skill, or a
subpath inside one, where the agent's instructions are; starting an action
tells the agent which to load. It should be more minimal than Iterante:
starting tests, the agent's work, a validation test.
<!-- tarav.breadcrumb c93cd0a6f189 -->

The first action to implement is a Step action: it closes a piece of the
agent's work into a step, with an initial test and closing tests. "Batchy"
(typed input, typed output, exit code) is a capability an action may have,
not the name of the first action.
<!-- tarav.breadcrumb 5ee0a71ec05c -->

A Step is given an input object that lives in the Operator Context. Its
closing tests are typed and can be Checks. It has an output object so steps
can be stacked. A step may be as large as wanted.
<!-- tarav.breadcrumb a450d0d6e219 -->

On the Operator Context: objects are produced for whatever consumer needs
them, not one per session; they need not be immutable, and a consumer that
cares detects changes with a hash. It is a place where agents put the typed
arguments of pipelines.
<!-- tarav.breadcrumb f524a3115742 -->
<!-- tarav.breadcrumb 8002498e0ecf -->
<!-- tarav.breadcrumb 97f18625aadc -->

The agent puts the starting input there and the workflow takes it from there:
the taking is under Tarav's control, so it can be checked and snapshotted.
Execution is stored elsewhere, and sessions working on an action are appended
to it. An object may name a Project, a session, both or neither.
<!-- tarav.breadcrumb d5563cd63862 -->
<!-- tarav.breadcrumb b43d2fa6a9cd -->

Everything is tracked and centralized: Tarav provides standard places for the
Operator Context and for the actions' durable data, using Records and the
Record Registry with its Git configuration, outside the Project's folder.
<!-- tarav.breadcrumb 7bfe7b5d4cd4 -->
<!-- tarav.breadcrumb 10661652faf8 -->

The User asked for a minimal viable product built with common sense, tried on
one of the test workflows with POI Types and blessings controlled by an
action.
<!-- tarav.breadcrumb 30bf9beac924 -->

### Current behavior (observed 2026-10-09)

- `tarav.l1.records.RecordRegistry().for_workflow(W)` gives a `RecordMap`: a
  Git repository per workflow under `~/Documents/tarav/records/<workflow
  ship>/`, one JSON file per key, with `insert`, `replace`, `load`, `names`
  and `commit`. `~/Documents/tarav/records/` does not exist yet on this
  machine.
- `tarav.l2.tests` holds the test workflows (`TestsWorkflow` and its
  navigation and scoring children), registered in the runtime.
- `BlessingStore(root).bless(poi, actor=, rationale=, support=)` stores a
  blessing; `support` is a list of typed references with a locator.
  `standing(poi)` reports blessed or unblessed.
- `SituationCheck` gives a check an identity from its Type and situation; its
  `CheckPOI`s carry that situation.
- `tarav.l1.agent.current_session.current_session()` names the running
  session (request 887).
- `tarav.l1.programs` holds the empty `TaravProgram` bootstrap. It is left
  as it is.

### Agent choices (proposals, not User decisions)

- **Operator Context** (`tarav.l1.operator_context`): `OperatorContext`, a
  base Record Type with an id, a creation time and optional `project` and
  `session`. Subtypes add their fields. `OperatorContextStore` over the
  workflow's Record Registry partition: `put` (insert or replace) and
  `take`, which loads, validates and returns the object with its record and
  hash. Taking commits the record.
- **Actions** (`tarav.l1.actions`):
  - `Action`: base, with a `skill` link (skill name and path) and nothing
    else.
  - `StepAction`: an `InputType`, `opening_checks(run, input)`,
    `closing_checks(run, input)`, `output(run, input)` and named
    `operations` that may only run while the run is running. Operations are
    how a domain write is placed under the action.
  - `ActionRun`: the recorded instance: action Type, state (`running`,
    `closed`), exit (`ok`, `error`), the intakes (context id, hash and
    snapshot each time the input was taken), the sessions that worked on it,
    the POIs of the opening and closing tests, the output.
  - `ActionRunStore` over the Actions partition; every transition commits.
  - A failed opening test still records a run, closed with an error, so the
    attempt is visible.
- **Blessing bundle** (`tarav.l2.actions.blessing`): `BlessingAction`, the
  root of blessing actions, a Step whose `bless` operation writes the
  blessing with a `support` reference to the run, and whose closing test
  requires such a blessing; `BlessedThroughAction`, a `BlessablePOI`
  capability meaning "blessed only through a blessing action"; and
  `UnharnessedBlessingCheck`, which raises a POI for a blessing of such a POI
  that names no action run.
- **Test workflow** (`tarav.l2.tests.actions`): a disposable workspace of text
  files; a `SituationCheck` per file raising a blessable POI for marker lines;
  `TestBlessingAction`, narrowed to that POI Type.
- **Commands**, keyed options only: `tarav operator-context put|show|list`
  and `tarav action start|do|close|show|list`. `start` prints which skill
  section to load. `--registry` selects another Record Registry root, for
  trials and tests.
- **Skill link target**: a short module in the Tarav package skill on how to
  work a Step action. Its existence is not checked yet.

### Open questions

- Partitioning inside a workflow's registry (flat keys for now).
- Whether a run's Project listing becomes a Project check that raises a POI
  for open runs.
- How the skill link is verified (Skillware reference checks).
- How Programs and Actions merge.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes:
`operator-context.md`, `programs.md`, `poi-system.md`, `daily/2026-10-09.md`.
Supporting session: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`.
Capture status: done (`operator-context.md` section, daily note).

## Execution.Plan

1. Operator Context workflow: Type, store, tests.
2. Actions workflow: `Action`, `StepAction`, `ActionRun`, store, the
   start/do/close mechanics; tests with a tiny in-test action.
3. Blessing bundle and the test workflow; tests for the whole loop: POIs
   raised, opening test, blessing through the action, closing test, output,
   a blessing made outside an action detected, a second session appended.
4. Commands and runtime registration; a live trial through the CLI against a
   temporary registry and workspace.
5. The skill module; `AGENTS.md` and `ARCHITECTURE.md`; Breadcrumbs; Wiki
   capture of the discussion since the last pass; completion commits.

## Impl.Log

- Design committed as `b900f88`, also the start checkpoint for this request's
  files, which are all new except `src/tarav/l3/runtime.py`, `pyproject.toml`
  and `ARCHITECTURE.md`; those three already held other agents' uncommitted
  edits and only this request's lines are committed from them.
- Slice 1, `tarav.l1.operator_context`: `OperatorContextWorkflow`,
  `OperatorContext` (id, creation time, optional `project` and `session`,
  open fields for subtypes), `Intake`, `OperatorContextStore` over the
  workflow's Record Registry partition (`put`, `names`, `load`, `take`).
  Placing an unchanged object makes no commit.
- Slice 2, `tarav.l1.actions`: `ActionsWorkflow`, `Action`, `SkillLink`,
  `StepAction`, `ActionRun`, `ActionRunStore`, explicit `register_action`,
  and `StepRunner` with `start`, `operate`, `close` and `abort`. Each command
  takes the input again and records its hash and record in the run; sessions
  are appended when a new one works on the run.
- Slice 3, `tarav.l2.actions.blessing` (root `BlessingAction`,
  `BlessedThroughAction`, the opening and closing checks with one POI Type per
  finding, `UnharnessedBlessingCheck`) and `tarav.l2.tests.actions`
  (`ActionsTestsWorkflow`, `TestMarkerCheck`, `TestMarkerPOI`,
  `TestBlessingInput`, `TestBlessingAction`).
- Slice 4, commands `tarav operator-context put|show|list` and
  `tarav action types|start|do|close|abort|show|list`, all with keyed options
  and `--registry`; workflows, Record Types and the test action registered in
  `tarav.l3.runtime`.
- Tests: `tests/test_actions_workflow.py` (6 tests: Operator Context, a
  generic Step, abort, sessions) and `tests/test_actions_blessing.py` (4
  tests: the blessing loop on the test workflow), both in `testpaths`. Full
  suite 261 passed in the shared worktree; Ruff clean.
- Live trial through the installed CLI against a temporary registry and
  workspace, in this Claude Code session: input placed with a Project; run
  started (opening passed, welcome names the skill module); `bless` refused
  without a rationale; `close` refused with `Tarav.Actions.Blessing.NotMadeInRun`
  and the run still running; rationale added with `put --id`; `bless` wrote the
  blessing with the session as actor and the run as support; `close` passed
  with the output; the run's intakes show two hashes; both registry partitions
  are Git repositories with one commit per transition. Nothing was written to
  `~/Documents/tarav/records/`.
- Defect found in the trial and fixed with a test: placing the same object
  twice failed on an empty commit.
- Skill module `tarav-md/skills/tarav-pkg/references/step-actions.md`, listed
  in the package skill; `ARCHITECTURE.md` paragraph.
- Product Breadcrumbs: 3 in `l1/operator_context/__init__.py`, 1 in its
  commands, 5 in `l1/actions/__init__.py`, 1 in its commands, 4 in
  `l2/actions/blessing.py`, 1 in `l2/tests/actions.py`, 1 in `l3/runtime.py`,
  5 in the test file, 2 in `ARCHITECTURE.md`, 3 in the skill module; audits
  clean after refreshing moved labels.
- Not done, by scope: no Project check for open runs; the skill link is not
  verified; no blessing action for real Projects; Programs untouched.
- Commit boundary. `src/tarav/l2/tests/` (the test workflows package) is
  another agent's uncommitted work; HEAD still has `tarav.l2.test_workflow`.
  The committed part therefore holds everything that stands on HEAD: the two
  workflows, the blessing bundle, the commands, their runtime registration,
  `tests/test_actions_workflow.py`, `ARCHITECTURE.md`. It was verified on a
  clean export of the commit: its 6 tests, the architecture, checks and agents
  tests (60) pass and Ruff is clean. Left uncommitted in the worktree until
  that package lands: `src/tarav/l2/tests/actions.py`,
  `tests/test_actions_blessing.py`, its `testpaths` line, and the runtime lines
  that register `ActionsTestsWorkflow`, `TestBlessingInput` and
  `TestBlessingAction`.
