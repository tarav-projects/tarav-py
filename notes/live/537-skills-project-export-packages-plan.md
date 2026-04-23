---
title: Skills Project Export Packages Plan
date: 2026-04-23
status: implemented
---

# Skills Project Export Packages Plan

## Goal

Extend `agentos skills` routing so a global source can be declared as an
`Agentos.Project`, and that project can publish named skill export packages from
its own `.agentos/config.json`.

This lets consumers write source-qualified package references such as:

```json
{ "name": "iterante:runtime" }
```

without copying every source-owned package definition into the global routing
config.

## Current Baseline

The current routing model supports:

- global `skills.routing.sources`
- direct skill-folder sources via `{ "path": "..." }`
- package/composite sources via `{ "package": [...] }`
- profile-selected source entries
- `include` and `exclude` filters on any source entry
- project-local depots selected by the resolved `Agentos.Project`

Current direct folder sources must keep working unchanged.

## Implementation State

Implemented in the current worktree for the core resolver path:

- registry `project` source kind
- default `<project>/skills` skill root
- exported packages loaded from source project `.agentos/config.json`
- source-qualified references like `{ "name": "iterante:runtime" }`
- implicit and explicit local export package entries
- include/exclude filter composition across export expansion
- cycle detection across exported packages
- focused skills routing tests

## Source Kinds

### Direct Folder Source

Existing behavior:

```json
{
  "skills": {
    "routing": {
      "sources": {
        "local-skills": {
          "path": "/repo/skills"
        }
      }
    }
  }
}
```

Meaning:

- `path` points directly at a folder to scan for `SKILL.md` directories.
- no project config is loaded from that source.
- `{ "name": "local-skills" }` imports the whole scanned source, subject to
  local include/exclude filters.

### Agentos Project Source

New behavior:

```json
{
  "skills": {
    "routing": {
      "sources": {
        "iterante": {
          "project": "/Users/pereiro/Documents/workspaces/oba-workspace/agentos-iterante-dev"
        }
      }
    }
  }
}
```

Meaning:

- `project` points at an existing Agentos project root.
- the default skill root is `<project>/skills`.
- source exports are read from `<project>/.agentos/config.json`.
- `{ "name": "iterante" }` imports the whole default skill root.
- `{ "name": "iterante:runtime" }` imports a package exported by that project.

Optional future field:

```json
{
  "project": "/repo",
  "skills_path": "custom-skills"
}
```

For the first pass, implement `project` with default `<project>/skills`; defer
`skills_path` unless implementation pressure shows it is needed immediately.

## Project Export Config

A source project publishes packages from its local `.agentos/config.json`:

```json
{
  "class": "agentos.project.config",
  "schema_version": 1,
  "skills": {
    "exports": {
      "packages": {
        "runtime": [
          {
            "include": [
              "iterante-cli-agent",
              "iterante-free-agent"
            ]
          }
        ],
        "missions": [
          {
            "include": [
              "iterante-mission-developer"
            ]
          }
        ]
      }
    }
  }
}
```

Package entries are implicitly local to the exporting source. The following is
equivalent inside the `iterante` project:

```json
{ "include": ["iterante-cli-agent"] }
```

and:

```json
{ "name": "iterante", "include": ["iterante-cli-agent"] }
```

The implicit form is preferred because the exporting config already belongs to
the source project.

## Reference Semantics

### Whole Source

```json
{ "name": "iterante" }
```

Imports the source's default skill root.

### Source Export Package

```json
{ "name": "iterante:runtime" }
```

Resolves global source `iterante`, loads its project export package `runtime`,
then expands that package into source-local entries.

### Consumer-Side Filters

Consumer-side filters still apply to the expanded package:

```json
{
  "name": "iterante:runtime",
  "exclude": ["iterante-free-agent"]
}
```

Filter composition should follow the existing include/exclude model:

- every filter context must match
- `exclude` wins over `include`
- unknown filter names are config errors

## Validation Rules

- A global source must define exactly one source target kind:
  - `path`
  - `project`
  - `package`
- `source:package` references require the source to be project-backed.
- Missing global source errors clearly:
  - `routing source references unknown registry source: iterante`
- Missing exported package errors clearly:
  - `routing source export package not found: iterante:runtime`
- A project-backed source must point at an existing Agentos project root.
- The project source default skill root `<project>/skills` must exist and be a
  directory when selected for import.
- Export package names must be valid path-safe names.
- Export package payloads must be arrays of source-entry objects.
- Export packages should detect cycles if exported packages are allowed to
  reference other exported packages.

## Cycle Policy

First pass should support `source:package` references in the normal consumer
routing payload and inside exported package payloads.

Cycle detection must include both global and source-qualified package edges:

- `core -> iterante:runtime -> iterante:runtime`
- `iterante:runtime -> iterante:missions -> iterante:runtime`

Use the existing registry stack idea, but track qualified names such as:

- `global:core`
- `source:iterante:runtime`

## Implementation Plan

### Phase 1: Data Model

- Extend `SkillsRoutingSource` with:
  - `kind`
  - `project_path_text`
  - existing `path_text`
  - existing `package_payload`
  - existing filter context
- Keep `SkillsImport` as the direct discovered source object, but allow
  project-backed registry sources to resolve into the same `SkillsImport`
  shape using `<project>/skills`.
- Add a small internal representation for resolved source references:
  - source name
  - optional export package name

### Phase 2: Config Parsing

- Update registry parsing so a source object accepts exactly one of:
  - `path`
  - `project`
  - `package`
- Preserve current errors for legacy unsupported fields.
- Parse source refs with `:` in `_append_sources_from_payload`.
- Reject malformed refs:
  - empty source name
  - empty package name
  - more than one colon unless a later design explicitly allows it

### Phase 3: Project Source Resolution

- Resolve project paths like current registry paths:
  - absolute paths stay absolute
  - relative registry paths resolve from `AGENTOS_HOME`
- Require `<project>/.agentos/project.json`.
- Resolve skill root as `<project>/skills`.
- Read exports from `<project>/.agentos/config.json`.
- Missing project config means no exported packages.

### Phase 4: Export Package Expansion

- Add a helper that loads:
  - `skills.exports.packages`
  - one named package payload
- Expand source-local package entries by defaulting missing `name` to the
  exporting source name.
- Support explicit `{ "name": "iterante" }` inside the source project config for
  symmetry.
- Apply filters from:
  - the consumer reference
  - the exported package entry
  - the registry source itself
- Reuse the existing direct-source append path after expansion.

### Phase 5: Tests

Add focused tests in `tests/test_skills_commands.py` for:

- direct `path` source behavior remains unchanged
- project source imports `<project>/skills` with `{ "name": "iterante" }`
- `{ "name": "iterante:runtime" }` resolves exported package entries
- consumer-side `include` / `exclude` filters apply after exported package
  expansion
- implicit local exported package entries work
- explicit local exported package entries work
- missing package errors clearly
- `source:package` against a non-project source errors clearly
- project source requires `.agentos/project.json`
- export package cycles error clearly

Add a dependent smoke test for a surface that calls `query_selected_skills`, if
needed, to make sure mission template filtering still works.

### Phase 6: Docs And CLI Refresh

- Update `README.md` skills routing contract.
- Update `notes/index/005-Agentos.Skills.md`.
- Run focused tests:

```sh
uv run pytest tests/test_skills_commands.py tests/test_mission_template_commands.py -q
```

- Refresh installed CLI after code changes:

```sh
uv tool install --reinstall --editable .
```

## Acceptance Signals

- Existing `path` and `package` source configs keep working.
- A global source can be declared with `project`.
- Whole project-backed source import works through `{ "name": "<source>" }`.
- Project export package import works through `{ "name": "<source>:<package>" }`.
- Export package definitions live in the source project's `.agentos/config.json`.
- Source-owned export packages can use concise implicit-local entries.
- Filters compose correctly across registry source, export package, and consumer
  reference.
- Error messages identify whether a missing thing is a source, package, project,
  or skill filter reference.

## Deferred Items

- Non-default `skills_path` for project sources.
- Cross-source exports from one source project's export package.
- Wildcard/glob include/exclude patterns.
- Exporting individual skill aliases.
- CLI commands for listing exported packages.
