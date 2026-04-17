---
name: agentos-team
description: "Coordinate role-based teamwork through shared live-notes and durable `impl-req` artifacts. USE WHEN the user assigns the agent a role inside `agentos-team`, such as `designer` or `implementer`, asks the agent to create, refine, read, or execute an `impl-req`, or wants team-style coordination through live-notes without mixing role responsibilities."
---

# Agentos Team

Shared protocol for role-based teamwork.

## Trigger Boundary

Use this skill when the user explicitly places the agent in `agentos-team`, names an
`agentos-team` role, or asks for `agentos-team` behavior.

Examples:

- `you are part of agentos-team as a designer`
- `use agentos-team in designer role`
- `as implementer, read this impl-req and tell me what you understand`
- `inside agentos-team, execute this impl-req`
- `act inside agentos-team and coordinate via live-notes`

Do not auto-apply from generic design, review, or implementation prompts alone.

## Core Contract

- Determine the requested role from the user instruction.
- Load only the role reference needed for the current assignment.
- If the role reads or writes `impl-req` artifacts, also read the shared artifact
  references below.
- Follow the role boundary strictly. Do not take on another role's responsibilities unless
  the user explicitly reassigns you.
- Use live-notes for durable cross-agent coordination artifacts, not as a transcript or
  casual scratchpad.
- When a live-note is created or updated, write for other-agent consumption: enough context,
  clear requests, explicit constraints, relevant file references, and concrete next action.
- Keep the shared protocol in this file small. Role-specific workflow belongs in
  `references/`.

## Shared Artifact References

- Read `references/impl-req.md` when the role reads or writes `impl-req` artifacts.
- Read `references/impl-req-example.md` only when the current task would benefit from a
  concrete sample of note structure or `End Log` updates.

## Live Note Dependency

Before suggesting or writing a live-note in `notes/live/`, read
`~/.agents/skills/agentos-live-note-base/SKILL.md` and follow its protocol for location,
numbering, and `agentos prefix next` usage.

## Role Routing

Current roles:

- `designer` -> read `references/designer.md`
- `implementer` -> read `references/implementer.md`

If the user names a role that is not documented here, say so briefly and continue only if a
safe fallback exists. If no role is explicit and the request materially depends on role
behavior, ask one concise question.

## Shared Handoff Standards

- Prefer one durable artifact per clear request.
- Cite concrete files, notes, or code surfaces when relevant.
- Distinguish clearly between accepted decisions, open questions, and out-of-scope items.
- Treat prior live-notes as coordination artifacts, not unquestionable truth. Current user
  direction wins.
- Do not rewrite or supersede a prior live-note unless the user asks or the role guidance
  explicitly requires it.
- Be direct and token efficient.

## Non-goals

- Do not collapse multiple roles into one blended workflow by default.
- Do not use live-notes as diary-style logs.
- Do not assume a role's authority extends beyond its documented responsibilities.
