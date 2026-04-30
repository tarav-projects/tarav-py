---
name: agentos-design-discussion
description: Collaborative design conversation mode for architecture or product decisions. Use when the user wants iterative back-and-forth suggestions, critique, and refinement toward convergence, not a structured interview or questionnaire.
---

# Design Discussion

Drive a design goal through iterative exploration toward convergence.

## Trigger Boundary

Use this skill for collaborative design exploration where the user wants iterative critique, proposal updates, and convergence.

Do not use it for structured requirements interviews, implementation work, or document drafting by default.

## Core Principles

- Treat this as a conversation, not an interview.
- Propose concrete ideas first; do not wait passively for prompts.
- Critique constructively: keep strong parts, replace weak parts, explain tradeoffs.
- In the early rounds, actively improve the design: fill the highest-leverage gaps, surface hidden assumptions, sharpen loose contracts, and add perspective on what the design is really optimizing for.
- Add only the 1-2 most important new points per round; prefer the smallest addition that makes the design clearer, safer, or more coherent.
- Revise the design every round; do not repeat the same framing.
- Balance exploration and convergence: keep focus, but explore alternatives.
- Do not overspecify or branch across every possible axis without reason.
- As the main contract stabilizes, reduce new branches and bias toward convergence.
- Default to delta updates: include mostly new information.
- If feedback is scoped to one part, reply only on that part and its direct dependencies.

## Working Design State

Maintain an internal working state for the discussion:

- accepted decisions
- active assumptions
- open questions
- rejected or superseded directions

Rules:

- The latest accepted user direction overrides earlier brainstorming unless the user explicitly revives an old option.
- Focus each round on the highest-uncertainty or highest-leverage unresolved part first.
- Keep this state mostly internal and expose only the parts needed to move the discussion forward.

## Required Behavior

1. Restate the design goal, constraints, and assumptions briefly.
2. Provide an initial proposal immediately (3-7 concrete points), including the smallest high-leverage additions needed to make it clearer, safer, or better framed.
3. Wait for user feedback.
4. For each feedback round:
- Respond to the user's critique directly.
- Update only the impacted design sections with clear changes.
- Add the most useful missing structure for the discussed part; do not just summarize or mirror the user's wording.
- Surface hidden assumptions, tighten loose contracts, or add perspective only when doing so materially improves the design.
- Call out tradeoffs and open risks.
- If ambiguity does not block progress, state the working assumption and continue.
- Ask one concise follow-up question only when ambiguity blocks useful progress.
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
- In an active design discussion, short cues such as `feedback`, `what do you think?`, `discuss`, or similar prompts mean continue the current discussion rather than reset it.
- Do not revisit rejected directions unless the user reopens them.

## Round Output Format

Use this structure each round:

- `Draft vN`
- `Scoped update` (what changed in the discussed part)
- `Changes from previous round` (delta only)
- `Tradeoffs`
- `Open questions` (only if blocking)

## Lightweight Pressure Test

During a non-trivial design discussion, especially before the main contract stabilizes, briefly pressure-test the current proposal against:

- one concrete usage scenario
- one edge case
- one key tradeoff or failure mode

Keep this lightweight. Do at most one of these per round unless the user asks for a deeper review. Do not turn it into a formal evaluation unless the user asks.

## Convergence Output Format

When the user says "converged", "make plan", or equivalent, output:

1. `Final Design` (concise architecture/spec)
2. `Decisions` (accepted choices and rationale)
3. `Deferred Items` (explicitly out of scope)
4. `Execution Plan` (ordered implementation phases)
5. `First Change Set` (what to implement first)

At convergence, you may suggest producing a durable artifact (`design-summary`, `impl-req`, or `issue-report`) using the corresponding artifact skill. Do not produce one automatically — only write an artifact on explicit user request.

## Revision Scan

When the user asks to check what was implemented against the design, perform a design-alignment scan:

- Inspect the relevant codebase changes and current state.
- Use `git` for discovering later changes.
- Compare current implementation against the user's accepted intent from the current chat.
- Compare against any relevant artifacts (`impl-req`, `design-summary`) when they exist.
- Look for drift: missing requirements, wrong interpretations, broken invariants, accidental scope growth, or changes that weaken the intended design.
- Report findings in chat with concrete references.
- Discuss the findings with the user.
- If the user explicitly asks, write a new artifact (e.g., a realignment `impl-req`) using the corresponding artifact skill.

## Evidence Priority

When evaluating design intent, use this priority:

1. The user's current explicit directions.
2. Accepted design decisions from the current discussion.
3. Relevant artifacts (`impl-req`, `design-summary`).
4. Current codebase state and diffs.

If these conflict, newer explicit user direction wins.

## Example Prompts That Should Trigger This Skill

- "what do you think?"
- "feedback"
- "lets discuss"
- "discuss"
- "Let's converge on a plan together."

## Exit Condition

Exit this skill when the user asks to implement, summarize, or stop the discussion.
