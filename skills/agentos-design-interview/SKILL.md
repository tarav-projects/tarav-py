---
name: agentos-design-interview
description: 'Gather requirements and make design decisions through Q&A conversation. Use ONLY when explicitly triggered by name (for example: "$agentos-design-interview" or "use agentos-design-interview"). Do not auto-apply from inferred intent.'
---

# Design Interview

Structured approach for gathering requirements and making design decisions through conversational Q&A.

## Trigger Boundary

Use this skill for structured decision-making through targeted questions when the user wants the agent to actively narrow options and resolve design choices.

Do not use it for free-form design exploration, implementation work, or document drafting by default.

## Critical Rule

**This is a CONVERSATION, not a form.** All questions MUST be printed as plain text in the chat.
NEVER use `AskUserQuestion` or any interactive/UI tool to ask questions. Just type them out.
This rule has NO exceptions.

## Working Decision State

Maintain an internal working state throughout the interview:

- accepted decisions
- active assumptions
- open questions
- rejected or superseded options

Rules:

- The latest accepted user direction overrides earlier options unless the user explicitly reopens them.
- Ask the highest-uncertainty or highest-leverage unanswered questions first.
- Do not re-ask resolved questions unless new information makes them unclear again.
- Keep this state mostly internal and expose only what is needed to move the interview forward.

## Live Note Dependency

When suggesting or writing a decision document in `notes/live/`, read the
`agentos-live-note-base` skill from the current available skills surface and follow its
protocol for path conventions, numbering, and `agentos prefix next` usage.

## Question Templates

### `options-decision`

**Tag**: `[options-decision]` — printed before each question.

**Spec**: The default and currently only template. Use for every question that drives
a design decision. The agent must think carefully about a good recommended answer and
place it as option a). Options are lettered a–d for content choices. Four special
meta-options (x0–x3) are always appended — they let the user control the conversation
flow rather than answer the question directly.

**Format**:

```
[options-decision]
**N. [Topic tag]**:
context: [Context — quote, current state, or brief situation].
question: [Question sentence ending in ?]
a) [Option A — short label]: [one-line implication] (recommended)
b) [Option B — short label]: [one-line implication]
c) [Option C — short label]: [one-line implication]
d) [Option D — short label]: [one-line implication]
x0) more context
x1) solve autonomously
x2) lets discuss
x3) different options
```

**Rules**:
- Option a) is always the agent's recommended choice, explicitly labeled `(recommended)`.
- Options b–d are alternatives. Minimum 2 content options (a, b). Maximum 4 (a–d).
- Meta-options are always present and always last:
  - `x0) more context` — the user cannot answer with the provided information. The agent must restate the question with more, different, or better-explained context.
  - `x1) solve autonomously` — the user delegates the decision entirely to the agent.
  - `x2) lets discuss` — opens a free-form conversational fork about this specific topic. The agent drops the template format, discusses the topic directly, calls out tradeoffs, updates the recommendation, then resolves the question or resumes the loop.
  - `x3) different options` — the current content options (a–d) don't fit. The agent must generate a new set of content options for the same question.

## Workflow

### Phase 0: Bootstrap

When `/agentos-design-interview` is called without a referenced document or clear context:

1. Ask one adaptive opener in plain text: *"What do we want to design or decide?"*
2. If the user has context but not yet a concrete decision list, allow a short context dump before switching into the question loop.
3. Based on the answer, branch:
   - **Document referenced** → proceed to Phase 1 (analyze document)
   - **Problem/topic described** → ask about scope and constraints, then enter Phase 2
   - **Still vague** → ask one more clarifying question before proceeding

### Phase 1: Initial Analysis

1. Read the referenced document or context
2. Identify all FEEDBACK items, open questions, or unclear requirements
3. Present a brief summary of what you found

### Phase 2: Question Loop

For each item requiring clarification:

1. Select the highest-leverage unresolved questions first.
2. Select the appropriate question template (currently: `options-decision`)
3. Print the question using the template format — all in plain chat text
4. Number questions sequentially (1, 2, 3...)
5. Wait for user reply

User replies with:
- Option letters (e.g., "a", "1b, 2a")
- "feedback" followed by answers
- Direct answers referencing question numbers
- Additional context

After each reply:
- Acknowledge decisions made
- If user picked `x0`: restate with richer context
- If user picked `x1`: decide and state the decision, continue
- If user picked `x2`: discuss openly only for that topic, call out tradeoffs, update the current recommendation, then resolve the question or resume the loop
- If user picked `x3`: regenerate content options for the same question
- If ambiguity does not block useful progress, state the working assumption and continue
- Ask follow-up questions only when the answer materially changes the design direction
- Continue the loop

**Keep rounds short**: 2–4 questions maximum per round.

### Phase 3: Exit

The loop ends when user requests an action:
- "make a summary"
- "implement this"
- "create a plan"
- Any concrete task

On exit:
- Build a decision document draft (issue/answer format), keeping only decision-driving Q/A (direct but complete).
- Read and follow `agentos-live-note-base` from the current available skills surface to compute the live-note path.
- Suggested filename must end with `-interview.md`.
- Ask explicitly in plain chat text before writing any file:
   - `Do you want me to save this as a live note at <absolute-path>? You can override the path.`
- If user says **yes**:
   - If user accepts suggested path, write there.
   - If user overrides path, write to the user path as given.
- If user says **no**:
   - Do not write any file.
   - Print a concise chat summary with:
     - `Final Design`
     - `Decisions`
     - `Deferred Items`
     - `Next Steps`
- Summarize next steps if implementation requested.

## Style

- Be direct, no fluff
- Questions must be specific and actionable
- Quote code or docs when relevant
- Prefer binary/multiple-choice over open-ended
- Group related questions
- Keep the interview conversational even when using the options format
- Do not revisit rejected directions unless the user reopens them

## Decision Document Format

```markdown
# [Topic] - Decisions
**Session**: [date/time, use common-sense format]

**Issue**: [Brief description]

**Q**: [Decision-driving question]
**A**: [Decision]

**Q**: [Decision-driving question]
**A**: [Decision]

**Decision**: [One short paragraph summarizing the final approach]
```
