---
name: issue-live-note-workflow
description: Drive issue resolution from a `notes/live` issue entry through discussion, explicit implementation approval, and in-place issue updates. USE WHEN the user wants to work from a specific live-note issue using an analyze-first, implement-later workflow.
---

# Issue Live Note Workflow

## Purpose

Use this skill when the user wants to work from a specific issue in a live note using this flow:
1. analyze and discuss first,
2. implement only after explicit user request,
3. update the source issue title in the live note as done.

## Trigger Intent

Use this skill when user intent matches:
- "work from this issue in notes/live"
- "discuss this issue first then implement"
- "update the issue in the live note when done"

## Required Inputs

The workflow requires both:
- absolute or repo-relative live note path (for example `notes/live/576-codebase-quality-review.md`)
- exact issue title text (the full `### Issue: ...` heading content)

If either input is missing, ask directly in chat for the missing input before proceeding.

## Fixed Phases

### Phase 1: Locate and Explain (No Edits)

1. Open the live note and locate the exact matching issue heading.
2. If exact heading is not found, stop and report mismatch with nearby candidate headings.
3. Produce a structured issue analysis with these required sections:
- `Where`
- `Why this matters`
- `Evidence`
- `Proposed plan`
- `Questions/risks`

Notes:
- Keep analysis factual and concrete.
- Include file paths and functions when possible.
- Do not modify code or files in this phase.

### Phase 2: Discussion Loop (No Edits)

1. Discuss tradeoffs and plan details with the user.
2. Refine scope based on feedback.
3. Continue until the user explicitly requests implementation.

Hard rule:
- Do not implement during this phase.

### Phase 3: Implementation (Edits Allowed)

Implementation starts only when user gives explicit implementation intent,
for example: `implement`, `go implement`, `apply this plan`.

On implementation:
1. Apply agreed code changes.
2. Run relevant tests.
3. Report outcomes and any residual risks.

### Phase 4: Live Note Update

After implementation is complete, update the source issue heading in-place.

Completion format rule:
- Strike only the issue title line using this exact syntax style:
  - `~~### Issue: ...~~`
- Keep the issue body intact unless user asks for additional edits.

## Behavior Rules

- Keep conversation concise and direct.
- Keep cognitive/judgment work in-agent.
- Prefer deterministic evidence from repository state.
- Do not silently change issue wording when striking out; preserve title text.
- Do not mark issue done before implementation + validation are complete.

## Output Contract Per Phase

- Phase 1 output: structured analysis (`Where`, `Why this matters`, `Evidence`, `Proposed plan`, `Questions/risks`).
- Phase 2 output: focused answers, decisions, and updated plan.
- Phase 3 output: what changed, tests run, and validation result.
- Phase 4 output: confirm note path and show updated struck heading text.

## Minimal Example

Given issue heading:
- `### Issue: sqlite runtime open/refresh/rebuild paths duplicate cache lifecycle logic`

Mark done as:
- `~~### Issue: sqlite runtime open/refresh/rebuild paths duplicate cache lifecycle logic~~`
