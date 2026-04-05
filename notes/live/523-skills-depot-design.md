---
title: Skills Depot Design
date: 2026-04-04
status: draft
---

# Skills Depot Design

## Goal

Clarify the `agentos skills` model by separating:

- source skill roots
- published destination roots
- public resolution surfaces

The main vocabulary change is to name the published destination of the import/sync process the `skills_depot`.

## Core Concepts

### `skills.imports`

- These are source skill roots.
- They define where `sync` reads from.
- They may include project-local paths, shared repositories, or Agentos-owned source areas.

### `skills_depot`

- This is the published destination root.
- It is the target of the import/sync process.
- `agentos skills sync` materializes discovered skills into this depot, typically as symlinks.

### Public Skill Surface

- The public skill surface should be made of depots only.
- Resolution commands should look at published depots, not raw import roots.

## Project Configuration

Project config should support:

```json
{
  "class": "agentos.project.config",
  "schema_version": 1,
  "skills": {
    "skills_depot": ".agents/skills",
    "imports": [
      { "name": "shared", "path": "../shared-skills" }
    ]
  }
}
```

Rules:

- `skills.imports` defines source roots.
- `skills.skills_depot` defines the project published depot.
- If `skills.skills_depot` is missing, default to `<project>/skills`.

## Global Configuration

Global config should support fallback imports:

```json
{
  "class": "agentos.global.config",
  "schema_version": 1,
  "skills": {
    "imports": [
      { "name": "agentos-src", "path": "skills" }
    ]
  }
}
```

Rules:

- Global `skills.imports` is a fallback source config.
- It is used only when the project does not define `skills.imports`.
- Explicit empty project imports disable the fallback.
- No merge by default.

## Global Depot Policy

- The default global public depot should be `~/.agents/skills`.
- `~/.agentos/skills` should not be the public depot.
- `~/.agentos/skills` is better treated as:
  - an Agentos-owned skill source area
  - an import source
  - an internal area

This avoids mixing:

- Agentos-owned/internal skills
- user-facing published global skills

## Public Resolution Surface

Inside a project, the public resolution surface should be:

1. project `skills_depot`
2. global public depot `~/.agents/skills`

Outside a project, the public resolution surface should be:

1. global public depot `~/.agents/skills`

Resolution should use published depots only.

## Intended Command Semantics

### `agentos skills sync`

- Reads from `skills.imports`
- Writes to `skills_depot`
- Uses project imports first
- Falls back to global imports if the project `skills.imports` field is missing

### `agentos skills list`

- Shows the published skills available from the public resolution surface
- Should not inspect raw import roots by default

### `agentos skills path`

- Resolves within the public resolution surface
- Should describe depot-based resolution, not import-source resolution

## Naming

CLI naming should use:

- `--skills-depot`
  - temporary override for the published destination

This is clearer than destination names like `--skills-folder`, because it makes the sync flow explicit:

- imports are the source
- depot is the published target

## Design Summary

- `skills.imports` = source roots
- `skills_depot` = published target
- project depot default = `<project>/skills`
- global public depot default = `~/.agents/skills`
- `~/.agentos/skills` is a source area, not the public global depot
- resolution uses depots only
- global imports are fallback-only, with no merge by default
