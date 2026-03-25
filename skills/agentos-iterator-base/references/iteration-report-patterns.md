# Iteration Report Patterns

Named pattern catalog for `Iteration.Report` design.

## Contents

- Usage
- Pattern Catalog
- Composition Examples
- Anti-patterns

## Usage

- Use these dotted names as shared documentation vocabulary for iterator skills.
- This file is one additive catalog within the iterator foundation.
- Do not treat these names as mandatory report headings.
- Concrete skills may expose them directly, rename them, merge them, or spread them across multiple sections.
- Some patterns preserve durable iteration state and others provide handoff guidance. That distinction is semantic only, not a required section split.
- A good `Iteration.Report` is curated markdown, not a transcript.
- Current user intent and fresh evidence outrank old handoff suggestions.
- `Iteration.Report` is a coordination artifact, not an authority surface.
- Repetition is useful when it is confirmatory.

## Pattern Catalog

### What.Next

- Purpose: Leave a concrete suggestion for a valuable next iteration.
- Use when: this iteration revealed an obvious next slice, check, or follow-up.
- Avoid when: the next move is too speculative or current evidence is too weak.
- Example:

```md
## What Next

- Inspect environment override precedence in `src/env.jl`.
- Recheck whether the duplicate-key fix also covers nested tables.
```

### Work.Done

- Purpose: Record the meaningful work completed in this iteration.
- Use when: later iterations could save time by knowing what was already covered.
- Avoid when: the entry would only restate trivial actions with no downstream value.
- Example:

```md
## This Iteration

- Work.Done: Reviewed config parsing in `src/config.jl`.
- Work.Done: Verified duplicate-key rejection with the current implementation.
```

### Work.Skipped

- Purpose: Make intentional non-coverage explicit.
- Use when: work was deferred, already handled elsewhere, or intentionally excluded.
- Avoid when: the omission was accidental or still unexplained.
- Example:

```md
## Scope Notes

- Work.Skipped: Did not inspect CLI flag parsing in this pass.
- Work.Skipped: Skipped database migrations because report `512-schema-review.md` already covers them.
```

### Claim.StillTrue

- Purpose: Strengthen a prior claim by explicit revalidation.
- Use when: this iteration rechecked an earlier statement and found it still accurate.
- Avoid when: the claim was not actually rechecked in this iteration.
- Example:

```md
## Confirmations

- Claim.StillTrue: Report `512-schema-review.md` is still accurate that duplicate keys fail fast in `src/config.jl`.
```

### Claim.Supersedes

- Purpose: Replace, narrow, or invalidate an earlier claim.
- Use when: the current iteration found better evidence than a prior report.
- Avoid when: the new statement only adds detail and does not actually change the earlier claim.
- Example:

```md
## Corrections

- Claim.Supersedes: Report `512-schema-review.md` said all duplicate keys fail fast. After rechecking, only top-level duplicates fail fast; nested duplicates still leak through.
```

### Decision.Reinforcement

- Purpose: State that a prior decision was reviewed again and still stands.
- Use when: the iteration revisits a design or workflow decision and confirms it.
- Avoid when: the item is purely a factual claim rather than a decision.
- Example:

```md
## Decisions

- Decision.Reinforcement: Keep `agentos prefix next` as append-only allocation. Rechecked against current numbering workflows and the decision still holds.
```

### Question.Open

- Purpose: Preserve uncertainty that should shape future work.
- Use when: this iteration identified a real unanswered question.
- Avoid when: the question is already resolved or too vague to guide later work.
- Example:

```md
## Open Questions

- Question.Open: Should nested duplicate-key handling match top-level behavior or remain permissive?
```

### Blocker.External

- Purpose: Record a dependency or missing input outside the current iteration.
- Use when: progress is limited by something this iteration cannot resolve alone.
- Avoid when: the blocker is really just more work for the same skill family.
- Example:

```md
## Blockers

- Blocker.External: Need the maintainer's decision on whether backward compatibility matters for nested key parsing.
```

### Scope.Boundary

- Purpose: State what this iteration intentionally did not try to settle.
- Use when: later agents could otherwise overread the report's conclusions.
- Avoid when: the boundary is obvious from context and adds no clarity.
- Example:

```md
## Boundaries

- Scope.Boundary: This pass reviewed parsing behavior only, not user-facing error messages or docs.
```

### Issue.Found

- Purpose: Record a concrete issue, defect class, or fidelity problem noticed in this iteration.
- Use when: the issue should influence later prioritization even if it was not fully resolved now.
- Avoid when: the note is too vague to guide a later pass.
- Example:

```md
## Issues Found

- Issue.Found: OCR dropped equation numbering on pages 12-14.
```

### Artifact.Used

- Purpose: Record intermediate artifacts or helper outputs that materially informed this pass.
- Use when: later iterations could save time by reusing the same artifacts or understanding where evidence came from.
- Avoid when: the artifact was trivial and leaves no meaningful reusable context.
- Example:

```md
## Artifacts Used

- Artifact.Used: Reviewed `workspace/pymupdf/blocks.jsonl` and rendered page `workspace/pypdfium2/p0018.png`.
```

### Progress.Snapshot

- Purpose: Capture a compact snapshot of current progress or coverage.
- Use when: the iterator family benefits from tracking coarse completion state across passes.
- Avoid when: the counts would be fabricated, unstable, or too noisy to compare later.
- Example:

```md
## Progress

- Progress.Snapshot: Sections 8/10 reviewed; equations 14/22 verified; references complete.
```

### Risk.Flag

- Purpose: Mark a change, uncertainty, or side effect that deserves special caution or spot-checking.
- Use when: this iteration made a risky correction, large deletion, or high-uncertainty change.
- Avoid when: the item is routine and does not merit elevated attention.
- Example:

```md
## Risk Flags

- Risk.Flag: Removed 18 transcript lines while correcting duplicated extraction output; needs spot-check against the PDF.
```

## Composition Examples

Concrete iterator skills should compose patterns into their own report format rather than inherit one shared template.

### Example A: Review Iterator

```md
# Config Review Iteration 3

## Summary

- Work.Done: Reviewed nested duplicate-key behavior.
- Claim.StillTrue: Report `512-schema-review.md` remains correct about top-level duplicate-key rejection.
- Claim.Supersedes: Nested duplicate keys are not rejected consistently.

## Open Questions

- Question.Open: Should nested behavior match top-level behavior?

## What Next

- What.Next: Inspect call sites that rely on permissive nested parsing.
```

### Example B: Cleanup Iterator

```md
# Cleanup Iteration 2

## This Pass

- Work.Done: Removed duplicated prefix-width parsing in two commands.
- Work.Skipped: Did not touch file-numbering docs in this pass.
- Decision.Reinforcement: Keep width `3` as the shared default.

## Boundaries

- Scope.Boundary: This iteration handled code cleanup only, not CLI wording.

## Handoff

- What.Next: Recheck docs and help text for stale width examples.
- Blocker.External: Need approval before changing public help output.
```

### Example C: Transcript Iterator

```md
# Iteration 014

## Summary

- Work.Done: Repaired section ordering in the current transcript.
- Issue.Found: Equation numbering is still missing on pages 12-14.
- Artifact.Used: Reused `workspace/pymupdf/blocks.jsonl` and rendered `workspace/pypdfium2/p0014.png`.
- Progress.Snapshot: References complete; figures complete; equations partially verified.

## Risk Flags

- Risk.Flag: Deleted 14 lines of duplicated OCR output and needs spot-checking.

## What Next

- What.Next: Recheck pages 12-14 against the PDF and resolve the remaining equation placeholders.
```

## Anti-patterns

- Do not dump raw chronology. Reports should preserve useful state, not every thought or command.
- Do not say something is still true unless it was actually rechecked.
- Do not silently replace earlier claims. Use explicit supersession when the meaning changed.
- Do not treat `What.Next` as binding. It is a suggestion for later iterations, not a command.
- Do not mark work as done if the report does not make the completion boundary clear.
