---
name: tasks001-history
description: >
  Retrieve and synthesize the accumulated context for a task from the
  work-assistant-001 tape and the current task definition in the note file.
  Read-only — does not modify the task file or the tape.
user-invocable: true
allowed-tools: Agent, Bash(agentos tape *), Read, Glob, Grep
---

# Tasks001 History

Show what happened with a task: its current definition plus a chronological
summary of all accumulated context from the tape.

## Trigger

Use only when explicitly invoked by name (e.g., `/tasks001-history`).
Do not trigger automatically from conversational prompts.

## Workflow

### 1. Identify the task (subagent)

Launch an Agent (subagent_type: `Explore`) with the following prompt
template.  Replace `{{USER_PROMPT}}` with the relevant fragment of the
user's message:

```
You are a task-identification helper.

USER PROMPT:
{{USER_PROMPT}}

JOB:
1. Read the task note file to find all task blocks (mdblocks format).
   The file path will be provided by the invoking agent or found via
   Glob in the current vault.
2. Match the user prompt against block IDs, headings, and content.
3. Return the best-matching TASK-ID and its full block content.
4. If ambiguous, return the top 2-3 candidates with brief labels so the
   caller can ask the user to disambiguate.

OUTPUT FORMAT (plain text):
TASK-ID: <id>
BLOCK-CONTENT:
<content>
```

If the subagent returns multiple candidates, present them to the user and
ask which one they mean before proceeding.

### 2. Read the task definition

The subagent from step 1 returns the TASK-ID and block content.  Use this
as the current task definition.

### 3. Query the tape

```sh
agentos tape query \
  --tape work-assistant-001 \
  --mode best_effort \
  --jmes "[?data.task_id=='TASK-ID']"
```

Replace `TASK-ID` with the resolved task ID from step 1.
This returns only matching records from `entries` (native tape query filter).
Use `--mode best_effort` to include both committed and staged records without
running `agentos tape consolidate`.

If source provenance is needed (file + line), use:

```sh
agentos tape query \
  --tape work-assistant-001 \
  --mode best_effort \
  --with-source \
  --jmes "[?record.data.task_id=='TASK-ID']"
```

If the tape does not exist yet or returns no records for the task, skip to
step 5 and report only the current definition.

### 4. Select and condense

If there are many matching records, select the most relevant ones to keep
the summary a reasonable length.  Prefer:

- Recent records over old ones.
- Records that capture decisions, status changes, or blockers.
- Drop redundant or superseded context.

### 5. Synthesize and output

Present in chat:

1. **Current definition** — the task block content (brief).
2. **Timeline** — chronological list of tape records, each showing:
   - Date (from `created_at`)
   - Source skill / writer (from `class` and `writer`)
   - Context summary (from `data.context`)
3. **Highlights** — call out key decisions, unresolved blockers, or
   notable status changes if any stand out.

Keep the output concise.  Do not reproduce raw JSON.

## Constraints

- **Read-only.**  Do not write to the task file or append to the tape.
- **No git-ref resolution.**  Report git-refs as-is if present; do not
  diff or expand them.
- **One task per invocation.**  If the user asks about multiple tasks,
  handle them sequentially.
