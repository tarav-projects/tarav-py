# Tarav

`tarav-py` is the maintained Python distribution for Agentos. It ships one
modular monolith under the `tarav` package: the CLI, runtime, daemon, Chatlas,
Archive, Diagram, SKW, agent/provider support, and Iterante runtimes.

See [ARCHITECTURE.md](ARCHITECTURE.md) for ownership and dependency direction.
`tarav.l0.kernel` provides the dependency-clean semantic roles and trusted Record
Type dispatch that Tarav applications may specialize without sharing schemas.

## Install

```sh
uv sync
uv tool install --reinstall --editable .
```

The distribution provides four executables:

- `tarav`
- `tarav-daemon`
- `iterante`
- `iterante2`

Use CLI help as the command reference; it is generated from the maintained
parser rather than copied into this document:

```sh
tarav --help
tarav <command> --help
```

## Project model

A Tarav project is identified by `<project>/.tarav/project.json`. Commands that
accept `--project` use an explicit path, or the current directory when the flag
is present without a value. Whether project selection is required is a command
contract, not a global CLI default.

Project metadata is portable project data. Machine-local locations and caches
belong in their owning registries or state roots, not in `project.json`.

### Optional Project-local Python harness

Explicitly scaffold a package and install it with Tarav into `.tarav/env`:

```sh
tarav project harness scaffold --project /path/to/project \
  --package my_project --tarav-source /path/to/tarav-py
tarav project harness sync --project /path/to/project
tarav project harness inspect --project /path/to/project
tarav run --project /path/to/project -- /path/to/script.py --flag value
tarav run --project /path/to/project -- -c 'import my_project; print(my_project.__file__)'
tarav run --project -- /path/to/script.py --flag value
```
<!-- tarav.breadcrumb 0f7d6215f010aefa07f9d8348928517983aebaa49b460465e501da996b4d8aaf -->

The Project directory must already exist. `--tarav-source` explicitly selects
a local Tarav checkout or wheel. An existing base/untyped marker requires
`--adopt`; its identity and other metadata are preserved. Specialized markers
are not overwritten. Rerunning scaffold preserves edited package source and
the generated class Ship. Sync retains `.tarav/uv.lock`; `.tarav/.gitignore`
ignores env while preserving existing rules.

The package under `.tarav/src/` owns a concrete `MyProject(TaravProject)` and
its trusted `__main__` launcher. `.tarav/pyproject.toml` holds package launch
configuration, separate from the marker. `tarav run` selects the Project
interpreter and working directory when `--project` is present. A bare
`--project` searches the current directory and its parents, failing if no
Project marker exists; a path starts the search there. Without `--project`,
the current Tarav interpreter is used, including inside a Project. All arguments after `--` go directly
to Python, whose exit status is returned. Scripts use library APIs explicitly;
the general runner does not inject `project` or `runtime`. An absent Project
environment requires explicit sync.
<!-- tarav.breadcrumb 183d55ff0858594084c5e551bf83b4d9788e9818c421b999213507943e110eab -->

The same filesystem operations are available through
`tarav.l2.project.harness.ProjectHarness`; runtime bootstrap and subprocess
launch are in `tarav.l3.project.harness`. Normal Project discovery neither installs
packages nor imports the Project's specialization.

## Main systems

- `tarav agent` — provider-neutral agent and account operations.
- `tarav chatlas` — retained chat data, lossless normalization, and queries.
- `tarav breadcrumbs` — opaque surface anchors, locator observations, and
  workflow-owned typed attachments.
- `tarav diagram` — semantic Models, Ships, Annotations, Views, and Drafts.
- `tarav scoring` — Assertion-owned candidate adaptation, explicitly enrolled
  concrete Ranking Pool Types, frozen Ranking Runs, retained experiment evidence, live
  derived scores, compact per-Assertion scoring histories, and graph tracing.
- `tarav skw document` and `tarav skw skills` — document compilation and skill packages.
- `tarav bloberia` — hosted JSON registry.
- `tarav.l1.references` — typed reference construction and resolution library.
- `tarav.l1.poi` — typed findings, bounded reports, and recorded blessings library.
- `tarav.l1.surfaces` — retained native parsers; standalone CLI disconnected.
- `tarav stdlib` — small reusable command and library primitives.

The complete current command set is always available through `tarav --help`.

## Development

```sh
uv run pytest
uv run ruff check src tests
```

The [Test Workflow example](dev/test_workflow_example.py) creates a fresh
Archive run and a retained Context for its Entity under `~/Documents/tarav/`:

```sh
uv run python dev/test_workflow_example.py
```

After changing installed command behavior, refresh the editable tool:

```sh
uv tool install --reinstall --editable .
```

Historical pre-consolidation repositories live under `_DEPRECATED/`. They are
sources for archaeology only; maintained code and tests live in `src/tarav/`
and `tests/`.
