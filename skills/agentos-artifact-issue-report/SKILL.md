---
name: agentos-artifact-issue-report
description: "Define and manage issue-report artifacts. Use when creating or reading a structured issue report live-note that describes a problem, its context, and expected resolution."
---

# Artifact: issue-report

Protocol for `issue-report` artifacts — structured live-notes that describe a discovered problem, its context, reproduction path, and expected resolution.

## Trigger Boundary

Use this skill when:

- The user asks to create or read an `issue-report`.
- Another skill needs to produce or consume an issue report artifact.

## Purpose

- An `issue-report` captures a problem clearly enough that another agent (or future session) can understand, reproduce, and fix it without additional context.
- Treat issue reports as durable coordination artifacts, not casual bug notes.

## Location And Naming

- Read `agentos-live-note-base` from the current available skills surface before writing.
- Use a filename ending in `-issue-report.md`.
- Store in `notes/live/`.

## Writing Guidance

- Write for another agent who has not seen the problem before.
- Be concrete: include specific files, error messages, and reproduction steps.
- Separate observation (what happens) from interpretation (why it happens).
- Do not include speculative fixes unless the user asks. Focus on describing the problem.
- Do not write an issue report automatically. Only write one on explicit user request.

## Minimal Structure

```md
# [Short Title] - issue-report

## Status

One sentence describing the current state of the issue.

## Problem

What is wrong. Observable behavior, not interpretation.

## Expected Behavior

What should happen instead.

## Reproduction

Steps or conditions to reproduce the problem.

## Context

Why this matters. Impact on the user, system, or other work.

## Relevant Files Or Surfaces

## Root Cause (if known)

## Suggested Fix (if known)

## Open Questions

## End Log
```

## Section Guidance

- `Status` is a plain-language one-sentence state note.
- `Problem` and `Expected Behavior` should be factual and specific.
- `Reproduction` can be steps, a command, a test case, or "see file X line Y."
- `Root Cause` and `Suggested Fix` are optional — include only when known. Do not speculate.
- `End Log` is append-only. Add concise dated notes as the issue progresses.

## Updating Guidance

- When the issue is investigated or fixed, update `Status` and append to `End Log`.
- Preserve the original problem description. Do not rewrite it to match the fix.
- If the root cause is discovered later, fill in the section rather than rewriting `Problem`.
