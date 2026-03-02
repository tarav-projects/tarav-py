---
name: tasks001-discuss
description: >
  Open a focused discussion about a specific task.  At explicit checkpoints
  the agent appends a context summary to the work-assistant-001 tape.
user-invocable: true
allowed-tools: Agent, Bash(agentos tape *), Read, Glob, Grep
---

# Tasks001 Discuss

Free-form discussion about a task with explicit checkpoint-to-tape support.

## Trigger

Use only when explicitly invoked by name (e.g., `/tasks001-discuss`).
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

### 2. Load tape context

Query existing records for this task:

```sh
agentos tape query \
  --tape work-assistant-001 \
  --mode best_effort \
  --jmes "[?data.task_id=='TASK-ID']"
```

Replace `TASK-ID` with the resolved task ID from step 1.
This applies native filtering on `entries`.
Use `--mode best_effort` to include committed and staged records without
running `agentos tape consolidate`.

Briefly review the returned `entries` to build background context.
Do not present them to the user unless asked — this is internal context
for the agent.

If the command fails because the tape does not exist yet, proceed without
prior context. If it succeeds with zero `entries`, also proceed without
prior context.

### 3. Discuss

Engage in free conversation about the task.  The agent has the task
definition and accumulated tape context loaded.  No format constraints —
follow the user's lead.

### 4. Checkpoint (explicit, user-approved)

Only when the user explicitly says "checkpoint", "save this", or similar:

1. **Draft the context text.**  Distill the discussion into a concise
   summary capturing: decisions made, open questions, blockers, and any
   other notable context.
2. **Show the draft to the user.**  Present the exact `context` text that
   will be appended and wait for approval.  Do not append until the user
   confirms.
3. **Append to the tape** after approval:

```sh
agentos tape append \
  --tape work-assistant-001 \
  --writer-id tasks001-discuss \
  --class tasks001-discuss \
  --data-json '{"task_id": "TASK-ID", "context": "APPROVED_CONTEXT_TEXT"}' \
  --init \
  --init-tape-name work-assistant-001
```

Use `--init` so the tape is created on first write if it does not exist.
Ensure `--data-json` is valid JSON (escape quotes/newlines in context text).
If escaping is cumbersome, write JSON to a file and use `--data-file`.

4. Confirm to the user that the record was appended.

Multiple checkpoints in a single session are allowed.

### 5. Exit

The discussion ends when the user moves on, says "done", or invokes
another skill.  No automatic checkpoint on exit — only explicit
checkpoints are persisted.

## Constraints

- **Task file is read-only.**  Do not modify the task note file (use
  `tasks001-update` for that).
- **Never auto-checkpoint.**  Only append to the tape when the user
  explicitly requests it.
- **Always show before appending.**  The user must see and approve the
  context text before it reaches the tape.
- **One task per session.**  If the user wants to discuss a different task,
  re-invoke the skill.
