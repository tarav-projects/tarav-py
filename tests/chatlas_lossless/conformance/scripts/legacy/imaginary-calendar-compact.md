# Chat.Script: imaginary-calendar-compact

A tool-free memory exercise with one manual compaction between turns 4 and 5. It holds the
human-authored turn sequence constant while comparing providers' native compaction encodings.

- **target:** `Compaction.Event`, `Compaction.Summary`, and user-authority purity
- **boundary:** manually execute `/compact` after turn 4; the command is not a canonical user turn
- **status:** two valid captures recorded (1 claude-code, 1 codex); finding F5 resolved by the stable-event-place model

## Operator run

Paste the numbered user turns verbatim. The executer direction is not a user turn.

1. Let’s reason about an imaginary calendar. Do not use tools or write code. Keep track of the invented names and explain each answer in plain language.
2. The calendar’s exact reference name is `ORCHID-CLOCK-482`. It has three seasons in this order: Luma, Neri, and Varo. Preserve every invented name exactly.
3. Each season has a symbol: Luma uses a silver circle, Neri uses a violet triangle, and Varo uses a golden square. Restate the associations as complete sentences.
4. The calendar holds one celebration in each season. Luma has Lantern Day, Neri has Quiet Day, and Varo has River Day. Describe the full calendar from first season to last.
   - » EXECUTER DIRECTION — COMPACT: after the assistant answers turn 4, manually execute `/compact`. Confirm that the provider records a compaction boundary before continuing. «
5. Without listing everything again, which symbol and celebration belong to the second season? Explain how you identified them.
6. What was the calendar’s exact reference name? Return it exactly, followed by one sentence explaining what it names.
7. Add a fourth season named Sora after Varo. Its symbol is a white star and its celebration is Echo Day. Explain how this changes the calendar’s ordering.
8. Summarize the final imaginary calendar as a numbered list with one season per item.

## Same-experiment check (raw)

- codex: one `compacted` record after turn 4; `replacement_history` contains the four exact
  pre-boundary user messages plus one native encrypted `compaction` item
- claude-code: one `system/compact_boundary` record after turn 4 followed by one user-transport
  record carrying `isCompactSummary: true` and `isVisibleInTranscriptOnly: true`
- both assistants correctly recall the pre-boundary calendar facts after compaction

A capture is valid only when the raw contains the provider's compaction signal at the requested
boundary. Merely entering the eight turns without a successful compaction is a failed run.

## Expected neutral shape

- exactly eight human-authored user turns, verbatim and in order
- one `compaction` event between turns 4 and 5
- no `lineage.rollback`: compaction is not rollback or abandonment
- `/compact` control input is excluded from `Normal.Turn::User.Turn`
- claude's generated recap is a system-role message produced by provider/assistant, typed as a
  compaction summary, and excluded from `Normal.Turn::User.Turn`
- codex has no separately readable summary; summary absence is justified by its raw
- tool events: 0

## Recorded provider sessions

| provider | session_id | identity_hash | captured | note |
|---|---|---|---|---|
| codex | 019fd977-c106-7830-a17b-62d074a4bfa3 | 7ad9a9814f1356d6338b5085331bd350c234ec8d7de955db7c9c78a139b10dbc | 2026-08-06 | valid manual compact; raw `compacted` ×1; normal emits one compaction event and preserves all eight user turns |
| claude-code | add4201e-3543-47d8-9914-aa1fc4fec86e | edb2d153091143cc9e9eba82f91767ac711c89472e5591b05ee81024dcf7a39c | 2026-08-06 | valid manual compact; normal emits the boundary plus a typed system-role compaction summary; `/compact` and the summary are excluded from `User.Turn` |
