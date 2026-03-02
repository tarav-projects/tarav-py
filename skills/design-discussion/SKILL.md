---
name: design-discussion
description: Collaborative design conversation mode for architecture or product decisions. Use when the user wants iterative back-and-forth suggestions, critique, and refinement toward convergence, not a structured interview or questionnaire.
model: opus
---

# Design Discussion

Drive a design goal through iterative exploration toward convergence.

## Core Principles

- Treat this as a conversation, not an interview.
- Propose concrete ideas first; do not wait passively for prompts.
- Critique constructively: keep strong parts, replace weak parts, explain tradeoffs.
- Revise the design every round; do not repeat the same framing.
- Balance exploration and convergence: keep focus, but explore alternatives.
- Default to delta updates: include mostly new information.
- If feedback is scoped to one part, reply only on that part and its direct dependencies.

## Required Behavior

1. Restate the design goal, constraints, and assumptions briefly.
2. Provide an initial proposal immediately (3-7 concrete points).
3. Wait for user feedback.
4. For each feedback round:
- Respond to the user's critique directly.
- Update only the impacted design sections with clear changes.
- Call out tradeoffs and open risks.
- Ask one concise follow-up question only if needed to unblock progress.
5. Repeat until the user signals convergence.

## Interaction Rules

- All in chat, no interactive forms or templates by default.
- Do not use forced multiple-choice templates by default.
- Ask at most 1-2 clarifying questions only when ambiguity blocks design progress.
- Keep tone direct and collaborative.
- Do not overspecify or overengineer; start with a simple proposal and iterate.
- Maintain the same level of abstraction; do not jump to low-level details too early.
- Do not restate the full plan on every round.
- Provide full recaps only when explicitly asked or at convergence.

## Round Output Format

Use this structure each round:

- `Draft vN`
- `Scoped update` (what changed in the discussed part)
- `Changes from previous round` (delta only)
- `Tradeoffs`
- `Open questions` (only if blocking)

## Convergence Output Format

When the user says "converged", "make plan", or equivalent, output:

1. `Final Design` (concise architecture/spec)
2. `Decisions` (accepted choices and rationale)
3. `Deferred Items` (explicitly out of scope)
4. `Execution Plan` (ordered implementation phases)
5. `First Change Set` (what to implement first)

## Example Prompts That Should Trigger This Skill

- "what do you think?"
- "lets discuss"
- "Let's converge on a plan together."

## Exit Condition

Exit this skill when the user asks to implement, summarize, or stop the discussion.
