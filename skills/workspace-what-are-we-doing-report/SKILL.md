---
name: agentos-workspace-what-are-we-doing-report
description: Reconstruct work in progress after a crash using `notes/live` and git evidence. USE WHEN the user wants an evidence-backed snapshot of what was completed, planned, and in progress in the workspace after losing session context.
user-invocable: true
disable-model-invocation: true
---

# What Are We Doing Report

Generate an evidence-backed snapshot of the current development surface after a crash.

## Scope
- Trigger only when explicitly invoked by the user.
- Use only repository evidence from:
  - `notes/live/`
  - git state (`status`, recent commits, and commit metadata when needed)
- Do not infer intent from `src/`, `test/`, or other folders unless referenced by selected git evidence.
- Output in chat only. Do not write files.

## Workflow

### Phase 1: Gather Evidence
Run lightweight evidence collection:

1. List active live notes and recency:
   - `ls -lt notes/live`
   - include `notes/live/000-DOING.md` when present
2. Read most recent relevant live notes (typically top 3-5 non-archive files).
3. Collect git evidence:
   - `git status --short`
   - `git log --oneline -n 8 --decorate`
4. If needed to disambiguate what was just finished, inspect HEAD:
   - `git show --name-status --oneline -n 1`

### Phase 2: Reconstruct State
Use only gathered evidence to classify:

- `completed`: work clearly committed (usually latest commit(s) + matching live notes)
- `planned`: decisions captured in live notes but not yet reflected in commit/worktree state
- `in-progress`: uncommitted work in `git status` (tracked or untracked), including active live notes

When uncertain, state uncertainty explicitly and cite the exact evidence line.

### Phase 3: Report Format
Return a short report in this exact shape:

1. One short summary sentence.
2. `completed`: 1-3 bullets.
3. `planned`: 1-3 bullets.
4. `in-progress`: 1-3 bullets.
5. `evidence`: concise bullets with explicit references.

Evidence rules:
- Always include concrete references.
- Include file paths for notes, and commit hash(es) for git conclusions.
- Include dates/timestamps when available and relevant.

## Output Template

```markdown
[One-sentence status summary]

- completed: ...
- completed: ...

- planned: ...
- planned: ...

- in-progress: ...
- in-progress: ...

Evidence:
- `notes/live/NNN-topic.md` (timestamp/date)
- commit `abcdef1` (message)
- `git status --short`: `?? notes/live/NNN-topic.md`
```

## Constraints
- Keep response concise and factual.
- No speculative architecture advice.
- No implementation changes unless explicitly requested in a follow-up.
