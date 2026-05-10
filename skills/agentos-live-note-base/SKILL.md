---
name: agentos-live-note-base
description: Define the live-note protocol for path and filename conventions. Use when the user mentions `live-note` or needs the canonical live-note location and numbering workflow. Uses `agentos` to allocate the next live-note prefix.
---

# Agentos Live Note Base

Minimal protocol for live notes.

## Scope
- This skill defines only live-note location and naming.
- This skill does not define note body structure.
- This skill follows the current `Notes.Numbering.Protocol` direction, but does not claim the repository is fully migrated to project-wide numbering yet.

## Live Note Protocol
- Live notes must be stored in `notes/live/`.
- Canonical ordinary live-note filename pattern: `NNN-short-topic.md`.
- `NNN` must be zero-padded 3 digits.
- Numeric prefixes are stable note handles and must not be changed after assignment.
- Gaps are allowed. Do not renumber existing notes to fill gaps.

## Numbering Ranges

Agentos note numbering is moving toward a project-wide md-surface protocol:

- `000-099`: reserved notes with fixed system roles
- `100-499`: rolling index notes
- `500-999`: rolling other notes, including ordinary live notes

Live-note implications:

- Ordinary agent-created live notes should use `500-999`.
- Reserved live notes may use fixed values in `000-099`.
- Example reserved live note: `notes/live/010.TODOS.md`.
- Note numbers should be unique across the project md surface, not only inside `notes/live/`.

## Migration Status

- Current CLI allocation still scans ordinary live notes with the existing `notes/live/NNN-*.md` pattern.
- This means reserved names such as `010.TODOS.md` are intentionally outside the ordinary allocator path for now.
- Until the CLI grows project-wide note-number checks, agents should avoid creating duplicate numeric prefixes across the md surface by inspection when relevant.

## Prefix CLI
- Tool: `agentos stdlib prefix next`
- Agents can call this directly from the terminal.
- Purpose: print the next ordinary live-note prefix as 3 digits.
- Empty/no-match behavior: print `500`.
- Minimum output floor: `500`.
- Current numbering source is only files matching `notes/live/NNN-*.md`.

## Usage
Run from a repository root:

```sh
agentos stdlib prefix next --root . --include notes/live --min 500 --width 3
```

Optional target directory argument:

```sh
agentos stdlib prefix next --root /path/to/repo --include notes/live --min 500 --width 3
```
