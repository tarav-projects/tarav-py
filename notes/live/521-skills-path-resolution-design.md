---
title: Skills PATH Resolution Design
date: 2026-04-04
status: draft
---

# Skills PATH Resolution Design

## Goal

Define `agentos skills` around one ordered skills-path vector, analogous to shell `PATH`, instead of separate global-vs-project concepts in the command semantics.

## Core Model

- The resolver uses one ordered `skills_path` vector.
- Resolution walks the vector in order.
- First matching skill name wins.
- Every resolved skill must always report its source.

## Default Skills Path

- Outside an `agentos` project:
  - `~/.agentos/skills`
- Inside an `agentos` project:
  - `<project-root>/skills`
  - `~/.agentos/skills`

## Resolution Rules

- If the same skill name exists in multiple roots, the first root in `skills_path` wins.
- The winning entry is the effective skill.
- Shadowed entries are not selected by default.
- All commands must use this same ordered resolver by default.

## Provenance Rules

- Skill-related commands must always report source information.
- Provenance is part of the default UX, not only a debug mode.
- Each resolved skill should expose:
  - `name`
  - `path`
  - `root`
  - `source_kind`
  - `resolved_from_index`

## Command Semantics

### `agentos skills path`

- Prints the full ordered `skills_path` vector.
- This is the search path used by resolution.
- Output should include source labels and path indices.

Example shape:

```text
PATH[0] project /repo/skills
PATH[1] global  /Users/pereiro/.agentos/skills
```

### `agentos skills path <name>`

- Resolves `<name>` against the ordered `skills_path`.
- Returns the winning match only.
- Output must include provenance.

Example shape:

```text
design-discussion
resolved_from: PATH[0]
source_kind: project
path: /repo/skills/design-discussion
```

### `agentos skills list`

- Walks the whole `skills_path`.
- Merges by skill name.
- First match wins.
- Always prints the winning source of each skill.

Example shape:

```text
design-discussion    project[0]  /repo/skills/design-discussion
openai-docs          global[1]   /Users/pereiro/.agentos/skills/openai-docs
```

### `agentos skills list --json`

- Returns structured resolved entries, not only bare names.
- Provenance fields are included by default.

Example shape:

```json
[
  {
    "name": "design-discussion",
    "resolved_from_index": 0,
    "source_kind": "project",
    "root": "/repo/skills",
    "path": "/repo/skills/design-discussion"
  }
]
```

### `agentos skills sync`

- Uses the same default resolver model for understanding the environment.
- Writes only to the project-local materialized skills layer.
- Default target remains the first project-local writable layer.
- Errors when no project-local layer exists.

### `agentos skills prune`

- Uses the same default resolver model for environment discovery.
- Operates on the project-local managed layer by default.
- Errors when no project-local layer exists.

## Design Intent

- Keep lookup semantics unified under one resolver model.
- Make debugging straightforward by always showing provenance.
- Avoid ambiguous hidden behavior when skills are shadowed across roots.
- Keep mutation commands explicit about writing to the project-local layer.

## Notes

- This design intentionally treats the skills path as the primary abstraction.
- “project” and “global” still exist as root kinds, but they should not be exposed as separate command-semantic models.
- The key mental model is: ordered search path, first match wins, source always visible.
