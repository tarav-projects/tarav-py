---
name: agentos-index-mdblock-base
description: Define the shared Agentos index-mdblock format and note-taking philosophy. Use when the user mentions `index-mdblock`, when deciding what an index-mdblock is, when applying that structure outside `notes/index/`, or when extracting the block concept from domain-specific systems such as `agentos-index-notes-*`.
---

# Agentos Index Mdblock Base

Minimal base spec for the index-mdblock format.

## Scope

- Define what an index-mdblock is.
- Define the note-taking philosophy behind the format.
- Define the generic structural expectations.
- Do not define storage paths, numbering, or filename conventions.
- Do not define any domain-specific workflow.

## Core Idea

- Files are containers. Blocks are the portable unit of meaning.
- An index block is a small, self-contained markdown section that carries one steering idea.
- An index-mdblock, historically called an index block, is the portable unit.
- The format was first formalized for index notes, but it is not limited to index notes.
- An index note is one application of the index-mdblock format, not the definition of the format itself.
- A block can live in any markdown document if that document wants the same high-signal, movable note style.

## Format

- Represent one block as one heading-scoped markdown section.
- Keep one primary idea per block.
- Prefer bullet-point structured text over long prose.
- Keep it small; target `<30` lines unless there is a clear reason not to.
- Make it self-contained enough to move between files without rewriting its meaning.
- Prefer decisions, constraints, patterns, definitions, and anti-patterns over narrative explanation.

## Philosophy

- High signal over completeness.
- Low friction capture: write first, reorganize later.
- Portability: moving a block between files should not change what it means.
- Container independence: storage location helps retrieval, but does not define the block format.
- Additive maintenance: improve wording, placement, and grouping incrementally.

## Generic Uses

- Curated design indexes.
- Live design notes.
- Architecture constraint notes.
- Steering sections inside larger specs.
- Small portable knowledge blocks extracted from longer documents.

## Relation To Domain Base Skills

- Domain `base` skills may add:
  - storage location
  - filename conventions
  - numbering rules
  - retrieval conventions
- Domain skills must not redefine the core meaning of `index-mdblock` unless they are intentionally evolving this shared base spec.
- If the shared concept changes, update this skill first and then simplify the domain skills to reference it.

## Non-goals

- Do not treat this as a full document format.
- Do not treat this as a numbering protocol.
- Do not limit the format to `notes/index/`.
- Do not equate every markdown heading section with an index block; the section must follow the high-signal portable-block philosophy.
