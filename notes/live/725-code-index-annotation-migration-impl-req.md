# Code–Index Annotation Migration — Impl.Req

## Impl.Abstract

- Status: implemented and verified.
- Scope: resolve the 941 strict Python code-surface POIs and make every selected source file declare at least one verified dependency on the Index design it implements or supports.
- Source authority: autonomous implementation request to address the complete inventory and attach code to its supporting Index concepts. ^c20260811-73u
- Baseline checkpoint: `7be64fb`.
- Out of scope: new annotation points below the file level, non-Python language backends, changing Index content, and converting ordinary comments into docstrings merely to evade the strict policy.

## Impl.Index

### Code.Design.Dependency

- Every configured Python file has exactly one file-level Skw annotation opening on line 1.
- Every file annotation declares one or more `--from` edges to the narrowest existing Index concepts that materially govern the file. Generic dependencies are used only when no more specific indexed design exists.
- The project `.skw/skw.json` declares the engaged core, Chatlas, Canvas, and Iterante Index depots. Code annotations remain provider- and language-neutral Dotted.Name edges; depot paths are project configuration rather than source-code knowledge.
- Dependency validity is a durable linter invariant: a selected file with no design dependency, an unresolved dependency, or a dependency colliding across engaged depots remains a POI.

### Comment.Leak.Resolution

- Ordinary prose, headings, separators, and inline explanations are removed or made unnecessary by clearer code structure and naming.
- Comments consumed by another tool may remain only as exact, content-sensitive `Non.Skw.Annotation` blessings. The lock records individual occurrences; there is no kind-wide or pattern-wide exception.
- Existing off-file Skw declarations are merged into the line-1 file annotation so their dependencies and grounding survive at the only currently legal `Annotation.Point`.
- Existing annotation dependencies are preserved when they remain honest, refined where a narrower Index concept exists, and never copied decoratively.

### Shared.Dependency.Engine

- Code dependency policy lives in the language-neutral code-surface engine. Language backends continue to supply only host parsing and comment tokens.
- Project configuration supplies the engaged depots once for every configured language. Adding another language reuses dependency resolution, collision handling, POI identity, and reporting without adding language branches.
- Project checks resolve annotations against actual Index blocks rather than trusting text-shaped Dotted.Names.

## Impl.Agendix

- touched: ^c20260811-73u — execution authority and whole-inventory acceptance target.
- touched: `index://tarav-pkg/Agentos.Skillware` — code is a managed Skillware product surface.
- touched: `index://tarav-pkg/Skw.Ann.Dependency` — `--from` expresses the code surface's declared dependency.
- touched: `index://tarav-pkg/Skw.Network` — dependency edges must resolve through engaged depots.
- touched: `index://tarav-pkg/Annotation.Point` — the file point is the universal and currently sole legal code attachment.
- touched: `index://tarav-pkg/Non.Skw.Annotation` — unannotated comments are review POIs, with exact blessing for justified foreign-tool directives.

## Execution.Plan

### Slice 1 — Enforced Index dependencies

- Status: completed.
- RED: prove that a header without `--from`, an unresolved Dotted.Name, and a depot collision currently pass the code check.
- GREEN: add shared dependency findings, connect project depots to the code engine, and configure the maintained Index depots.
- Check: focused code-policy, project-check, and CLI report tests.

### Slice 2 — File attachment migration

- Status: completed.
- GREEN: inventory source modules by subsystem, add or repair line-1 annotations, preserve legitimate existing grounding, and attach each file to its closest supporting concepts.
- Check: all selected files have one line-1 annotation, at least one dependency, and no missing, illegal, unresolved, or colliding dependency POIs.

### Slice 3 — Comment migration and exact exceptions

- Status: completed.
- GREEN: remove ordinary comments and separators, improve code where commentary masked unclear structure, and exactly bless only required foreign-tool directives.
- Check: zero active `Non.Skw.Annotation` findings; lock entries correspond only to present, reviewed comments.

### Slice 4 — Whole-system closure

- Status: completed.
- Check: live `agentos skw check`, full tests, Ruff, `git diff --check`, package build, isolated wheel import, editable reinstall, and installed CLI smoke.

## Impl.Log

- 2026-08-11 — Execution gate registered as ^c20260811-73u.
- 2026-08-11 — The completed strict-linter foundation was checkpointed as `7be64fb` before migration edits.
- 2026-08-11 — Baseline inventory is 353 files and 941 active POIs: 209 missing headers, 718 non-Skw comments, and 14 illegal attachments.
- 2026-08-11 — Completion deliberately adds dependency validation; merely placing syntactically valid `--from` text on every file would not prove attachment to the Index.
- 2026-08-11 — Dependency validation now reports a missing file-level `--from`, an unresolved concept, and a concept collision through the shared code-surface engine; the Python backend remains host-syntax-only.
- 2026-08-11 — The project engages the core Agentos, Chatlas, Canvas, and Iterante depots. All 354 selected files declare at least one dependency that resolves exactly once.
- 2026-08-11 — The Index resolver now limits inline definitions to design/index chapters, preventing POI description prose from falsely defining foreign concepts.
- 2026-08-11 — All 718 ordinary-comment findings were reviewed mechanically by token class: prose, headings, separators, and inline explanations were removed; 28 foreign-tool directives remain as exact content-and-location blessings in `.skw/lock.json`.
- 2026-08-11 — Installed project check proves zero code-surface POIs across 354 files. The 11 separately reported edition-history POIs predate and remain outside this migration scope.
- 2026-08-11 — Verification passed: 1,814 tests, Ruff over `src` and `tests`, `git diff --check`, wheel/sdist build, isolated wheel import, editable reinstall, installed CLI version/help, and installed code-surface check.
