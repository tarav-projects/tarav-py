# Index Linter: agendix surfaces invisible to --scope - issue

## Issue.Abstract

- **symptom:** `agentos index linter --depot <depot> --scope <depot>/agendix[/file.md]` fails with `Index.Linter/Surface.Invalid — Configured --scope path matches no configured linter file`, even though the depot-wide run does lint agendix files.
- **status:** open
- **found:** 2026-07-15, during an agendix capture verification pass on the `agentos-pkg` depot (`agendix/Normalization.Pipeline::Account.Usage.Model-agendix.md`).

## Repro

```
cd agentos-md
agentos index linter --depot skills/agentos-pkg
# → 0 errors, 20 checks passed (agendix typed-line/anchor checks included)

agentos index linter --depot skills/agentos-pkg --scope skills/agentos-pkg/agendix
# → [ERROR] Index.Linter/Surface.Invalid @ skills/agentos-pkg/agendix
```

Same error when scoping to an individual agendix file. Scoping to `design/` or `appendix/` paths works.

## Root.Cause

- agendix files are discovered late, directly in the typed-files pass (`agentos/index/linter.py:1331-1339`): `agendix/` dirs are derived from appendix/depot paths and globbed into `typed_files` with kind `"agendix"`.
- they are never added to `state.surfaces` or `state.files_by_kind` — the JSON `files` inventory lists only `index` and `appendix`.
- `_check_scope_paths` (`linter.py:773`) validates `--scope` against exactly those two collections, so any agendix path is "no configured linter file" → hard error.
- consequence beyond the error: even if the error were suppressed, scope filtering (`_rel_path_in_scope`) would work — findings carry rel paths — but the inventory/validation layer rejects the scope before that matters.

## Expected

- agendix surfaces are first-class linted surfaces (typed-line syntax, `AS:` placement, agendix anchor coverage, grounding provenance all run over them) — `--scope` should accept them like any other linted file, and the `files` inventory should report them under a `agendix` kind.

## Fix.Sketch

- register discovered agendix dirs/files in `files_by_kind["agendix"]` (and optionally as surfaces) at discovery time, so `_check_scope_paths` and the JSON inventory see them; no change to check behavior itself.
