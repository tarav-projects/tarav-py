---
title: Local Skills Context Routing Design
date: 2026-04-17
status: superseded
---

# Local Skills Context Routing Design

## Status

Superseded by the current `Agentos.Project` contract and the shipped project-target
rules for `agentos skills`.

Use these as the canonical current references instead:

- `notes/index/004-Agentos.Project.md`
- `notes/live/531-project-command-enforcement-impl-req.md`
- `README.md`

This note is preserved as historical context for the transition away from bindings.

## Goal

Replace the current bindings-based routed skills model with a simpler local-context model:

- no global visible skills depot in the public `agentos skills` flow
- no path-to-profile bindings table
- one local published depot per resolved local context
- default behavior imports profile `default` into that local depot

This keeps the public skill surface local to the current project/worktree and prevents accidental exposure of a wider global skill catalog.

## Main Decision

The routed public surface should be built only into a local depot:

- default depot: `<local-context-root>/.agents/skills`

Public `agentos skills` commands should not use `~/.agents/skills` as the visible skill surface for this routed flow.

Reason:

- if the public surface points at the global depot, then all globally visible skills leak into every local context
- that breaks the whole routing boundary

## Local Context Root Resolution

Resolve a local skills context root with this order:

1. `--project <path>` if provided
2. otherwise search upward from `cwd` for the nearest local `.agents/` directory
3. ignore `~/.agents` during that upward search
4. otherwise fall back to the normal `agentos` project root
5. otherwise no local skills context exists

Important meaning:

- finding local `.agents/` means this tree is allowed to host a local routed skills surface
- it does not mean `.agents/skills` is an import source
- `.agents/skills` remains the sync target only

## Profile Selection

Remove global `bindings`.

Profile selection should no longer come from a global path-to-profile table.

Instead:

1. resolve the local context root
2. check whether that local context has an associated profile
3. if not, use the global default profile

This keeps profile association local and removes the old “closest bound parent path” mechanism.

## Default Behavior

The default mechanism is:

1. resolve local context root
2. resolve selected profile
3. resolve depot
4. sync discovered skills into the local depot

Default selected profile:

- global `default_profile` if configured
- otherwise hardcoded `default`

Default depot:

- `<local-context-root>/.agents/skills`

If no local context root can be resolved:

- `agentos skills import` does nothing
- `agentos skills list` should return an authoritative empty result

## Public Command Flow

### `agentos skills import`

The command should do this sequence:

1. get the local context root
2. resolve selected profile
3. resolve target depot
4. resolve packages/imports for that profile
5. run skill syncing into the local depot

This means:

- we know what to import
- we know where to import it

### `agentos skills list`

The command should describe the routed catalog for the selected profile and local depot target.

It should stay authoritative and should not encourage agents to search outside the routed contract.

### `agentos skills path`

The command should resolve paths only within that same local routed catalog.

## Config Model

Keep these global routing config objects:

- `imports_registry`
- `packages`
- `profiles`
- `default_profile`

Remove:

- `bindings`

Roles:

- `imports_registry`: named source definitions
- `packages`: reusable groups of imports
- `profiles`: materialization policy and import composition
- `default_profile`: default selected profile when no local override exists

## Correct Shape For Default Config

`core` is a package, not an import source.

So the default config shape should look like:

```json
{
  "skills": {
    "routing": {
      "imports_registry": {
        "agentos": {
          "path": "/Users/pereiro/projects/agentos/skills"
        },
        "md-library": {
          "path": "/Users/pereiro/Documents/md-library/skills"
        }
      },
      "packages": {
        "core": {
          "imports": [
            { "name": "agentos" },
            { "name": "md-library" }
          ]
        }
      },
      "default_profile": "default",
      "profiles": {
        "default": {
          "packages": [
            { "name": "core" }
          ],
          "imports": []
        }
      }
    }
  }
}
```

## Local Profile Association

The local context may optionally associate itself with a profile.

Likely direction:

- store the local profile selection in local config, not global routing bindings

Example shape:

```json
{
  "skills": {
    "routing": {
      "profile": "research"
    }
  }
}
```

If this local override is missing, the system falls back to global `default_profile`.

## Why This Model Is Better

- simpler than bindings
- keeps the published surface local
- avoids global skill leakage into unrelated repos
- preserves reusable global routing definitions
- still allows per-project specialization later

## Superseded Direction

This design supersedes the earlier routed model based on:

- closest matching global bindings
- fallback `base` profile
- internal public depots under `~/.agentos/skills-depot/<profile>/`

The new preferred model is:

- local context root
- local published depot
- default profile fallback
- no global path binding layer

## Follow-up

Implementation should update the current routed layer to:

1. remove bindings from selection
2. add local context root resolution
3. add global `default_profile`
4. use profile `packages` correctly
5. sync only into `<local-context-root>/.agents/skills`
6. never use `~/.agents/skills` as the routed public surface
