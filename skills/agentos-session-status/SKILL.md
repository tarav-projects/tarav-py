---
name: agentos-session-status
description: "Reconnect the user with the current session state. Maintains a session todo list and provides context on what's happening and what's next. USE WHEN the user says 'status', 'catch me up', 'what are we doing', 'what's next', 'anything left', 'what's missing', or similar reconnect requests."
---

# Session Status

## Goal

Reconnect the user with the current session state. Maintain a running todo list of session work items and provide enough context to resume focus quickly.

This skill is a **semantic guide**, not a rigid template. The user may append directions after invocation (e.g., `/agentos-session-status what's left?`) — adapt the output weight accordingly.

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

Name items by intent ("Design the agentos-session-status skill"), not by implementation detail ("Read SKILL.md files and discuss merge").

### What does NOT count
- **Commit cycles** — excluded by default. "We should commit" is infrastructure, not a work item. Only include if the user explicitly treats it as a task.
- Meta-tasks about the conversation itself.
- Speculative ideas that were never adopted.

### Item states
Keep it simple:
- **done**: completed in this session.
- **open**: not yet completed.
- **suggested**: agent-proposed task derived from session direction. The agent may add these to the list when the session naturally points toward a next step. These are proposals, not commitments — the user accepts them by acting on them.

## Default Output Shape

```
[Session title — plain text, no markdown]

## Todo
- [x] done item — brief description
- [ ] open item — brief description → next action
- [ ] suggested: derived task → next action

## Context
- one sentence bullet
- one sentence bullet
```

### Format rules
- **Session title**: plain text line, under 10 words, naming the current focus. No `**bold**`, no `#` heading, no markdown formatting. Brackets optional.
- **Checkboxes only**: done items use `- [x]`, open/suggested use `- [ ]`. No other bullet styles in the todo list.
- **Item shape**: `short name — brief description` for done items. `short name — brief description → next action` for open/suggested. The em dash `—` separates name from description. The arrow `→` separates description from next action. Every open/suggested item MUST have a `→` clause — if you can't name a next action, the item isn't concrete enough to list.
- **One line per item**: no nested bullets, no multi-line items. If it needs two lines to explain, it's too detailed.
- **Whitespace**: blank line between title and `## Todo`, blank line between `## Todo` and `## Context`. No blank lines between list items.
- **Empty sections**: if there are no done items or no open items, omit that part of the list rather than showing an empty section.

### Done item pruning
- Show at most 3–5 recent done items that inform current work.
- Prune older completions that no longer matter for what's next.
- The todo list is a status tool, not a changelog or session history.

### Context rules
- 2–4 bullets, one sentence each, max.
- Cover what/why/where-we-are. No implementation details.

### Anti-pattern: session-as-history
The todo list reflects **current state**, not session history. Do not reconstruct the full arc of work done in the session. A reader should understand what's live and what's next in under 10 seconds.

## Adapting to User Direction

The user may steer the output by appending text after invocation:

- `/agentos-session-status` → default: todo list + context
- `/agentos-session-status what are we doing?` → heavier on context, lighter on audit
- `/agentos-session-status what's left?` → skip context, focus on open items
- `/agentos-session-status detailed` → full breakdown: include evidence references, expand done items, elaborate on blockers

The skill defines intent and evidence rules. The format flexes.

## Constraints

- Keep output concise, factual, and evidence-backed.
- Weight user messages highest.
- Bullet points over paragraphs.
- Do not write files or modify the repository.
- Do not run repository-wide discovery or broad git analysis.
- Do not infer rationale beyond what the session supports. State uncertainty explicitly.
- Commit cycles are excluded from the todo list by default.
