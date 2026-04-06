---
name: session-issues-inventory
description: >
  Scan the current conversation and produce a short numbered inventory of
  open issues with status, provenance, and description.  Read-only,
  conversation-scoped.  USE WHEN the user asks "where am I?", "what's next?",
  wants a quick issue list for the current session, or needs to know what
  open items remain.
user-invocable: true
allowed-tools: []
---

# Session Issues Inventory

"Where am I?" / "What's next?" — a quick numbered inventory of open issues
in the current session.

## Trigger

Invoke when the user says any of:

- "where am I?"
- "what's next?"
- `/session-issues-inventory`

Do not trigger automatically or from unrelated conversational prompts.

## Evidence Priority

Use only session-scoped evidence.  Rank it in this order:

1. **User messages** — requests, corrections, constraints, approvals,
   concerns, questions.  Strongest signal.
2. **Confirmed generated responses** — assistant statements or tool results
   that the user clearly accepted, adopted, or acted on.
3. **Tool actions and results** that directly support an already-relevant
   session fact.

Treat these as weak evidence and usually ignore:

- Assistant progress chatter and framing that was never confirmed.
- Speculative suggestions that were not adopted.
- Abandoned branches that never changed current state.
- Unconfirmed assistant "I will..." statements that were never completed
  or accepted.

The evidence tier determines provenance:

- An issue grounded in tier-1 evidence is `user`.
- An issue grounded in tier-2 or tier-3 evidence is `agent`.
- An issue inferred from the session arc without specific evidence is `next`.

## Workflow

### 1. Infer a session title

Derive a short title (3-8 words) that captures the **full arc** of the
conversation, not just the first message.  If the session pivoted topics,
reflect the pivot.

### 2. Identify issues

Scan every turn in the conversation.  An issue is anything that "needs
attention" that surfaced during the session:

- Explicit requests or questions from the user.
- Problems discovered during work.
- Concerns raised.
- Pending actions mentioned.
- Decisions deferred.

Use common sense.  If something was raised and resolved, it is done.

Apply these rules while identifying:

- **Supersession:** the latest accepted direction overrides earlier
  superseded plans.  If the user said "let's fix X" then later said
  "forget X, let's do Y", drop X.
- **Deduplication:** merge repeated mentions of the same thread into
  one issue.  Prefer the user's wording for the label.

### 3. Classify provenance

Each issue gets exactly one provenance tag based on its evidence tier:

| Tag     | Evidence tier | Meaning                                            |
|---------|---------------|----------------------------------------------------|
| `user`  | Tier 1        | Originated from a user message.                    |
| `agent` | Tier 2-3      | Emerged from agent work: bug found, test failure.  |
| `next`  | Inferred      | Obvious logical next step from the session arc.    |

### 4. Classify status

Assign a short status label to each issue.  Examples:

- `not started`
- `in progress`
- `under review`
- `found`
- `pending`
- `blocked`
- `in discussion`
- `done`

Use whatever label fits naturally.  Keep it to 1-2 words.

### 5. Rank and select

Ranking order:

1. All `user` issues first.
2. Then `agent` issues.
3. Then `next` issues, only if slots remain.

Display rules:

- Show **~5-6 issues** maximum.
- **Drop done issues** to free slots.  Only show done issues if there is
  nothing else to show.
- If there are 6+ `user` issues, do not show `agent` or `next` at all.
- Within each provenance tier, order by recency of last mention in the
  conversation (most recent first) or by natural priority if obvious.

### 6. Format output

```
Session: <inferred session title>

 1. <provenance> | <status>
    <one-sentence description with enough context to act on>

 2. <provenance> | <status>
    <one-sentence description with enough context to act on>
 ...
```

Formatting rules:

- First line per issue: number, provenance, pipe, status.
- Second line per issue: indented one-sentence description.
- The description should carry enough context to understand the issue
  without scrolling back through the conversation.  Include relevant
  identifiers, file names, or specifics when they exist.
- Blank line between issues for readability.
- Numbered sequentially so the user can refer to issues by number
  (e.g., "work on #3").

Example:

```
Session: tara-stdlib-js review

 1. user | under review
    TapeMachine spec review (spec 134) — checking state transitions and edge cases

 2. user | found
    smoke.spec.ts is missing an isRecord assertion that other spec files include

 3. user | not started
    taralib-js examples may have drifted from current API after recent changes

 4. user | pending
    Live note 507 needs archival before closing the review cycle

 5. agent | found
    assertEqual inconsistency in spec 134 — uses assertEqual in some places, assertEquals in others

 6. next | pending
    Re-run smoke tests after the isRecord fix lands to confirm nothing else broke
```

## Constraints

- **Read-only.**  Do not write files, modify state, or append to tapes.
- **Conversation-scoped.**  Do not pull from external task files, tapes,
  or project state.  Only mine the current conversation.
- **Concise.**  The entire output should be scannable at a glance.
  No prose, no explanations, no summaries beyond the list itself.
- **No subagent.**  Run inline.
