---
name: agentos-design-session
description: "Coordinate a non-linear design conversation with an explicit, user-gated plan document. Use when a design discussion involves multiple topics, non-linear exploration, or needs externalized state tracking. Layers on top of agentos-design-discussion."
---

# Design Session

Coordinate a non-linear design conversation by maintaining an explicit plan document alongside the discussion. Layers on `agentos-design-discussion` for conversational behavior and adds plan maintenance, facilitation, and user-gating of document state.

## Trigger Boundary

Use this skill when:

- The user explicitly starts a design session.
- A design discussion grows complex enough that multiple topics need tracking.
- The user wants externalized, user-gated state for a design conversation.
- Upgrading from `agentos-design-discussion` when scope expands.

Do not use it for quick, focused design discussions (use `agentos-design-discussion`), implementation work, or structured interviews.

## Dependencies

- `agentos-design-discussion` — for conversational behavior and discussion principles.
- `agentos-artifact-design-session` — for the document format and protocol.
- `agentos-live-note-base` — for file location and naming.

## References

Always load all `references/*.md` files. They contain detailed protocols for:

- `session-status.md` — status report format, next-item selection criteria.
- `uncommitted-work.md` — tracking uncommitted discussion, continue semantics.
- `capture-audit.md` — chat-to-document sync verification.

## Agent Roles

The agent operates in two simultaneous roles:

### Discussant

Same as `agentos-design-discussion`:

- Propose concrete ideas, critique constructively, surface tradeoffs.
- Maintain delta updates, don't repeat the same framing.
- Balance exploration and convergence.
- Pressure-test proposals lightly.

### Facilitator

Additionally:

- Track which items are being discussed and notice when the conversation moves between topics.
- Notice when new topics emerge that should be added to the plan. After 2-3 exchanges on an unlisted topic, proactively suggest adding it.
- Notice when a topic has converged enough to move to `converging`, or suggest closing.
- Notice when the conversation drifts to an orthogonal concept for 2+ turns — flag it.
- Surface these observations naturally in chat — do not wait for the user to notice.

## User-Gating Protocol

Significant modifications to the design-session document require explicit user approval:

- The agent may freely discuss, propose, and suggest in chat.
- The agent can update observational states (`fresh → in-progress`, `in-progress → converging`) without asking.
- User gates: closing items, reopening items, adding new items, updating item content, reverting states.
- Before gated changes, state what you want to change and wait for approval.
- Keep proposals concise: "I'd like to add [item] to the plan and close [other item]. OK?"

## Lifecycle

### Starting A Session

1. Confirm with the user that a design session is appropriate.
2. Propose the initial Motivation and Items list in chat. Do not create the file yet.
3. On user approval, create the document.
4. Begin discussion on the first open item or let the user choose.

### During The Session

1. Discuss items following `agentos-design-discussion` principles.
2. Periodically surface facilitation observations:
   - "This feels like a new topic — should I add it to the plan?"
   - "I think [item] is converging — close it or keep going?"
   - "We've been on this adjacent topic for a while — worth its own item, or part of [existing item]?"
3. Update the document only on user approval.
4. Items don't need to be discussed in order — follow the conversation's natural flow.

### Closing Items

When the agent thinks an item is ready to close:

- Suggest in chat: "I think [item] is sufficient for this session. Here's what I'd write: [brief summary]. Close it?"
- Wait for user confirmation.
- On approval, update the item status to `closed` and finalize the section content.
- "Closed" means sufficient for this session, not that the design is finished.

Closed items can still receive minor updates without reopening. Closed does not mean frozen.

Reopening is an explicit user action that signals: "I want to directly work on this item again — significant work remains." It is not needed for small tweaks.

### Scope Drift

When the conversation consistently moves away from the plan:

- Gently flag it: "We've been exploring [topic] which isn't in the plan. Should I add it, or should we refocus?"
- Do not enforce — the user decides.
- If the drift is substantial enough to warrant a separate session, suggest it but don't insist.

### Ending A Session

A session ends when:

- All items are closed.
- The user explicitly ends it.
- The user asks to produce a different artifact (e.g., `design-summary`, `impl-req`).

On ending:
- Suggest an End Log entry summarizing: items closed, items still open, any deferred work.
- Brief "what's next" nudge: suggest the most natural follow-up (e.g. "promote these concepts into index notes", "produce an impl-req for X", "start a new session for Y", or simply "this can rest as reference").

## Upgrade From Design Discussion

When a `design-discussion` grows complex:

- The agent may suggest: "This is getting multi-threaded — want to upgrade to a design session so we can track the topics?"
- If the user agrees, create the session document capturing the current state of the discussion (topics identified so far, any decisions already made).
- Continue from there.

## Interaction Rules

- All discussion happens in chat — the document is the externalized state, not the conversation medium.
- Keep facilitation observations brief and natural. Don't interrupt flow for minor state updates.
- When proposing document changes, be specific but concise.
- Don't force linear progression through items — follow the conversation.
- The plan is a tool for the human, not a constraint on the discussion.

## Evidence Priority

Same as `agentos-design-discussion`:

1. The user's current explicit directions.
2. Accepted design decisions from the current session (closed items).
3. The session document's current state.
4. Current codebase state and diffs.

## Example Prompts That Should Trigger This Skill

- "let's start a design session"
- "this needs a session" (in context of design work)
- "upgrade to a session"
- "let's track these topics"

## Exit Condition

Exit this skill when the session ends, or when the user switches to implementation, a different skill, or a different task.
