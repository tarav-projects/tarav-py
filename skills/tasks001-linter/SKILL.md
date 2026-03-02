---
name: tasks001-linter
description: >
  Read the task note file and report formatting problems against the
  expected mdblocks task conventions.  Read-only, no fixes applied.
user-invocable: true
allowed-tools: Bash(agentos mdblocks *), Read, Glob, Grep
---

# Tasks001 Linter

Lint the task note file and report formatting issues in chat.

## Trigger

Use only when explicitly invoked by name (e.g., `/tasks001-linter`).
Do not trigger automatically from conversational prompts.

## Workflow

### 1. Run agentos mdblocks lint

Run the structural linter on the task note file first:

```sh
agentos mdblocks lint <task-file-path>
```

Collect its output — this catches structural mdblocks issues such as
malformed separators, oversized blocks, and other format violations.

### 2. Read the task file

Read the task note file and identify all task blocks for task-specific
checks that go beyond what `agentos mdblocks lint` covers.

### 3. Task-specific checks

Check every task block for:

- **Missing TASK-ID** — block has no identifiable ID in the heading.
- **Duplicate TASK-ID** — two or more blocks share the same ID.
- **Empty block** — heading present but no content below it.
- **Inconsistent structure** — blocks that deviate from the dominant
  pattern used by the majority of other blocks in the file (e.g., most
  blocks have a status line but one does not).

### 4. Report

Present findings in chat, combining results from both passes:

- **Summary line** — e.g., "12 blocks checked, 3 issues found."
- **Structural issues** (from `agentos mdblocks lint`) — listed first.
- **Task-specific issues** (from in-agent checks) — listed after.
- Each issue shows:
  - TASK-ID (or "unknown" if missing)
  - Line number or approximate location
  - Brief description of the problem
- If no issues found, say so.

## Constraints

- **Read-only.**  Do not modify the task file.
- **No fixes.**  Report only.  The user decides what to change.
