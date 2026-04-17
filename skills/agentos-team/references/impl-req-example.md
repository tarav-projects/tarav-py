# Impl-Req Example

Example only. Adapt the exact wording and section weight to the current request.

```md
# Tara Mobile Design Realignment - impl-req

## Impl-Req State

Ready for implementation. User and designer agreed on the realignment scope; no known
blockers remain.

## User Intent

Bring the current screen flow back in line with the intended design while preserving the
accepted navigation model.

## Why This Exists

The implemented screen drifted from the agreed design discussion. The user wants a focused
realignment request that another agent can execute without replaying the full conversation.

## Current Situation

The current implementation includes the new section order, but it also introduced a second
entry action that was not part of the accepted design. The layout now sends mixed signals
about the primary flow.

## Requested Change

Remove the extra entry action and restore one clear primary action. Keep the reordered
sections and the accepted screen grouping.

## Constraints And Invariants

- Preserve the accepted navigation model.
- Do not redesign unrelated screens.
- Keep existing data wiring intact unless the current layout depends on changing it.

## Out Of Scope

- Visual polish outside the affected screen
- Analytics changes
- Text copy revisions unrelated to the realignment

## Acceptance Signals

- The screen exposes one clear primary entry action.
- The accepted reordered sections remain intact.
- No unrelated navigation behavior changes.

## Relevant Files Or Surfaces

- `apps/tara_mobile/lib/screens/home_screen.dart`
- `notes/live/540-home-screen-design-impl-req.md`
- current branch diff for the affected screen

## Open Questions

- None at the time of writing.

## Related Impl-Reqs

- `notes/live/540-home-screen-design-impl-req.md` - earlier request that the new note
  refines

## End Log

- 2026-04-16: Designer created this note after revision scan found drift between accepted
  design intent and current implementation.
- 2026-04-17: Implementer confirmed understanding with the user before editing. Execution
  not started yet.
```
