---
name: session-status
description: "Reconnect the user with the current session state. Maintains a session todo list and provides context on what's happening and what's next. USE WHEN the user says 'status', 'catch me up', 'what are we doing', 'what's next', 'anything left', 'what's missing', or similar reconnect requests."
---

# Session Status

## Goal

Reconnect the user with the current session state. Maintain a running todo list of session work items and provide enough context to resume focus quickly.

This skill is a **semantic guide**, not a rigid template. The user may append directions after invocation (e.g., `/session-status what's left?`) — adapt the output weight accordingly.

## Evidence Rules

Use only session-scoped evidence from the current chat.

Rank evidence in this order:

1. **User messages**: requests, corrections, constraints, approvals, goals, rationale.
2. **Confirmed responses**: assistant output the user clearly accepted, adopted, or acted on.
3. **Tool actions/results** that directly support an already-relevant session fact.
4. **File evidence** only for files explicitly mentioned in this session, when needed to confirm status.

Ignore:
- Unconfirmed assistant framing or speculative suggestions.
- Progress chatter and repeated restatements.
- Abandoned branches that never changed direction.

Do not default to repository-wide analysis. Only inspect files explicitly referenced in the session.

## Session Todo List

The todo list is the core persistent object of this skill within a conversation.

### First invocation
- Scan the full session history.
- Extract work items: things the user asked for, agreed to, or that emerged from accepted plans.
- Build the initial todo list and output it.
- Be explicit that this is a reconstructed list ("Here's what I reconstructed from our session").

### Subsequent invocations
- Tend the existing list: mark items done, add new items, adjust scope.
- Do not rebuild from scratch — evolve the list.

### What counts as a work item
- Explicit user requests or tasks.
- Agreed-upon steps from accepted plans.
- Blockers or issues that need resolution.

Name items by intent ("Design the session-status skill"), not by implementation detail ("Read SKILL.md files and discuss merge").

### What does NOT count
- **Commit cycles** — excluded by default. "We should commit" is infrastructure, not a work item. Only include if the user explicitly treats it as a task.
- Meta-tasks about the conversation itself.
- Speculative ideas that were never adopted.

### Item states
Keep it simple:
- **done**: completed in this session.
- **open**: not yet completed.

## Default Output Shape

```
[Session title — one line]

## Todo
- [x] done item — brief description
- [x] done item — brief description
- [ ] open item — brief description → next action
- [ ] open item — brief description → next action

## Context
- what/why bullet
- current focus bullet
- suggestion: [optional — agent may propose new tasks based on session direction]
```

### Output rules
- **Session title**: one specific line naming the current focus, under 10 words. Not generic.
- **Todo list**: done items first (recent/relevant ones for historical reference), then open items. Each open item ends with a concrete next action after `→`.
- **Context section**: 2-4 bullet-point sentences covering what we're doing, why, and current focus. The agent may suggest new tasks here — these are proposals, not commitments.
- **Empty sections**: if there are no done items or no open items, omit that part of the list rather than showing an empty section.

## Adapting to User Direction

The user may steer the output by appending text after invocation:

- `/session-status` → default: todo list + context
- `/session-status what are we doing?` → heavier on context, lighter on audit
- `/session-status what's left?` → skip context, focus on open items
- `/session-status detailed` → full breakdown: include evidence references, expand done items, elaborate on blockers

The skill defines intent and evidence rules. The format flexes.

## Constraints

- Keep output concise, factual, and evidence-backed.
- Weight user messages highest.
- Bullet points over paragraphs.
- Do not write files or modify the repository.
- Do not run repository-wide discovery or broad git analysis.
- Do not infer rationale beyond what the session supports. State uncertainty explicitly.
- Commit cycles are excluded from the todo list by default.
