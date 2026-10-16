# 915 — Project Git hooks, and the tarav-change workflow

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Autonomous. Phase: Develop.
Status: executing; slice 1 done.

Two levels. First, a Git hook system for Tarav Projects: a Project whose
root is a Git repository declares in its `.tarav/config.json` which Tarav
hook handlers it uses; Tarav installs small hook scripts that call the
`tarav` CLI with Git's context, and Project checks keep the installation
true. Second, its first application, the tarav-change workflow: every commit
made through the hooks gets a random ID written twice, as a lowercase
`tarav-change: <id>` commit trailer and as a line appended to the tracked
file `.tarav/changes`. Commit hashes change when history is rewritten; the
ID travels with the commit's content and message, so a reference that
carries it still finds the commit afterwards.

Non-goals: enabling the hooks in repositories other than tarav-py; carrying
tarav-change IDs inside Tarav References; importing git-filter-repo commit
maps; rewriting the old citations left by the tarav-md history purge; the
daemon's event hooks (`tarav daemon hook`), which stay as they are.

## Why

The tarav-md history was rewritten to remove leaked Chatlas exports, which
changed 488 commit hashes and left notes citing commits that no longer
exist. The User proposed Tarav-controlled stable markers kept in the
repository, in a tracked `.tarav` file whose lines are appended over time,
so that the commit where a marker first appears can be found in any history.
<!-- tarav.breadcrumb a90ed2c6822d42d79e23862a3d2dc211af83800a16b8ba3f0cccec20460919e0 -->

Gerrit's `Change-Id` trailer is the proven precedent: a `commit-msg` hook
adds an ID that survives amend and rebase. Tarav is an external harness, so
the User chose to require Tarav Git hooks in a Project, calling the `tarav`
CLI with the context Git gives, and handling the rest internally.
<!-- tarav.breadcrumb 9469ca8cc85e6978e868310e15ee2f31bfb73bf13b64d6509369a30dbaa000ae -->
<!-- tarav.breadcrumb 76331b3ca36d9ea2d1c02e0f2b4fa14793dfb9de05cce27a544670d3fc788e96 -->

User decisions: both the trailer and the file carry the ID; hooks are not a
guarantee and that is accepted, more systems are added over time to make
references reliable; a tarav-change is one more kind of data a reference can
carry; a missing `tarav` warns and lets the commit through; the hooks belong
to the Project configuration, with checks that maintain them; the trailer
key is lowercase `tarav-change`. The User split the work into these two
levels and asked for it to be developed.
<!-- tarav.breadcrumb 4c0477783babdf9f2b6ea74968f90d171a0d21d6582919c6d4dd5ebb31387bb0 -->
<!-- tarav.breadcrumb fc8cbd0666af11d2fcdd7eb978fd14bdf94f6fbc644a220fe0ad7e561e95d6cb -->

## Current behavior

- `tarav.l1.git` has `GitRepository` (bounded Git operations) and no hooks.
- `tarav.l1.hooks` is the daemon's namespaced event dispatcher
  (`tarav daemon hook`); asynchronous, unrelated to Git hooks.
- `.tarav/config.json` holds one section per workflow, registered with
  `register_config_section` in `tarav.l3.runtime` (`agents`, `skills`,
  `diagram`). `ProjectFilesCheck` reports unknown or invalid sections.
- `TaravProject.Checks.suite()` composes `ProjectFilesCheck`, the agents
  file and skills checks.
- `tarav git commit` (`tarav.l0._core.git_repository.commit_paths`) commits
  through a temporary `GIT_INDEX_FILE` and raises unless the commit retains
  the prepared message exactly. A `commit-msg` hook that appends a trailer
  makes it raise after the commit exists.

## Design

### Experiments that fixed the mechanics (scratch repository, git 2.x)

- Only `pre-commit` can stage into the commit: a file staged by
  `prepare-commit-msg` lands in the next commit.
- `pre-commit` sees `GIT_INDEX_FILE` set to the index being committed:
  `.git/index` for a plain commit, `index.lock` for `-a`,
  `next-index-*.lock` for `git commit <paths>`, the temporary index for
  `tarav git commit`. `git add` through it is included in every mode.
- With `git commit <paths>` and with `tarav git commit`, the repository's
  own index keeps the old file (`MM` in status). A `post-commit` that resets
  the file in the repository's own index (with `GIT_INDEX_FILE` unset) when
  the worktree equals HEAD fixes both.
- An amend cannot be told from a new commit: `--amend -m` reports the source
  as `message`.

### Level 1: Git hooks for Projects (`tarav.l1.git.hooks`)

- `GitHookHandler`: a named handler (`name`), the Git hook names it uses
  (`hooks`), the `.gitattributes` lines it needs (`attributes`), `run(call)`
  and an optional `check(project)` returning its Check.
- `GitHookCall`: hook name, Git's arguments, repository root, standard input.
- Handlers are registered in runtime composition
  (`register_git_hook_handler`), like config sections.
- Config section `git`, owned by the Git workflow:
  `{"hooks": {"handlers": ["tarav-change"], "chain": ".husky"}}`.
  `chain` is an optional hooks folder, relative to the repository root, whose
  same-named hooks run first; their failure still stops the commit.
- Scripts live tracked in `.tarav/git-hooks/<hook>`, one per hook the
  configured handlers use; `core.hooksPath` points there. A script runs the
  chained hook, then `tarav git hook --name <hook> --arg <a> ...` when
  `tarav` is on PATH, else warns; it always lets Git continue.
- `tarav git hook` runs in process (not through the daemon): it reads the
  Project config at the repository root and runs every configured handler
  that uses the hook. A handler failure is printed as a warning; the exit is
  0, so a broken Tarav never blocks a commit.
- `tarav git hooks install --project [PATH] [--handler NAME ...]` adds the
  named handlers to the config, writes the scripts, sets `core.hooksPath`
  and adds the attribute lines.
- `GitHooksCheck` (in the base Project suite): no `git` section, no
  findings. Otherwise POIs `Tarav.Git.Hooks.NotInstalled` (`core.hooksPath`
  is not `.tarav/git-hooks`), `Tarav.Git.Hooks.Stale` (a script is missing
  or differs from what install writes), `Tarav.Git.Hooks.UnknownHandler`,
  `Tarav.Git.Hooks.AttributesMissing`; plus each configured handler's check.
  A Project whose root is not a repository root gets `NotInstalled`.

### Level 2: tarav-change (`tarav.l1.git.change`)

- `pre-commit`: a new UUID4, appended to `.tarav/changes` and staged through
  the inherited `GIT_INDEX_FILE`; kept for `commit-msg` in
  `$(git rev-parse --git-path tarav/change)`.
- `commit-msg`: adds `tarav-change: <id>` with `git interpret-trailers`.
- `post-commit`: the index realignment above.
- `post-rewrite`: appends `{"command", "old", "new", "at"}` lines to
  `$(git rev-parse --git-path tarav/rewrites.jsonl)`; clone-local evidence.
- `.gitattributes`: `.tarav/changes merge=union`, so appends from two
  branches never conflict.
- `find(repository, id)`: commits whose `.tarav/changes` gained the line or
  whose trailer carries it, oldest first. `tarav git change find --id ID
  --repo PATH [--json]`.
- `TaravChangeCheck`: POI `Tarav.Git.Change.Missing` for each non-merge
  commit after the first commit of `.tarav/changes` with neither the trailer
  nor a new line, over the latest 200 commits.

### Agent decisions (autonomous)

- **Amend.** The proposal was that amend keeps the ID. Since `pre-commit`
  cannot detect an amend, an amended commit gains a new ID and keeps the old
  line it inherited; both IDs resolve to it, so a reference made before the
  amend still finds the amended commit. No amend detection is attempted.
- **Copies.** Cherry-pick and rebase replay content and message without
  `pre-commit`: the ID is preserved; when one ID is in several commits,
  `find` lists them all, oldest first.
- Names left open in discussion: the file is `.tarav/changes` (one UUID per
  line), the scripts folder `.tarav/git-hooks/`, the IDs UUID4.
- `commit_paths` accepts a message the hooks extended with trailer lines
  after the prepared message, and nothing else.
- Merge commits get no ID and are not reported.

## Impl.Req.Wiki

- Product project: tarav-py. Wiki: `tarav-md/notes/wiki/` (Project.Wiki of
  the root); relevant notes `projects.md`, `checks-workflow.md`,
  `references.md`; a new topical note for tarav-change when captured.
- Supporting turns: session `abd0372d`, turns cited above.
- Capture status: pending until completion.

## Execution.Plan

Core data: `GitHooksConfig {handlers: list[str], chain: str | None}`,
`GitHookHandler`, `GitHookCall`, the `.tarav/changes` line format (one
UUID4), the trailer `tarav-change: <uuid4>`.

1. **Hooks for Projects** (feature). `tarav.l1.git.hooks`, the `git` config
   section, `tarav git hooks install`, `tarav git hook`, `GitHooksCheck` in
   the Project suite. Check: tests install into a scratch Project repository,
   a real `git commit` runs a test handler through the script and `tarav` on
   PATH, a missing `tarav` warns and commits, and the check reports each POI.
2. **tarav-change** (feature). The handler, `commit_paths` accepting
   hook trailers, `find`, `tarav git change find`, `TaravChangeCheck`.
   Check: tests commit in a scratch repository in plain, `-a`, `<paths>`
   and `tarav git commit` modes and through an amend and a rebase; each
   commit carries the same ID in its trailer and file, the index stays
   clean, `find` resolves an ID across a rewrite, the check reports a
   `--no-verify` commit.
3. **Dogfood and docs** (feature). Enable tarav-change in tarav-py; update
   AGENTS.md (through its skw source) and ARCHITECTURE.md. Check: the next
   commits of tarav-py carry IDs; `tarav status --project --all` passes the
   new checks; the full suite and ruff pass.

Deviation triggers: Git behavior differing from the experiments; the base
Project suite cannot import the check without a layering cycle.

## Impl.Log

- Design: experiments recorded above; request written.
- Start checkpoint: `edb7b1e` (with the request).
- Slice 1 done. `tarav.l1.git.hooks` (config model, handler registry,
  scripts, install, dispatch, `GitHooksCheck` and its four POIs); `git`
  config section and POI types registered in `tarav.l3.runtime`;
  `git_hooks_suite` in `TaravProject.Checks.suite()`; `tarav git hook` and
  `tarav git hooks install` in `tarav.l3.git.commands`. A chained hook's
  standard input is captured once and fed to both callees. Handler and Check
  classes are not Record types, as with `ProjectFilesCheck`. Check:
  `tests/test_git_hooks.py` 6 passed (install, dispatch, real commits with
  and without `tarav` on PATH, chain refusal, every POI, Project suite);
  full suite 297 passed; ruff clean. Breadcrumbs: 3 in `hooks.py`, audit ok.
