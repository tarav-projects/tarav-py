---
name: tasks001-overview
description: >
  Read all tasks from the note file and the work-assistant-001 tape, then
  produce a prioritized summary.  Read-only.
user-invocable: true
allowed-tools: Bash(agentos tape *), Read, Glob, Grep
---

# Tasks001 Overview

"What's on my plate?" — a quick prioritized summary of all tasks.

## Trigger

Use only when explicitly invoked by name (e.g., `/tasks001-overview`).
Do not trigger automatically from conversational prompts.

## Workflow

### 1. Read the task file

Read the task note file and parse all task blocks (mdblocks format).
Extract each TASK-ID and its block content.

### 2. Query the tape

```sh
agentos tape query \
  --tape work-assistant-001 \
  --mode best_effort \
  --jmes "[?data.task_id]"
```

This keeps only entries that carry `data.task_id`.
Use `--mode best_effort` to include committed and staged records without
running `agentos tape consolidate`.

If the command fails because the tape does not exist yet, proceed with task
definitions only. If it succeeds with zero `entries`, also proceed with task
definitions only.

Group returned `entries` by `data.task_id`. For each task, select the record
with max `created_at` (do not assume input order is strictly chronological),
then note:
- That record's `created_at` (last interaction date).
- That record's `data.context` (latest context snippet).

### 3. Prioritize

For each task, determine its status from two sources:

- **Task block content** (primary): look for explicit status keywords,
  labels, or markers written by the human in the block.
- **Tape recency** (secondary): tasks with recent tape activity rank
  higher among tasks with the same status.

Sort into groups:

1. **Active / in-progress** — tasks the human has marked as current or
   that have recent tape activity.
2. **Blocked** — tasks with explicit blockers mentioned in the block or
   latest tape context.
3. **Stale** — tasks with no tape activity and no recent edits.
4. **Done / closed** — tasks marked as complete.  Omit unless the user
   asks for them.

### 4. Output

Present in chat as a concise list.  For each task:

- **TASK-ID** and title (from block heading)
- **Status** (active / blocked / stale / done)
- **One-liner** — the most relevant context: either from the block
  content or the latest tape record, whichever is more informative.

Keep the entire output scannable — aim for one line per task plus a
short summary line at the top (e.g., "5 tasks: 2 active, 1 blocked,
2 stale").

## Constraints

- **Read-only.**  Do not modify the task file or append to the tape.
- **No deep dives.**  Keep each task to one line.  For details, the user
  should invoke `/tasks001-history`.
- **No subagent.**  The file is known; read it directly.
