# 916 — tarav-change witness, and hooks that stop with an overrule

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Autonomous. Phase: Develop.
Status: implemented and verified; Wiki captured.

Follow-up to request 915. A machine-local witness, outside the repository,
keeps the tarav-change IDs each Project's branch had at its last commit. The
tarav-change `pre-commit` compares it with the `.tarav/changes` being
committed: when IDs the witness holds are missing, the hook stops the
commit, unless an overrule flag names the handler. Stops and overrules
become actions registered on the Project, and the tarav-change check makes
the same comparison between commits, so a history rewrite that cut the file
is noticed even though the repository no longer shows it. The Git hook
contract changes from "never blocks" to "may stop, with an overrule flag".

Non-goals: finding the new commit of a lost ID (the witness is a witness,
not a link); witness sharing between machines; content matching such as
`patch-id`; enabling the hooks in other repositories.

## Why

Request 915 found that an amend cannot be detected, so an amended commit
gains a new ID and keeps the old line. The User answered that this is why
the file exists: the change-id file must be append-only, so that even
surgery cutting parts of history must cut the file itself, which survives
many modes of change; and proposed a global registry under
`~/Documents/tarav` recording change-ids and commits outside the repository.
<!-- tarav.breadcrumb 4e47f2e80797 -->

The User then weighed the registry: knowing which change-id matched which
commit does not find the new commit once the repository's ID was cut or
amended; the strength of the file is that it sits next to the edits it
tracks.
<!-- tarav.breadcrumb f5ab9cc27d78 -->

The User set the bar: this is best effort to make references more robust,
not a system that fills the last 5% of cases; whoever rewrites Git owns the
consequences, and references carry other hints about their subject. Knowing
when a loss happened is worth having.
<!-- tarav.breadcrumb 52b3819de20c -->

On the claim that only what remains in history can be checked, the User
corrected it: the external registry can track the change-id file and test
that it stays append-only, and the hook can stop the commit when that is
broken, with an overrule (for instance an environment variable) as a
speedbump.
<!-- tarav.breadcrumb 144f1caab6d3 -->

User decisions for this request: every stop or overrule is recorded and
sensed by the tarav hook and handed to the Project as an Action registered
on it; the hook contract is relaxed to "hooks stop, with an overrule flag",
to give an agent the opportunity to respond and rethink what it is doing;
the witness is stored as Records, one per Project and branch, under
`~/Documents/tarav/git-changes/`, machine-local.
<!-- tarav.breadcrumb 9688fe6ae684 -->

## Current behavior (after 915)

- `tarav.l1.git.hooks.dispatch` turns every handler failure into a warning;
  `run_hook` always exits 0; the script prints a warning on any non-zero
  exit and exits 0.
- `tarav.l1.git.change.TaravChange` appends an ID in `pre-commit`, adds the
  trailer in `commit-msg`, realigns the index in `post-commit`, logs
  rewrites in `post-rewrite`; `TaravChangeCheck` reports
  `Tarav.Git.Change.Missing`.
- `ProjectActions` (`tarav.l1.actions.project`) registers actions from a
  suite of check results: `start` builds new actions, `update` also hands
  the results to every registered action (closing what is gone).
- Data root: `tarav.l0._core.data_root.default_tarav_data_root()`; roots
  follow "argument, then environment variable, then default"
  (`TARAV_WORKSPACES_ROOT`, `TARAV_RECORDS`).

## Design

### Hook contract (`tarav.l1.git.hooks`)

- A handler may raise `GitHookRefusal(message)`. `dispatch` returns the
  warnings and the refusals separately; `run_hook` prints both and exits
  with `REFUSED_EXIT` (75) when anything refused.
- The script exits 1 (stopping Git) on `REFUSED_EXIT` only; any other
  failure, and a missing `tarav`, still warns and lets Git continue.
  Refusals in `post-*` hooks stop nothing, as Git ignores their status.
- `TARAV_GIT_HOOKS_OVERRULE` names the handlers whose stops are overruled,
  comma-separated (or `all`); `GitHookCall.overrule` carries them. A handler
  that would stop checks it and records the overrule instead.

### Witness (`tarav.l1.git.witness`)

- `ChangeWitness` Record (`Tarav.Git.Change.Witness`): `project` (the
  Project's `project_id`), `branch`, `changes` (IDs in file order), `at`.
  One file per Project and branch, rewritten at each commit:
  `<root>/<project_id>/branches/<branch, percent-quoted>.json`.
- `ChangeOverrule` Record (`Tarav.Git.Change.Overrule`, an entity): `id`,
  `project`, `branch`, `commit`, `missing`, `at`. Written once:
  `<root>/<project_id>/overrules/<id>.json`.
- `ChangeWitnesses(root=None)`: root from the argument, then
  `TARAV_GIT_CHANGES_ROOT`, then `~/Documents/tarav/git-changes`.

### tarav-change with the witness

- The branch is `git symbolic-ref --short HEAD`; a detached HEAD has no
  witness and is not compared. A Project without `project_id` neither.
- `pre-commit`, before appending: missing = witness IDs not in the file.
  If any are missing and `tarav-change` is not overruled: register the
  action of a `Tarav.Git.Change.Removed` POI and raise `GitHookRefusal`
  whose message says how many IDs are gone, that history may have been
  rewritten, and how to overrule. If overruled: keep the missing IDs in
  `.git/tarav/overrule` for `post-commit`, then go on.
- `post-commit`: realign the index (as before); then, when a pending
  overrule exists, write a `ChangeOverrule` with HEAD's commit and register
  the action of a `Tarav.Git.Change.Overruled` POI; then set the witness to
  HEAD's file, unless IDs are missing without an overrule (a `--no-verify`
  commit skips `pre-commit` but not `post-commit`): then the witness stays,
  so the loss keeps being reported.
- `TaravChangeCheck` adds: `Tarav.Git.Change.Removed` when HEAD's file
  lacks IDs of the current branch's witness (situation: project, branch;
  missing IDs in details), and one `Tarav.Git.Change.Overruled` per
  overrule record of the Project (situation: project, branch, commit), so
  those actions stay open until blessed. The hook raises the same POIs from
  the same check Type, so `tarav status` reconciles the actions it opened.
- `ProjectActions.register(checks)` registers the actions of new POIs and
  writes them, without handing results to other actions (`update` would
  treat the one-check suite as the whole run).

### Agent decisions (autonomous)

- The overrule flag is one variable for all handlers, valued with handler
  names, rather than a tarav-change-specific variable: the stop is a hook
  contract, and the refusal message names the exact value to set.
- `git reset --hard` past commits, then committing, is stopped too: it
  discards IDs; the overrule is the intended path.
- Witness files are rewritten in place and are not a Git repository: a Git
  commit inside every hook would cost more than it gives. Overrule records
  are written once.

## Impl.Req.Wiki

- Product project: tarav-py. Wiki: `tarav-md/notes/wiki/`; topical note
  `tarav-change.md`, daily note.
- Capture status: captured in `notes/wiki/tarav-change.md` ("Append-only,
  with a witness outside the repository") and the daily `2026-10-16.md`;
  tarav-md commits `03a9361` (checkpoint), `07e0b0a`.

## Execution.Plan

Core data: `ChangeWitness {project, branch, changes, at}`, `ChangeOverrule
{id, project, branch, commit, missing, at}`, `GitHookRefusal`,
`REFUSED_EXIT = 75`, `TARAV_GIT_HOOKS_OVERRULE`, `TARAV_GIT_CHANGES_ROOT`.

1. **Hooks may stop** (feature). Refusal path in dispatch, `run_hook` and
   the script; overrule parsing. Check: tests where a handler refuses in a
   real `git commit` (stopped, message shown) and is overruled (commit
   passes); other failures still pass; existing hook tests adapted.
2. **Witness and speedbump** (feature). `tarav.l1.git.witness`, the
   tarav-change pre/post-commit changes, `ProjectActions.register`, the
   check additions, runtime registration of the Records and POIs. Check:
   tests in scratch repositories with redirected roots: a witness after a
   commit; removing a line by hand stops the next commit and opens a
   Removed action; the overrule commits, records a ChangeOverrule, opens an
   Overruled action and moves the witness; a `--no-verify` commit keeps the
   witness; the check reports Removed between commits and Overruled
   afterwards; other branches are independent.
3. **Dogfood and docs** (feature). Reinstall the scripts in tarav-py;
   AGENTS.md (skw source) and ARCHITECTURE.md. Check: the next tarav-py
   commits pass and write the witness; full suite and ruff.

Deviation triggers: action registration from inside a hook fails or
deadlocks on the action registry's Git; refusal codes collide with the CLI.

## Impl.Log

- Design: request written.
- Start checkpoint: `83cd002`.
- Slice 1 done. `GitHookRefusal`, `REFUSED_EXIT = 75`,
  `TARAV_GIT_HOOKS_OVERRULE` (`GitHookCall.overrule`, `overrules()`),
  `dispatch` returning warnings and refusals, `run_hook` exiting 75 on a
  refusal, and the script exiting 1 only then. Check:
  `tests/test_git_hooks.py` 11 passed: a refusal and its overrule through
  `dispatch` and `run_hook` (with the environment variable); a fake `tarav`
  on PATH shows a real `git commit` stopped by 75 only, while exit 1 warns
  and commits and 0 commits. Full suite passed; ruff clean.
- Slice 1 commit: `220c7a4`.
- Slice 2 done. `tarav.l1.git.witness` (`ChangeWitness`, `ChangeOverrule`,
  `ChangeWitnesses` with `TARAV_GIT_CHANGES_ROOT`); tarav-change compares in
  `pre-commit` before appending, stops with `GitHookRefusal` and registers a
  `Tarav.Git.Change.Removed` action, or keeps the overrule for
  `post-commit`, which records a `ChangeOverrule`, registers a
  `Tarav.Git.Change.Overruled` action and moves the witness (kept when IDs
  vanished without an overrule); `TaravChangeCheck` raises both POIs;
  `ProjectActions.register`. Found on the way: (1) `TaravObject` Record
  interfaces must declare `type` themselves (as `GitRepository` does), the
  hook warned and wrote no witness until both Records did; (2) an overrule
  file was opened before serializing, leaving it empty on failure, now
  serialized first; (3) importing `TaravProject` from Git made a
  `git` ↔ `project.base` cycle (architecture test): `TaravChangeCheck` now
  takes the root and the hook reads the Project marker for its actions.
  Check: `tests/test_git_change.py` 13 passed (witness after a commit; a lost
  ID stops the commit, names the overrule and opens a Removed action without
  appending; the overrule commits, records itself, opens an Overruled action
  and moves the witness; `reset --hard` is seen between commits and a
  `--no-verify` commit keeps the witness; branches are independent); Git
  and architecture tests 70 passed; the full suite before the cycle fix had
  only that architecture failure (321 passed); ruff clean. Breadcrumbs:
  `witness.py` 3, `change.py` 3, audits ok.
- Slice 2 commit: `92071cd`; its post-commit already wrote tarav-py's
  real witness (`~/Documents/tarav/git-changes/<project_id>/branches/main.json`).
- Slice 3 done. `tarav check --project .` reported the four tarav-py hook
  scripts as `Tarav.Git.Hooks.Stale` (they predated the refusal path);
  `tarav git hooks install --project .` rewrote them and the check is back
  to the 2 pre-existing MarkerPOIs. AGENTS.md (skw source, label copied
  back, product identical) and ARCHITECTURE.md describe stops, overrules and
  the witness. Check: full suite 322 passed; ruff clean; doc audits ok.
- Completion. Breadcrumbs: `hooks.py` 1, `witness.py` 3, `change.py` 3,
  `AGENTS.md` 1, `ARCHITECTURE.md` 1, this note 5; Wiki 7; audits ok. Not
  done, as scoped: finding the new commit of a lost ID, sharing witnesses
  between machines, hooks in other repositories.
