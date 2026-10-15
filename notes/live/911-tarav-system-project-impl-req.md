# 911 — The Tarav System Project — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented.

A machine has one Tarav System Project: an ordinary Project at
`~/Documents/tarav/system/`, from which work on all Projects is done in a
formal way. Projects never know about it.

1. `TaravSystemProject` (`Tarav.Project.System`, `tarav.l2.project.system`)
   is the base Type; its record adds `active`, a manual list of Project
   paths.
2. `tarav init --system --tarav-source <path>` creates it on this machine:
   the folder, its `.tarav/project.json` with a fresh `project_id`, its own
   Type subclassing `TaravSystemProject` in its harness, the environment,
   and a Git repository. It refuses when one exists.
3. Its checks add, for each active Project, one check that the Project loads
   through its own harness, run in that Project's environment.

Non-goals: workflow ownership (nothing changes there); installing or
bootstrapping Tarav itself; any automatic feeding of `active`; checks of
the data areas beside it.

## Design narrative

### User decisions

A default global Tarav Project: the root Project of a machine, with all
Projects under it without their knowing; a way to work on all Projects, as
in the migration, but formalized. Start minimal: information about the
Projects, a list of active ones, basic operations such as running checks,
and checks of its own over the others.
<!-- tarav.breadcrumb cc593e68554a3c9642c95d9c6ad701eb2bbcbe8c02e0b023772b045bc4b2f179 -->

It is a Project with a Git repository, skills and documentation, the top of
the user's Tarav system, named `TaravSystemProject`. The active list is
manual only: just a list in its configuration.
<!-- tarav.breadcrumb 1818491be691cb45b11a81eb3b6c090ab2758b150b7c77262da2a54690251b1e -->

It lives at `~/Documents/tarav/system/`; it is created by `tarav init
--system`, which needs Tarav already installed; how Tarav itself is
installed and bootstrapped is parked.
<!-- tarav.breadcrumb 963ebaf256503b8e95f00e77da83f935d638c650ffd99b65737ac7ada73a1df8 -->

A Project means a place, as a project does in Claude or Codex. Keep it
simple and explicit.
<!-- tarav.breadcrumb 96eb4367a3fbd315ecdd358dd3438e2fdf024e3dca8f9de85c2badadb05b37a9 -->

Nothing new: just a new Project at `~/Documents/tarav/system/`. Build it.
<!-- tarav.breadcrumb 6db58ca92b8a6a7e478da2425420da9ee6270b83bc1045024dabb94cf161354f -->

A discussion of making the System Project the owner of all workflows (in
place of `Tarav.Workflow`) and of Projects having library and harness roles
ended there: Projects are places, workflows stay as they are.

### Current behavior (inspected)

- `tarav project init --scope project|global` (`l1/project/commands.py`)
  initializes a Project folder or `~/.tarav`; there is no top-level
  `tarav init`.
- `default_tarav_data_root()` (`l0/_core/data_root.py`) is
  `~/Documents/tarav`; it holds the data areas (`archive`, `chatlas`,
  `records`, `scoring`, …), and no `system/`.
- `ProjectHarness.scaffold()` (`l2/project/harness.py`, request 909) writes
  a package whose class subclasses `TaravProject`, the manifest, and
  `harness` in project.json; `sync()` builds the environment with uv.
- A Root's `ChildProjectCheck` (`l2/project/root.py`) runs a child in its
  own environment: `[interpreter, *harness.command(code=…)]`.

### Proposals of the agent

**Layout.** The Project folder is `~/Documents/tarav/system/` with the
standard `.tarav/project.json` (an ordinary Project: "nothing new"). The
environment is the standard `.tarav/env`.

**Type.** `TaravSystemProject(Project)`, record field `active: list[str]`
(absolute paths, `~` allowed); `active_paths()` resolves them. Its suite:
the base Project suite, plus one `ActiveProjectCheck` per path.

**Check.** `ActiveProjectCheck` runs, in the active Project's own
environment, the launcher with code that only loads it. POIs (family
`Tarav.Project.System.ActivePOI`): `ActiveProjectMissing` (no marker at the
path) and `ActiveProjectDoesNotLoad` (no harness, no environment, or the
launcher failed; details hold the error's last lines).

**Init.** `tarav init --system --tarav-source <path>`: layout, scaffold
with base `TaravSystemProject` (package `tarav_system_harness`, class
`SystemProject`), sync, `git init` with a `.gitignore` of the Project's
local state (`.tarav/env/`, `state/`, `tmp/`, `indexes/`, caches). The
scaffold gains a `base` parameter (the generated class's base, as
`module:Class`).

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md`, root
`tarav-md/notes/wiki/`. Relevant notes: `projects.md`, `daily/2026-10-15.md`.
Supporting chat: session `abd0372d`. Capture status: pending.

## Execution.Plan

Core data shape: `TaravSystemProject.RecordInterface.active: list[str]`.

1. Feature — the Type and its check. Check: tests on temporary Projects
   (an active Project that loads, one missing, one without a harness).
2. Feature — `tarav init --system` and scaffold's `base`. Check: a test
   with a temporary data root (refuses a second time); then the real one on
   this machine, `tarav status --project ~/Documents/tarav/system`.
3. Docs (`ARCHITECTURE.md`, README), breadcrumbs, Wiki, commits.

Risk: `~/Documents` synced by iCloud would sync the environment; deviation
trigger: if it is, move `harness.environment` outside and log it.

## Impl.Log

- Design written from the discussion of 2026-10-15.
- Start checkpoint: skip — tarav-py held only this note.
- Slice 1: `tarav.l2.project.system`: `TaravSystemProject` (`active`,
  `active_paths()`), `ActiveProjectCheck` (runs `harness.command(code="pass")`
  in the active Project's environment), POIs `ActiveMissing` and
  `ActiveDoesNotLoad` (family `Tarav.Project.System.ActivePOI`), registered
  in the runtime. Test: a Project that loads in the test's own environment,
  one without a harness, a missing path.
- Slice 2: `scaffold(base=...)` (the generated class's base); `tarav init
  --system --tarav-source` in `tarav.l3.project.system` (package
  `tarav_system_harness`, class `SystemProject`, `active: []`, `.gitignore`,
  `git init`, sync); refuses when one exists. Test with a temporary data root.
  `tarav init` is new at the top level; `tarav project init --scope
  project|global` remains beside it.
- `~/Documents` is not in iCloud Drive (no `Documents` under CloudDocs), so
  the environment is the standard `.tarav/env`.
- Live: `tarav init --system` created `~/Documents/tarav/system/`
  (project_id 52237d33-ac59-4b3e-ba6c-91ec1e883e5c, Type
  `Project.tarav_system_harness.SystemProject`); with one active Project
  (`~/projects/taravangian-project`, set by the agent to try it; the list is
  the User's), `tarav check` runs the active check with no POI and nothing
  incomplete; `tarav status` opens the usual bootstrap actions of a new
  Project (no AGENTS.md, skills or package skill yet).
- Checks: Ruff clean; whole `tests/` 463 passed, 1 failed (`test_scoped_lines`,
  foreign).
- Breadcrumbs: audited on `l2/project/system.py`, `l3/project/system.py`,
  README, ARCHITECTURE, this note. ARCHITECTURE also held three provisional
  markers of another session (473c89a0, committed in 20a981b) that blocked
  the submit; refreshing that Codex session in Chatlas let all of them
  register.
