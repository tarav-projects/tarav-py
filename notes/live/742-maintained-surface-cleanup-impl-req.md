# Maintained Surface Cleanup — Impl.Req

## Intent

Tighten the maintained `tarav-py` surface after the distribution and Index redesign. Remove public compatibility paths that no longer carry product behavior, and replace accumulated migration-era guidance with a compact description of the system that exists now.

## Evidence

- `tarav --help` still advertises the deprecated `skillware` alias and an empty `future` command group.
- `README.md` describes the package and executable as `agentos`, including commands that are no longer the maintained CLI.
- `ARCHITECTURE.md` mixes `tarav.*` and retired `agentos.*` Python namespaces and still describes Chatlas2 as a separate experiment.
- `AGENTS.md` has grown into a chronological subsystem ledger containing retired Index CLI, `.agentos` project-surface, and migration-window instructions.
- `src/tarav/chatlas2/` has no maintained source files; the lossless model lives in `tarav.chatlas.lossless`.

## Required changes

### 1. Canonical maintained guidance

- Rewrite `README.md` around the installed `tarav` distribution and current top-level CLI.
- Rewrite `ARCHITECTURE.md` as the concise, current dependency and ownership map.
- Tighten `AGENTS.md` to durable contributor constraints and current subsystem boundaries. Move no historical implementation journal into it.
- Keep `Agentos` where it names the product/domain. Use `tarav` for Python imports and executable examples.

### 2. Retire empty and deprecated CLI surfaces

- Remove the `skillware` alias; `tarav skw` is the sole command.
- Remove the empty `tarav future` command group.
- Update tests and help expectations so reintroducing either public surface fails visibly.

### 3. Preserve data contracts

- Do not rename persisted `agentos.*` or `tarav.chatlas2.*` class/schema identifiers in this pass.
- Do not rename established machine-state paths or environment variables without a designed migration.
- Do not alter lossless Chatlas behavior or Index record storage.

## Validation

- CLI help exposes `skw` and does not expose `skillware` or `future`.
- Focused CLI, Skillware, and architecture tests pass.
- Ruff passes on edited Python files.
- A final search distinguishes intentional persistent identifiers from stale maintained prose.

## Out of scope

- Persisted schema and application-record migrations.
- Renaming machine-local Agentos homes.
- Refactoring large subsystem implementation modules merely to reduce line count.
