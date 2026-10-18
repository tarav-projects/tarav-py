# 909 — A Project bootstraps from its project.json — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented.

Every Project must be of a Type of its own, and loading a Project is a
bootstrapping act configured in its marker. Today the three Projects of this
workspace are of generic Tarav Types, the marker is a loose JSON object with
legacy fields, and the import paths of Project Types sit in the environment's
manifest instead of the marker.

1. `.tarav/project.json` is the Project workflow's file: the Project's Record
   and its core configuration — `type` (the Record's tag), `project_id`,
   `created_at`, `project_name`, `harness` (`environment`, `type` as
   `module:Class`) and what a Type adds (`children` for a Root). It is
   validated by the Type's RecordInterface; `harness` has its own model.
2. `.tarav/config.json` holds sections owned by other workflows (`skills`,
   `agents`, `diagram`), each validated by its owner's model.
3. Loading: read `harness` from `project.json`, start that environment's
   interpreter, import `harness.type`, load `project.json` as its Record;
   the Record's `type` tag must name the same class.
4. Gone: `class` and `schema_version` in both files; `index`; the manifest's
   `[tool.tarav.harness]` table (`projects`, the scaffold's single class);
   the `harness.project` ancestor indirection and the `harness.manifest`
   field; the rule that keeps environment paths inside the Project.
5. A check validates both files and raises POIs.
6. Local Types for this workspace: `TaravangianRootProject` (a package of
   the root), `TaravPyProject` (in tarav-py's own package), `TaravMdProject`
   (a package of tarav-md); the root environment installs them with uv.
7. The root becomes a Git repository tracking an allowlist.
8. The markers of this workspace's Projects (root, tarav-py, tarav-md) are
   migrated; every other marker on the machine is migrated later.

Non-goals: what else the root tracks (`notes/`, `dev/`, …, later review);
moving other Projects' Types out of their roots' packages; a second
environment per child.

## Design narrative

### User decisions

`PythonPackageProject` and `DocsProject` are the Types of some Projects of
this harness; that is not right. Types must be local: they may extend those,
not be those. Each Project must be of a unique Type.
<!-- tarav.breadcrumb 909d44615c7b -->

Every Tarav Project has a code base, at least the code of its harness;
whether it shares a code base with the rest of the system is an
organization decision. A Project configures where its harness and its
environment are.
<!-- tarav.breadcrumb 600bd8f10276 -->

The target is one local Type per Project, each extending a generic class
with its own Ship and name, all named `*Project`. The root should be
tracked by Git; how it interacts with the child repositories was to be
discussed.
<!-- tarav.breadcrumb 8987299ebb49 -->

The root tracks only its own files, the child repositories ignored. What
else the root tracks is decided later; focus on bootstrapping the root
Project and its repository.
<!-- tarav.breadcrumb bd83231bb5e6 -->

The child Projects' Types are not defined in the root: each in its own
Project's package.
<!-- tarav.breadcrumb ce5fb0324f6f -->

Folders such as `.tarav/src` are only defaults: bootstrapping needs a path,
inside the Project's environment, to the Project Type.
<!-- tarav.breadcrumb b61378ec1e5d -->

There is no reason to declare the Types in the manifest rather than the
marker. The marker is just configuration, where the loading process is
configured; loading a Project is a bootstrapping act, and explicit
configuration and paths are fine. There is no rule against it.
<!-- tarav.breadcrumb 76a1b6d6bc96 -->
<!-- tarav.breadcrumb 221057dd44ec -->

The launcher needs two things only: an environment and a path to the Project
Type, loaded from a package installed in the environment with ordinary uv.
<!-- tarav.breadcrumb c1db11410ea9 -->
<!-- tarav.breadcrumb 83e25e8ccc33 -->
<!-- tarav.breadcrumb ce28cdec5d36 -->

`"class": "agentos.project"` is legacy and must go. A pydantic object must
describe the marker, and a check must check Project markers. The
`harness` with `environment` and `type` makes sense.
<!-- tarav.breadcrumb a6a70637134a -->

The marker being the whole Record is a problem: split it into
`project.json`, the Project Record with only the Project's core
configuration, and `config.json`, the rest.
<!-- tarav.breadcrumb a594f26dd9c9 -->

`harness` stays in `project.json`: `config.json` exists so that other
workflows can add their configuration; `project.json` is where the Project
workflow keeps its core configuration.
<!-- tarav.breadcrumb 37bf015764c6 -->

Keep both the Record's `type` tag and `harness.type`. Build it.
<!-- tarav.breadcrumb 592460cac042 -->

### Current behavior (inspected)

- Marker loading: `load_project_marker` (`l0/project/__init__.py`) requires
  `class == "agentos.project"` and a UUID `project_id`; `load_project_config`
  requires `class == "agentos.project.config"`. `initialize_project_layout`
  writes both with `class` and `schema_version`. `l0/testing.py` builds test
  markers the same way.
- `TaravProject.RecordInterface` (`l1/project/base.py`) declares only
  `project_id` (alias of `id`) and `marker_class` (`class`). Everything else
  is read raw: `harness` and `children` (`l2/project/runner.py`,
  `l1/project/scope.py`), `agents.package_skill` (`l1/project/skills.py`,
  from the Record), `diagram.main_model` (`l2/unsorted/storage.py`, which
  also writes it into the marker), `project_name` (`project_marker_name`).
  `index` has no reader.
- Environment: `ProjectLaunchConfiguration.from_path` (`l2/project/runner.py`)
  resolves no `harness` (defaults `.tarav/pyproject.toml`, `.tarav/env`),
  `{manifest, environment}` (inside the Project) or `{project: ".."}` (an
  ancestor that lists this Project and owns its harness).
- Types: `ProjectHarness.project_types()` (`l2/project/harness.py`) reads the
  manifest's `[tool.tarav.harness]`: `projects = ["module:Class", …]` or the
  scaffold's `package`/`class_name`/`type_ship`/`type_name`.
  `tarav.l3.project.launch` imports them and loads the marker, whose Type
  must be one of them. `tarav status`/`check` relaunch inside the harness
  (`in_harness`, `l3/check.py`); the root's `ChildProjectCheck`
  (`l2/project/root.py`) runs each child in its harness. `scaffold()` writes
  the manifest table and a package under `.tarav/src/<package>`.
- `config.json` exists in every Project (`class`, `schema_version`); only
  skills routing reads it (`skills.routing`).
- The global `tarav` is a uv tool installed editable from `tarav-py`: a
  change to the loader is live for every marker on the machine at once.
- Markers on this machine: 88 (`~/projects`, `~/Documents`, depth 5). All
  have `class` and `schema_version`; 76 have a `type`, 12 none; 52 a
  `harness`; 22 `children`; 18 `diagram`; 15 `project_name`; 7 `index`; 6
  `agents`. Most of the other workspaces already have local Types
  (`Project.<package>.<Class>`), defined in their root's harness package and
  listed in its manifest's `projects`.

### Proposals of the agent

**project.json.** `TaravProject.RecordInterface`: `id` (`project_id`),
`created_at`, `project_name` (optional), `harness` (optional
`ProjectHarnessDeclaration`: `environment` relative to the Project root,
`type` `module:Class`). `RootProject` adds `children`. Unknown fields are
rejected.

**config.json.** `ProjectConfig`: a mapping of sections; a workflow
registers its section name and model (`register_config_section`): `skills`
(skills routing), `agents` (`package_skill`, Project skills), `diagram`
(`main_model`, Diagram). Reading a section validates it with its model; an
unregistered section is reported by the check, not refused.

**Loading.** `ProjectLaunchConfiguration` reads `harness` from
`project.json`: interpreter `<environment>/bin/python`, manifest
`<environment>/../pyproject.toml` (for `uv sync`, as uv expects). The
launcher imports `harness.type`, loads the Record with that class and
requires that its `type` tag names it. `ChildProjectCheck` and `in_harness`
keep relaunching, with the new configuration. A Project without `harness`
loads only through an explicit class (`from_path(cls)`), as today.

**Scaffold.** `scaffold()` writes `harness` into `project.json` and the
package; the manifest only lists dependencies.

**Check.** `ProjectFilesCheck` in the base Project suite, one POI Type per
case: the Record does not validate (an old field is just an unknown field:
no legacy handling anywhere); the harness environment is missing; `harness.type` does not import or is not the
Record's Type; a config section is unregistered or invalid.

**This workspace.** `TaravangianRootProject(RootProject)` in a package of
the root (`.tarav/src/taravangian_harness`), `TaravPyProject
(PythonPackageProject)` in `tarav.dev.project` (already installed editable
in the root environment), `TaravMdProject(DocsProject)` in a package of
tarav-md; the root manifest installs the root and tarav-md packages as
editable path dependencies.

**Root repository.** `git init`; `.gitignore` ignores `/*` and allows
`.gitignore`, `AGENTS.md`, `README.md`, `.tarav/project.json`,
`.tarav/config.json`, `.tarav/pyproject.toml`, `.tarav/uv.lock`,
`.tarav/skillware/`, `.tarav/src/`; caches ignored.

**Migration.** One script, per marker: move `agents` and `diagram` to
`config.json`; drop `class`, `schema_version`, `index`; derive
`harness.environment` (own `.tarav/env`, or the ancestor's for
`harness.project`) and `harness.type` (the entry of that environment's
`projects` whose class name matches the marker's Type); drop the manifest's
`[tool.tarav.harness]` table.

### Migration scope (decided)

The migration would touch 88 markers in about 55 repositories; because the
global `tarav` is editable from tarav-py, a Project not migrated stops
loading when the loader changes. The User chose to make taravangian work now
and migrate the rest later: the other workspaces, and the Projects of this
folder that the root does not list (`tarav-js`, `tarav-chatlas-md`,
`tarav-pkg-testground`, `historical-touched-index`, `_DEPRECATED/*`), stay
on the old shape and do not load until then.

## Impl.Req.Wiki

Product project: `tarav-py`; also the root `taravangian-project` (new
repository) and `tarav-md`. Wiki owner: `tarav-md`, root
`tarav-md/notes/wiki/`. Relevant notes: `projects.md` (harness history,
824, 861), `daily/2026-10-15.md`. Supporting chat: session `abd0372d`.
Capture status: done (`projects.md`, section "A Project bootstraps from its
project.json — 909"; daily 2026-10-15).

## Execution.Plan

Core data shape: `ProjectHarnessDeclaration(environment, type)`;
`TaravProject.RecordInterface` (id, created_at, project_name, harness) and
subclasses; `ProjectConfig` with registered sections.

1. Feature — the files (tarav-py). Models for `project.json` and
   `config.json`; `load_project_marker`, `initialize_project_layout`,
   `l0/testing.py`, section readers (skills routing, Project skills,
   Diagram) on the new shape. Check: the Project, harness and skills tests
   on temporary Projects.
2. Feature — loading (tarav-py). Launch configuration from `harness`;
   launcher import and Type match; scaffold writes `harness`; old manifest
   table, ancestor indirection and containment rule removed. Check: harness
   tests with a real uv environment; `ChildProjectCheck` test.
3. Migration — every marker in scope; then `tarav status` in this
   workspace and a sample of the others.
4. Feature — the check. Check: a test per POI Type; `tarav status` on
   migrated Projects raises none.
5. Feature — this workspace's local Types and the root repository. Check:
   `tarav status` at the root and in each child; the extension lists them.
6. Docs (`ARCHITECTURE.md`, README harness section, the extension if it
   reads markers), breadcrumbs, Wiki, commits.

Risk: readers of the old shape outside tarav-py (the extension's scripts,
other workspaces' harness code); deviation trigger: one found is migrated
in its slice and logged.

## Impl.Log

- Design written from the discussion of 2026-10-15.
- Start checkpoint: skip — tarav-py held only this note; tarav-md and the
  extension were clean; the root was not a repository.
- The User added, while execution started: no legacy handling. The loader
  accepts only the new shape, and the check has no legacy case: an old field
  is an undeclared field.
- Files: `l0/project` drops `class`/`schema_version` checks and writes
  neither; `project_marker_name` reads only `project_name`;
  `ProjectHarnessConfig` (environment, type) lives in `l0.project`, because
  `project.runner` importing `l1.project` closed a subsystem cycle
  (`test_architecture`). `TaravProject.RecordInterface`: `project_id`,
  `created_at`, `project_name`, `harness`; `RootProject` adds `children`.
  The Project now holds its state as attributes (`fields` keeps what a Type
  adds and undeclared fields), as the record contract test requires.
  `tarav.l1.project.config`: `ProjectConfig`, `register_config_section`;
  sections `agents` (`AgentsConfig` in `l1.project.agents`: main, aliases,
  the two prompt switches, package_skill — one section, two readers),
  `skills` (`SkillsConfig`, shallow; routing keeps its detailed checks) and
  `diagram` (`DiagramConfig`: main_model, models), registered by the
  runtime. `index` had no reader and is dropped.
- Loading: `ProjectLaunchConfiguration` reads `harness` (environment may
  leave the Project; manifest = `<environment>/../pyproject.toml`);
  `TaravProject.load_project` imports `harness.type`, binds it in the current
  registry when unknown, loads, and requires the type tag to name the same
  class. `bootstrap(path)`, `main(argv)`; `tarav.l3.project.launch` is the
  only entry. Scaffold writes `harness` into project.json; the manifest table
  `[tool.tarav.harness]`, the package `__main__`, the ancestor indirection
  and the containment rule are gone.
- Check: `ProjectFilesCheck` (`tarav.l1.project.files`) in the base Project
  suite; POIs `UnknownField`, `NoHarness`, `HarnessEnvironmentMissing`,
  `HarnessTypeMismatch`, `UnknownConfigSection`, `InvalidConfigSection`
  (family `Tarav.Project.Files.POI`). Test `tests/test_project_files.py`.
- This workspace: `TaravangianRootProject` (`.tarav/src/taravangian_harness`),
  `TaravPyProject` (`tarav.l2.dev.project` — not a top-level `tarav.dev`,
  which would break the l0–l3 layout), `TaravMdProject`
  (`tarav-md/.tarav/harness`, package `tarav_md_harness`). Type names
  `Taravangian.<Class>` were an agent choice. The root manifest is a package
  and installs tarav-md's harness; `uv sync` done. Markers migrated; `agents`
  and `diagram` moved to config.json.
- Root repository: `git init`; `.gitignore` ignores `/*` and allows the
  listed files only.
- Extension: `scripts/_common.py` `load_project` uses `bootstrap(path)`.
- Checks: Ruff clean; whole `tests/` 448 passed, 1 failed
  (`test_scoped_lines`, foreign). Live: `tarav status` at the root shows the
  same 15 open actions; each Project loads as its `Taravangian.*` Type; the
  root's members are `TaravPyProject` and `TaravMdProject`; `tarav check`
  runs `ProjectFilesCheck` with no POI; the extension's scripts load.
- Breadcrumbs: audited on `l0/project`, `l1/project/base.py`, `config.py`,
  `files.py`, `l2/project/runner.py`, `l2/dev/project.py`, README,
  ARCHITECTURE, this note and the Wiki.
- Not migrated (by decision): every other marker on the machine (85), which
  no longer loads until a later pass.
