---
name: agentos-edit-diff-lines-base
description: Define the edit-diff-lines format for proposing text changes as unified diff lines. USE WHEN creating or applying skills that should present file or in-chat edits for human review instead of rewriting text directly.
---

# Edit Diff Lines Base

## Purpose

This skill defines a **communication format**, not an action.
It describes how an agent formally presents proposed changes to a text so a human
can review, give feedback, and decide whether to apply them.

The target text can be:
- A file on disk
- Text from a previous chat message

## Format

Use unified diff style. Changed lines are prefixed; unchanged context lines are not.

```
- old line
+ new line
```

Rules:
- `-` prefix: line being removed or replaced.
- `+` prefix: line being added or replacing the removed line.
- No prefix: unchanged context line (included for orientation).
- Do not use `---`/`+++`/`@@` headers unless exact git diff output is explicitly requested.

## Context Lines

Always include 1–2 unchanged lines above and below each change block.
Context lines have no prefix and are taken verbatim from the surrounding text.
They serve as the visual anchor — do not paraphrase them.

## Anchoring the Change

### File target
Include a `file:line` or `file:line-range` reference before the diff block.

```
src/Kernel/core/007-system-init.md:16-17
- `resolve_*` may read existing state but must avoid side effects.
+ `resolve_*` may read existing state but must avoid disk side effects.
```

### In-chat text target
No file reference. The surrounding context lines serve as the anchor.
Quote the original text faithfully so the diff block is self-locating.

```
- Pure utilities (e.g., `_is_lite(val)`) don't take it, `I0x` = pure
+ Pure with respect to the integration system (no `SimOs`, no `SIMOS[]`)
```

## Usage

Agents invoke this format when:
- Proposing an edit to an index note, spec, or any text
- Giving the user an explicit before/after for review

After presenting the diff, wait for user feedback or approval before applying.
