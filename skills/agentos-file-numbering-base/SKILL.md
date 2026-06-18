---
name: agentos-file-numbering-base
description: Define, review, or extend Agentos numeric filename protocols and prefix allocation workflow. USE WHEN adding a new numbered artifact type, checking which files determine the next `NNN-` prefix, deciding prefix floors or reserved ranges, or verifying whether gaps and renumbering are allowed.
---

# Agentos File Numbering Base

Minimal protocol for Agentos-managed numeric filename workflows.

This is a `Batchy.Skill`. Load `agentos-skills-base` for the full convention.

- `-h` / `--help` prints this skill's help into the chat instead of running; it takes no arguments.

## Scope

- Define shared numbering mechanics, not document body structure.
- Centralize how `agentos stdlib prefix next` relates to numbered artifact protocols.
- Define only the base numbering rules that domain-specific `base` skills inherit.

## Shared Numbering Rules

- Canonical numbered filename shape is `NNN-short-topic.ext`.
- `NNN` is zero-padded to a fixed width, currently `3`.
- Numeric prefixes are stable handles, so the meaningful title may change while the number remains fixed.
- A numbering domain is defined by:
  - the project-relative target path
  - the filename pattern matched by the allocator
  - the allocation range
  - any manually assigned reserved prefix table
  - whether numbers must be unique only inside the domain or across a broader project surface
- For Agentos project-aware allocation, the numbering source is the configured project scan scope for numbered surfaces, filtered by the resolved target route.

## Allocator Behavior

- `agentos stdlib prefix next --project --project-name <declared-project-name> --target <path>` resolves the `Agentos.Project`, asserts the declared project name from `.agentos/project.json`, loads the project prefix policy, and allocates for the project-relative target path.
- Use `--project /path/to/project --project-name <declared-project-name> --target <path>` when outside the intended project tree.
- Numbered artifact prefixes must be allocated with `agentos stdlib prefix`; do not assign ordinary prefixes by manual inspection.
- If `agentos stdlib prefix` fails, stop and ask the user how to resolve the project or numbering surface. Do not fall back to inspection.
- In nested workspaces, verify that the resolved project marker is the intended numbered surface. Use `--project-name <declared-project-name>` so the command fails if the wrong project was resolved; do not use `--project .` unless `.` is the actual initialized project root.
- It scans the configured project numbered-surface scope. The current default includes are `notes` and `dev/live`.
- It extracts ordinary allocated prefixes using the filename regex `^(\d{width})-`.
- It ignores files that do not begin with a valid zero-padded ordinary prefix.
- Reserved prefixes are manually assigned fixed-role prefixes, not ordinary allocator output.
- It returns:
  - the selected route lower bound if no eligible prefixes exist
  - otherwise `max(existing eligible prefixes in the selected route range) + 1`
- This is append-only allocation, not gap-filling allocation.

## Stability Rules

- Numeric prefixes are stable identifiers once assigned.
- Gaps are allowed.
- Deleted files do not cause renumbering of surviving files.
- Deleted prefixes are not reused by the shared allocator.
- Do not renumber existing numbered files, because renumbering breaks links and external references.

## Domain Ownership

- This skill must not carry a concrete inventory of numbering domains.
- Each domain `base` skill must define its own:
  - location
  - filename pattern
  - target path
  - numbering source or project scan-scope assumption
  - allocation range or reserved range
  - uniqueness scope
  - exact `agentos stdlib prefix next` command, if allocation is automated
- This skill owns only the shared numbering semantics that all those domain skills inherit.

## Cross-Domain Coordination

- Some systems need numbers to be unique across a broader surface than one folder.
- Example: Agentos notes are moving toward project-wide md-surface uniqueness, where the same note number should not identify different notes in different note folders.
- Current `agentos stdlib prefix next --project ... --project-name ... --target ...` supports project-aware allocation with declared project-name assertion. Full project-wide diagnostics such as duplicate reports, range violations, and reserved-prefix consistency checks remain future `prefix doctor` or equivalent work.

## Workflow For A New Numbered Artifact Type

1. Decide the domain root and canonical filename extension.
2. Decide whether the domain is human-managed, agent-managed, or split by range.
3. Pick a minimum floor and any reserved range policy.
4. Define the target path and numbering source, for example `--project --project-name <declared-project-name> --target notes/live` using the project numbered-surface scan policy.
5. Add a domain base protocol skill or base spec that states:
   - location
   - filename pattern
   - target path
   - numbering source or project scan-scope assumption
   - allocation range or reserved range
   - uniqueness scope
   - exact `agentos stdlib prefix next` command, if allocation is automated
   - stability rule: gaps allowed, no renumbering
6. Ensure the domain protocol stays focused on numbering/location only, unless it intentionally owns broader structure.
7. Update this skill only if the shared numbering model changes, not merely because a new domain was added.

## Review Checklist

- Is the target path routed to the intended range?
- Has `agentos stdlib prefix next --project ... --project-name ... --target ...` been run successfully for this exact allocation?
- Does the resolved project root and declared project-name assertion match the intended artifact surface?
- Does the filename pattern use the same width as the allocator?
- Does the protocol state the exact numbering source?
- Is the minimum floor explicit?
- Is the human-vs-agent range policy explicit?
- Is the uniqueness scope explicit?
- Does the protocol explicitly allow gaps and forbid renumbering?
- Does the protocol include the exact `agentos stdlib prefix next` command when automation exists?

## Non-goals

- Do not define body templates for notes, scripts, or reports here.
- Do not introduce gap-filling or reuse semantics unless the allocator is intentionally redesigned.
- Do not treat directory-local habits as protocol until they are written in the relevant base skill or spec.
