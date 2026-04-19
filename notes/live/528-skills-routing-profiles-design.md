---
title: Skills Routing Profiles Design
date: 2026-04-16
status: superseded
---

# Skills Routing Profiles Design

## Status

Superseded by the later local/project-target skills model and the current
`Agentos.Project` enforcement contract.

Use these as the canonical current references instead:

- `notes/index/004-Agentos.Project.md`
- `notes/live/531-project-command-enforcement-impl-req.md`
- `README.md`

This note is preserved as historical design context for the earlier caller-context,
bindings, and `base` profile routing model.

## Goal

Redesign `agentos skills` so agents only see a routed public skills surface, while the real skill sources and materialization logic stay behind `agentos`.

This design replaces the older “public depot plus PATH-like resolution” model with:

- one public agent-facing contract
- route profiles selected by caller context
- internal per-profile materialized depots

## Public Contract

The public `agentos skills` surface is intentionally minimal:

- `agentos skills list`
- `agentos skills path <name>`

Rules:

- `list` is the authoritative routed catalog for the current caller context.
- `path <name>` resolves only within that same routed catalog.
- Public commands must not expose raw import roots or hidden registry topology.
- Public commands may accept routing arguments such as `--project`.
- Internal admin and registry commands are not part of this public surface.

## Master Skill

Create one visible compatibility-hook skill:

- `agentos-skills`

Role:

- teach traditional skill loaders how to use the routed public CLI
- trigger when an agent needs to discover or load another skill
- usually trigger once per session

The skill protocol is:

1. run `agentos skills list`
2. choose a routed skill from that catalog
3. run `agentos skills path <name>`
4. read the returned skill path

The master skill must also tell agents:

- do not search for skills outside `agentos skills`
- treat empty routed results as authoritative

## Routing Model

Routing is based on profiles and bindings.

### Profiles

All profiles are the same kind of object.

There is no special profile type for `base`.

For now, every profile uses the same mechanism:

- configure source roots
- discover `SKILL.md` directories
- materialize symlinks into an internal depot

`base` is just another profile name, used only as the final fallback selection.

### Bindings

Bindings associate filesystem roots with profile names.

Selection rule:

- choose the closest matching bound parent context for the caller root
- if no binding matches, fall back to profile `base`

Example:

- caller root: `bla/blo/blu`
- binding exists for `bla/blo`
- no binding exists for `bla/blo/blu`
- selected profile is the one bound to `bla/blo`

## Caller Context Resolution

Caller context resolution order:

1. `--project <path>` if provided
2. otherwise the normal `agentos` project root resolved from `cwd`
3. otherwise raw `pwd`

Then:

1. normalize the chosen root
2. select the closest matching binding
3. fall back to `base` if nothing matches

## Materialized Routed Depot

Profiles are materialized into internal depots managed by `agentos`.

Likely shape:

- `~/.agentos/skills-depot/<profile>/`

Purpose:

- hide raw source topology from agents
- give `list` and `path` a stable routed surface to read from
- reuse the existing import/discovery/symlink machinery behind the router

Important boundary:

- reuse the current skills-import backend
- do not reuse the old public command contract

## Reuse of Current Skills Import System

The current skills import system already solves most of the backend problem:

- configure a set of sources
- discover skills
- symlink them into one depot

This should be reused as the materialization engine for routed profiles.

That means:

- the new router selects a profile
- the selected profile config is fed into the existing import/materialization machinery
- the resulting routed depot becomes the only source for public `agentos skills` output

## Public Output Rules

### `agentos skills list`

The command should return the routed table for the selected profile.

Expected fields:

- `name`
- `description`
- `source`
- `path`

Rules:

- `description` comes from skill frontmatter
- `path` is the absolute routed path inside the internal routed depot
- `source` is abstract provenance, not a raw import filesystem path

### `agentos skills path <name>`

The command resolves one canonical routed skill name within the selected profile only.

It must not bypass the router or inspect hidden sources directly.

## Empty Result Semantics

An empty result is a valid policy outcome.

If the selected profile exposes no skills:

- `agentos skills list` returns no skills
- the CLI warns clearly that the result is authoritative

If no binding matches and `base` is empty:

- the router still resolves to `base`
- `list` still returns no skills
- this is not treated as an error in itself

The empty-state message should discourage agents from breaking the boundary.

## Current Mock Implementation State

Current work completed:

- public `agentos skills` surface reduced to `list` and `path`
- `agentos-skills` master skill added under repo `skills/`
- current `list` mock returns an empty catalog
- current `path` mock returns routed not-found for every skill
- empty-state message explicitly tells agents not to search outside `agentos skills`

This is an intentional staging step before wiring real profile-backed routing.

## Next Implementation Direction

1. define routing config under `~/.agentos`
2. implement closest-binding profile resolution
3. map selected profile config into the current import/materialization engine
4. materialize routed depot under `~/.agentos/skills-depot/<profile>/`
5. make `agentos skills list` and `path` read from that routed depot
6. keep raw source topology hidden from public output
