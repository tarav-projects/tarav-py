# 899 — Suites are detectors that hold their run — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented.

`tarav project status` is the command agents repeat, and it ran the whole
pytest suite of `tarav-py` every time, about a minute. Running only part of
the checks was not possible without wrongly closing actions: an action
closed as gone whenever its POI was not in the results. This request makes
partial runs safe and uses them for the tests.

1. A suite is a class with a Type id. It holds the code that runs checks and
   nested suites, and the results of its one run. `CheckRun` is removed; what
   it held is on the suite.
2. A suite can run whole or filtered, and it says whether it ran completely.
3. An action records the chain of suites above the check that raised its
   POI. It closes as gone when the nearest suite above it that ran
   completely did not produce its POI.
4. `PyTestSuite` is a base Type in Tarav. It calls pytest once and produces
   one bound suite per test file.
5. `tarav project status` and `tarav check` skip suites that are not part of
   the routine run, which today is the pytest suite. `--all` runs everything.
6. The existing action records are deleted; the first `--all` run opens them
   again. No code reads records of the old shape.

Non-goals: selecting inside pytest; a history of runs; a cost model for
checks; a child Project in its own Python environment.

Follow-up in another repository:
`vscode-tarav-center/notes/live/008-the-status-gives-a-suite-impl-req.md`.

## Design narrative

### User decisions

The status command took a very long time because of the test suite check.
<!-- tarav.breadcrumb 9e227f4fffda735b9202df7da95bf37706d3bdd72a485721b95c323f25688fd0 -->

Each failing test as one POI is good. The problem is convenience: the
status command is called constantly by agents as the mechanical feedback
about the Project, so it cannot be that slow. Agents can focus on a subset;
the full suite does not need to run all the time.
<!-- tarav.breadcrumb 1456ec11e90b40344e075fb2b529bfaa587b53b42f5648957978aa2773d6eeb2 -->

A check result cannot say which situations it covered: the situations that
disappeared cannot be listed. So the concept of a suite returns: tests are
put in compartments, and it is known which suites ran completely. Actions
know which suites they belong to, and those that need to detect a missing
POI look at complete suite runs. Suites are recursive and subsets of them
can be run.
<!-- tarav.breadcrumb ac01f2ad8cde62e5d35f8e7bb5bbb9759e6bef1a871f07c106dbfc8a703c9a0a -->

A suite has an identity, not a path: simpler, and no migration when it
moves. A suite is a container that groups checks and their run information.
It can be run partially or completely, for instance filtered by check Type.
<!-- tarav.breadcrumb fecc93ee3da5330282079e9c1ef5084d0aa21b37448f63b3a1579ea12486e3d4 -->

All the data lives on the suite, the run results included. Every suite is a
class, as every check is a class, and it contains the method that runs the
checks.
<!-- tarav.breadcrumb a1088c58d55161dffb728d8ae3251c5c6717f720b4b82d71f88ad337e24e07c9 -->

One suite instance holds one run, or its results can be reset. A check only
returns its result. Fewer object Types is fine when clarity does not
suffer. No history of runs: whoever wants one keeps an old instance.
<!-- tarav.breadcrumb f47fbbc78d12d335b8fdae56776fa19068b9bbd69875d5657011f630f9c4eb5d -->

A correction the user asked to state explicitly: a suite does not contain
checks, and the checks cannot be enumerated, because many depend on
situations and situations cannot be enumerated. A suite contains code that
runs the checks, and which ones run can change from run to run.
<!-- tarav.breadcrumb f31418e924922e447b122760803e71f6ebcb2e3b2f3d345c9538eed15433b11b -->

The closing rule: the signal is gone when the detector no longer detects it.
<!-- tarav.breadcrumb 1f85b6dfe1ac25479cc484862f29ffcb1a29d067e8fd306ba09b1464ec734ff9 -->

One bound suite per test file. Any default is fine to start with; what
matters is a flag that runs everything. Selection inside pytest is left
out; a minimal filter on the whole pytest suite, and a `PyTestSuite` base
type. No legacy code: old data is deleted or migrated.
<!-- tarav.breadcrumb 9db2d03c908010205751d032c661a6acdb070ae879cc7d79e2d2118ae8392057 -->

Write the request and build it; delete the existing records and reopen.
<!-- tarav.breadcrumb 0598e2403be5cad4b33b6ccfea72cd28c69b1e382797d72665405e26968003e1 -->

### Current behavior (inspected)

- `CheckSuite` (`l1/checks/__init__.py`) is one class without identity: a
  source of checks, nested suites or ready results, possibly a function.
  `run()` returns a `CheckRun` with the flat results; `CheckRun` builds the
  summary and the grouped report.
- `POIResolutionAction.on_checks` closes an action as gone when its POI is
  not in the run, unless a check of the same Type did not complete.
- `TestSuiteCheck` (`l2/project/dev.py`) is one check that runs the whole
  pytest suite and raises one POI per failing test.

### Proposals of the agent

**Suite.** `CheckSuite` stays the base Type and takes over `CheckRun`:
`add`, `results`, `results_of`, `pois`, `findings`, `summary`, `report`,
`clean`. New:

- `produce()`: the code that yields what to run: checks, nested suites or
  ready results. The default reads the source given at construction; a
  function there receives the suite, to read what ran before.
- `run(select=None, on_result=None)`: resets, runs what `produce()` yields
  and returns the suite. `select` is asked for each check and nested suite
  before it runs; one it refuses is kept as not run.
- `complete`: the suite ran, nothing was refused, every check completed and
  every nested suite is complete.
- `identity`: `{"type", "key"}` for a suite of a subclass or a suite given a
  `key`; a plain grouping has none and counts as part of the suite above it.
- `routine`: a class says whether it belongs to the run that is repeated.
- `walk()`: each result with the chain of identified suites above it.

**Closing rule.** The action keeps the chain in `event.suites`. When its POI
is not raised, `on_checks` looks for the innermost suite of the chain that
is in this run; when none is, the suite handed over stands for it. That
suite is conclusive: the situation is absent and an open action closes as
gone. It is not: the action stays, with the situation `check failed` when
a check failed and `not run` when something was left out.

Changed while building, see the log: a suite answers for its own code and
not for nested suites that have an identity, and it answers per Type of
check.

**Tests.** `PyTestSuite` (`l1/checks/pytest_suite.py`), not routine, runs
pytest once with a JUnit report to learn which files ran, and yields one
`PyTestFileSuite` per file holding one result with that file's failing
tests. `TestSuiteCheck` is removed; `PythonPackageProject` uses the suite.

**Commands.** Both commands take `--all`. Without it, suites that are not
routine are refused. The status says which suites did not run.

**Project.** `project.checks.run(select=, on_result=)` returns the suite.
`ProjectStatus.checks` is each Project's own suite and `suite()` gathers
them for the report.

**Data.** The records of the Actions partition of the Record Registry are
deleted once, by hand, and the deletion committed in that registry.

### Open questions

- What the routine run should include is to be learned by using it.
- More suites could be given identities to make closing finer.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md`, root
`tarav-md/notes/wiki/`. Relevant notes: `poi-system.md`,
`checks-workflow.md`, `daily/2026-10-12.md`. Supporting chat: session
`abd0372d` above. Capture status: done (`poi-system.md`, section "Suites are detectors that hold
their run"; `checks-workflow.md`; daily 2026-10-12).

## Execution.Plan

1. Checks: the suite takes over the run; `select`, `complete`, identity,
   `walk`; remove `CheckRun`.
2. Actions: the chain on the record and the closing rule.
3. `PyTestSuite`; the dev Project uses it; providers and the root adapt.
4. Commands: `--all`, the skipped suites in the output.
5. Tests rewritten; full suite and Ruff.
6. Delete the action records; real runs with and without `--all`.
7. Instructions and architecture text; extension request 008; Wiki capture.

## Impl.Log

- Design written from the discussion of 2026-10-12.
- Implemented. Two changes to the plan, both found by the tests:
  - With "ran completely" meaning everything below a suite, leaving the
    pytest suite out made the Project's top suite incomplete, so a routine
    run could close nothing at all. A suite now answers for its own code
    (`exhausted`); a nested suite with an identity answers for itself.
  - One failed check kept every action under the same suite. A suite now
    answers per Type of check (`conclusive_for`), as the rule did before.
- The suite of each skill package has a key, so its actions name it.
- `routine()` in `tarav.l1.checks` is the filter both commands and the
  extension use.
- Checks: Ruff clean; `uv run pytest` 292 passed.
- Data: the 52 records of the Actions partition were deleted and the
  deletion committed there. The empty `records` folder had to be recreated,
  because the registry refuses a partition without it.
- Real runs on the root: the routine status took about 4 seconds, opened 51
  actions and named the pytest suite as not run. `--all` ran 394 checks in
  1 minute 38 and changed nothing. A routine run after it changed nothing.
- Not exercised on real data: a failing test opening and closing its
  action. The pieces are tested separately.
- Instructions: the canonical Tarav System Prompt names `--all`; the three
  agents files were regenerated; `ARCHITECTURE.md` and `step-actions.md`
  updated.
- Not committed with this request: `src/tarav/l2/tests/actions.py` and
  `tests/test_actions_pois.py` still wait for another agent's package.

