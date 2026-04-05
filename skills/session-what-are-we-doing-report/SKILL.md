---
name: session-what-are-we-doing-report
description: Reconstruct the current session from chat history and brief the user on what we are doing, why, how, what is already done, and what comes next. USE WHEN the user asks for a refresh like "what were we doing", "catch me up", "session recap", or "I forgot what I was doing", and wants a concise current-session briefing based only on prior chat evidence.
---

# Session What Are We Doing Report

## Goal
Rebuild current session state from chat history and return an in-chat briefing in either `large` or `short` mode.

## Modes
This skill supports two output modes:
- `large`: structured recap with bullets and explicit evidence references (the current behavior).
- `short` (default): one-paragraph recap for quick context recovery.

Mode selection:
- If the user explicitly asks for "short", "brief", "one paragraph", "quick recap", or similar, use `short`.
- If the user explicitly asks for "large", "full", "detailed", or similar, use `large`.
- If the user does not specify a mode, default to `short`.

## Evidence Priority
Use only session-scoped evidence from the current chat.

Rank evidence in this order:

1. user messages:
   - requests
   - corrections
   - constraints
   - approvals
   - explicit goals and rationale
2. explicitly confirmed generated responses:
   - assistant statements, tool results, or generated outputs only when the user clearly accepted, adopted, or acted on them in the session
3. tool actions/results that directly support an already-relevant session fact
4. file evidence only for files explicitly mentioned in this same session, when needed to clarify status

Treat these as weak evidence and usually ignore them:

- assistant framing that was never confirmed
- speculative suggestions that were not adopted
- progress chatter
- repeated restatements
- abandoned branches

Do not default to repository-wide analysis. Only inspect files that are explicitly referenced in the current session.

## Significant Session Evidence

Only keep evidence that changes the user's current briefing. Prefer items that establish:

- what the current objective is
- why the user wants it
- how the work is supposed to proceed
- what has already been completed
- what changed direction
- what remains next

Ignore trivial detours unless they materially changed the current direction.

## Workflow

### 1. Gather session context
1. Read the visible conversation history for this session.
2. Extract and rank:
   - latest user objective
   - explicit user rationale
   - explicit user-approved method or workflow
   - actions already completed
   - requested changes or corrections
   - work that is still pending
3. Collect only explicitly mentioned file paths from the session.
4. If a file mention is relevant to the recap, read only the minimum needed content from that file.
5. Ignore unconfirmed assistant suggestions, speculative framing, and progress chatter.

### 2. Reconstruct state
Reconstruct strictly from session evidence:

- `what`: the current objective or active task
- `why`: the stated reason, motivation, or user goal
- `how`: the agreed method, workflow, or constraints
- `done`: actions already completed in this session
- `next`: the latest pending or active next step

Use these rules:

- The latest accepted direction overrides earlier superseded plans.
- If `why` or `how` are not explicitly supported by the session, say that briefly instead of inferring.
- When uncertain, state uncertainty explicitly and cite the relevant session evidence.

Also derive a one-sentence session title that names the current session focus. The title should be specific to the active task (not generic like "Session recap").

### 3. Select mode
Choose `large` or `short` using the mode-selection rules above before writing the report.

### 4. Report format

#### `large` mode
Output only chat text in this shape:
1. One-sentence session title (top line).
2. One short summary sentence.
3. `what`: 1-2 bullets.
4. `why`: 1-2 bullets.
5. `how`: 1-2 bullets.
6. `done`: 1-3 bullets.
7. `next`: 1-3 bullets.
6. `Evidence:` concise bullets with message-based references.

Template:

```markdown
[One-sentence session title]

[One-sentence status summary]

- what: ...
- what: ...

- why: ...
- why: ...

- how: ...
- how: ...

- done: ...
- done: ...

- next: ...
- next: ...

Evidence:
- user: "<relevant request or confirmation>"
- confirmed generated response: "<accepted assistant/tool/generated result>"
- tool/output: "<relevant result>" (if used)
- file: `<path>` (only if explicitly mentioned in this session)
```

#### `short` mode (default)
Output only:
1. One-sentence session title (top line).
2. Exactly one paragraph recap (no bullets, no heading, no separate `Evidence:` section).

The paragraph should cover, in compact form:
- what we are doing
- why we are doing it, if explicitly supported
- how we are doing it, if explicitly supported
- what has already been completed, if anything
- what comes next or what the latest user request changed
- any uncertainty or blocker (if present)

Keep it factual and grounded in session evidence. If uncertain, say so explicitly in the paragraph.

## Constraints
- Keep output concise, factual, and evidence-backed.
- Weight user messages highest.
- Use generated responses only when explicitly confirmed or clearly adopted in-session.
- Default to `short` unless the user asks for `large` or another explicitly detailed recap.
- Every mode must start with a one-sentence session title on the first line.
- `short` mode body must be exactly one paragraph.
- `large` mode uses the structured bullets + `Evidence:` format.
- Output in chat only. Do not write files.
- Do not run repository-wide discovery or broad git analysis by default.
- File inspection is allowed only for paths explicitly mentioned in this session.
- Do not infer rationale, workflow, or intent beyond what the session supports.
- Do not propose speculative architecture advice.
