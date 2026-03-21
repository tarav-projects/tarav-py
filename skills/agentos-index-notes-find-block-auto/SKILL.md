---
name: index-find-block-auto
description: "Index System: Find the most relevant index block from a user text description using agentos markdown block extraction"
user-invocable: true
disable-model-invocation: true
---

# Index Block Finder (Autonomous)

Read and follow `skills/index-base/FOUNDATION.md` before proceeding.

Find the best matching index block for a user-provided text description and return precise block references.

**Key constraints (duplicated from foundation):**
- **Never modify any file** — analysis and reporting only
- Report is **printed to chat** (ephemeral), never saved to a file
- Be direct — brevity over completeness
- **Format exception:** this retrieval skill returns 1 best match plus up to 2 alternatives (instead of 3-5 findings)

## Inputs

- User description text (natural language).
- Project index notes (`notes/index/` by default, or location from `AGENTS.md`).

If description text is missing or too vague, ask one short clarifying question and stop until the user responds.

## Workflow

### Phase 1: Orient

1. Read `AGENTS.md` to locate the index directory.
2. If not specified, assume `notes/index/`.
3. If index directory is missing, print a short report and stop.

### Phase 2: Retrieve Candidates (Required via agentos)

1. Run deterministic retrieval:
   - `agentos mdblocks find <index-root> --min-level 2 --max-level 4 --query "<user description>" --top-k 3 --json`
2. If the user explicitly requests regex matching, add `--regex` (and `--case-sensitive` only if explicitly requested).
3. Treat returned `matches` order as source of truth; do not implement custom reranking in this skill.
4. Use `matches[i].link` as the companion `path#Lline` reference.
5. Never paste full JSON payloads in chat; only emit final summarized matches.

### Phase 3: Select Output

1. If `match_count == 0`, report no confident match.
2. Otherwise:
   - Use `matches[0]` as best match.
   - Include up to 2 alternatives from `matches[1:]`.
3. Confidence labeling (deterministic):
   - `high`: only one match, or `score_1 >= 1.5 * score_2`
   - `medium`: `score_1 >= 1.15 * score_2`
   - `low`: otherwise

### Phase 4: Report

Print to chat in this format:

```markdown
## Index Block Finder Report

### Query
**Input**
- "[user description text]"
**Index root**
- `<index-root>`

### Best Match
**Location**
- `path/to/file.md:line`
**Companion link**
- `path/to/file.md#Lline`
**Score**
- `[numeric score from agentos output]`
**Confidence**
- `high|medium|low`
**Why this matches**
- [1-3 concise bullets]

### Alternatives
- `path/to/file.md:line` — [short rationale, include score]
- `path/to/file.md:line` — [short rationale, include score]
```

If no confident match:

```markdown
## Index Block Finder Report

No confident block match found for the given description.

Nearest candidates:
- `path/to/file.md:line` — [why it was close]
- `path/to/file.md:line` — [why it was close]
```
