---
name: agentos-live-scripts-base
description: Define the live-scripts protocol for path and filename conventions under `dev/live`. Use when the user mentions `live-scripts`, or when proposing, creating, or reviewing rolling interface/design scripts used as product-surface drafts in any project language or runtime.
---

# Agentos Live Scripts Base

Minimal protocol for live scripts.

## Scope
- Define only live-script location and naming.
- Do not define script body/content structure.
- Do not assume a specific programming language.
- Treat runnable status as optional: scripts may run, but this is not required.

## Live Script Protocol
- Store live scripts in `dev/live/`.
- Canonical filename pattern: `NNN-short-topic.<ext>`.
- `NNN` must be zero-padded 3 digits.
- Use the extension that matches the project language or execution model.
- Numbering source is only files matching the `NNN-` live-script prefix in `dev/live/`.
- Prefix range `000-499` is reserved for direct human management.

## Archive
- `dev/live/archive/` may be used as an archive location for rolled scripts.
- Archive usage is optional and intentionally outside strict protocol enforcement.

## Prefix CLI
- Tool: `agentos prefix next`
- Agents can call this directly from the terminal.
- Purpose: print the next live-script prefix as 3 digits.
- Empty/no-match behavior: print `500`.
- Minimum output floor: `500`.

## Usage
Run from a repository root:

```sh
agentos prefix next --root . --include dev/live --min 500 --width 3
```

Optional target directory argument:

```sh
agentos prefix next --root /path/to/repo --include dev/live --min 500 --width 3
```
