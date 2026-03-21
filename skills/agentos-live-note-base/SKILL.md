---
name: agentos-live-note-base
description: Define the live-note protocol for path and filename conventions. Use when the user mentions `live-note` or needs the canonical live-note location and numbering workflow. Uses `agentos` to allocate the next live-note prefix.
---

# Agentos Live Note Base

Minimal protocol for live notes.

## Scope
- This skill defines only live-note location and naming.
- This skill does not define note body structure.

## Live Note Protocol
- Live notes must be stored in `notes/live/`.
- Canonical filename pattern: `NNN-short-topic.md`.
- `NNN` must be zero-padded 3 digits.
- Numbering source is only files matching `notes/live/NNN-*.md`.
- Prefix range `000-499` is reserved for direct human management.

## Prefix CLI
- Tool: `agentos prefix next`
- Agents can call this directly from the terminal.
- Purpose: print the next live-note prefix as 3 digits.
- Empty/no-match behavior: print `500`.
- Minimum output floor: `500`.

## Usage
Run from a repository root:

```sh
agentos prefix next --root . --include notes/live --min 500 --width 3
```

Optional target directory argument:

```sh
agentos prefix next --root /path/to/repo --include notes/live --min 500 --width 3
```
