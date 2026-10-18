# 910 — Every Project under ~/projects on its own harness — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented.

Request 909 changed how a Project starts (`harness` in `project.json`,
other workflows in `config.json`) and migrated only the Taravangian
workspace; every other Project under `~/projects` stopped loading. This
request migrates them all to the Taravangian layout.

1. Every non-archival Project's `project.json` holds `harness: {environment,
   type}` and no `class`, `schema_version`, `index`, `agents` or `diagram`;
   `agents` and `diagram` move to `config.json`, which loses `class` and
   `schema_version`.
2. A child's Type lives in the child's own harness: its class moves out of
   the root's package into `<child>/.tarav/harness/` (its own package,
   installed by the root's environment), keeping its Ship. A root's package
   keeps the root's Type only.
3. Manifests lose `[tool.tarav.harness]`; scaffold packages lose their
   `__main__.py` (the launcher is `tarav.l3.project.launch`).
4. Each root becomes a Git repository tracking a conservative allowlist.
5. Migration commits in every repository touched, holding only the
   migration's files.

Non-goals: archival Projects (no Type: the six under `taravangian-project/`
and `_DEPRECATED/ansible-lab`) are left untouched; markers outside
`~/projects`; what else each root tracks beyond the obvious files.

## Design narrative

### User decisions

Migrate the other Projects, with a configuration similar to Taravangian's,
across all of `~/projects`; first a read-only check.
<!-- tarav.breadcrumb 01c5fce36a65 -->

All Projects under `~/projects` become Tarav Projects with an architecture
like Taravangian's. Child Types move into each child's own package: Types
are, by default, in the Project's own harness. Roots become Git
repositories, conservatively: ignore most of what is there except obvious
things such as notes. Archival Projects are ignored. Commits in the other
repositories: yes.
<!-- tarav.breadcrumb 48dbc956c32c -->

### Current behavior (inspected, read-only survey of 2026-10-15)

82 markers under `~/projects`: 3 already new (Taravangian), 7 archival, 72
to migrate in five patterns.

- A (17 roots: FamilyInc, academy, breadguis, cellar, csc-reactor, miacad,
  miaplayer, miatube, notebook, paperson, pdf-readings, pereiros, simuleos,
  tara, utilities, voice-readings, xtt-readings): the root's scaffolded
  package `.tarav/src/<root>_harness/project.py` defines the root's and every
  child's class (each only `class_entity`); children use
  `harness.project: ".."`; the manifest lists them in `projects`.
- B (md-library, tankefactory): children's Types are in the library
  (`md_library.dev`, `tankefac.dev`), installed from `*-py`; md-library's
  root is of the generic `Tarav.Project.Root`.
- C (telar, g70203): `harness: {manifest, environment}` inside the `*-py`
  child (`telar-py/.venv`); Types in the product package.
- D (biblio, miaperiod, saving-air, spec-surfaces): standalone scaffolds.
- E (archival): no Type, no harness.
- Only miaperiod and spec-surfaces roots are Git repositories. Many child
  repositories hold others' uncommitted work; most never tracked `.tarav/`;
  pdf-readings-py and voice-readings-py ignore `.tarav/`; five children are
  not repositories (academy/index-test, academy/workflow-for-ai-coding,
  cellar-md, notebook-pi, oba-js).

### Proposals of the agent

**Child harness.** `<child>/.tarav/harness/`: `pyproject.toml` (hatchling,
name `<child>-harness`, depends on `tarav`), `src/<child>_harness/`
(`__init__.py`, `project.py` with the moved class), `.gitignore`
(`__pycache__/`, `*.egg-info/`). The class keeps its Ship and its base; its
label becomes `Project.<child>_harness.<Class>` (the Ship resolves, the
label follows the package). The root's manifest adds it as an editable
path dependency.

**Pattern B.** Types stay in the library (the owner's organization
decision); md-library's root gets its own Type in a root package
(`md_library_project_harness.MdLibraryRoot`). **Pattern C.** Only `harness`
changes (`environment: "telar-py/.venv"`; the manifest beside it already
is the product's). **Pattern D.** `harness` from the scaffold table.

**Root allowlist.** `.gitignore`, `AGENTS.md`, `README.md`, `notes/` when
present, and `.tarav/{project.json, config.json, pyproject.toml, uv.lock,
skillware/, src/}`; an existing root `.gitignore`'s rules are kept below.

**Commits.** Per repository, only the files the migration wrote, through
`tarav git commit`. A tracked `project.json` that was already modified is
committed with the migration (it is the file being migrated). In the two
repositories that ignore `.tarav/`, the migration's files are force-added.
Children that are not repositories stay untracked (reported).

**Script.** One script, dry run first (prints the plan), then apply; then
`uv sync` each root's environment and load every migrated Project through
its harness.

## Impl.Req.Wiki

Product project: `tarav-py`; touches the repositories under `~/projects`.
Wiki owner: `tarav-md`, root `tarav-md/notes/wiki/`. Relevant notes:
`projects.md` (section 909), `daily/2026-10-15.md`. Supporting chat: session
`abd0372d`. Capture status: done (`projects.md`, section "Every Project under
~/projects on its own harness — 910"; daily 2026-10-15).

## Execution.Plan

Core data shape: per Project `{root, pattern, type label, Ship, class path,
environment}`, derived from the survey.

1. Migration — dry run: the plan per Project and per repository. Check: every
   one of the 72 has an environment and a class path; no file written.
2. Migration — apply: markers, configs, child harnesses, root packages,
   manifests, root repositories. Check: `uv sync` per root; every migrated
   Project loads as its Type through its harness.
3. Commits per repository; `tarav status` on a sample of roots.
4. Breadcrumbs, Wiki capture, completion commits.

Risk: a manifest or package that differs from the scaffold shape; deviation
trigger: such a Project is migrated by hand and logged.

## Impl.Log

- Design written from the survey and the User's answers of 2026-10-15.
- Start checkpoint: skip — the migration commits only its own files in each
  repository, as the User chose; others' uncommitted work stays untouched
  (voice-readings-py keeps its 29 staged files staged).
- Dry run (one-off script `migrate910.py`, kept with the session's scratch
  files): 25 roots and singles, 47 children, 7 archival skipped. A first run
  stopped on g70203-project, a nested root (child of pereiros) with its own
  environment: it is migrated as its own root and pereiros runs it in a
  subprocess. The repository of files not yet written was resolved from the
  nearest existing folder.
- Apply: 212 existing files backed up first. Pattern A: 37 child classes
  moved to `<child>/.tarav/harness/src/<child>_harness/` (Ship kept, label
  `Project.<child>_harness.<Class>`); the roots' packages keep the root's
  class; `__main__.py` removed from the 21 scaffold packages. md-library's
  root got `md_library_project_harness.MdLibraryProjectRoot` and its manifest
  became a package. Pattern C (telar, g70203): `harness.environment` is the
  product's `.venv`; the product `__main__.py` files of telar, g70203 and
  md-library call `main()` (the launcher reads `harness.type`).
- `uv sync` of the 23 `.tarav/env` environments: all ok.
- Checks: all 72 migrated Projects load through their harness as the Type
  their project.json names; every root loads its listed children (pereiros
  runs g70203 in its own environment, as designed); `tarav check` on the 25
  roots: no `Tarav.Project.Files` POI, no incomplete check; `tarav status` on
  paperson, tankefactory, telar, biblio runs (their open actions are the
  agents/skills bootstrap checks, new only because these Projects could not
  load since 909).
- md-library-py: `tests/test_tarav_checks.py` moved to the new marker and
  `bootstrap(path)` (a local depot class is installed as a module); the
  test does not run because md-library still imports the removed Blessing
  store (`BlessingRecord`, `BlessingStore` from `tarav.l1.blessings`), a
  break older than 909, left for its own request.
- Roots: 23 `git init` with the allowlist (an existing root `.gitignore`'s
  rules kept, telar); first commits hold only allowed files.
- The five children that were not repositories (academy/index-test,
  academy/workflow-for-ai-coding, cellar-md, notebook-pi, oba-js) got a
  repository each, with the same conservative allowlist adapted to a child
  (`AGENTS.md`, `README.md`, `notes/`, `.tarav/project.json`, `config.json`,
  `harness/`); first commits 508cb47, d422219, 155da57, c7d1d9e, 665eb24.
  Every migrated Project is now tracked.
- Commits: 44 repositories through `tarav git commit` (only the migration's
  files); pdf-readings-py and voice-readings-py ignore `.tarav/`, so their
  files were force-added and committed with a path-limited `git commit`.
- Scope extended by the User to the six markers under `~/Documents`.
  md-library (the depot) already had its Type and `.venv`: `harness` now
  names them and its manifest lost the `projects` table (811da8f). PaperSON,
  Obsidian/notebook, js/obajs-monorepo, workspaces/main-workspace and
  workspaces/csc-reactor had no Type: `tarav project harness scaffold
  --adopt` gave each a package and Type (`Project.<pkg>.<Class>`), then the
  legacy fields were removed, `diagram` moved to config.json, environments
  synced; all load as their Types. Scaffold does not remove legacy fields on
  adoption; done by hand. Commits: PaperSON 57d0b06 (its `.gitignore`
  ignores `_*`, so `__init__.py` was force-added, path-limited commit),
  notebook bcbd1fc, obajs-monorepo 201c4cd; the two workspaces got
  repositories with the child allowlist (c6741af, 346bab3).
- Notebook's config.json keeps `agentos_index_canvas`, read by its Obsidian
  plugin; `ProjectFilesCheck` reports it as a section no Tarav workflow owns.
- The depot's `tarav check` fails in md-library: `MdLibraryDepot.checks()` is
  a method, an older Tarav API (now the `checks` namespace) — with the
  Blessing store, md-library's own pending migration.

