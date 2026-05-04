# Session Status Report

When the user asks for session status, provide a short structured report.

## Format

```
Session: [title]
Progress: [N closed / M converging / K open] — T total

Items:
  [converging]
  - [item] — [one-line state]

  [in-progress]
  - [item] — [one-line state]

  [fresh]
  - [item] — [one-line state]

Uncommitted:
  - [item] — [what was discussed but not written]

Suggest closing:
  - [item] — [why: saturated / no new ground / sufficient for session]

Active: [what we're currently discussing, if anything]

Next:
1. [item] — [why]
2. [item] — [why]
3. [item] — [why]

Recommendation: [N] — [short reason].
```

## Rules

- Group items by status, most actionable first.
- Split open items into "has work" (`in-progress`) vs "not started" (`fresh`).
- Uncommitted lists items with chat discussion not yet captured in the document. Say "none" if clean.
- Suggest closing lists items the agent thinks are ready to close (saturated, no new ground, sufficient). Omit section if none.
- Next suggests up to 3 items with one-line rationale. Include a recommendation.
- Keep it scannable. The user may call this repeatedly.

## Next Item Selection Criteria

In rough priority:

- Items with significant uncommitted work (finish what's started).
- Items that unblock other items.
- Highest-leverage open items.
- Items closest to closing.

Keep explanations to one line each. The user picks.
