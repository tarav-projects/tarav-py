# 861 — A root Project over child Projects, and one environment for several Project types

<!-- tarav.sessions
5a029cbf = claude-code:8c55cc60-f28a-439f-a6a0-0521567e600e @5a029cbf49a299c9709013b8ccb3fc517b2fb56fed373d3da819b6ea842afa2f
-->

## Impl.Abstract

Knowledge.Surface: wiki
Alignment.Mode: Autonomous
Status: implemented (execution 2026-10-05); Wiki captured.

Tarav gains what a development folder made of several Projects needs. A root
Project lists its child Projects and its checks are theirs. Several Projects
can share one Python environment, and one Python library can provide several
Project types. Request 862 adopts this in `taravangian-project`; md-library-py
requests 621 and 622 depend on it.

Non-goals: no object that models a Python library; no separate Harness object;
no discovery of children by scanning folders; no parallel execution.

## Design narrative

### User direction

Tarav does not model the Python library. A Tarav Project is an object inside a
Python library, and a library can hold several Project objects.
<!-- tarav.breadcrumb 15693ee16b125dcab5738b06de3099f2dcd30a6092cb27efddc1a6e671e8d485 -->

Where the code of a Project sits is a packaging choice: the development
harness can share the code base of the library it harnesses, for example under
`.dev`, or live apart. Tarav only needs to know how to find the Project object
that harnesses a folder.
<!-- tarav.breadcrumb cdfbc3c57c27d6d733e35730d4326474c2d2c0589adfeedb43ebf233e9ec65c0 -->

A development folder is a small graph of Projects: a root Project that, asked
to run the checks, runs the checks of the Projects below it; the Projects below
use the same Python environment, kept at the root.
<!-- tarav.breadcrumb c27bcb83fddaecee0c14268adbf4a4c9733bfa675530ef286af554b5acfef40c -->

The root pattern is general and is wanted in Taravangian as well.
<!-- tarav.breadcrumb fc246e4bb8e8964304a440fe1caa3a7fec0b111f5cc7d5975f123b2b97a4c6c6 -->

Produce the requests needed for this design; design only.
<!-- tarav.breadcrumb 4c8b87f05d5d3f3e336a9a70727c1140d94f128c54b454aa644ddd381321166a -->
<!-- tarav.breadcrumb fccfa63c77a8663a1ae68e7d382c93d1c16e9c07dfa4bd4a3cfd7fc8c00bf1a2 -->

### Observed (inspected)

- `TaravProject` (`src/tarav/l1/project/base.py`) is a `CheckProvider`; a
  marker's `type` selects the class through `load_project`.
- `tarav check --project` (`src/tarav/l3/check.py`) runs
  `CheckSuite.of(project.checks()).run()` inside the Project's own harness
  environment, through `tarav.l3.project.harness.run`.
- `ProjectLaunchConfiguration` (`src/tarav/l2/project/runner.py`) requires
  `harness.manifest` and `harness.environment` to resolve inside the Project
  root. A child cannot point at an environment kept by its parent.
- The launcher (`src/tarav/l3/project/harness.py`) starts
  `python -m <package>`, where the manifest's `[tool.tarav.harness]` names one
  package and one class, and `bootstrap` rejects a marker whose Type is not
  exactly that class. So one manifest serves one Project type, and a package
  serves one type through its `__main__`.
- No Project class knows other Projects. `taravangian-project`, `tarav-py`
  and `tarav-md` each have an untyped marker.

### Decisions (agent)

- **Root Project.** A Tarav-provided class (working name `Tarav.Project.Root`)
  whose marker lists its children as relative paths. `children()` loads them;
  `checks()` returns a `CheckSuite` made of each child's suite, in the listed
  order. A listed child that is missing or cannot be loaded is reported as an
  incomplete result, not skipped. Only listed folders are children: a root
  folder can hold a link to a place that is not its child.
- **Shared environment.** A child marker can declare that it uses the harness
  of an ancestor Project. This is the one case where the manifest and the
  environment lie outside the child's root; the containment rule stays for
  every other path. The ancestor must be a Project that lists the child.
- **Several Project types per environment.** The launch entry becomes a
  property of the Project, not of the manifest: the marker's Type is resolved
  among the Project types that the environment's packages provide, and the
  exact-class restriction is replaced by "the marker's Type is one of the
  trusted types of this environment". How a package declares the types it
  provides (an entry in its manifest listing several, or an entry-point group)
  is left to the executor; the existing single-class manifest keeps working.
- **A subtype marker runs.** A Project whose class subtypes a library's class,
  with its own code in its folder, launches as today (request 824).
- **One run for the tree.** With a shared environment the root runs every
  child's suite in one process. A child with its own environment is run in
  that environment and its results are merged into the root's `CheckRun`; if
  that is costly to build, the first version may report such a child as one
  result with its counts, stated in the Impl.Log.

## Acceptance

- In a fixture with a root and two children sharing the root's environment,
  `tarav check --project` in the root reports both children's results, and in
  a child reports only that child's.
- A child that declares the ancestor harness launches with the ancestor's
  interpreter; a child declaring a path outside its root any other way is
  still refused.
- One package provides two Project types and a marker of either type loads.
- A folder with a marker that the root does not list is not run.
- Existing harness tests (`tests/test_project_harness.py`) still pass.

## Impl.Req.Wiki

Product owner: `tarav-py`.
Wiki owner/root: `tarav-md/notes/wiki`.
Relevant context: `projects.md` section "Places, libraries and Project
classes"; requests 824, 826, 858, 859, 860.
Capture status: done, tarav-md 0ea3b6e (`projects.md`, daily 2026-10-05).

## Execution.Plan

1. Trusted types of an environment: several Project types per package.
2. Ancestor harness for a child marker.
3. Root Project class, `children()`, collected `checks()`.
4. Tests on fixtures; README and wiki capture.

## Impl.Log

### 2026-10-05 — Execute

Executed in the same Claude Code session that designed it, by the User's
`/goal` invocation of `tarav-hugentics --impl --exec` over requests 861, 862
and md-library-py 621–623.
<!-- tarav.breadcrumb 2276f08d3cf9a0213c5a85782c5acf7e45c629510b57e0a80950f5a8486884f5 -->

- Checkpoint: the declared scope was clean at b341761; no empty commit made.
- Several Types per environment: `ProjectHarness.project_types()` reads
  `[tool.tarav.harness] projects` (trusted `module:Class` paths); the old
  single `package`/`class_name` form still returns its one Type.
  `ProjectHarness.command()` builds the launch arguments; a `projects`
  manifest starts through the new `tarav.l3.project.launch`, which imports the
  listed Types and calls `main()`. A single-class manifest still starts
  through its package's `__main__`, exactly as before: md-library-py's
  manifest names a class its package does not export, so a generic import
  would have broken it. `bootstrap()`/`main()` accept a Type or a sequence.
- Ancestor harness: a marker `harness: {"project": ".."}` resolves through
  `ProjectLaunchConfiguration._from_ancestor`; the ancestor must be a strict
  ancestor folder, have its own marker and harness (no chains), and list the
  child in `children`. `harness_root` records whose folder holds the harness;
  containment checks use it. Other paths outside the root are still refused.
- Root Project: `RootProject` (`Tarav.Project.Root`, `tarav.l2.project.root`)
  subclasses the featured `Project`. `child_paths()` validates the listed
  paths (relative, below the root after resolving links); `child()` and
  `children()` load them; `checks()` is a run-time suite of each child's
  suite. A child whose environment is the running one (`sys.prefix`) runs in
  place; a child with its own environment runs through `ChildProjectCheck` in
  a subprocess and returns one `ChildProjectPOI` per POI type with its count
  (the first-version fallback the design allowed). A missing marker, an
  unbound Type or a child without checks is an incomplete result.
- Deviation: `RootProject` is not registered in `create_runtime()`. Doing so
  made the harness `bootstrap()` fail with a duplicate Type binding when a
  manifest lists it; it is trusted through manifests like any library Type.
- Tests: `tests/test_project_tree.py` (9 tests: ancestor harness, unlisted
  and outside paths, several Types per manifest, loading, root run, missing
  child, own-environment child with a stubbed subprocess, child path
  validation). `tests/cli`, `tests/test_architecture.py`,
  `tests/test_checks_workflow.py`: 76 passed. Ruff clean.
- Manual: md-library-py's existing harness still launches
  (`MdLibraryProject` loaded through `tarav.l3.project.harness.run`).
- `tarav project harness inspect|sync` accept a `projects` manifest; inspect
  reports `harness_root` and paths relative to it.
- Full suite after the change: 169 passed (`uv run pytest`).
- Docs: README "Root Projects and shared environments"; AGENTS.md Project
  model bullet.
- Product.Surface Breadcrumbs (all audits ok, 0 POIs): `runner.py`,
  `harness.py`, `root.py`, `README.md`, `AGENTS.md`, attached to User Turns
  75f0c9ab, c885f97b and 557ff2e6.

