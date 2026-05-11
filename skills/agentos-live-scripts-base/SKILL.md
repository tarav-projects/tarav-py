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

- Current CLI allocation is project-aware through `agentos stdlib prefix next --project --project-name <declared-project-name> --target dev/live`.
- The default project prefix policy scans numbered Agentos surfaces under `notes` and `dev/live`, then allocates from the rolling `500-999` route for `dev/live`.
- Full consistency checks for duplicate numeric prefixes, range violations, and reserved-prefix drift are future `prefix doctor` or equivalent work.

## Archive
- `dev/live/archive/` may be used as an archive location for rolled scripts.
- Archive usage is optional and intentionally outside strict protocol enforcement.

## Prefix CLI
- Tool: `agentos stdlib prefix next`
- Agents can call this directly from the terminal.
- Purpose: print the next ordinary live-script prefix as 3 digits.
- Empty/no-match behavior: print `500`.
- Allocation route: `500-999`.
- Target: `dev/live`.
- Default project scan scope: `notes` and `dev/live`.
- If `agentos stdlib prefix` fails, stop and ask the user how to resolve the project target. Do not assign a live-script prefix by manual inspection.

## Usage
Preferred project target, when the caller is inside the intended project tree:

```sh
agentos stdlib prefix next --project --project-name <declared-project-name> --target dev/live
```

Explicit project path target, when the caller is outside the intended project tree:

```sh
agentos stdlib prefix next --project /path/to/project --project-name <declared-project-name> --target dev/live
```

In nested workspaces or sibling repositories, do not use `--project .` unless `.` is the actual initialized project root. Use `--project-name` so allocation fails if the wrong project marker was resolved.
