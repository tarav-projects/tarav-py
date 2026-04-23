---
title: Mission Control Implementation Plan
date: 2026-04-12
status: draft
---

# Mission Control Implementation Plan

## Overview

Add `agentos mission` subcommand — a coordination surface for named blocks of work with goal, validation, todos, and freeform notes. See index note `003-Agentos.Mission.md` for concept and design.

## Storage Layout

Missions live in `.agentos/missions/` (project-scoped, requires agentos project).

```
.agentos/missions/
  auth-rewrite.mission.json # one file per mission
```

### Mission File Schema

```json
{
  "class": "agentos.mission",
  "schema_version": 1,
  "name": "auth-rewrite",
  "goal": "Replace session auth with JWT",
  "validation": "All tests pass + JWT integration tests green",
  "status": "active",
  "created": "2026-04-12T10:00:00Z",
  "last_activity": "2026-04-12T10:00:00Z",
  "finished": null,
  "todos": [
    {"text": "swap middleware", "done": false},
    {"text": "write integration tests", "done": false}
  ],
  "notes": [
    "Related to rate-limiter mission — shares the middleware layer",
    "Plan lives in live-notes/auth-plan"
  ]
}
```

## Module Structure

New module at `src/agentos/mission/`:

```
src/agentos/mission/
  __init__.py     # exports register_mission_commands
  commands.py     # CLI handlers + argparse registration
  core.py         # business logic (load, save, list, mutate)
```

## Implementation Steps

### Step 1: Core logic (`core.py`)

Data access layer — no CLI concerns.

Functions:

- `missions_dir(project_root) -> Path` — returns `.agentos/missions/`, creates if needed
- `mission_path(project_root, name) -> Path` — returns path for a named mission file
- `load_mission(project_root, name) -> dict` — read + validate a mission file
- `save_mission(project_root, mission) -> None` — write mission file
- `list_missions(project_root) -> list[dict]` — load all missions
- `create_mission(project_root, name, goal, validation) -> dict` — create + save new mission
- `resolve_mission_name(project_root, name | None) -> str` — if name is None, use the most recently active mission; error if none

Validation:
- Mission name: kebab-case, filesystem-safe (reuse `validate_string_for_path`)
- Status: must be one of `active`, `done`, `parked`
- No duplicate mission names

### Step 2: CLI commands (`commands.py`)

Follow existing patterns (`prefix/commands.py` as template).

#### `agentos mission new <name> --goal "..." --validation "..."`
- Creates mission file with status `active`
- Does NOT auto-activate (user decides)
- `--json` flag for structured output

#### `agentos mission activate <name>`
- Marks the mission as recently active
- Sets status to `active`
- Mission must exist
- `--json` flag

#### `agentos mission status [name]`
- If no name: show the most recently active mission
- If name given: show that mission
- Prints goal, validation, status, todos (with indices), notes
- `--json` flag dumps the full mission object

#### `agentos mission done [name]`
- Resolves name (or most recent active)
- Sets status to `done`, sets `finished` timestamp
- `--json` flag

#### `agentos mission park [name]`
- Resolves name (or most recent active)
- Sets status to `parked`
- `--json` flag

#### `agentos mission list`
- Shows all missions grouped by status and ranked by `last_activity`
- Columns: name, status, goal (truncated), todo progress (e.g. 2/5)
- `--json` flag

#### `agentos mission todo add "text"`
- Appends to most recent active (or `--mission <name>`) mission's todos
- `--json` flag

#### `agentos mission todo done <index>`
- Marks todo at 1-based index as done
- `--json` flag

#### `agentos mission note "text"`
- Appends to most recent active (or `--mission <name>`) mission's notes
- `--json` flag

#### `agentos mission fork "text" [--as-mission <name>]`
- If `--as-mission`: creates new mission with the text as goal, adds a note on current mission linking them
- If no flag: just adds a note prefixed with `FORK:` to current mission
- `--json` flag

### Step 3: CLI registration

In `cli.py`:
- Import `register_mission_commands` from `agentos.mission`
- Add `register_mission_commands(subparsers)` call

### Step 4: Reinstall

```bash
uv tool install --reinstall --editable .
```

## Output Format (text mode)

### `mission status` example output:

```
mission: auth-rewrite [active]
goal:    Replace session auth with JWT
check:   All tests pass + JWT integration tests green
last:    2026-04-12T10:15:00Z

todos:
  1. [ ] swap middleware
  2. [x] write integration tests

notes:
  - Related to rate-limiter mission — shares the middleware layer
  - Plan lives in live-notes/auth-plan
```

### `mission list` example output:

```
active (most recent first):
  auth-rewrite    Replace session auth with JWT              [2/3 todos]  [last 2026-04-12]

parked:
  rate-limiter    Rework rate limiting middleware             [0/1 todos]  [last 2026-04-11]

done:
  setup-ci        Configure CI pipeline                      [done 2026-04-10]
```

## Design Decisions

- **Project-scoped only** — missions require an agentos project. No global missions.
- **No structured relations** — relations are just notes text. Keeps the system simple.
- **1-based todo indexing** — matches human-friendly display.
- **`fork` is sugar** — it's just `note` + optionally `new`. Could be removed without losing capability.
- **Multiple active missions** — there is no singleton active-mission pointer; commands default to the most recently active open mission.
- **`--json` everywhere** — consistent with all other agentos subcommands for agent consumption.
