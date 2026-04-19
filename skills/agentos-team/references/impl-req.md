# Impl-Req Reference

Shared protocol for `impl-req` artifacts used by `agentos-team` roles.

## Purpose

- `impl-req` means an implementation-request artifact for other-agent consumption.
- Use `impl-req` live-notes to capture what should be implemented, what constraints matter,
  and how later work should be evaluated.
- Treat `impl-req` notes as durable coordination artifacts, not as chat transcripts.

## Location And Naming

- Read `agentos-live-note-base` from the current available skills surface before
  suggesting or writing an `impl-req` in `notes/live/`.
- Use a filename ending in `-impl-req.md` unless the user overrides it.

## Writing Guidance

- Be direct and clear.
- Write for another agent who did not see the full discussion.
- Prefer references to files, notes, commands, or surfaces over pasted code.
- Do not include large file fragments or long code excerpts.
- Be flexible about exact headings when needed, but keep the same semantic coverage.

## Minimal Structure

Use this as the default shape:

```md
# [Short Title] - impl-req

## Impl-Req State

One sentence describing the current state of the request.

## User Intent

## Why This Exists

## Current Situation

## Requested Change

## Constraints And Invariants

## Out Of Scope

## Acceptance Signals

## Relevant Files Or Surfaces

## Open Questions

## Related Impl-Reqs

## End Log
```

## Section Guidance

- `Impl-Req State` is a plain-language one-sentence state note, not a fixed status enum.
- `Relevant Files Or Surfaces` may include code paths, notes, commands, or spec surfaces.
- `Related Impl-Reqs` should call out predecessors, follow-ups, or superseded requests.
- `End Log` is append-only. Add concise dated notes at the end as work progresses.

## Updating Guidance

- Preserve the original request intent unless the user explicitly changes it.
- When refining an `impl-req`, prefer focused updates over full rewrites.
- When implementation work occurs, update `Impl-Req State` and append a short note to
  `End Log` describing what changed, what remains, and any important drift or blockers.
