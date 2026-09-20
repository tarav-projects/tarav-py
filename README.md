# Tarav

`tarav-py` is the maintained Python distribution for Agentos. It ships one
modular monolith under the `tarav` package: the CLI, runtime, daemon, Chatlas,
Archive, Diagram, SKW, agent/provider support, and Iterante runtimes.

See [ARCHITECTURE.md](ARCHITECTURE.md) for ownership and dependency direction.
`tarav.harness` provides the dependency-clean semantic roles and trusted Record
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
- `tarav.references` — typed reference construction and resolution library.
- `tarav.poi` — typed findings, bounded reports, and recorded blessings library.
- `tarav.surfaces` — retained native parsers; standalone CLI disconnected.
- `tarav stdlib` — small reusable command and library primitives.

The complete current command set is always available through `tarav --help`.

## Development

```sh
uv run pytest
uv run ruff check src tests
```

After changing installed command behavior, refresh the editable tool:

```sh
uv tool install --reinstall --editable .
```

Historical pre-consolidation repositories live under `_DEPRECATED/`. They are
sources for archaeology only; maintained code and tests live in `src/tarav/`
and `tests/`.
