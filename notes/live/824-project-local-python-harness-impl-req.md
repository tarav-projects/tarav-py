# Project-local Python harness

## Impl.Abstract

Knowledge.Surface: wiki. Phase: Execute. Alignment.Mode: Interactive.
Status: complete; disposable-Project verification and capture passed.

Give a filesystem Project a local Python harness: `.tarav/env`, managed using
uv, containing Tarav and an editable project package. That package defines a
default concrete Project subtype representing the project's node. Preserve
the separation between class identity and project-instance identity.

Non-goals: provisioning existing projects in this Design pass, automatic
installation on discovery, global plugin scanning, in-process interpreter
switching, replacing a product's own environment, or migrating all markers.

## Impl.Req.Wiki

Product: tarav-py. Wiki: tarav-md/notes/wiki, topical projects.md and
daily/2026-09-28.md. Evidence session:
codex:01a0d86c-9538-7be1-af96-014cd4203d61,
identity 6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b.
User turns d99b85664b7ab1df (local environment, uv, package, default subtype)
and 5456b14057a1721c (Design invocation; interpreted --desig as --design).

## Inspected boundaries

- src/tarav/l1/project/base.py: TaravProject.from_path() discovers a marker
  without mutation; load_project() dispatches its declared Type through the
  current trusted registry. Neither installs packages or changes interpreters.
- src/tarav/l0/_core/project.py: initialize_project_layout() creates the legacy
  marker/layout, preserving an existing ID under explicit ensure semantics.
  It does not provision this Python harness.
- src/tarav/l0/kernel/environment.py: TaravEnvironment is a running-process
  trusted Type-binding object, not a virtual-environment provisioner. Bindings
  may reference installed Python classes; retained Records never select imports.
- tests/kernel/test_environment.py demonstrates lazy installed external Type
  loading, including a Record with UUID and label.
- src/tarav/l1/python_env/core.py and commands.py describe and run the current
  interpreter. Preserve `tarav python run` semantics rather than silently
  changing it to select a project environment.
- src/tarav/l3/runtime.py composes a runtime with an explicit environment.
  Lower project layers must not import that composition module.

## Proposed layout

```text
<project-root>/
  .tarav/
    project.json
    pyproject.toml
    uv.lock
    src/<project_package>/
      __init__.py
      project.py
      __main__.py
    env/
```

Only `.tarav/env` and the presence of a project package are user-specified;
the source/manifest/entrypoint layout is the proposed implementation default.
Track source, manifest, lock and marker. Ignore env; preserve all other `.tarav`
data and existing ignore rules. The package is the harness, not necessarily the
product being built. Allow explicit package/class names rather than deriving
Python identifiers unsafely from arbitrary folder names.

The generated MyProject(TaravProject) defines class_entity() with its own stable
TypeShip and Project ownership. `.tarav/project.json` identifies its instance
through the existing project_id and declares that concrete Type. Use the
existing UUID-plus-label reference shape; do not store an import path there.
Regeneration must not allocate replacement class or project identities.

## Minimal mechanics and placement

Propose a ProjectHarness helper under tarav.l2.project.harness for filesystem
layout, explicit scaffolding and uv provisioning. Keep TaravProject minimal;
do not require every base Project to have an environment. These operations
should have keyword-led interfaces, for example scaffold(path=..., package=...,
class_name=..., tarav_source=...) and sync(path=...). Exact names are provisional.

Keep runtime-aware launch composition under tarav.l3.project. Expose explicit
project harness commands through the existing Project command family, wired
at l3 rather than importing l3 from l1/project/commands.py. No new Workflow
identity is required for this first integration.

Separate three actions:

1. Discover/inspect: find nearest canonical marker and expected harness paths;
   read metadata without importing the project package or invoking uv.
2. Scaffold/sync: explicit mutation creates the package, resolves its declared
   dependencies, installs Tarav and the editable package into `.tarav/env`.
   Target that path explicitly; do not accidentally create `.tarav/.venv`.
3. Run: start that environment's interpreter in a subprocess. A generated
   package entrypoint explicitly binds MyProject using TaravEnvironment,
   composes/selects the runtime, then calls TaravProject.load_project(path=...).
   It should offer a minimal way to run project-aware code with that runtime.

The Python package entrypoint is trusted executable source. Installation alone
does not register a Type in Tarav. Do not make project.json an arbitrary import
instruction, and do not scan/import all installed packages. Package launch
selection can be declared separately in harness configuration; pin down one
simple convention during execution. A process cannot return a live child
Project object to the parent; results cross the process boundary as output and
exit status. In-environment Python callers can work with the object directly.

Do not assume the distribution named tarav on an index is the intended source.
The scaffold accepts an explicit dependency source/version; tests use this
checkout or a built wheel. Record the chosen dependency in packaging metadata
and lock it. Development-local source paths must not enter project.json.
Validate uv's installed command behavior during execution; no uv operations
are performed during this design.

## Existing projects and failure behavior

Default layout is a bootstrap convention, not a requirement for reading older
Projects. Existing markers remain readable without provisioning. Adoption is
an explicit action: preserve project_id and unrelated fields, show/validate the
change to the concrete Type, and never overwrite an already specialized Type
or existing package source without alignment. Untyped markers need an explicit
Type update for typed loading, not a read-time fallback.

Missing uv, absent env, failed dependency resolution, incompatible sources and
invalid package/class names produce actionable errors. A run must not silently
fall back to global Python or install missing packages. Setup must not delete
an existing environment to recover. Reruns preserve edited source and identities;
partial setup remains inspectable and can be retried explicitly.

## Execution.Plan

- [x] Cold-read current instructions and checkpoint product per Execute policy.
- [x] Recheck project initialization, runtime binding and existing extension
  package examples; settle minimal launcher/config convention, not a plugin system.
- [x] Implement inspect/scaffold library mechanics with explicit names/source.
- [x] Add explicit uv sync targeting `.tarav/env`; preserve lock and source.
- [x] Add generated concrete Project class and trusted bootstrap entrypoint.
- [x] Wire explicit launch adapters; preserve generic loading and python run.
- [x] Test temporary projects and update architecture/usage guidance.
- [x] Capture actual results; do not provision this workspace automatically.

## Acceptance and verification

- Discovery from project root/subdirectory selects nearest `.tarav/project.json`
  without installs or project imports; nested projects remain separate.
- Fresh scaffold has distinct stable class and instance identities. Reruns
  preserve both plus custom source; adoption preserves unrelated marker fields.
- A subprocess in `.tarav/env` imports Tarav and the editable project package,
  registers the Type, loads MyProject with the existing project ID, and executes
  a project-specific method. Check sys.prefix and executable inside the child.
- Product environment and global tool environment remain untouched. Include
  spaces in paths and shell metacharacters in argv; do not use shell interpolation.
- Unknown Type, invalid source, missing uv/env and failed sync do not silently
  fall back, rewrite records or destroy existing state.
- Unit tests use a fake subprocess runner; one isolated real uv integration
  exercises local package installation without relying on a public Tarav release.
- Run focused project/environment/CLI tests, architecture checks, Ruff and full
  suite in execution; record commands/results. No product tests run in Design.

## Impl.Log

- Execute checkpoint: `8bbf491` (clean product repository).
- Implementation choices: launcher metadata lives in `[tool.tarav.harness]`
  in `.tarav/pyproject.toml`; trusted package `__main__` bootstraps its explicit
  Type, then runs code/file with `project` and `runtime` globals. Scaffold
  accepts a local Tarav checkout or wheel; no implicit public Tarav source.
- Existing markers require explicit adoption; specialized Types and edited
  package source are preserved. Sync targets `.tarav/env` explicitly and run
  uses that interpreter in a subprocess. No workspace provisioning is implied.
- Implemented `tarav.l2.project.harness.ProjectHarness` and the trusted
  bootstrap/launcher in `tarav.l3.project.harness`. CLI registration lives
  in l3 and is injected into the existing Project command family. The l3
  Project initializer remains thin; existing layer and cycle checks pass
  without exceptions. Updated README, architecture and Project guidance.
- Verification: focused Project, CLI, Environment and architecture tests:
  73 passed. Full `uv run pytest -q`: 1,379 passed. Following Product
  Breadcrumb submission, all six harness tests passed again. The real uv
  test verifies editable behavior and failed-sync preservation in a disposable
  Project. `uv run ruff check src tests tooling` and `git diff --check` passed.
- Reinstalled the editable tool with `uv tool install --reinstall --editable .`;
  installed CLI help confirms inspect/scaffold/sync/run. This workspace's
  marker and harness were not provisioned.
- Product Breadcrumbs in `src/tarav/l2/project/harness.py`:
  d06d769f0a631a2b4912f8edbcf3a42aacdc491b6f0c596f513f941b493ebfd2 and
  d6ba8cb735d3af7f6f1877c97fa39b76945f91ef13cab93971e91dbcfe147568.
  Both resolve against design User Turn d99b85664b7ab1df; audit returned
  status ok with no findings.
- Execute capture: projects.md and daily/2026-09-29.md, grounded in current
  session 1f561f5d8db849a3a445b83a91a5e94acbb80927f9c332d45322ac70f8705a74,
  User Turn d9c6dfb2b080d9f3. New topical Breadcrumb:
  8a2e200a8fed357e223b7f119293f83ac0a399bdb21fcb29253e48ed5fdb32eb;
  daily: fb42468b73baa4fff3e8d3e5d3f43b1d1bf5467ae74ace32d128be0264646722.
  Both Wiki audits returned status ok with no findings. Scoped Wiki commit:
  a816272c83a56cf58ad0ef2969675aaffd7a9b24. No unresolved capture gaps.

- Inspected Project discovery, initialization, external Type bindings, current
  Python runner and runtime composition. Kept bootstrap separate from loading.
- Captured projects.md and daily/2026-09-28.md; both Breadcrumb audits returned
  status ok with no findings. Wiki-only commit:
  06dca07fe2a24701735b32dd8664492d9f890256.
- New Breadcrumb IDs: topical 82d59f20c6207a475a83c907cc45648c90bf0e29825e1ea48193d2e4d362a34c
  and 5f9589358437a88df624b5aac9a2e04a444e564ead5c252f6bd4ac55687caf5c;
  daily caf02316201844979a0cc633556bb3abcd422a5e5a7b6227989a1edc66cf8cc3
  and 56a97b1cd1a1a287485c229eb08239c66723df1e4ce30671b88b63187b25376c.
