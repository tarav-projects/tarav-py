---
title: Global Skills Imports Fallback Design
date: 2026-04-04
status: draft
---

# Global Skills Imports Fallback Design

## Goal

Allow `agentos` projects to inherit a default `skills.imports` configuration from the global Agentos config when the project does not define its own `skills.imports`.

## Core Decision

- Support `skills.imports` in global config at `~/.agentos/config.json`.
- Use the same structure as project `skills.imports`.
- Do not merge project and global imports by default.
- Global imports act only as a fallback.

## Configuration Shape

Project config:

```json
{
  "class": "agentos.project.config",
  "schema_version": 1,
  "skills": {
    "imports": [
      { "name": "shared", "path": "../external-skills" }
    ]
  }
}
```

Global config:

```json
{
  "class": "agentos.global.config",
  "schema_version": 1,
  "skills": {
    "imports": [
      { "name": "shared", "path": "/Users/pereiro/.agentos/imported-skills" }
    ]
  }
}
```

## Resolution Rule

For project-local sync/import configuration:

1. If project `skills.imports` exists, use it.
2. If project `skills.imports` does not exist, use global `skills.imports`.
3. Do not merge the two lists by default.

## Important Distinction

- Missing project `skills.imports` means fallback is allowed.
- Explicit project `skills.imports: []` means the project intentionally imports nothing.
- Therefore an explicit empty list disables fallback.

## Scope Of Fallback

This fallback applies to import configuration lookup for `agentos skills sync`.

It does not change the runtime skills path model:

- inside project:
  - `<project>/skills`
  - `~/.agentos/skills`
- outside project:
  - `~/.agentos/skills`

The global config fallback affects how the project-local skills layer is materialized, not how the effective lookup path is ordered.

## Intended Command Semantics

### `agentos skills sync`

- Still requires a real project-local Agentos project.
- Still writes to the project-local skills layer.
- When choosing imports:
  - prefer project `skills.imports`
  - otherwise use global `skills.imports`

### `agentos skills prune`

- No change in configuration source.
- Still operates on the project-local managed skills layer.

### `agentos skills list` and `agentos skills path`

- No change in default search path semantics.
- They continue to inspect the materialized skills roots.

## Why No Merge

- Merging project and global imports would create unclear precedence and ownership.
- Duplicate import names would become harder to reason about.
- Duplicate discovered skill names across merged import lists would complicate sync behavior.
- A pure fallback rule is simpler and more predictable.

## Recommended Semantics Summary

- Project imports override global imports.
- Missing project `skills.imports` falls back to global imports.
- Explicit empty project imports disable fallback.
- No automatic merge.
- Same JSON shape for project and global config.
