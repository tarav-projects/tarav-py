# 862 — taravangian-project is a root Project over tarav-py and tarav-md

<!-- tarav.sessions
5a029cbf = claude-code:8c55cc60-f28a-439f-a6a0-0521567e600e @5a029cbf49a299c9709013b8ccb3fc517b2fb56fed373d3da819b6ea842afa2f
-->

## Impl.Abstract

Knowledge.Surface: wiki
Alignment.Mode: Autonomous
Status: implemented (execution 2026-10-05); Wiki captured.
Depends on request 861.

The Taravangian development folder becomes a tree of typed Projects: a root
over `tarav-py` and `tarav-md`, sharing one environment. The Project classes
that harness Tarav's own development live in the Tarav code base under a
development namespace. Running the checks at the root runs the children's.

Non-goals: no large set of development checks; the first set is small and
grows with use. No change to the existing `diagram` and `index` marker
fields.

## Design narrative

### User direction

Tarav as a library and the harness used to maintain and improve that library
are different objects, and Tarav must be able to express both.
<!-- tarav.breadcrumb 89838ebc05f9e29b9b74fcc1e270ea777d1d5c76fa4e6ac7da83b45a2fff3e20 -->

A development harness can live in the same code base as the library, under a
namespace such as `.dev`, for the same reason a library ships its tests.
<!-- tarav.breadcrumb 2b8d32bf459bb29310bf03554bec555478c3d69b443ac88acc71b57d61be1639 -->

The root pattern described for md-library should be implemented in Taravangian
as well.
<!-- tarav.breadcrumb 28590df078527100b70da44c42222336dd542d9acc5ba266c001accfd3de2645 -->

### Observed (inspected)

- `taravangian-project/.tarav/project.json`, `tarav-py/.tarav/project.json`
  and `tarav-md/.tarav/project.json` are untyped markers that carry `diagram`
  and `index` fields.
- Other agent sessions work in these repositories; `tarav-md` had uncommitted
  changes from them on 2026-10-05.

### Decisions (agent)

- **Classes.** `tarav.dev` holds the Project class for `tarav-py` and the one
  for `tarav-md`. The root uses the Root class of 861 directly unless it needs
  behaviour of its own.
- **A documentation Project class** (skills, wiki, notes) is a candidate for a
  general Tarav class, since md-library needs the same (md-library-py 622).
  Provide it as a general class and let `tarav.dev` use or subtype it.
- **First checks.** For `tarav-py`: the test suite passes, reported as one
  Check. For `tarav-md`: every skill builds from its source without a change,
  and changed wiki Notes have no provisional Breadcrumb markers. Anything more
  is added later.
- **Markers.** The three markers get their Type; the root lists the two
  children; the children declare the root's harness. Existing fields are kept.
- **Environment.** One environment at the root. If the current tool install of
  Tarav must stay as it is, the root environment is added beside it and the
  Impl.Log says which commands use which.

## Acceptance

- `tarav check --project` at the root reports the results of both children;
  in a child it reports that child's only.
- `TaravProject.load_project` returns the typed class in each of the three
  folders.
- Commands that read the `diagram` and `index` marker fields behave as
  before.

## Impl.Req.Wiki

Product owner: `tarav-py`.
Wiki owner/root: `tarav-md/notes/wiki`.
Relevant context: request 861; `projects.md`.
Capture status: done, tarav-md 0ea3b6e (`projects.md`, daily 2026-10-05).

## Execution.Plan

1. Development and documentation Project classes with the first checks.
2. Root environment; markers typed; children listed.
3. `AGENTS.md` of the three folders say which Project harnesses them and how
   to run its checks; wiki capture.

## Impl.Log

### 2026-10-05 — Execute

Executed after 861 in the same session, by the User's `/goal` invocation of
`tarav-hugentics --impl --exec`.
<!-- tarav.breadcrumb fe3f7aa1ca6b17e11f603005ec68eb66022d2aa7578f268264ab6c650c25d247 -->

- Classes (deviation from "tarav.dev"): the general classes live in
  `tarav.l2.project.dev`: `PythonPackageProject` (`Tarav.Project.PythonPackage`,
  one `TestSuiteCheck` running pytest with the running interpreter; each
  `FAILED`/`ERROR` line is a `TestFailurePOI`) and `DocsProject`
  (`Tarav.Project.Docs`: each skill package's own `SkwSkill.checks()` suite,
  a `SkillLoadCheck` incomplete result when a skill cannot load, and
  `ProvisionalMarkersCheck` over `notes/wiki`). Tarav has no behaviour of its
  own yet, so the markers use these classes directly and no `tarav.dev`
  subclasses or new top-level package were added; AGENTS.md says the root
  package holds metadata only. A Tarav-specific subtype is added when a
  Tarav-only check appears.
- "Every skill builds without a change" became "each skill's own checks":
  building in place would mutate the tree, and `SkwSkill` already provides a
  suite through Tarav's interface.
- Root environment: `taravangian-project/.tarav/pyproject.toml` (virtual
  project: `tarav` editable from `../tarav-py`, `pytest`; `projects` lists
  RootProject, PythonPackageProject, DocsProject), `.tarav/.gitignore`
  ignores `env/`; synced with `tarav project harness sync --project .`.
- Markers: root typed `Tarav.Project.Root` with `children: [tarav-py,
  tarav-md]`; `tarav-py` and `tarav-md` typed and `harness: {project: ".."}`.
  `diagram` and `index` fields kept; `Project.from_path` still resolves
  (checked on `tarav-md`, including `wiki()`).
- Runs: `tarav check --project` in `tarav-md`: 357 checks, 53 POIs (StaleContext
  13, UnannotatedOutputLink 19, UnreachableBlock 12, ProvisionalMarker 9), 11 s.
  At the root: 358 checks (adds TestSuite, completed, no failing test), same
  53 POIs, 32 s.
- The root folder is not a Git repository: its marker, manifest, lock and
  `AGENTS.md` section are written but not committed anywhere.
- Tests: `tests/test_project_dev.py` (3). Breadcrumbs: `dev.py`, tarav-py
  `AGENTS.md`, tarav-md `AGENTS.md`, root `AGENTS.md` (audits ok, 0 POIs).
- Follow-up found by md-library-py 622: pytest stops at a test file that
  cannot be collected (exit 2), which made the whole TestSuite Check
  `failed`. `TestSuiteCheck` now passes `--continue-on-collection-errors`, so
  the file is an `ERROR` POI and the rest of the suite runs; test added.

