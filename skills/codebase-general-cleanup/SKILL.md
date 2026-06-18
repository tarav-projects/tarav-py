---
name: agentos-codebase-general-cleanup
description: Improve a git-tracked codebase in place by making targeted cleanup refactors. USE WHEN the user wants the agent to simplify code, reduce duplication, address SSOT or DRY violations, remove poor abstractions, centralize repeated knowledge, tighten boundaries, or generally clean up a repository after implementation; create a checkpoint commit before editing, apply the improvements, and summarize the results.
---

# Codebase General Cleanup

Improve the current repository directly. Do not stop at an audit unless blocked. The default outcome is edited code plus a short summary of the changes and rationale.

Default assumption: backward compatibility is not a goal unless the user explicitly asks for it. If an old abstraction, interface, or implementation should be replaced, replace it instead of preserving it behind compatibility layers.

This is a `Batchy.Skill` — called like a terminal command. Load `agentos-skills-base` for the full convention.

- `-h` / `--help` prints the help into the chat instead of running (`Batchy.Skill.Help`).
- supplied flags resolve to the `Skill.Arg` names below; a bare path is `--codebase`.

## Skill.Arg.Section

### Skill.Arg:Target.Codebase
- the git-tracked repository to clean in place
- required: false
- default: the current repository
- help: "the repository to clean"
- examples: --codebase "./my-repo"

### Skill.Arg:Alignment.Mode
- whether the agent prompts at each `Alignment.Checkpoint` or resolves them itself and runs end-to-end
- required: false
- default: Interactive
- type: switch
- help: "run autonomously instead of prompting at checkpoints"
- examples: --AUTO

## Cleanup Model

Use these dimensions internally to decide what to improve:

- SSOT: centralize repeated knowledge such as constants, paths, config keys, branching rules, and helper logic.
- DRY: remove repeated code when the shared abstraction is clearer than the duplication.
- Design clarity: reduce boundary leakage, unclear ownership, needless indirection, and dead layers.
- Maintainability: improve naming, file organization, API shape, error handling, and local complexity.
- Safety: prefer small and reversible refactors over speculative rewrites.

Only act on changes that improve the repo under its current architecture. Respect existing style and conventions, but treat public interfaces as replaceable unless the user explicitly asks for backward compatibility.

## Workflow

### 1. Reconstruct local context

- Inspect repo structure, primary languages, tooling, tests, and `git status`.
- Identify a small set of high-value cleanup candidates.
- If nothing is clearly worth changing, stop and say that no cleanup was justified.

### 2. Choose a scoped cleanup set

- Prefer 1-3 coherent cleanup themes that can be verified together.
- Prioritize repeated knowledge, bypassed abstractions, dead code, oversized functions, and confusing module boundaries.
- Avoid broad rewrites, repo-wide renames, or architecture migrations unless the user asked for them.

### 3. Create a checkpoint commit before the first edit

- This commit is mandatory before any file modification.
- Analyze first; do not create a checkpoint until you are confident you will edit files.
- If the worktree is dirty, create a checkpoint commit that captures the repo exactly as found.
- If the worktree is clean, create an empty checkpoint commit so there is an explicit rollback point.
- Use a clear message such as `chore: checkpoint before codebase-general-cleanup`.
- If the repo is not a git repo, has unresolved conflicts, or the checkpoint commit fails, stop and explain the blocker.

### 4. Apply improvements

- Make the smallest change set that resolves the selected cleanup theme.
- Prefer extracting or reusing existing helpers over creating new abstractions.
- Prefer centralization over indirection.
- Prefer replacing obsolete code over preserving legacy compatibility paths.
- Delete dead code only when confident it is unused or clearly replaced.
- Do not keep legacy APIs, adapters, flags, or transitional glue unless the user explicitly requests backward compatibility.
- Keep touched files internally consistent.

### 5. Validate

- Run the narrowest relevant verification for the changed area: tests, linters, type checks, build steps, or focused commands.
- Fix any issues introduced by the cleanup.
- If verification cannot be run, say so explicitly.

### 6. Finish

- Leave the cleanup changes in the worktree unless the user asked for a final cleanup commit.
- Summarize what changed, why it was worth doing, what verification ran, and any remaining risk.
- Mention the checkpoint commit so the user can roll back easily.

## Constraints

- Do not produce a long findings report before acting unless the user explicitly asks for one.
- Do not touch unrelated files just because they look messy.
- Do not replace understandable duplication with an abstraction that is harder to read.
- Do not introduce new frameworks or cross-cutting patterns just to clean up local code smells.
- Prefer module-local helper extraction before creating broad utility layers.
- Do not spend effort preserving backward compatibility by default. Replace outdated interfaces cleanly when reimplementation is the better design.
- If the repository state is unsafe for automatic work, stop early with a concrete explanation.

## Response Shape

After the cleanup work, respond with a concise summary that includes:

- what you changed
- why those changes were chosen
- what verification ran
- the checkpoint commit details
