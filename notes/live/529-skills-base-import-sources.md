---
title: Skills Base Import Sources
date: 2026-04-17
status: draft
---

# Skills Base Import Sources

## Goal

Record the current source pool considered for the `base` routed skills profile and the current decision for what `base` should expose by default.

## Current Decision

The `base` profile should stay narrow for now.

Current `base` imports:

- `agentos`
- `md-library`

Do not create more profile splits yet.

## Why

The routed system exists to control visibility.

If `base` includes every previously configured import source, the new router would recreate the old “many skills visible everywhere” behavior behind a different interface.

The goal of `base` is:

- provide a useful generic default
- avoid exposing domain-specific skill families in unrelated repos

## Source Pool Considered

These are the import sources previously configured in the old global `skills.imports` pool:

- `md-library`
  - path: `/Users/pereiro/Documents/md-library/skills`
- `io-capitalist`
  - path: `/Users/pereiro/Documents/IoCapitalist/skills`
- `agentos`
  - path: `/Users/pereiro/projects/agentos/skills`
- `spec-surfaces`
  - path: `/Users/pereiro/projects/spec-surfaces/skills`
- `simuleos`
  - path: `/Users/pereiro/.julia/dev/Simuleos/skills`
- `phd`
  - path: `/Users/pereiro/University/Phd/skills`
- `paperson`
  - path: `/Users/pereiro/University/CODE/PaperSON`
- `biblio`
  - path: `/Users/pereiro/Documents/js/obajs-monorepo/apps/biblio-cli/skills`

## Base Inclusion Decision

### Include In `base`

- `agentos`
  - reason: this is the main general-purpose local skill set
- `md-library`
  - reason: generic enough to be useful outside one narrow project domain

### Keep Out Of `base` By Default

- `io-capitalist`
- `phd`
- `paperson`
- `simuleos`
- `biblio`

Reason:

- these are domain-specific or project-specific skill families
- they should not be exposed everywhere by default

### Borderline Case

- `spec-surfaces`

Decision for now:

- keep it out of `base`

Reason:

- it may be useful in generic design/spec contexts
- but including it now would widen `base` before the routing model settles

## Current Live Routing Config

The current global routing config now uses only one routed profile:

- profile: `base`
- registry entries:
  - `agentos`
  - `md-library`
- imports:
  - `{ "name": "agentos" }`
  - `{ "name": "md-library" }`

No extra profiles or bindings have been created yet.

## Follow-up

Later, if needed:

- add dedicated profiles for domain-specific roots
- add bindings for repos or parent worktrees that should select those profiles
- revisit whether `spec-surfaces` belongs in `base` or in its own profile
