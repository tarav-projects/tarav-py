---
name: index-ssot-check
description: "Index System: Scan codebase for Single Source of Truth violations — duplicated knowledge, bypassed interfaces, magic values"
user-invocable: true
disable-model-invocation: true
---

# SSOT Checker

Read and follow `skills/index-base/FOUNDATION.md` before proceeding.

You scan for **Single Source of Truth (SSOT) violations** — places where the same knowledge is encoded in multiple locations instead of being centralized.

**Key constraints (duplicated from foundation):**
- **Never modify any file** — analysis and reporting only
- Report is **printed to chat** (ephemeral), never saved to a file
- 3-5 findings, <10 lines each, bullet-point structured text
- Be direct — brevity over completeness

## Workflow

### Phase 1: Orient

1. Read the project's `AGENTS.md` to understand the codebase structure and locate the index
2. Use Glob to discover source files (try `src/**/*.jl`, `src/**/*.py`, `src/**/*.js`, `src/**/*.ts`, `src/**/*.go`, `src/**/*.rs` — use whichever match)
3. Skim the index to understand what patterns/decisions the user has already documented
   - This gives you context for what "should" be centralized

Use Glob, Grep, and Read tools — do NOT shell out to grep/find/rg.

### Phase 2: Scan for violations

Check these categories, in priority order:

**A. Bypassed interfaces (highest priority)**
- If a centralized function/constant exists, search for code that constructs the same value without using it
- Cross-reference the index: if the index declares "use X for Y", check if code actually does

**B. Repeated path construction**
- Search for path-building functions (`joinpath`, `path.join`, `os.path.join`, `Path(`, etc.)
- Flag when 2+ files construct the same path independently

**C. Magic strings**
- Repeated domain-specific string literals (file names, config keys, status values) in 3+ locations
- Ignore trivial strings (`"w"`, `"r"`, `"utf-8"`, `""`, `"/"`, `"\n"`)

**D. Magic numbers**
- Numeric literals in multiple files with domain meaning (ports, timeouts, thresholds)
- Ignore 0, 1, 2 and standard mathematical constants

**E. Duplicated logic**
- Functions with similar names/signatures across files
- Same multi-line pattern or conditional logic repeated in 2+ places

**F. Index-codebase drift**
- Patterns declared in the index that the codebase no longer follows
- Centralized decisions in the index that have been silently bypassed

### Phase 3: Rank and select top 3-5

Score by judgment, not formula:
1. **Bypasses existing interface** — always ranks first
2. **Index-codebase drift** — the index says one thing, code does another
3. **Frequency** — more duplicate locations = higher priority
4. **Blast radius** — paths, config, core domain > cosmetic duplication
5. **Specificity** — concrete and fixable > vague patterns

Only include findings you are confident about — precision over recall.

### Phase 4: Report

Print to chat using foundation report format:

```markdown
## SSOT Check Report

### [Finding title]
**Where**
- `src/Foo.jl:12`, `src/Bar.jl:45`
**Issue**
- What knowledge is duplicated and why it matters
  - Supporting detail if needed
**Proposal**
- Concrete suggestion: name the function, constant, or module to extract

### [Next finding]
...
```

## Report Example

```markdown
## SSOT Check Report

### Session directory path built in 3 places
**Where**
- `src/Recorder/session.jl:28` — builds `joinpath(root, "sessions", label)`
- `src/Core/query/loaders.jl:15` — builds `joinpath(root, "sessions", label)`
- `src/Core/project.jl:42` — has `session_dir(root, label)` helper
**Issue**
- Two files construct the session path manually instead of using the existing `session_dir` helper
  - Changing the directory structure requires editing 3 files instead of 1
**Proposal**
- Replace manual `joinpath` calls with `session_dir(root, label)` from `project.jl`

### Tape file extension hardcoded as magic string
**Where**
- `src/Recorder/pipeline.jl:55`, `src/Core/query/loaders.jl:31`, `src/Core/json.jl:12`
**Issue**
- The string `".tape.jsonl"` appears in 3 files with no shared constant
  - Renaming the tape format requires a multi-file hunt
**Proposal**
- Define `const TAPE_EXT = ".tape.jsonl"` in `types.jl` or `project.jl`

### Index says "use full qualified names" but 4 files use bare imports
**Where**
- `src/Recorder/macros.jl:3`, `src/Recorder/session.jl:1`
- Index: `AGENTS.md` line 5: "Use full qualified names in code"
**Issue**
- Index declares a naming convention that parts of the codebase don't follow
  - This is index-codebase drift — the constraint exists but isn't enforced
**Proposal**
- Replace bare `using` with qualified access in the flagged files
```

If the codebase is clean, print a short "No significant SSOT violations found" message.
