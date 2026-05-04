# Uncommitted Work

The document is the committed state. The chat is the working tree. Discussion that hasn't been captured in the document is uncommitted work.

The agent tracks this internally — no formal computation needed. It knows what was discussed and what made it into the document.

## When To Surface

- **After any document update:** "BTW, [other item] also has uncommitted discussion — want me to propose an update for that too?"
- **On continue triggers:** when the user says "continue", "what's next", "now what", or similar — surface uncommitted work before suggesting the next item.
- **On item switch:** if the user moves to a different item and there's substantial uncommitted work on the previous one — brief nudge: "[previous item] has uncommitted discussion — park it or update?"

## Continue Semantics

When the user says "continue" / "what's next" / "now what":

1. If there's uncommitted work: "We have uncommitted discussion on [item] — want me to propose an update before moving on?"
2. If the user declines (or nothing uncommitted): show session status + next item suggestions.
3. If resuming a previously discussed item: briefly recall where we left off.
