# Iteration Orientation Patterns

Named orientation catalog for iterator skills.

## Contents

- Usage
- Pattern Catalog
- Anti-patterns

## Usage

- Use these `Orient.*` names as shared documentation vocabulary for iterator skills.
- Orientation patterns describe what an iteration should inspect before acting.
- Orientation patterns may read both `Authority.Surfaces` and `Coordination.Surfaces`.
- Orientation patterns do not replace the need to inspect `Authority.Surfaces`.
- When orientation findings conflict, `Authority.Surfaces` win.
- Choose only the orientation patterns that materially improve the current iterator family.

## Pattern Catalog

### Orient.Authority

- Purpose: Inspect the declared `Authority.Surfaces` directly before trusting coordination history.
- Use when: the iterator family has authority-backed artifacts that define current truth.
- Avoid when: the iterator family genuinely has no declared authority surface for the current question.
- Example:

```md
- Orient.Authority: Read the current transcript and canonical PDF directly before trusting prior iteration reports.
```

### Orient.ReportLatest

- Purpose: Load the most recent coordination report fully before starting the current pass.
- Use when: the latest iteration is likely to contain the most relevant carry-forward context.
- Avoid when: there are no prior reports or the iterator family does not use reports.
- Example:

```md
- Orient.ReportLatest: Read `reports/iteration-014.md` fully before starting the current pass.
```

### Orient.ReportSample

- Purpose: Sample a small number of older coordination reports for broader context and drift detection.
- Use when: the latest report alone may hide repeated patterns, stale assumptions, or long-running blockers.
- Avoid when: the report history is very short or the extra sampling would not change prioritization.
- Example:

```md
- Orient.ReportSample: Also sampled `reports/iteration-006.md` and `reports/iteration-010.md` for repeated failure modes.
```

### Orient.DiffRecent

- Purpose: Inspect recent diffs on authority-backed artifacts before trusting coordination reports too much.
- Use when: the main artifact has changed across recent iterations, commits, or manual edits.
- Avoid when: the artifact is new, unversioned, or the recent history is irrelevant to the current pass.
- Example:

```md
- Orient.DiffRecent: Reviewed recent diffs on `library/foo/foo.md` to confirm the report history still matches the live transcript.
```

## Anti-patterns

- Do not skip `Orient.Authority` just because prior reports are detailed or recent.
- Do not use orientation patterns as a substitute for reading current authority-backed state.
- Do not treat the latest report as authoritative just because it is recent.
- Do not sample old reports mechanically when the iterator family has no meaningful history yet.
- Do not inspect diff history without tying it back to the current authority-backed artifact.
