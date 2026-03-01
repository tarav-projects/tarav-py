---
name: index-base
description: "Index System: Shared foundation for index maintenance agents. Use when creating, updating, or reviewing any `index-*` skill to enforce system-wide constraints, report format, and naming conventions."
---

# Index Base

Read and follow `skills/index-base/FOUNDATION.md` before proceeding.

Use this skill as the canonical baseline for all `index-*` skills.

## Workflow

### Phase 1: Load Foundation

1. Read `skills/index-base/FOUNDATION.md`
2. Treat it as the source of truth for index-system behavior

### Phase 2: Enforce Shared Constraints

1. Apply read-only behavior unless a skill explicitly states an exception
2. Keep reports in chat only; do not write reports to files
3. Keep findings concise, structured, and directly actionable

### Phase 3: Align Skill Design

1. Ensure new index skills follow `index-*` naming
2. Ensure each skill duplicates required key constraints inline
3. Ensure any deviation from the foundation is explicit and justified
