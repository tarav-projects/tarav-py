---
name: index-better-naming
description: >
  Scan the entire project's naming index — code identifiers (functions, globals,
  structs), file and folder names, and notes titles — to find names that are
  unclear, inconsistent with codebase conventions, or misaligned with the mental
  model they represent. Reports the top 5 most improvable names with
  explanations and proposed replacements. "Index" here means the project-wide
  knowledge graph of all named things, not the notes/index/ subsystem
  specifically (though notes/index/ names are included in the scan).
  Use when the user asks to review naming, find inconsistent names, or improve
  the project's naming quality.
user-invocable: true
disable-model-invocation: true
---

# Better Naming Review

Read and follow `skills/index-base/FOUNDATION.md` before proceeding.

Find the 5 names across the project that would benefit most from renaming —
for clarity, convention alignment, or both.

**Key constraints (aligned with foundation):**
- **Never modify any file** — analysis and reporting only
- Report is printed to chat only
- Be direct and concrete
- **Format exception:** this skill returns exactly 5 naming proposals

## Scope

The scan covers every named node in the project's knowledge graph:

- **Code identifiers** — functions, globals, constants, structs, type aliases,
  module names in all `.jl` files (`src/`, `scripts/`, `test/`).
- **File and folder names** — script files, source files, note files,
  directories.
- **Notes titles** — `notes/index/` entries, `notes/live/` entries, any
  markdown document titles.

## Ranking Criteria

A name is a candidate for improvement when it has one or both of:

1. **Pattern mismatch** — it breaks the codebase's own conventions.
   Examples: a global not in `ALL_CAPS`, a private function missing the `_`
   prefix, a script file not following the `NNN-kebab-name.jl` pattern, a note
   missing its numeric prefix.

2. **Clarity deficit** — the name is cryptic, ambiguous, or misleading
   regardless of convention. It does not communicate what the thing is or does
   to someone reading the code for the first time.

Both criteria are weighted equally. Use common sense to pick the 5 most
impactful cases — names that, if improved, would make the project noticeably
easier to navigate and understand.

## Workflow

### 1) Discover codebase conventions

Before judging names, build a picture of the project's naming patterns:

- Scan `src/**/*.jl` and `scripts/**/*.jl` for globals, functions, structs.
- Scan file and folder names across the repo.
- Scan `notes/index/` and `notes/live/` for title and filename patterns.
- Identify the dominant conventions:
  - Globals: `ALL_CAPS_SNAKE`
  - Public functions: `snake_case`
  - Internal functions: `_snake_case`
  - Mutating functions: `snake_case!`
  - Types: `PascalCase`
  - Script files: `NNN-kebab-name.jl`
  - JSON dict keys: `dot.namespaced.strings`
  - Notes: `NNN-kebab-name.md`
  - Section markers: `# MARK: Label`

Note any project-specific patterns that extend or override Julia defaults.

### 2) Collect all names

Build a flat list of every named thing with:
- **name** — the identifier, filename, or title
- **kind** — function, global, struct, file, folder, note, etc.
- **location** — `path:line` for code, path for files/notes

### 3) Evaluate each name

For each name, assess:
- Does it follow the codebase convention for its kind?
- Is it clear to a newcomer what it refers to?
- Does it align with how similar things are named in the project?
- Is there a better name that improves both consistency and clarity?

### 4) Rank and select top 5

From all candidates, pick the 5 most impactful. Prefer names that:
- Appear frequently or in prominent positions (exports, main scripts, index notes)
- Would cause the most confusion if misread
- Have an obvious, unambiguous improvement available

### 5) In-session deduplication

If this skill has already been invoked earlier in the same chat session,
exclude any names that were previously reported. Surface 5 **new** candidates
instead.

## Output Format

Print the report directly to chat. Do not write any file.

```
## Naming Review

### 1. `CURRENT_NAME` (kind) — location

**Issue**: [What is wrong — pattern mismatch, clarity, or both]

**Context**: [How the name is used, what convention it should follow, what
similar names look like in the codebase]

**Proposed**: `BETTER_NAME`

**Why**: [Concrete explanation of what improves — readability, consistency,
discoverability]

---

[repeat for issues 2-5]
```

## Constraints

- **Report only** — never rename anything automatically.
- **Respect the project's own conventions** — do not impose external style
  guides. The codebase's patterns are the standard.
- **Be specific** — every proposal must include a concrete new name, not just
  "rename this to something clearer."
- **No fluff** — explanations should be direct and technical.
- **5 issues exactly** — no more, no less. If fewer than 5 genuine issues
  exist, say so and report only what is real.
