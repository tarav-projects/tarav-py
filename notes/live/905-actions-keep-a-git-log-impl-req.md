# 905 — Actions keep a Git log — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented.

An action stays after it closes, and nothing in it says what state the
files were in when it opened or closed. This request gives each action a
small log of the Git state of the repositories its checks read, so that
what happened can be traced back with Git alone.

1. A check suite declares the Git repositories its checks read. A Project's
   suites declare the Project's own repository.
2. When a suite runs, it takes the state of its declared repositories at the
   start: HEAD and whether the working tree is clean (untracked files count
   as changes). Each result carries the state of the nearest suite above it
   that declares repositories.
3. An action logs that state: at every status change (opened, closed by any
   exit, reopened) the HEAD of each repository, clean or not; and, per
   repository, the first clean state seen after the last status change.
4. The action's Context shows the log, and advises committing and running
   the checks again while the current phase has no clean entry.
5. `tarav status` names the repositories that were dirty, with the same
   advice.

This is good to have, not a requirement: no exit depends on the log.

Non-goals: running checks on a commit or in a Workspace
(`tarav check --workspace`); the code's own commit (`tarav-py` that ran the
checks); a rehash exit for `OutputChanged`; any change to POI situations;
storing diffs or snapshots.

## Design narrative

### User decisions

The user turned one `OutputChanged` case into a question about the action
model: an action remains after it closes, so its closing must keep a record,
and what happened must be traceable later.
<!-- tarav.breadcrumb 965aeea22fcd -->

Checks can be run on HEAD, which records which commit they saw, or on the
working folder, which decouples them from Git history; trackability must
not be lost. Rerunning the checks is always possible: the model is not
wrong, a working-folder run and a commit run say different things. Storing
snapshots or diffs is too expensive; Git is the store.
<!-- tarav.breadcrumb eaaab24ed2bb -->

A check records the commit it was run on; Workspaces may later produce a
folder to run checks in.
<!-- tarav.breadcrumb 295e5260257a -->

A run can give commit provenance to checks: the checks themselves can see
whether the relevant repositories are dirty.
<!-- tarav.breadcrumb cf6ee81cdc8b -->

Make it good to have. Checks detect automatically, at the level of the whole
repository first, whether they ran on a committed state. Actions record the
best commit data they can: the commit when triggered and when closed, HEAD
when the repository is dirty. Agents are advised to keep things clean.
<!-- tarav.breadcrumb 741d5bf28516 -->

Check suites declare the repositories involved; it is a declaration, and the
maintainers are responsible for it. Actions keep a log of the Git state at
some events: open; still open and the first clean state; every status
change, recording HEAD when dirty; the first clean state since a status
change.
<!-- tarav.breadcrumb 97fa87f94ad0 -->

Clean states are logged per repository. Write the request and build it,
integrated well with the rest of Tarav.
<!-- tarav.breadcrumb 34f723014c5f -->

### Current behavior (inspected)

- `CheckSuite` (`l1/checks/__init__.py`) runs what `produce()` yields; a
  suite has an identity (`type`, `key`) or is a plain grouping. Nothing about
  Git. `CheckResult` holds the check, status, POIs and data.
- A Project runs its checks in `TaravProject.status()`
  (`l1/project/base.py`): `self.checks.own().run(...)`, then
  `self.actions.update(checks)`; members do the same for themselves. The
  Project suites are plain `CheckSuite`s built in `base.py`, `root.py`
  (`suite`, `own`) and `dev.py` (`PythonPackageProject`, `DocsProject`).
- `ProjectActions.update()` (`l1/actions/project.py`) registers new actions
  (`start`) and hands the suite to every action of the Project, open or
  closed (`refresh`). `POIResolutionAction.on_checks()`
  (`l1/actions/pois.py`) marks the situation, reopens, or closes as `gone`
  through `close_run()` (`l1/actions/__init__.py`). Blessing closes through
  `StepRunner.close()` and the same `close_run()`.
- `ActionRun` keeps the current closing; earlier states are only in the Git
  history of the actions registry.
- `GitRepository` (`l1/git/repository.py`) resolves a repository root and
  exact commits; `l1/git` imports only `l0`, so `l1/checks` and
  `l1/actions` may import it without a cycle.
- `tarav status` (`l3/status.py`) prints changes and open actions.

### Proposals of the agent

**State.** `GitRepository.state()` returns `{"commit": <HEAD>, "clean":
<git status --porcelain is empty>}`. `repository_states(paths)` in `l1/git`
maps each declared folder to its repository root and state; a folder outside
any repository, or a repository without a commit, is left out.

**Declaration.** `CheckSuite(..., repositories=(...))` holds folders. A
Project declares `TaravProject.repositories()`, by default its root, and
each Project suite passes it. The root of `taravangian-project` is not a
repository and records nothing.

**Run.** `CheckSuite.run()` takes `repository_states()` of its declared
folders before running anything; a suite that declares none keeps what the
suite above it took. Each result gets that mapping as `result.git`, and the
suite keeps it as `suite.git`.

**Log.** An action record gains `git`:
`{"repositories": [<root>...], "log": [{"event", "at", "exit"?, "repositories":
{<root>: {"commit", "clean"}}}]}`. Events: `opened`, `reopened`, `closed`
(with `exit`), and `clean` (one repository). A status entry whose repository
is clean already counts as that phase's clean entry. `repositories` is what
the latest raising declared; a blessing, taken outside a run, reads the
state of those repositories when it closes.

**Where it lives.** The log rules are one small module,
`tarav.l1.actions.git`, used by `close_run()` and by the POI action's
`on_checks()`; any Action Type whose run has a `git` section gets the same
closing entry.

**Advice.** Context entry `git` on every action: the log, and while the
current phase has no clean entry for a repository, "commit it and run the
checks again". `tarav status` adds one line per dirty repository the run
read, with the same advice.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md`, root
`tarav-md/notes/wiki/`. Relevant notes: `checks-workflow.md`,
`poi-system.md`, `daily/2026-10-14.md`. Supporting chat: session `abd0372d`
above. Capture status: done (`poi-system.md`, section "Actions keep a Git
log"; daily 2026-10-14).

## Execution.Plan

Core data shape: a repository state `{commit, clean}` keyed by repository
root; `CheckSuite.repositories` and `CheckSuite.git`; `CheckResult.git`; the
action's `git` section.

1. Feature — repository state. `GitRepository.state()`,
   `repository_states()`. Check: a test on a temporary repository, clean,
   with an edit, with an untracked file.
2. Feature — suites take it. `repositories=` on `CheckSuite`, `suite.git`,
   `result.git`, inherited by nested suites. Check: a test with a declaring
   suite, a nested plain suite and one without any declaration.
3. Feature — Projects declare. `TaravProject.repositories()` and the five
   Project suites. Check: the suite of a Project in a temporary repository
   carries its state.
4. Feature — actions log. `tarav.l1.actions.git`, the `git` record field,
   `opened()`, `on_checks()`, `close_run()`. Check: a test walking dirty
   open → clean while open → dirty gone → clean after closing → no repeat;
   and a blessing logs a closed entry with a fresh state.
5. Feature — advice. Context entry `git`; status line. Check: the test
   reads the entry; a real `tarav status` run.
6. Verification and docs: Ruff, the whole `tests/`, a real status run at
   the root, `ARCHITECTURE.md` if it describes actions or suites, the step
   actions module of `tarav-pkg`.
7. Breadcrumbs on the implemented surfaces; Wiki capture.

Risks: a commit made while a suite runs labels the run clean for that
suite (the state is taken at the start); accepted. Deviation trigger: if
any existing test or record format breaks beyond the new optional field.

## Impl.Log

- Design written from the discussion of 2026-10-14.
- No start checkpoint: the declared files hold other agents' uncommitted
  hunks, as in 904. Copies of every touched file taken before editing.
- Deviation: the state reading went into `tarav.l0._core.git_repository`
  (`repository_states`), not `l1/git`. `l1.checks` importing `l1.git`
  closed a cycle among subsystems (`checks → git → breadcrumbs → checks`,
  since `git` also has an `l2` part), which `test_architecture` rejects.
  `l1.git` re-exports it and `GitRepository.state()` uses it.
- Slices 1–5 done as planned. Checks: the suite test
  (`test_a_suite_records_the_git_state_of_the_repositories_it_declares`);
  the action tests (`test_an_action_logs_the_git_state_of_its_repositories_at_its_changes`,
  `test_an_action_whose_checks_declare_no_repository_logs_nothing`); a real
  run of the `tarav-md` and root Project suites (state of `tarav-md`; none
  for the root, which is not a repository).
- Two existing tests changed: the expected context entries now include
  `git`; the fake `subprocess.run` of
  `test_a_child_with_its_own_environment_reports_its_counts` passes Git
  commands to the real one.
- Found, not changed: `test_situation_checks_snapshot_validate_and_bind_poi_identity`
  fails when its file runs alone, before and after this change (it needs a
  runtime another test configures).
- Real run, `tarav status --project .` at the root: "Not committed:
  tarav-py (HEAD 023bbee)". A `tarav-md` action opened in that run logs
  `opened` at `e74fb61`, clean; its advice is empty.
- Checks: Ruff clean; default run 299 passed; the whole `tests/` folder 441
  passed, 1 failed (`test_scoped_lines`, another agent's area).
- Docs: `ARCHITECTURE.md`; `tarav-pkg/references/step-actions.md` (source
  `.skw/src/references/step-actions.skw.json`, a plain block, compiled).
- Breadcrumbs: submitted and audited ok on `l0/_core/git_repository.py`,
  `l1/checks/__init__.py`, `l1/project/base.py`, `l1/actions/git.py`,
  `l3/status.py`, both tests, `ARCHITECTURE.md`, this note, and the Wiki.
  The step-actions source is JSON, which holds no inline Breadcrumb.
