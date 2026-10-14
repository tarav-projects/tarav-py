# 906 — Test actions on the live path — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented.

Working on actions means watching real ones react: open, close as gone,
reopen, be blessed, log Git. Today that needs a real POI of some Project.
This request lets an agent and the User set up test actions on purpose, on
the live path: the real registry, the real status, the extension, the Git
log.

1. While `<project>/.tarav/tests/` exists, every Project's checks include a
   suite `Tarav.Test.Actions.Fixtures`. Each `*.txt` file in it is checked
   by the existing `TestMarkerCheck`: its lines holding `TODO` raise one
   `TestMarkerPOI` (blessable), whose action is registered under the
   Project like any other.
2. The folder ignores itself with a `.gitignore` holding `*`, so fixtures
   never make a repository dirty.
3. Deleting the folder stops the suite; its actions close as gone and stay
   in the registry, like any action.
4. `tarav-pkg/references/step-actions.md` gets a section with scenarios an
   agent can drive with the User.

Non-goals: other fixture kinds (a check that crashes, a suite left out)
until a scenario needs one; a command that creates the folder; changing the
automated pytest workspace (`update_workspace`).

## Design narrative

### User decisions

To help tests like the check of an action's Git log, the User proposed test
workflows with dummy actions: files under `<project>/.tarav/tests/` whose
presence makes a check register a test action, with different test actions
for different workflows.
<!-- tarav.breadcrumb 921a70ba258acd3260923cf14aa55329e2d63b340d141486acf477ca4dafc99c -->

They are real actions. The folder is ignored by Git if possible. It is part
of Tarav itself, not of one Project. Reuse the existing test workflows when
one fits, and add more when necessary.
<!-- tarav.breadcrumb 9d2200847df4a16d8dd2a45530aba42d4e387802e649b2d4dcc548c4bedffd68 -->

These tests are not always run: they are run to test and work on actions
without touching the real ones. They are interactive, more natural tests
that involve the User.
<!-- tarav.breadcrumb eb659821f445c69685f44359ad1f6f8d83630af2f2a27bc94335209c77b2ee70 -->

They test the real live path.
<!-- tarav.breadcrumb 87824b44867d09ee5b1399cf061221c5c4674f2476f1786f2d232827c82d4f24 -->
<!-- tarav.breadcrumb 327a91b0f85688afe4a82120189d49ce7cf5d8ebb9874da0ba09a2bc8d821878 -->

### Current behavior (inspected)

- `tarav.l2.tests.actions` (`ActionsTestsWorkflow`) has `TestMarkerCheck`
  (one per `*.txt` file; situation: the file name and its `TODO` lines) and
  `TestMarkerPOI` (blessable). It is used only by `tests/test_actions_pois.py`
  through `update_workspace`, a fake Project dict and a temporary registry;
  that test is in the default pytest run.
- `TestMarkerCheck` puts the lines in the details as well as in the
  situation; details must not repeat the situation (decided 2026-10-13).
- The l2 `Project` (`tarav.l2.project.Project`) is the base of the Docs,
  PythonPackage and root Projects; each builds its suite on
  `super().suite()`. `.tarav/` is partly tracked (`project.json`); only
  `.tarav/state/` is ignored.
- A suite with an identity is a detector: when it is no longer yielded, the
  suite above, run completely, closes its actions as gone.

### Proposals of the agent

**Suite.** `TestFixturesSuite` in `tarav.l2.tests.actions`, Type
`Tarav.Test.Actions.Fixtures`, key `.tarav/tests`, producing
`workspace_checks(folder)`.

**Where Projects take it.** `Project.Checks.suite()` in `tarav.l2.project`
adds a plain suite that, when it runs, yields the fixtures suite if the
folder exists. Deciding at run time keeps a built suite honest when the
folder appears or goes.

**Details.** `TestMarkerCheck`'s details keep only the file's full path.

**Scenarios.** In step-actions: create the folder and its `.gitignore`;
open, then fix; change the lines (a new situation: one closes, one opens);
bless, then fix; commit and run (a clean entry in the Git log); delete the
folder.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md`, root
`tarav-md/notes/wiki/`. Relevant notes: `poi-system.md`,
`daily/2026-10-14.md`. Supporting chat: session `abd0372d` above. Capture
status: done (`poi-system.md`, section "Test actions on the live path";
daily 2026-10-14).

## Execution.Plan

Core data shape: the folder `.tarav/tests/` of `*.txt` files; one
`TestFixturesSuite` per Project; one `TestMarkerPOI` per file with marker
lines.

1. Feature — the suite. `TestFixturesSuite`; details without lines. Check:
   the existing `tests/test_actions_pois.py` passes.
2. Feature — Projects take it. `Project.Checks.suite()`. Check: a test with
   a real `DocsProject` in a temporary folder: no folder, no suite; a fixture
   opens an action under the Project; deleting the folder closes it as gone.
3. Docs — scenarios in step-actions; `ARCHITECTURE.md` one sentence.
4. Verification: Ruff, the whole `tests/`, the architecture test (no
   subsystem cycle), and a live scenario in `tarav-py` run with
   `tarav status`.
5. Breadcrumbs; Wiki capture; commit.

Risk: `project → tests` may close a subsystem import cycle through
`actions`; deviation trigger: if it does, move the fixture suite where the
graph allows and record it.

## Impl.Log

- Design written from the discussion of 2026-10-14.
- The repository was clean before the first edit, so the evidence commit
  covers exactly this request; no start checkpoint was needed (empty scope).
- Slice 1: `TestFixturesSuite` (`Tarav.Test.Actions.Fixtures`, key
  `.tarav/tests`) in `tarav.l2.tests.actions`; `present(root)` gives it while
  the folder exists. `TestMarkerCheck` details hold only the file path.
- Slice 2: `Project.Checks.suite()` in `tarav.l2.project` adds a plain suite
  that yields it at run time. No subsystem cycle (`test_architecture`).
  Test: `test_a_projects_test_fixtures_open_real_actions_on_the_live_path`
  (a real `DocsProject`, real `project.status()`, a temporary registry).
- Slice 3: "Testing the action loop" in `tarav-pkg/references/step-actions.md`
  (plain source block, compiled); one sentence in `ARCHITECTURE.md`.
- Checks: Ruff clean; default run 300 passed; the whole `tests/` folder 442
  passed, 1 failed (`test_scoped_lines`, another agent's area).
- Live run in `tarav-py`: `.tarav/tests/hall.txt` opened a
  `Tarav.Test.Actions.MarkerPOI` action under `tarav-py`; its Git log says
  `opened` at `286b46d`, not clean (this request's own edits), with advice.
  `git status --untracked-files=all .tarav` lists nothing: the folder is
  ignored.
- Breadcrumbs: audited ok on `l2/tests/actions.py`, `l2/project/__init__.py`,
  `tests/test_actions_pois.py`, `ARCHITECTURE.md`, this note and the Wiki.
- Completion commit `38d7ac4` (tarav-py) and `11c92af` (tarav-md Wiki and
  step-actions), both through `tarav git commit` with Breadcrumb evidence.
- The live scenario, continued after the commit: with `tarav-py` clean, the
  next run logged `clean` at `38d7ac4` and the advice became empty; deleting
  `.tarav/tests/` closed the action as gone, logged `closed gone` at
  `38d7ac4`, clean. The action stays in the registry, closed.

