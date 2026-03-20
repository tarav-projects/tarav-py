---
name: index-drift-review
description: Review invariant/spec notes under notes/index/ against code, report significant drift in a numbered notes/live report.
user-invocable: true
disable-model-invocation: true
---

# Index Drift Review

Read and follow `skills/index-base/FOUNDATION.md` before proceeding.

## Goal
Evaluate invariants in `notes/index/*.md` against the codebase, report the most significant drift. Do not update specs or code; only write a single report file.

**Key constraints (aligned with foundation):**
- Do not modify index specs or application code
- **Explicit exception:** this skill writes exactly one report file under `notes/live/`
- Keep findings concise and evidence-based
- Be direct — brevity over completeness

## Live Note Dependency
When writing reports in `notes/live/`, use `live-note-base` protocol:
- Path and naming: `notes/live/NNN-short-topic.md`
- Number source: files matching `notes/live/NNN-*.md`
- Reserved range: `000-499` is human-managed
- Prefix CLI (terminal): `agentos prefix next --root . --include notes/live --min 500 --width 3`

## Inputs
- Notes: index root from `AGENTS.md` (default `notes/index/`), starting with `index.md` when present.
- Codebase: scan all source files unless the user provides narrower hints.
- Prior reports: read at least the last 3 files matching `^\d\d\d-index-drift-review\.md$` in `notes/live/` with numbers lower than the new report.

## Invariant Parsing
- Each `##` heading is one invariant.
- The heading text is the invariant name.
- The bullets under the heading are the invariant statements.
- Use `agentos mdblocks blocks <index-root> --min-level 2 --max-level 2 --json` to extract invariant blocks deterministically.
- Use `agentos mdblocks links <index-root> --min-level 2 --max-level 2` for companion block links (`path#Lline`).

## Workflow
1. Read `AGENTS.md` and resolve `<index-root>` (default `notes/index/`).
2. Read `<index-root>/index.md` first when present, then remaining index files.
3. Identify invariants and their statements from `agentos mdblocks blocks` output.
4. Scan code for evidence supporting or contradicting invariants. Use file path + line number as anchors.
5. Select up to 5 most significant drifts (use common sense; prioritize clear contradictions or repeated violations).
6. Find the next report number using `live-note-base`:
   - Run `agentos prefix next --root . --include notes/live --min 500 --width 3` from repo root.
   - Use the returned `NNN` directly.
   - Build target filename `notes/live/NNN-index-drift-review.md`.
7. Read at least 3 prior reports with smaller numbers (if available) to avoid repeating old known drift without new value.
8. Write the report to `notes/live/NNN-index-drift-review.md`.

## Output Rules
- Write exactly one file: `notes/live/NNN-index-drift-review.md`.
- Max 80 lines total.
- Include up to 5 drift findings.
- Each finding should include: invariant name, file:line, and 1–2 sentence rationale.
- No “no drift found” output. If nothing significant, keep the report minimal (title + short note that no significant drift was found).

## Constraints
- Do not modify specs or code.
- Do not run tests.
- Do not create backward-compat layers.
- Be portable: avoid assumptions specific to this repo beyond paths and numbering rules.

## Optional Hints
If the user provides target paths or modules, prioritize those while still checking global hotspots when relevant.
