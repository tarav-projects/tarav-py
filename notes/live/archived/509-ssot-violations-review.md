# SSOT Violations Review (Codebase Quality Pass)

## Context
- Review date: 2026-03-01
- Scope: `src/agentos` SSOT-focused quality review
- Goal: identify duplicated knowledge and bypassed canonical interfaces

## Top Findings
1. Scope values are duplicated in CLI argument declarations instead of using one authority.
2. Storage subpaths (`tapes`, `indexes`, `tmp`) are re-constructed in multiple modules.
3. Exclude matching logic is duplicated between `mdblocks` and `prefix` scanners.
4. `git_line_span` payload schema is manually rebuilt in many `refs` handlers.
5. Span validation logic is partially duplicated in `git-refs from-span`.

## Evidence Anchors
- `src/agentos/_core/project.py` defines `SCOPE_VALUES` and canonical storage path maps.
- `src/agentos/system/commands.py` and `src/agentos/tape/commands.py` repeat scope literals and storage joins.
- `src/agentos/mdblocks/core.py` and `src/agentos/prefix/core.py` contain near-identical exclude helpers.
- `src/agentos/refs/commands.py` repeats the same reference payload structure at multiple command handlers.
- `src/agentos/_core/utils.py` already provides `_validate_span`, but `refs` command layer repeats checks.

## Prioritized Improvements
1. Centralize parser scope choices on `SCOPE_VALUES`.
2. Add a scoped storage-path resolver and remove manual path joining in command modules.
3. Extract shared path-exclude matcher utility for scanner modules.
4. Add a single `git_line_span` payload builder in `refs`.
5. Keep span validation in one place by relying on `_validate_span`.

## Expected Impact
- Lower maintenance risk when changing path/scope behavior.
- Fewer drift bugs between command modules.
- Cleaner internals with clearer single ownership for domain rules.
