---
name: agentos-iterator-base
description: "Define or review Agentos iterator skills: reusable skills that select a target, do one bounded iteration per run, inspect Authority.Surfaces for current truth, use Coordination.Surfaces for cross-iteration continuity, optionally consult Derived.Sources, and write Iteration.Report artifacts for later iterations. Use when creating, extending, or evaluating iterative, report-driven skill workflows."
---

# Agentos Iterator Base

Minimal base protocol for iterator-style skills.

## Scope

- Define what an iterator skill is.
- Define `Authority.Surfaces`, `Coordination.Surfaces`, and `Derived.Sources`.
- Define the minimal iteration contract that concrete iterator skills inherit.
- Define the concrete iterator-skill structure concepts `Target.Selection`, `Orientation.Policy`, and `Iteration.Workflow`.
- Organize reusable guidance as additive named catalogs.
- Provide current catalogs for orientation patterns and `Iteration.Report` patterns.
- This skill does not define report path, naming, numbering, or exact markdown layout.
- This skill does not define how many iterations a larger workflow should run.

## Core Concepts

- An iterator skill does one bounded iteration per invocation.
- A larger task may require many invocations of that skill across time.
- Each concrete iterator skill should declare its `Authority.Surfaces`.
- `Authority.Surfaces` are the declared sources of truth for current state.
- Each concrete iterator skill should declare its `Coordination.Surfaces`.
- `Coordination.Surfaces` are curated non-authoritative artifacts used to coordinate iterations, preserve progress, and reduce redundant work.
- Current coordination-surface inventory includes `Iteration.Report`.
- Each concrete iterator skill may declare its `Derived.Sources`.
- `Derived.Sources` are supporting sources fetched or generated for the current iteration.
- By default, `Derived.Sources` help interpret, verify, or fill gaps; they are not `Authority.Surfaces`.
- When `Coordination.Surfaces` conflict with `Authority.Surfaces`, `Authority.Surfaces` win.
- Each iteration should be contextualized by:
  - the current user request
  - the current task or repository state
  - the declared `Authority.Surfaces`
  - the relevant `Coordination.Surfaces`
  - any relevant `Derived.Sources`
- Each iteration should produce one new `Iteration.Report`.
- `Iteration.Report` means the report artifact concept, not one universal filename or file schema.
- An `Iteration.Report` is curated markdown for later agents, not a transcript of every intermediate thought.

## Concrete Skill Structure

- `Target.Selection` defines how one iteration chooses what it will work on.
- `Orientation.Policy` defines how one iteration builds context before acting, usually by selecting `Orient.*` patterns plus any family-specific rules.
- `Iteration.Workflow` defines the bounded per-invocation sequence of phases after target selection and orientation.
- These are structure concepts for concrete iterator skills, not catalogs.
- A concrete iterator skill may expose them as explicit headings or define them equivalently in another clear form.

## Iterator Contract

1. Read the current request and current task state first.
2. Resolve `Target.Selection`.
3. Apply `Orientation.Policy`, including `Orient.Authority` for the declared `Authority.Surfaces`.
4. Load the relevant `Coordination.Surfaces`.
5. Consult any relevant `Derived.Sources` when they materially help the current iteration.
6. Do one meaningful slice of work under the declared `Iteration.Workflow`.
7. Update authority-backed artifacts when that iterator family owns such edits.
8. Write one new `Iteration.Report` that preserves useful state and improves the next iteration.
9. Stop after that iteration. Do not continue into an implicit next pass.

## Report Guidance

- Concrete iterator skills own the exact report format.
- This base owns additive catalogs of reusable patterns, not a section template.
- Reports may have many sections. `What Next` and `What We Did` are common examples, not mandatory structure.
- Distinguish between durable iteration state and advisory handoff guidance, but do not force that distinction into fixed headings.
- Repetition is useful when it is confirmatory. If a later iteration rechecks something and it still holds, say so explicitly.
- If a later iteration changes or invalidates an earlier claim, say so explicitly.
- Treat prior reports as `Coordination.Surfaces`, not unquestionable truth.
- Treat prior handoff guidance as advisory. Current user intent and current evidence take priority.
- Cite an earlier report when practical if a statement is being reaffirmed or superseded.
- Use reports to coordinate iterations, preserve useful progress, and make later passes more accumulative and efficient.

## Child Skill Responsibilities

Each concrete iterator skill should define its own:

- `Authority.Surfaces`
- `Coordination.Surfaces`
- `Derived.Sources` when the iterator family uses them
- `Target.Selection`
- `Orientation.Policy`
- `Iteration.Workflow`
- iteration boundary: what counts as one iteration
- report location, naming, and numbering
- exact markdown schema
- required, optional, and disallowed report patterns
- any stronger supersession or citation rules needed by that iterator family

## Catalog Index

Catalogs are additive registries, not a closed taxonomy.

- `Orient.*` — patterns for building iteration context before acting. Current names include:
  - `Orient.Authority`
  - `Orient.ReportLatest`
  - `Orient.ReportSample`
  - `Orient.DiffRecent`
- `Iteration.Report` pattern catalog — patterns for what later iterations should learn from a report. Current names include:
  - `What.Next`
  - `Work.Done`
  - `Work.Skipped`
  - `Claim.StillTrue`
  - `Claim.Supersedes`
  - `Decision.Reinforcement`
  - `Question.Open`
  - `Blocker.External`
  - `Scope.Boundary`
  - `Issue.Found`
  - `Artifact.Used`
  - `Progress.Snapshot`
  - `Risk.Flag`

Read `references/iteration-orientation-patterns.md` for the orientation catalog.
Read `references/iteration-report-patterns.md` for the `Iteration.Report` catalog.

## Non-goals

- Do not define one universal `Iteration.Report` layout.
- Do not treat `Coordination.Surfaces` as a substitute for `Authority.Surfaces`.
- Do not treat `Derived.Sources` as `Authority.Surfaces` by default.
- Do not use reports as diary-style logs.
- Do not let old `What.Next` suggestions override the user's current request.
