---
name: index-discover-auto
description: "Index System: Scan codebase and notes to discover and propose new index block candidates — patterns, decisions, conventions not yet captured"
user-invocable: true
disable-model-invocation: true
---

# Index Discovery Scanner

Read and follow `skills/index-base/FOUNDATION.md` before proceeding.

Scan the full project (codebase + non-index notes) and propose 1 strong new index block candidate per run.

**Key constraints (duplicated from foundation):**
- **Never modify any file** — analysis and reporting only
- Report is **printed to chat** (ephemeral), never saved to a file
- **1 finding per run** (exception to the 3-5 default — focused output by design)
- Be direct — brevity over completeness

## What Makes a Good Candidate

Ranked by how much it would steer future development:

1. **Undocumented enforced pattern** — a pattern already followed consistently in code but not captured in the index
2. **Constraint in comments/notes** — a decision or rule mentioned in comments, docstrings, AGENTS.md, or `notes/**/*.md` but missing from the index
3. **Repeated convention** — naming, structure, error handling, or architectural pattern repeated enough to deserve formalization

The candidate must be something that, if a new developer joined, they'd need to know to avoid breaking the project's consistency.

## Workflow

### Phase 1: Orient

1. Read the project's `AGENTS.md` to find the index location and project structure
2. If `AGENTS.md` does not reference an index, note the absence in your report
3. Discover all index files (glob the index directory)
4. Discover non-index notes: glob `notes/**/*.md`
5. Discover source files: glob `src/**/*.jl`, `src/**/*.py`, `src/**/*.ts`, etc. — use whichever match

Use Glob, Grep, and Read tools — do NOT shell out to grep/find/rg.

### Phase 2: Index Scan

1. Read all existing index notes
2. Build a mental inventory of what's already captured — patterns, decisions, constraints, naming rules
3. This inventory is your "already known" set. The goal is to find something **not** in this set

### Phase 3: Discovery Scan

Scan these sources for candidates, in priority order:

**A. Codebase patterns**
- Look for repeated structural patterns (how modules are organized, how errors are handled, how APIs are shaped)
- Look for naming conventions followed consistently but not documented
- Look for constants, configuration patterns, or architectural boundaries that imply decisions

**B. Non-index notes (`notes/**/*.md`)**
- Read notes that are NOT part of the index
- Look for decisions, constraints, or patterns that belong in the index but were dumped in a note
- These are high-signal — the user wrote them down but hasn't promoted them yet

**C. Comments and docstrings**
- Search for `TODO`, `NOTE`, `IMPORTANT`, `CONVENTION`, `DECISION` in code comments
- Look for inline explanations of "why" that suggest an underlying rule

For each potential candidate, check against the Phase 2 inventory. Skip anything already captured.

### Phase 4: Rank

1. Score remaining candidates by:
   - **Steering power** — would this change how a developer writes new code?
   - **Specificity** — is it concrete enough to be a useful constraint?
   - **Evidence strength** — how clearly is the pattern demonstrated in the codebase/notes?
2. Select the single strongest candidate

### Phase 5: Report

Print to chat using this format:

```markdown
## Index Discovery Report

### Proposed Index Block
**Topic:** [short descriptive title]

[The proposed section note — ready to copy-paste into the index. <30 lines, bullet-point structured text, following the index style.]

---

**Evidence**
- `file_path:line_number` — [what this location demonstrates]
- `file_path:line_number` — [what this location demonstrates]
- [additional evidence as needed]

**Why this matters**
- [1-2 bullets on how this would steer future development]

**Suggested index location**
- [which index file this note would fit in, or "new file: <name>" if none fits]
```

If no strong candidate is found, print:

```markdown
## Index Discovery Report

No strong candidate found this run. The index appears well-aligned with the codebase.
```
