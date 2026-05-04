---
name: agentos-artifact-design-session
description: "Define and manage design-session artifacts. Use when creating or reading a design-session live-note that tracks a non-linear design conversation with an explicit plan of topics, their states, and converged outcomes."
---

# Artifact: design-session

Protocol for `design-session` artifacts — structured live-notes that externalize the state of a non-linear design conversation. They track what topics need discussion, what has converged, and what remains open.

## Trigger Boundary

Use this skill when:

- The user asks to create or read a `design-session` document.
- The `agentos-design-session` behavioral skill needs to create or update the session document.
- Another skill needs to consume a design-session artifact as input.

## Purpose

- A `design-session` document is a live coordination surface for non-linear design conversations.
- It externalizes the plan of topics to discuss, their current state, and the converged outcomes.
- Unlike a `design-summary` (which captures post-hoc decisions), a `design-session` is actively maintained during the conversation and evolves with it.
- Treat it as the rolling extraction of what has converged from the chat.

## Location And Naming

- Read `agentos-live-note-base` from the current available skills surface before writing.
- Use a filename ending in `-design-session.md`.
- Store in `notes/live/`.

## Item States

States reflect the agent's evaluation of where each item is. They are feedback signals, not gates.

- `fresh` — just added, no discussion yet.
- `in-progress` — some discussion has happened.
- `converging` — getting mature, likely ready to close soon.
- `closed` — done for this session (user-gated).
- `reopened` — user reopened a previously closed item. Pairs with any other state except `fresh` (e.g. `[in-progress, reopened]`).

Transition rules:
- Agent can move: `fresh → in-progress`, `in-progress → converging` (observational, not gates).
- User gates: `→ closed`, `→ reopened`, and any revert.
- Agent can suggest closing in chat but does not change the label without user approval.

Semantics: `closed` means "sufficient for this session," not "design is finished." A session is delta work — it does not claim completeness.

## Minimal Structure

```md
# [Short Title] - design-session

## Motivation

What we are trying to design and why. This section evolves as understanding deepens.

## Items

- Item 1: [status] short description
- Item 2: [status] short description
- Item 3: [status] short description

## Item 1

Content evolves from open question to converged decision.
Early: the question or topic framing.
Later: the accepted design outcome and rationale.

## Item 2

...

## Notes

Observations, ideas, or considerations that have emerged but are not yet promoted to their own item.

## End Log
```

## Section Guidance

- `Motivation` is a living section. Update it as the session's understanding of the goal sharpens.
- `Items` is the table of contents with status at a glance. Keep it in sync with item sections.
- Each item section is the full substance. It starts as a topic framing and grows into the converged outcome.
- `Notes` is a staging area for things that came up but don't yet warrant their own item.
- `End Log` is append-only. Add concise dated notes for significant state changes.

## Writing Guidance

- Write for readability mid-session — someone joining the conversation should be able to scan the document and understand the current state.
- Item sections should be self-contained enough to understand without reading the full chat.
- When an item reaches `closed`, its section should contain the session's outcome (which may range from a brief concept introduction to a full converged design).
- Reference relevant files, notes, or surfaces rather than duplicating their content.

## Updating Guidance

- All modifications to the document require user approval before writing.
- When updating, preserve closed items unchanged unless the user explicitly reopens them.
- When promoting a note to an item, add it to both the Items list and create its section.
- When an item's status changes, update both the Items list and note it in End Log if significant.

## Length Management

The main session document should stay compact and focused on active work. When it grows long (~400-500+ lines), consider extracting content into companion live files.

### End Log Extraction

When the End Log grows large, extract it to a companion file:

- Create a sibling live file (e.g. `NNN-session-name-log.md`).
- Replace the End Log section in the main document with a link: `See [session log](./NNN-session-name-log.md)`.
- The agent appends freely to the extracted log file.

### Content Extraction

When items (closed or just long) add length pressure, their content can be moved out:

- Keep the one-line summary in the Items list (with status and short description).
- Move the full item section content to a companion aux file: `NNN-session-name-aux-0.md`, `NNN-session-name-aux-1.md`, etc.
- Add a link in the Items list pointing to the aux file and section.
- The full content is still accessible but out of the way of active work.
- Multiple aux files allow splitting by theme, size, or any natural grouping.

### Extraction Rules

- Extraction is optional and triggered by length, not by status change. Closing does not auto-extract.
- The main document remains the coordination surface — it should always show the full Items list with statuses.
- Extracted content is still part of the session, just housed in companion files.
- Extraction is user-gated like other document modifications.

## Relationship To Other Artifacts

- A `design-session` may produce a `design-summary` at the end if the user wants a cleaner post-hoc record.
- Items that need implementation can spawn `impl-req` artifacts.
- The session document itself is the primary coordination artifact during active work.
