# Configured Python process launching

<!-- tarav.sessions
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
1f561f5d = codex:01a0b984-4664-7871-934a-89cf92595b64 @1f561f5d8db849a3a445b83a91a5e94acbb80927f9c332d45322ac70f8705a74
-->

## Impl.Abstract

- Knowledge.Surface: wiki
- Alignment.Mode: Interactive
- Status: complete.
- Outcome: make configured Python execution a typed Python Workflow contract,
  expose it through `tarav run`, and let Project supply one
  `RunnerConfigurator` subtype that selects the Project environment.
- Scope: file, inline-code and stdin execution; current and Project runner
  configurations; Project launch paths in `.tarav/project.json`; reuse of the
  existing Python runner and Project harness mechanics.
- Non-goals: automatic environment switching during imports or Record loading,
  cross-environment Type dispatch, distributed runtimes, runtime factories in
  Project configuration, global package scanning, or automatic provisioning
  during ordinary execution.

The user selected this refined Design after inspecting the original 826
proposal. This request replaces its earlier factory-driven child bootstrap with
a configured Python runner and workflow-owned configurator subtypes.
<!-- tarav.breadcrumb 1dfb0ef9cc1d -->

## Design narrative

Tarav code in one Python environment supplies the semantics for that runtime.
Ordinary Type dispatch remains local: a missing Type fails rather than causing
Tarav to search for or launch another environment. Environment selection is an
explicit operation performed by caller code or a workflow, not a hidden part of
Record loading.
<!-- tarav.breadcrumb 19e82d971b0b -->

Tarav already has the required execution primitive in
`tarav.l1.python_env`: it runs a file, inline source, or stdin with the Python
interpreter currently running Tarav. Generalize that primitive so it consumes
an explicit runner configuration. The runner's responsibility remains small:
run Python with the supplied configuration and arguments, inherit ordinary
process streams, and return the exit status.
<!-- tarav.breadcrumb 6000934c2349 -->

Workflows decide which configuration to use. The Python Workflow supplies the
default current-environment configurator. The Project Workflow supplies a
subtype that reads the Project's common launch configuration and selects its
interpreter. This is the same runner and configuration contract; the generated
`.tarav` harness is only the default Project configuration.
<!-- tarav.breadcrumb 0bd238f6fb2a -->

The launcher never imports a configured runtime factory and never injects a
Project or working runtime merely because an environment was selected. It runs
the Python operation provided by the caller. A script can construct its own
runtime; a Project workflow operation can supply Python code or a module
invocation that constructs a runtime and loads the concrete Project. Those are
caller behaviors layered over the runner.
<!-- tarav.breadcrumb 1cf555404545 -->

### Bootstrap and working roles

When Project-aware configuration is requested, the process running the Tarav
command already has a normal Tarav runtime in whichever environment supplied
the command. That bootstrap runtime contains the Project Workflow. The workflow
reads the stable Project launch fields and produces a runner configuration. If
that configuration names another interpreter, the runner starts a fresh Python
process there.
<!-- tarav.breadcrumb aafa86b8cf2a -->

The launched code may construct a working Tarav runtime in the selected
environment. The bootstrap and working roles do not require new runtime
subclasses, and the generic runner does not require that a working runtime be
created at all. Direct Python invocation from an already suitable environment
continues to work without a bootstrap transition.
<!-- tarav.breadcrumb 62f59d33819b -->

## Typed Python Workflow contract

Introduce a `PythonWorkflow` and the smallest useful owned Type family:

```python
class RunnerConfiguration(PythonObject):
    """Resolved configuration consumed by the Python runner."""


class RunnerConfigurator(PythonObject, ABC):
    @abstractmethod
    def configure(self) -> RunnerConfiguration:
        ...


class CurrentRunnerConfigurator(RunnerConfigurator):
    def configure(self) -> RunnerConfiguration:
        ...
```

`RunnerConfigurator` is an abstract behavioral obligation: incomplete subtypes
cannot be instantiated. `RunnerConfiguration` is a runtime TaravObject. Its
minimum required state is the interpreter; add cwd or explicit environment
overrides only where the current execution contracts require them. Do not make
ambient environment variables part of its retained Record projection.

Project implements the contract through an independently owned subtype:

```python
class ProjectRunnerConfigurator(RunnerConfigurator):
    def __init__(self, launch: ProjectLaunchConfiguration) -> None:
        ...

    def configure(self) -> RunnerConfiguration:
        ...
```

The base Type's class entity belongs to Python Workflow. The subtype's class
entity belongs to Project Workflow. Python inheritance states the reusable
behavioral contract while workflow ownership states which domain supplies the
specialization.
<!-- tarav.breadcrumb a46af47c1e29 -->

The runner consumes the resolved value rather than knowing the workflow that
produced it:

```python
launch = ProjectLaunchConfiguration.from_path(project_path)
configuration = ProjectRunnerConfigurator(launch).configure()
run_file("task.py", configuration=configuration, arguments=())
```

`ProjectLaunchConfiguration.from_path()` discovers the marker and projects only
the common launch fields. It does not call `TaravProject.load_project()` or ask
the Type registry to resolve the marker's concrete Project class. This keeps the
bootstrap boundary usable when that class exists only in the selected Project
environment.
<!-- tarav.breadcrumb f92c76b7c422 -->

Keep configuration selection and execution separate. `run_file()` and
`run_source()` must not call Project discovery or choose a configurator.

## Project launch configuration

`.tarav/project.json` remains the authoritative Project marker and manifest.
Its optional `harness` member selects the manifest and environment using paths
relative to the Project root:

```json
{
  "harness": {
    "manifest": "g70203-py/pyproject.toml",
    "environment": "g70203-py/.venv"
  }
}
```

There is no `kind`, package, class path, or runtime factory in this declaration.
Absence of `harness` selects the existing generated defaults:
`.tarav/pyproject.toml` and `.tarav/env`. Both declared paths must resolve
inside the Project root. Inspection reads configuration without importing,
installing, launching, or rewriting anything. Sync may explicitly use the
manifest and environment through the existing harness operation.

The bootstrap Project Workflow reads only this common launch surface. It need
not dispatch the complete marker to its concrete Project Type. Once code is
running in the selected environment, a caller that needs the concrete Project
must construct the appropriate local runtime and register/load that Type using
ordinary local mechanics. Merely installing a package does not cause Tarav to
scan or register its classes.

The existing `[tool.tarav.harness]` metadata generated by 824 remains
scaffolding metadata for that generated package. It is not the source for
Project environment selection, and this request requires no migration or
fallback reader for declared product packages.

## Public execution surface

Preserve the existing local interface:

```sh
tarav python run --file task.py
tarav python run --src 'print("hello")'
```

It delegates to `CurrentRunnerConfigurator` and the shared runner. Add the
general adapter:

```sh
tarav run --file task.py
tarav run --project --file task.py
tarav run --project /path/to/project --src 'print("hello")'
tarav run --project --file - <<'PY'
print("hello")
PY
```

Exactly one of file or source is required; `--file -` consumes stdin as Python
source. Arguments after `--` become script arguments. Without `--project`, use
the current configurator. Bare `--project` discovers upward from cwd; a path
changes the discovery start. Resolve file paths before changing any execution
cwd. Missing requested Projects, invalid paths, and incomplete environments
fail explicitly without fallback or installation.

`tarav project harness run` may retain its workflow-specific behavior by
supplying its own Python/module invocation to the shared runner. The generic
runner itself does not create `runtime` or `project` globals.

## Current code and reuse

- `src/tarav/l1/python_env/core.py` already owns current-interpreter reporting
  and file/source subprocess execution. Generalize it around an explicit
  `RunnerConfiguration`; do not implement another subprocess engine.
- `src/tarav/l1/python_env/commands.py` keeps `tarav python` as the explicit
  current-environment adapter.
- `src/tarav/l1/project/workflow.py` owns Project Workflow identity. Add the
  Project-owned configurator in the Project namespace without making
  `ProjectWorkflow` itself a configurator subtype.
- `src/tarav/l2/project/harness.py` already discovers generated paths and
  performs explicit uv sync. Separate common marker path resolution from its
  generated-package scaffolding metadata.
- `src/tarav/l3/project/harness.py` currently combines interpreter launch,
  generated package bootstrap, runtime construction and script execution.
  Delegate process execution to the shared runner while keeping any deliberate
  Project operation as workflow-supplied code.
- `src/tarav/l3/runtime.py` composes workflows and CLI adapters. Register
  Python Workflow and its Types there; do not teach `create_runtime()` or
  TypeRegistry to switch environments.
- `src/tarav/l0/kernel/environment.py` remains the current process's trusted
  Type-binding surface. It is not a virtual-environment selector or provisioner.

## Execution.Plan

1. Re-read the request, current instructions, runner, Project harness and tests;
   checkpoint according to the execution workflow before product edits.
2. Add Python Workflow identity, `RunnerConfiguration`, abstract
   `RunnerConfigurator`, and the current-environment subtype. Register their
   class/workflow identities with the normal runtime composition.
3. Generalize the existing Python runner to consume explicit configuration;
   preserve file/source/stdin, argv, streams and exit status.
4. Add `ProjectRunnerConfigurator`. Read optional marker `harness` paths,
   apply generated defaults when absent, enforce Project-root containment, and
   keep discovery/inspection free of imports, installs and mutation.
5. Add `tarav run` using current or Project configuration. Delegate existing
   Python and Project adapters to the shared runner without duplicating process
   mechanics.
6. Update focused usage and architecture guidance. Verify unit behavior and one
   real isolated Project environment, then perform required Product.Surface and
   Wiki capture during Execute.

## Acceptance checks

- `RunnerConfigurator` cannot be instantiated without `configure()`;
  `CurrentRunnerConfigurator` and `ProjectRunnerConfigurator` satisfy the same
  behavioral contract and declare their correct workflow ownership.
- Project configuration succeeds when the marker declares a concrete Type that
  is absent from the bootstrap registry; no concrete Project dispatch occurs.
- Current configuration reports the interpreter running Tarav. Project
  configuration selects the declared environment interpreter or the generated
  default when no harness declaration exists.
- Declared manifest/environment paths are relative, remain inside the Project,
  and reject redirects or incomplete environments explicitly.
- `run_file()` and `run_source()` use only the supplied configuration. They do
  not discover Projects, import factories, build Tarav runtimes, load concrete
  Project Types, or switch environments after execution begins.
- `tarav python run` retains current-interpreter behavior. `tarav run` selects
  current or Project configuration and preserves file/source/stdin, argv,
  output streams, caller cwd and nonzero exit status.
- A Project script executed in a declared product environment can import that
  environment's installed packages. Any product runtime construction and
  concrete Project loading are performed by the script or an explicit Project
  workflow operation.
- Existing generated harness inspection, scaffold, sync and workflow-specific
  run behavior remain covered. No global Python fallback, package scanning,
  environment provisioning, or retained-data rewrite is introduced.
- Run focused Python/Project/runtime/CLI tests, architecture checks, Ruff and
  the appropriate broader suite. Include one real isolated-environment smoke
  test without requiring a public Tarav release.

## Impl.Req.Wiki

Product: tarav-py. Wiki owner: tarav-md/notes/wiki. Relevant context:
[Projects](../../../tarav-md/notes/wiki/projects.md) and
[824](824-project-local-python-harness-impl-req.md). Original evidence session:
`codex:01a0d86c-9538-7be1-af96-014cd4203d61`, identity
`6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b`.
Refined Design evidence session:
`codex:01a0b984-4664-7871-934a-89cf92595b64`, identity
`1f561f5d8db849a3a445b83a91a5e94acbb80927f9c332d45322ac70f8705a74`.

The original Wiki capture describes the earlier factory-driven proposal and
must not be read as the final 826 contract. This Design updates the live note;
selective Wiki correction belongs to implementation closure unless separately
requested.

## Impl.Log

- Inspected current `python_env`, runtime, Project harness, Project Wiki context
  and the original 826 note.
- Design refinement: the Python Workflow owns a typed runner configuration
  contract; Project supplies a configurator subtype; the runner only executes
  caller-supplied Python in the resolved environment.
- Removed runtime-factory, package-import and automatic working-runtime
  construction requirements from the Project marker and generic runner.
- Retained explicit bootstrap responsibility in the normal Tarav runtime and
  its Project Workflow, without adding cross-environment Type dispatch.
- Checkpointed the ready request in `8766dcb` before product edits, as required
  by the Execute workflow.
- Implemented Python Workflow ownership, the abstract configurator contract,
  current and Project configuration, the shared configured subprocess engine,
  declared Project manifest/environment paths, and the general `tarav run`
  adapter. Project bootstrap uses `ProjectLaunchConfiguration`, not a loaded
  concrete `TaravProject`.
- Verification passed: 1,386 tests, repository-wide Ruff, editable CLI
  reinstall, command help, and a direct `tarav run` smoke check. The maintained
  real-uv harness test exercises both generated and declared product
  environments, including import of the declared package.
- Product Surface Breadcrumbs `8930a4c61accc47d`, `f342326ee3e6fed1`, and
  `107c07cf7367ba3a` ground the configurator contract, caller-controlled runner,
  and bootstrap-safe Project projection. The clarification in this request is
  grounded by `f92c76b7c422ef9c`; all Product Surface audits returned no
  findings.
- Wiki capture updated the daily note and `projects.md`, with six new audited
  Breadcrumbs, and closed as commit `cb574e61fe6188a996f8390c4161ade108b9236f`.
- Submitted Design Breadcrumbs
  `1dfb0ef9cc1dbd45`, `19e82d971b0bba8e`, `6000934c2349057a`,
  `0bd238f6fb2aed68`, `1cf5554045456734`, `aafa86b8cf2afab5`,
  `62f59d33819ba3fe`, and `a46af47c1e299f53`; the `chatlas-context` audit
  resolved all eight positions and attachments with no findings.
