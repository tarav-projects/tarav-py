---
name: agentos-file-numbering-base
description: Define, review, or extend Agentos numeric filename protocols and prefix allocation workflow. Use when adding a new numbered artifact type, checking which files determine the next `NNN-` prefix, deciding prefix floors or reserved ranges, or verifying whether gaps and renumbering are allowed.
---

# Agentos File Numbering Base

Minimal protocol for Agentos-managed numeric filename workflows.

## Scope

- Define shared numbering mechanics, not document body structure.
- Centralize how `agentos stdlib prefix next` relates to numbered artifact protocols.
- Define only the base numbering rules that domain-specific `base` skills inherit.

## Shared Numbering Rules

- Canonical numbered filename shape is `NNN-short-topic.ext`.
- `NNN` is zero-padded to a fixed width, currently `3`.
- Numeric prefixes are stable handles, so the meaningful title may change while the number remains fixed.
- A numbering domain is defined by:
  - the scan root include path
  - the filename pattern matched by the allocator
  - the minimum floor
  - any reserved prefix range policy
  - whether numbers must be unique only inside the domain or across a broader project surface
- The numbering source is only the files inside that domain that match the configured `NNN-` prefix pattern.

## Allocator Behavior

- `agentos stdlib prefix next` scans files under the requested `--include` paths.
- It extracts prefixes using the filename regex `^(\d{width})-`.
- It ignores files that do not begin with a valid zero-padded numeric prefix.
- It returns:
  - `minimum` if no eligible prefixes exist
  - otherwise `max(existing eligible prefixes) + 1`
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
  - numbering source
  - floor or reserved range
  - uniqueness scope
  - exact `agentos stdlib prefix next` command, if allocation is automated
- This skill owns only the shared numbering semantics that all those domain skills inherit.

## Cross-Domain Coordination

- Some systems need numbers to be unique across a broader surface than one folder.
- Example: Agentos notes are moving toward project-wide md-surface uniqueness, where the same note number should not identify different notes in different note folders.
- Current `agentos stdlib prefix next` behavior is still include-path based. Until a domain has project-wide allocation/checking support, domain skills should document any broader uniqueness expectation and require inspection or deterministic checks when relevant.

## Workflow For A New Numbered Artifact Type

1. Decide the domain root and canonical filename extension.
2. Decide whether the domain is human-managed, agent-managed, or split by range.
3. Pick a minimum floor and any reserved range policy.
4. Define the numbering source as a concrete glob-like file family, for example `notes/live/NNN-*.md`.
5. Add a domain base protocol skill or base spec that states:
   - location
   - filename pattern
   - numbering source
   - floor or reserved range
   - uniqueness scope
   - exact `agentos stdlib prefix next` command, if allocation is automated
   - stability rule: gaps allowed, no renumbering
6. Ensure the domain protocol stays focused on numbering/location only, unless it intentionally owns broader structure.
7. Update this skill only if the shared numbering model changes, not merely because a new domain was added.

## Review Checklist

- Is the include path narrow enough to avoid cross-domain collisions?
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
