---
name: index-toc-auto
description: "Index System: Generate a table-of-contents listing of all index files with one-sentence content summaries"
user-invocable: true
disable-model-invocation: true
---

# Index TOC Generator

Read and follow `skills/index-base/FOUNDATION.md` before proceeding.

Scan all files under the project's index directory and print a proposed table-of-contents section — a flat markdown list with a one-sentence content summary per file.

**Key constraints (duplicated from foundation):**
- **Never modify any file** — analysis and reporting only
- Report is **printed to chat** (ephemeral), never saved to a file
- Be direct — brevity over completeness

**Format exception:** Output is a plain markdown list (not the standard findings report format).

## Workflow

### Phase 1: Orient

1. Read the project's `AGENTS.md` to locate the index directory
2. If not specified, assume `notes/index/`
3. Read the current `index.md` file to understand existing structure

### Phase 2: Scan

1. Glob all files under the index directory (e.g., `notes/index/**/*.*`)
2. Exclude `index.md` itself from the list
3. For each file found, read its content

### Phase 3: Summarize

1. For each file, write a **single sentence** summarizing what the file covers
   - Base the summary on actual content, not just the filename or title
   - Keep it short — one line, no fluff
2. Use the file's path relative to the index directory (e.g., `patterns/naming.md`)

### Phase 4: Print

1. Print a heading: `## Index TOC`
2. Print the flat markdown list, one entry per file, sorted alphabetically by path
3. Format: `- **relative/path/file.md** — one-sentence hint`

## Output Example

```markdown
## Index TOC

- **architecture/boundaries.md** — Defines subsystem boundaries and allowed dependency directions
- **conventions/naming.md** — Naming rules for modules, types, and files across the codebase
- **decisions/blob-format.md** — Records the decision to use content-addressed blob storage
- **patterns/scope-navigation.md** — Describes the pattern for traversing nested project scopes
```
