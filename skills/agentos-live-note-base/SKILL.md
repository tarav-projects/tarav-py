---
name: agentos-live-note-base
description: Define the live-note protocol for path and filename conventions. USE WHEN the user mentions `live-note` or needs the canonical live-note location and numbering workflow. Uses `agentos` to allocate the next live-note prefix.
---

# Agentos Live Note Base

Minimal protocol for live notes.

This is a `Batchy.Skill`. Load `agentos-batchy-skills` for the full convention.

- `-h` / `--help` prints this skill's help into the chat instead of running; it takes no arguments.

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

- Current CLI allocation is project-aware through `agentos stdlib prefix next --project --project-name <declared-project-name> --target notes/live`.
- The default project prefix policy scans numbered Agentos surfaces under `notes` and `dev/live`, then allocates from the rolling `500-999` route for `notes/live`.
- Reserved names such as `010.TODOS.md` are manually assigned fixed-role prefixes. They are part of the numbering system but not ordinary allocator output.
- Full consistency checks for duplicate numeric prefixes, range violations, and reserved-prefix drift are future `prefix doctor` or equivalent work.

## Prefix CLI
- Tool: `agentos stdlib prefix next`
- Agents can call this directly from the terminal.
- Purpose: print the next ordinary live-note prefix as 3 digits.
- Empty/no-match behavior: print `500`.
- Allocation route: `500-999`.
- Target: `notes/live`.
- Default project scan scope: `notes` and `dev/live`.
- If `agentos stdlib prefix` fails, stop and ask the user how to resolve the project target. Do not assign a live-note prefix by manual inspection.

## Usage
Preferred project target, when the caller is inside the intended project tree:

```sh
agentos stdlib prefix next --project --project-name <declared-project-name> --target notes/live
```

Explicit project path target, when the caller is outside the intended project tree:

```sh
agentos stdlib prefix next --project /path/to/project --project-name <declared-project-name> --target notes/live
```

In nested workspaces or sibling repositories, do not use `--project .` unless `.` is the actual initialized project root. Use `--project-name` so allocation fails if the wrong project marker was resolved.
