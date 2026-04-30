# Agentos.Skills

Selection and import model for project-local skills in `agentos`.

---

## What It Is

- A small contract for how `agentos` selects skills for one project target.
- A shared vocabulary for sources, profiles, depots, and imported skills.
- The boundary between config-derived selection and depot-sync behavior.

## Core Terms

- **`source`** — a direct skill root or package-like expansion that contributes discoverable skills
- **`source entry`** — one object in a profile, package, or export package that resolves one source contribution
- **`project-backed source`** — a global source whose root is an `Agentos.Project`
- **`export package`** — a named skill package published by a project-backed source from its own project config
- **`profile`** — an ordered selection of sources plus one or more local depots
- **`depot`** — a project-local directory where imported skill symlinks are materialized
- **`selected skills`** — the catalog computed from the resolved profile before depot sync
- **`imported skills`** — the selected skills after `agentos skills import` syncs the depots

## Project Boundary

- `agentos skills ...` is a project command and uses the `Agentos.Project` targeting model.
- The resolved project target must already be an **`existing project`**.
- `.agents/`, `.claude/`, or local skill depots do not define project existence by themselves.

## Selection Model

- Profile selection resolves in this order:
  - local `.agentos/config.json` override at `skills.routing.profile`
  - global `skills.routing.default_profile`
  - hardcoded `default`
- Profiles are defined in global config under `skills.routing.profiles`.
- Registry sources are defined once in global config under `skills.routing.sources`.
- A source is either:
  - a direct `{ "path": "..." }` entry
  - an Agentos.Project-backed `{ "project": "..." }` entry
  - a `{ "package": [...] }` entry that expands other sources left to right
- Project-backed sources use `<project>/skills` as their default skill root.
- Project-backed sources may publish export packages from
  `<project>/.agentos/config.json` under `skills.exports.packages`.
- A source-qualified reference such as `{ "name": "source:package" }` resolves
  `package` from the project-backed global source `source`.
- Any source entry may add exact `include` and `exclude` arrays.
  - `include` narrows that entry's direct or expanded skills.
  - `exclude` removes matching skills and wins over `include`.
  - Filter names may match the final imported skill name or the source-local skill
    directory name.
  - Unknown filter names are config errors.
- Relative registry source paths resolve from `AGENTOS_HOME`.
- Relative inline profile source paths resolve from the selected project root.

## Global Routing Contract

Global routing lives in `AGENTOS_HOME/config.json` under `skills.routing`.
The global registry is the only place where named sources are registered.

```json
{
  "class": "agentos.global.config",
  "schema_version": 1,
  "skills": {
    "routing": {
      "sources": {
        "agentos": {
          "project": "/Users/pereiro/projects/agentos-project/agentos"
        },
        "scratch": {
          "path": "/Users/pereiro/tmp/scratch-skills"
        },
        "core": {
          "package": [
            { "name": "agentos:maintenance" },
            { "name": "scratch", "exclude": ["scratch-draft-skill"] }
          ]
        }
      },
      "default_profile": "default",
      "profiles": {
        "default": {
          "depots": [
            ".agents/skills",
            ".claude/skills"
          ],
          "sources": [
            { "name": "core" }
          ]
        }
      }
    }
  }
}
```

Registry source kinds:

- `{ "path": "/repo/skills" }` points directly at a directory containing skill folders.
- `{ "project": "/repo" }` points at an existing Agentos project root and scans `/repo/skills`.
- `{ "package": [...] }` expands a list of source entries in order.

## Source Entries

Source entries appear in profile `sources`, registry `package` arrays, inline
packages, and project export packages. They always resolve to one or more
discoverable source roots before the catalog is built.

Whole registered source:

```json
{ "name": "agentos" }
```

Source export package:

```json
{ "name": "agentos:maintenance" }
```

Inline direct source:

```json
{ "name": "local", "path": "skills" }
```

Filtered source entry:

```json
{
  "name": "agentos:maintenance",
  "include": ["agentos-codebase-general-cleanup"],
  "exclude": ["agentos-draft-cleanup"]
}
```

## Project Export Packages

A project-backed source may publish named packages from its own
`<project>/.agentos/config.json`.

```json
{
  "class": "agentos.project.config",
  "schema_version": 1,
  "skills": {
    "exports": {
      "packages": {
        "maintenance": [
          {
            "include": [
              "agentos-codebase-general-cleanup",
              "agentos-git-commit-trigger"
            ]
          }
        ],
        "notes": [
          {
            "include": [
              "agentos-live-note-base",
              "agentos-index-notes-base"
            ]
          }
        ]
      }
    }
  }
}
```

Inside an export package, entries are implicitly local to the exporting source.
For a package exported by global source `agentos`, these are equivalent:

```json
{ "include": ["agentos-live-note-base"] }
```

```json
{ "name": "agentos", "include": ["agentos-live-note-base"] }
```

The implicit form is preferred for local source packages. Export packages may
reference other packages from the same source with source-qualified names such
as `{ "name": "agentos:notes" }`; cycles are config errors.

## Resolution Rules

- `{ "name": "source" }` resolves a global registry source.
- `{ "name": "source:package" }` requires `source` to be a project-backed global source.
- Resolving `source:package` loads `source` project config, reads
  `skills.exports.packages.package`, then expands that package's source entries.
- Consumer-side filters apply after the exported package expands.
- Every filter context must match for a skill to remain selected.
- `exclude` wins if the same skill matches both `include` and `exclude`.
- Disabled source entries are skipped before expansion.

## Validation Rules

- A registry source must define exactly one of `path`, `project`, or `package`.
- `source:package` references against direct-folder or registry-package sources are errors.
- Project-backed sources must point at an existing Agentos project root with
  `.agentos/project.json`.
- Selected project-backed sources must have an existing `<project>/skills` directory.
- Export package names must be valid path-safe names and must not contain `:`.
- Export package payloads must be arrays of source-entry objects.
- Unknown registry sources, unknown export packages, duplicate enabled source
  names, invalid filters, and package cycles are config errors.

## Depot Model

- Depots are project-local paths chosen by the resolved profile.
- When `depots` is omitted, the default depots are:
  - `.agents/skills`
  - `.claude/skills`
- All depots are equal.
- There is no canonical or primary depot.

## Command Contract

- `list` previews the selected skills.
  - It is config-derived and does not sync depots.
- `path` previews the local load paths for one selected skill, or prints depot roots with
  `--depot`.
  - It is config-derived and does not sync depots.
- `import` syncs the selected skills into every configured depot as managed symlinks.
- `import --force` rebuilds the managed symlink layer in every configured depot.
  - Conflicting non-symlink entries still error instead of being deleted.
- `status` compares every configured depot against the selected skills without syncing.

## What This Is Not

- Not a bootstrap skill.
- Not a compatibility skill layer for skill discovery.
- Not a global public skills surface.
- Not direct discovery from raw source roots during normal skill loading.

## Consequences

- The local depots are the loadable skill surface after import.
- Agents and humans can inspect the operational contract directly through
  `agentos skills --help` and subcommand help.
- An empty selected catalog is a normal result, not a special bootstrap condition.
