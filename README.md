# Tarav

`tarav-py` is the maintained Python distribution for Agentos. It ships one
modular monolith under the `tarav` package: the CLI, runtime, daemon, Chatlas,
Index, Skillware, Canvas, agent/provider support, and Iterante runtimes.

See [ARCHITECTURE.md](ARCHITECTURE.md) for ownership and dependency direction.

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
- `tarav index` — distributed Index surfaces, records, capture, and linting.
- `tarav skw` — Skillware build, checking, context, and edition history.
- `tarav surfaces` — thin native source normal models.
- `tarav anchory`, `bloberia`, and `wayfinder` — storage and reference
  primitives.
- `tarav poi` — shared POI resolution and inspection.
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
