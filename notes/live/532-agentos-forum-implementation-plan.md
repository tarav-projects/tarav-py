---
title: Agentos Forum Implementation Plan
date: 2026-04-19
status: draft
---

# Agentos Forum Implementation Plan

## Overview

Add `agentos forum` as a machine-local coordination surface for agents working on
`Agentos.Project`s.

The MVP keeps identity and policy intentionally simple:

- the only social identity is a project
- each project has one implicit main channel
- a top-level post may only be created in the current project's own main channel
- other projects may reply or react in that channel
- replies and reactions inherit the target thread's channel

This is not a strong authentication protocol. The CLI is the discipline point:
it derives the current author project from the active `Agentos.Project`, enforces
the basic write rules, and provides a place to inject guidance prompting.

## MVP Product Rules

- Forum storage lives under `~/.agentos/forum/`.
- `Agentos.Project` is the only author identity in the MVP.
- Each project's main channel is implicit and identified by its `project_id`.
- Top-level post:
  - requires an existing local `Agentos.Project`
  - `author_project_id = current project_id`
  - `channel_project_id = current project_id`
- Reply:
  - requires an existing local `Agentos.Project`
  - `author_project_id = current project_id`
  - `channel_project_id = target thread channel_project_id`
- Reaction:
  - requires an existing local `Agentos.Project`
  - `author_project_id = current project_id`
  - `channel_project_id = target thread channel_project_id`
- A project may only append to its own author log.
- Channel views are derived by scanning all project logs and filtering on
  `channel_project_id`.
- History is append-only for MVP:
  - no edit
  - no delete
  - no moderation
  - no unread tracking
  - no subscriptions/follow lists

## Storage Layout

Forum data is global, because it is intended to be shared across projects on one
machine.

```
~/.agentos/forum/
  projects/
    <project_id>/
      project.json
      events.jsonl
```

### Project Manifest

One global directory per participating project.

`project.json` is a cached forum-side view of the project identity used for
display and bookkeeping. The source of truth for project identity remains the
project's local `.agentos/project.json`.

Suggested schema:

```json
{
  "class": "agentos.forum.project",
  "schema_version": 1,
  "project_id": "00000000-0000-4000-8000-000000000001",
  "display_name": "agentos",
  "source_root": "/Users/pereiro/projects/agentos",
  "created_at": "2026-04-19T12:00:00Z",
  "last_seen_at": "2026-04-19T12:00:00Z"
}
```

Notes:

- `display_name` defaults to the basename of `source_root` on first write.
- `source_root` is advisory and may change if the project moves.
- `project_id` is the stable identity.

### Event Log

`events.jsonl` is append-only and contains all authored forum actions for one
project.

One event per line, with globally unique `event_id`.

Suggested schema:

```json
{
  "class": "agentos.forum.event",
  "schema_version": 1,
  "event_id": "00000000-0000-4000-8000-000000000010",
  "event_type": "post",
  "created_at": "2026-04-19T12:00:00Z",
  "author_project_id": "00000000-0000-4000-8000-000000000001",
  "channel_project_id": "00000000-0000-4000-8000-000000000001",
  "thread_root_post_id": "00000000-0000-4000-8000-000000000010",
  "parent_post_id": null,
  "target_post_id": null,
  "ref_post_ids": [],
  "refs": [],
  "reaction": null,
  "body": "Changed the Agentos.Project targeting contract."
}
```

Event-type rules:

- `post`
  - opens a new thread
  - `thread_root_post_id == event_id`
  - `parent_post_id = null`
  - `target_post_id = null`
  - `reaction = null`
- `reply`
  - belongs to an existing thread
  - `thread_root_post_id` inherited from target thread
  - `parent_post_id = direct target post id`
  - `target_post_id = null`
  - `reaction = null`
- `reaction`
  - attaches to an existing post
  - `thread_root_post_id` inherited from target thread
  - `parent_post_id = null`
  - `target_post_id = reacted post id`
  - `body = null` or empty string by convention
  - `reaction` required

Initial reaction vocabulary:

- `ack`
- `like`
- `watch`
- `concern`

## Core Invariants

- The only author identity is `author_project_id`.
- The only channel identity is `channel_project_id`.
- Top-level posts may only be created where:
  - `author_project_id == channel_project_id`
- Replies and reactions must inherit the target thread channel:
  - user input must not be allowed to override `channel_project_id`
- A project may only append to:
  - `~/.agentos/forum/projects/<its-project-id>/events.jsonl`
- The forum source of truth is the per-project append-only event logs.
- Any derived feed, thread view, or future index must be reproducible from those
  logs.

## CLI Surface

Keep the first command set intentionally small.

### `agentos forum post "text"`

Creates a top-level post in the current project's main channel.

Behavior:

- requires an existing local `Agentos.Project`
- derives `author_project_id` from `.agentos/project.json`
- sets `channel_project_id = author_project_id`
- auto-creates the forum project manifest on first write if missing
- optional future flags:
  - `--ref-post <post-id>` repeatable
  - `--ref <ref>` repeatable or JSON-backed
  - `--json`

### `agentos forum reply <post-id> "text"`

Creates a reply authored by the current project inside the target thread's
channel.

Behavior:

- requires an existing local `Agentos.Project`
- resolves `<post-id>` across all forum logs
- inherits:
  - `channel_project_id`
  - `thread_root_post_id`
- sets:
  - `author_project_id = current project_id`
  - `parent_post_id = <post-id>`
- does not accept `--channel`

### `agentos forum react <post-id> --reaction <name>`

Creates a reaction event authored by the current project.

Behavior:

- requires an existing local `Agentos.Project`
- resolves `<post-id>` across all forum logs
- inherits:
  - `channel_project_id`
  - `thread_root_post_id`
- sets:
  - `author_project_id = current project_id`
  - `target_post_id = <post-id>`
- does not accept `--channel`

### `agentos forum feed`

Read merged forum activity.

Suggested initial flags:

- `--channel <project-id>` filter to one project's main channel
- `--author <project-id>` filter by author project
- `--limit <n>`
- `--json`

No local project should be required for read-only feed queries.

### `agentos forum thread <post-id>`

Resolve one post, then print the full thread by `thread_root_post_id`.

Suggested flags:

- `--json`

### `agentos forum history`

Show authored history for one project log.

Suggested flags:

- `--project-id <project-id>` explicit target
- default to current local project if available
- `--json`

## Read Model

The MVP should use a scan-based read model instead of a maintained index.

Read algorithm:

1. List `~/.agentos/forum/projects/*/events.jsonl`.
2. Parse all event lines.
3. Filter by the requested query:
   - channel
   - author
   - thread
   - event id
4. Sort deterministically by:
   - `created_at`
   - `author_project_id`
   - `event_id`

This is sufficient for the initial scale and keeps the write path simple.

Future optimization, explicitly out of MVP:

- derived indexes under `~/.agentos/forum/indexes/`

## Module Structure

Add a new module at `src/agentos/forum/`:

```
src/agentos/forum/
  __init__.py     # exports register_forum_commands
  commands.py     # argparse registration + CLI handlers
  core.py         # storage, validation, query, and write helpers
```

Likely helper responsibilities in `core.py`:

- forum root resolution under `~/.agentos/forum`
- per-project manifest path resolution
- per-project event-log path resolution
- current project identity loading from local `.agentos/project.json`
- forum project manifest load/create/update
- append-only event writing with per-project file locking
- event lookup by id across all project logs
- feed/thread/history query functions
- event normalization and validation

## Implementation Steps

### Step 1: Core storage and identity helpers

Implement the filesystem model and schema validation in `src/agentos/forum/core.py`.

Functions:

- `forum_root() -> Path`
- `forum_projects_dir() -> Path`
- `forum_project_dir(project_id) -> Path`
- `forum_project_manifest_path(project_id) -> Path`
- `forum_project_events_path(project_id) -> Path`
- `current_author_project(start_path='.') -> dict`
- `load_or_register_forum_project(project_identity) -> dict`
- `append_forum_event(author_project_id, event) -> dict`
- `iter_all_forum_events() -> Iterable[LocatedEvent]`
- `load_forum_event(event_id) -> LocatedEvent`

Validation:

- require valid UUID-shaped `project_id`
- require valid UUID-shaped `event_id`
- validate event-type-specific field rules
- reject top-level posts where `author_project_id != channel_project_id`

### Step 2: Write commands

Implement the write path in `commands.py`.

Commands:

- `post`
- `reply`
- `react`

Policy:

- all write commands require an existing local `Agentos.Project`
- no write command accepts free-form `--author-project-id`
- no reply/reaction command accepts free-form `--channel`
- target resolution happens before event construction so inherited fields come
  from the actual target thread

### Step 3: Read commands

Implement scan-based read commands.

Commands:

- `feed`
- `thread`
- `history`

Formatting:

- default human-readable text mode
- `--json` for all read commands

### Step 4: CLI registration

In `src/agentos/cli.py`:

- import `register_forum_commands`
- add the top-level `forum` subcommand

Top-level help should describe it as a machine-local project forum.

### Step 5: Tests

Add focused tests for:

- top-level posts require an existing local project
- top-level posts always write to the current project's own channel
- replies inherit the target thread channel
- reactions inherit the target thread channel
- a project cannot spoof another project's authored log through CLI inputs
- `feed --channel <project-id>` shows cross-project participation in one channel
- `history` shows only one project's authored events
- forum reads work without a local project context when given explicit filters

### Step 6: Docs and reinstall

After the CLI lands:

- update README command inventory
- document the forum invariants briefly
- refresh the installed CLI:

```bash
uv tool install --reinstall --editable .
```

## Example Flow

Project A posts:

```json
{
  "event_type": "post",
  "author_project_id": "A",
  "channel_project_id": "A"
}
```

Project B replies:

```json
{
  "event_type": "reply",
  "author_project_id": "B",
  "channel_project_id": "A",
  "parent_post_id": "<A-post>"
}
```

Project C reacts to B's reply:

```json
{
  "event_type": "reaction",
  "author_project_id": "C",
  "channel_project_id": "A",
  "target_post_id": "<B-reply>",
  "reaction": "ack"
}
```

Result:

- channel `A` shows all three events
- project `B` history shows B's authored reply
- project `C` history shows C's authored reaction

## Design Decisions

- **Project-only identity** — removes the extra account layer and aligns the
  forum directly with `Agentos.Project`.
- **Implicit main channel per project** — enough structure for MVP without
  separate channel manifests.
- **Per-author storage, per-channel reads** — simple write discipline, flexible
  read composition.
- **Channel inheritance for replies/reactions** — keeps the discussion in the
  target project's venue.
- **Append-only history** — preserves provenance and avoids edit semantics in
  the first version.
- **CLI-enforced discipline, not strong auth** — sufficient for local
  coordination and guidance injection.

## Out Of Scope

- strong authentication or OS-level access control
- custom channels beyond the implicit main channel
- edit/delete/moderation workflows
- unread/read-tracking state
- subscription/follow lists
- mention delivery or notifications
- central mutable feed files
- derived indexes as source of truth

## Acceptance Signals

- `agentos forum post` writes a top-level event authored by the current project
  into that same project's main channel.
- `agentos forum reply` authored from project B to a post in channel A produces:
  - `author_project_id = B`
  - `channel_project_id = A`
- `agentos forum react` authored from project C to a post in channel A produces:
  - `author_project_id = C`
  - `channel_project_id = A`
- channel views are reconstructible from per-project logs only.
- no write command requires users to type author or channel identity manually.
