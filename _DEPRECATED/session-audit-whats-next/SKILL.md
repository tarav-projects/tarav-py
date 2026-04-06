---
name: session-audit-whats-next
description: 'Audit the current chat session for unresolved significant topics before suggesting next steps. USE WHEN the user asks things like "anything left?", "is this session complete?", "did we finish everything?", "what is still open?", or "what next?" and wants a short completion check focused on unfinished business in the current session.'
---

# Session Audit What's Next

## Goal

Check whether the current chat session is complete before moving on. Find unresolved significant topics, keep the report short, and suggest next steps only after the audit is clear.

## Scope

Use session-scoped evidence only:
- user and assistant messages in the current chat
- tool actions and tool results from this chat
- explicit constraints, corrections, blockers, and commitments stated in this chat
- file content only when a file was explicitly mentioned in this same session and reading it is needed to confirm status

Do not default to repository-wide analysis, broad git inspection, or new project exploration.

## Evidence Priority

Rank session evidence in this order:

1. user messages:
   - requests
   - corrections
   - constraints
   - approvals
   - explicit deferrals or parking decisions
2. explicitly confirmed generated responses:
   - assistant statements, tool results, or generated outputs only when the user clearly accepted, adopted, or acted on them in the session
3. tool actions/results that directly support an already-relevant session fact
4. file evidence only for files explicitly mentioned in this same session, when needed to confirm status

Treat these as weak evidence and usually ignore them:

- assistant progress chatter
- speculative suggestions that were never adopted
- repeated audit restatements
- abandoned branches that never changed the current state
- unconfirmed assistant framing
- unconfirmed assistant `I will...` statements that were never completed or accepted

## Significant Topics

Treat a topic as significant only when the session contains at least one of these:
- an explicit user request
- an explicit assistant commitment or promised action
- an unresolved user question or pending decision request
- a blocker, failed step, or missing verification that prevented completion
- an explicitly deferred or parked item

Ignore casual side remarks, abandoned brainstorming branches that were never adopted, and trivial wording detours.

## Topic States

Classify each significant topic as one of:
- `closed`: handled in this session with closure evidence
- `open`: still requires handling now
- `parked`: explicitly deferred; surface only after all `open` items are cleared
- `superseded`: replaced by a newer direction in the same session
- `uncertain`: appears significant but the closing state is ambiguous

Closure evidence means at least one of:
- explicit user acceptance or confirmation
- a clear completed result tied to the request
- an explicit decision that resolves the thread
- an explicit defer/park decision
- a clearly newer accepted direction that supersedes the old one

Do not classify a topic as `closed` solely because the assistant sounded done.
Treat the session as actively incomplete when any `open` or `uncertain` significant topic remains.

## Workflow

1. Read the visible conversation history for the current session.
2. Extract the significant topics and merge repeated mentions of the same thread.
3. Compare against earlier audit messages in the same session and deduplicate topic labels instead of treating repeated mentions as new issues.
4. Give each significant topic a short stable label, preferring the user's wording or an explicitly named artifact when possible.
5. Classify each topic using the states above and the evidence-priority rules.
6. Count unresolved active items (`open` and `uncertain`) and count `parked` items separately.
7. If the user asked `what next?` or equivalent, run the audit first.
8. Suggest follow-ups only when no unresolved active items remain.

Use these additional rules while classifying:
- The latest accepted direction overrides earlier superseded threads.
- If the safest classification depends on an assumption, state that assumption briefly.
- If closure evidence is missing or conflicting, prefer `uncertain` over `closed`.

## Output

Keep the feedback short.

Start with one status line:
- `N unresolved significant items remain.`
- `No unresolved significant items remain; N parked items remain.`
- `No unresolved significant items remain; this session appears complete.`

Then follow these rules:
- Show at most 3 item paragraphs.
- Use one item per paragraph.
- Start each item paragraph with a bold status-prefixed label using the topic's classified state and short label, for example `**[Parked] Hello-World Implementation**`.
- Use the topic's deduplicated label consistently if it appears again in later audits in the same session.
- In each paragraph, after the label, explain briefly why the item is still relevant, then propose one concrete action.
- For `uncertain` items, state exactly what evidence is missing, conflicting, or ambiguous.
- For `parked` items, state briefly why the item was parked before proposing the next step.
- If more items exist than shown, end with `+N more unresolved items not shown.` or `+N more parked items not shown.`

Dummy format example:

```md
No unresolved significant items remain; 2 parked items remain.

**[Parked] Hello-World Implementation**
This was explicitly deferred after the planning note was written. Concrete next action: scaffold the app shell.

**[Parked] Touch-Event Schema**
The exact first write format was intentionally left for a later design pass. Concrete next action: decide the minimal v1 touch-event fields.
```

When the user asks `what next?`:
- if any unresolved active item exists, report only those items
- if no unresolved active item exists and parked items remain, mention parked items first, then optionally suggest resuming one or closing the session cleanly
- if no unresolved active item exists and no parked item remains, propose 1-3 local follow-ups grounded in the current session

Keep follow-ups local to the session. Prefer actions such as finish verification, summarize results, perform the already-agreed next step, document the outcome, or close the thread cleanly. Do not invent unrelated new directions.
Any proposed follow-up must be the minimal next action implied by the audited topic state, not a new workstream.

## Constraints

- Keep output factual, short, and evidence-backed.
- Prefer the current chat over repository discovery.
- State uncertainty explicitly when evidence is ambiguous.
- Do not introduce new work while unresolved active items still exist.
- Do not write files or modify the repository unless the user explicitly asks.
