# Project-local Python harness

## Impl.Abstract

Knowledge.Surface: wiki. Phase: Design. Alignment.Mode: Interactive.
Status: ready for a bounded first implementation; details below are proposals,
not a claim of separately approved interfaces. No product implementation here.

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

- [ ] Cold-read current instructions and checkpoint product per Execute policy.
- [ ] Recheck project initialization, runtime binding and existing extension
  package examples; settle minimal launcher/config convention, not a plugin system.
- [ ] Implement inspect/scaffold library mechanics with explicit names/source.
- [ ] Add explicit uv sync targeting `.tarav/env`; preserve lock and source.
- [ ] Add generated concrete Project class and trusted bootstrap entrypoint.
- [ ] Wire explicit launch adapters; preserve generic loading and python run.
- [ ] Test temporary projects and update architecture/usage guidance.
- [ ] Capture actual results; do not provision this workspace automatically.

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

- Inspected Project discovery, initialization, external Type bindings, current
  Python runner and runtime composition. Kept bootstrap separate from loading.
- Captured projects.md and daily/2026-09-28.md; both Breadcrumb audits returned
  status ok with no findings. Wiki-only commit:
  06dca07fe2a24701735b32dd8664492d9f890256.
- New Breadcrumb IDs: topical 82d59f20c6207a475a83c907cc45648c90bf0e29825e1ea48193d2e4d362a34c
  and 5f9589358437a88df624b5aac9a2e04a444e564ead5c252f6bd4ac55687caf5c;
  daily caf02316201844979a0cc633556bb3abcd422a5e5a7b6227989a1edc66cf8cc3
  and 56a97b1cd1a1a287485c229eb08239c66723df1e4ce30671b88b63187b25376c.
