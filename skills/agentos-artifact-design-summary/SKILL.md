---
name: agentos-artifact-design-summary
description: "Define and manage design-summary artifacts. Use when creating or reading a structured design summary live-note that captures converged design decisions."
---

# Artifact: design-summary

Protocol for `design-summary` artifacts — structured live-notes that capture the converged output of a design discussion: decisions, execution plan, and deferred items.

## Trigger Boundary

Use this skill when:

- The user asks to create or read a `design-summary`.
- A design discussion has converged and the user asks to write it down.
- Another skill needs to consume a design summary as input.

## Purpose

- A `design-summary` captures converged design decisions in a form that can guide implementation, coordinate agents, or serve as a durable reference.
- It is the written-down version of a `design-discussion` convergence output.
- Treat design summaries as durable coordination artifacts, not discussion transcripts.

## Location And Naming

- Read `agentos-live-note-base` from the current available skills surface before writing.
- Use a filename ending in `-design-summary.md`.
- Store in `notes/live/`.

## Writing Guidance

- Write for another agent or future session that did not participate in the discussion.
- Capture decisions and rationale, not the exploration path.
- Be concrete about what was decided and what was deferred.
- Reference relevant files, notes, or surfaces rather than duplicating their content.
- Do not write a design summary automatically. Only write one on explicit user request.

## Minimal Structure

```md
# [Short Title] - design-summary

## Summary

1-3 sentences describing what was designed and why.

## Accepted Decisions

Numbered list of decisions with brief rationale.

## Execution Plan

Ordered phases or chunks for implementation.

## Deferred Items

Items explicitly out of scope or left for later.

## Relevant Files Or Surfaces

## Open Questions

## End Log
```

## Section Guidance

- `Accepted Decisions` should be concrete and actionable. Each decision should be understandable without reading the full discussion.
- `Execution Plan` should be ordered. If phases have dependencies, note them.
- `Deferred Items` are not rejected — they are intentionally postponed. Note why if the reason is not obvious.
- `End Log` is append-only. Add concise dated notes as the design evolves or implementation proceeds.

## Updating Guidance

- Preserve accepted decisions unless the user explicitly changes them.
- When implementation reveals that a decision needs revision, note it in `End Log` and update the decision only with user approval.
- If a deferred item is picked up later, move it to the relevant section and note the change in `End Log`.
