# Agentos.Project

Identity and targeting model for project-scoped agentos behavior.

---

## What It Is

- A small contract for deciding what counts as an agentos project.
- A shared vocabulary for commands that operate relative to a project root.
- The boundary between project resolution and per-command project policy.

## Core Terms

- **`project root`** — the directory that contains `.agentos/`
- **`project target`** — the root selected for a command by project resolution
- **`existing project`** — a project target where `.agentos/project.json` exists

## Identity

- `.agentos/project.json` is the only canonical marker for project existence.
- A directory is an **`Agentos.Project`** iff its project root contains `.agentos/project.json`.
- `.agentos/config.json` is project-local config, but it does not define project existence.
- Other local surfaces do not define an `Agentos.Project` by themselves.
  - Example: `.agents/`, `.agents/skills`, or similar exported folders are not project markers.

## Project Resolution

Commands that support project targeting have exactly two entry paths:

- **implicit discovery** — parent-walk from `cwd`
- **explicit targeting** — `--project`

Explicit targeting rules:

- `--project <path>` targets that path
- bare `--project` targets the current directory

In both cases, the resolved project target is the directory being targeted, not yet a guarantee
that it is an existing project.

## Command Policy Boundary

After a command resolves a `project target`, command policy decides what is allowed:

- some commands require the target to already be an **`existing project`**
- some commands may auto-init when the target was selected explicitly via `--project`
- some commands are not project commands at all

Important safety rule:

- implicit discovery never implies project creation
- parent-walk failure must not auto-init a project

## What This Is Not

- Not a full local storage layout catalog
- Not a global/project config precedence spec
- Not a subsystem inventory
- Not a git repository spec

## Consequences

- A command can talk precisely about a `project target` even before project existence is verified.
- Commands that require a real project should ask for an **`existing project`**.
- Commands that support explicit initialization should do so only from explicit `--project`
  targeting, never from failed implicit discovery.
