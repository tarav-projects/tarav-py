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
- This skill follows the current Agentos numbered-surface direction, but does not claim the repository is fully migrated to project-wide numbering checks yet.

## Live Script Protocol
- Store live scripts in `dev/live/`.
- Canonical ordinary live-script filename pattern: `NNN-short-topic.<ext>`.
- `NNN` must be zero-padded 3 digits.
- Use the extension that matches the project language or execution model.
- Numeric prefixes are stable handles and must not be changed after assignment.
- Gaps are allowed. Do not renumber existing scripts to fill gaps.

## Numbering Ranges

Agentos numbered surfaces are moving toward stable project-level ranges:

- `000-099`: reserved fixed-role surfaces
- `100-499`: rolling index notes
- `500-999`: rolling other numbered surfaces, including ordinary live scripts

Live-script implications:

- Ordinary agent-created live scripts should use `500-999`.
- Reserved fixed-role live scripts, if introduced, may use `000-099`.
- Live-script numbers should avoid collisions with other project numbered surfaces when they are used as shared handles.

## Migration Status

- Current CLI allocation still scans ordinary live scripts with the existing `dev/live/NNN-*` pattern.
- Until the CLI grows broader project-level checks, agents should avoid obvious duplicate numeric prefixes by inspection when relevant.

## Archive
- `dev/live/archive/` may be used as an archive location for rolled scripts.
- Archive usage is optional and intentionally outside strict protocol enforcement.

## Prefix CLI
- Tool: `agentos prefix next`
- Agents can call this directly from the terminal.
- Purpose: print the next ordinary live-script prefix as 3 digits.
- Empty/no-match behavior: print `500`.
- Minimum output floor: `500`.
- Current numbering source is only files matching the `NNN-` live-script prefix in `dev/live/`.

## Usage
Run from a repository root:

```sh
agentos prefix next --root . --include dev/live --min 500 --width 3
```

Optional target directory argument:

```sh
agentos prefix next --root /path/to/repo --include dev/live --min 500 --width 3
```
