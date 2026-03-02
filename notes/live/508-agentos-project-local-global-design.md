# Agentos Project-Based Local/Global Layout Design

## Context
- Discussion date: 2026-03-01
- Goal: make `agentos` project-based, like git, with local project attachment and a global user home.

## Agreed Direction
- `agentos` should support a local project folder at `<project>/.agentos`.
- `agentos` should also have a global user folder at `~/.agentos`.
- Project marker file must be inside `.agentos`: `<project>/.agentos/project.json`.
- Add `agentos init` to initialize project context and create the marker.
- Context discovery should mirror git behavior by walking parent directories from CWD.
- Mirror git-style project introspection commands:
- `agentos rev-parse --is-inside-agentos-project`
- `agentos rev-parse --show-toplevel`
- Add explicit scope flags for relevant commands:
- `--scope project|global|auto`
- Add `agentos doctor` output for detected project context and resolved local paths.

## Scoped Focus for First Implementation
- Prioritize project-local behavior first (`<project>/.agentos`).
- Defer full global project-registry behavior for later.
- Defer settings precedence discussion for later.

## Explicitly Deferred
- Detailed settings resolution order (`project > global > defaults`) not finalized yet.
- Global project registry and cross-project metadata flows.
- Default git tracking policy for `.agentos` contents; user/project decides.

## Proposed First Change Set
- Implement `agentos init` for local project bootstrap.
- Implement git-like project discovery utility (`find nearest .agentos/project.json`).
- Implement `agentos rev-parse --is-inside-agentos-project`.
- Implement `agentos rev-parse --show-toplevel`.
- Add `--scope` flag plumbing where needed.
- Extend `agentos doctor` with project-context diagnostics.
