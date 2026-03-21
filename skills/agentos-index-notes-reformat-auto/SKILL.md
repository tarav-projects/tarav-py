---
name: index-reformat-auto
description: "Index System: Review index notes for verbose or prose-y formatting and propose bullet-point reformat rewrites through in-chat report feedback loop"
user-invocable: true
disable-model-invocation: true
---

# Index Reformat Reviewer (Report-Feedback Loop)

Read and follow `skills/index-base/FOUNDATION.md` before proceeding.

Review index notes for formatting quality and propose rewrites toward short, direct, bullet-point structured text through an in-chat report-feedback loop.

**Key constraints (duplicated from foundation):**
- **Never modify any file** — analysis and reporting only
- Report is **printed to chat** (ephemeral), never saved to a file
- 3 findings max, <10 lines each, bullet-point structured text
- Be direct — brevity over completeness

## What "Bad Format" Means

Ranked by severity (worst first):

1. **Verbose** — says in 10 lines what could be said in 3
2. **Prose-y** — paragraphs instead of bullet-point structured text; long sentences instead of short direct ones
3. **Unstructured** — no subsections, everything in one blob

The goal is convergence: all notes should trend toward the same short/direct/focused style.

## Workflow

### Phase 1: Orient

1. Read the project's `AGENTS.md` to find the index location and structure
2. If `AGENTS.md` does not reference an index, ask the user where it is
3. Discover all index files (glob the index directory)
4. For block-level formatting analysis, use `agentos mdblocks blocks <index-root> --min-level 2 --max-level 6 --json` instead of manual ad-hoc block parsing.
5. Validate file naming:
   - Each index file must follow pattern `NNN-short-topic.md`
   - `NNN` must be zero-padded 3 digits in range `000-499`
   - If violations found, include them in the final report under a "Naming Issues" section
   - Example violations: missing prefix, wrong padding, out of range

### Phase 2: Exemplar

1. Read all index notes
2. Identify 1-2 notes that are **already well-formatted** — short, bullet-point, focused
3. These are your **style reference**. All rewrites must converge toward this style
4. Keep these exemplars in mind for Phase 4

### Phase 3: Scan

1. Score each note against the "bad format" signals (verbose, prose-y, unstructured)
2. Rank notes from worst to best formatting
3. Select the top 3 worst candidates
4. For each candidate, draft a proposed rewrite that:
   - Preserves all essential information
   - Removes padding, justifications, redundancy
   - Uses bullet-point structured text with meaningful indentation
   - Matches the exemplar style from Phase 2
   - Includes a loss-check note listing any information left out from the original block

### Phase 4: Report Proposal (First Output)

Print one full proposal report immediately in this format:

```markdown
## Format Review Report — Proposal

### Scan Summary
- **Notes scanned:** [count]
- **Style reference:** [exemplar note name(s)]
- **Candidates found:** 3 (ranked by severity)

### Naming Issues
[Include this section only if naming violations found]
- `filename.md` — [issue: missing prefix / wrong padding / out of range]
- `another-file.md` — [issue description]

---

### [Candidate 1 name]
**Location:** `file_path:line_number`
**Problem:** [one-line description — e.g., "verbose, 15 lines could be 5"]
**Status:** proposed
**Original block (to change):**
> [quoted original text]

**Proposal block (replace original with this):**
[rewritten version]

**Left-out information review:**
- **Lost information:** [none / list specific removed information]
- **Rationale:** [why removal is safe, or why proposal must be revised]

---

### [Candidate 2 name]
**Location:** `file_path:line_number`
...

---

### [Candidate 3 name]
**Location:** `file_path:line_number`
...
```

After printing the proposal, stop and wait for user feedback.
Do not ask questions.

### Phase 5: In-Chat Feedback Loop

Treat user feedback as direct report edits:

- If user requests changes to specific candidates, return only the updated candidate sections by default
- If user requests a full reprint, print the full report again
- If user provides rewrite text directly, treat that text as authoritative
- Keep the left-out information review updated after each revision
- If user approves/rejects candidates, update their `Status` in subsequent output
- Continue until the user says the review is complete
