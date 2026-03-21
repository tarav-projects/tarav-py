---
name: agentos-index-notes-file-organizer-auto
description: "Agentos Index Notes System: Scan index files for file-organization issues and propose file renames and block relocations with insertion hints"
user-invocable: true
disable-model-invocation: true
---

# Index File Organizer (Autonomous)

Read and follow `skills/agentos-index-note-base/FOUNDATION.md` before proceeding.

Scan index notes and propose three high-impact file-organization changes (file rename, block relocation, or creation of a new destination file).

**Key constraints (duplicated from foundation):**
- **Never modify any file** — analysis and reporting only
- Report is **printed to chat** (ephemeral), never saved to a file
- 3 findings, <10 lines each, bullet-point structured text
- Be direct — brevity over completeness

## Scope

- Scan **index files only**
- Focus on organization quality:
  - Filename clarity (does filename match contained blocks?)
  - Block placement (is each block in the most discoverable file?)
  - Missing file boundaries (would a new file improve retrieval?)

## Workflow

### Phase 1: Orient

1. Read `AGENTS.md` to locate the index root
2. If no index location is declared, print a short report stating it is missing and stop
3. Enumerate all index markdown files
4. Use `agentos mdblocks blocks` to map blocks (heading + body) with file paths/lines.
   - Example: `agentos mdblocks blocks <index-root> --min-level 2 --max-level 2 --json`
   - Use `agentos mdblocks links <index-root> --min-level 2 --max-level 2` when you need companion block links.

Use Glob, Grep, and Read tools for discovery and context loading.

### Phase 2: Score organization fit

For every block and file, score organization fit using these signals:

1. **Retrieval impact (highest priority)**
   - A developer is unlikely to find the block by guessing the current filename
2. **Filename-topic mismatch**
   - Dominant topics in file content diverge from the filename
3. **Cross-file fragmentation**
   - Related blocks are split across files with no clear boundary
4. **Evidence strength**
   - Clear textual evidence from headings, repeated keywords, and neighboring block themes
5. **Churn control**
   - Prefer changes that improve retrieval with minimal moves

### Phase 3: Select top 3 proposals

1. Rank candidates by retrieval impact first
2. Choose exactly 3 proposals total
3. Proposal types allowed:
   - File rename proposal
   - Block relocation proposal
   - New destination file proposal (with suggested filename)

### Phase 4: Report

Print one chat report with exactly 3 proposals.

````markdown
## Index File Organization Report

### Proposal 1: [short title]
**Type**
- `file-rename` | `block-relocation` | `new-file`
**Why this matters**
- [retrieval impact in one bullet]
**Change**
- [old -> new filename] OR [move block from A to B]
**Evidence**
- `path:line` — [supporting signal]
- `path:line` — [supporting signal]
**If block relocation**
- **Original block (verbatim):**
> [block text]
- **Destination insertion hint:**
```md
...
[text from destination]
<INSERT BLOCK HERE>
[more destination text]
...
```
---
### Proposal 2: ...
---
### Proposal 3: ...
````

## Reporting rules

- Keep proposals specific and executable by the user
- For relocation proposals, include:
  - source file path
  - destination file path (or proposed new file path)
  - exact insertion hint using `<INSERT BLOCK HERE>`
  - original block text quoted verbatim
- Do not ask questions in autonomous mode
- If no strong organization issues exist, still report the 3 best low-severity opportunities, clearly labeled as low priority
