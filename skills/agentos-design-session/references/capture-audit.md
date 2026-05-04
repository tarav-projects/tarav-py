# Capture Audit

Scan the chat to verify that all relevant user ideas, approvals, and decisions have been captured in the design-session document.

## Triggers

- User requests: "capture-audit", "did we miss anything?", "scan the chat", "check what we missed"
- Agent suggests it when appropriate: after a long discussion stretch, before ending a session, or when multiple items were discussed rapidly without document updates.

## Output

Produce a short report — do not auto-update the document:

```
Capture audit:
- [item]: [what's missing — user idea, approval, constraint, correction]
- [item]: [what's missing]
- [new]: [concept mentioned but not yet an item]
```

If nothing is missing: "Capture audit: document is in sync."

## After The Report

The user decides what to update. The agent may propose specific edits based on the report, but waits for approval as usual.
