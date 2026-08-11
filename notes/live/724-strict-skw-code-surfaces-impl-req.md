# Strict Skw Code Surfaces — Impl.Req

## Impl.Abstract

- Status: implemented and verified.
- Scope: make project-configured code files first-class Skw lint surfaces; report every selected file without its required file annotation and every Python comment token outside Skw machinery.
- Source authority: autonomous implementation request for a shared language-neutral engine, Python as the first language backend, and project-owned target selection. ^c20260811-66u
- Baseline checkpoint: `ae6944a`.
- Out of scope: annotating the existing findings, allowing ordinary comments, docstring policy, function/class annotation points, JavaScript or other language implementations, automatic remediation, and compatibility aliases for the old implicit code scan.

## Impl.Index

### Project.Code.Surface

- `.skw/skw.json` gains `code_surfaces`, a list of typed selectors. Each selector contains `language`, one or more project-relative `include` glob patterns, and optional project-relative `exclude` glob patterns.
- The existing top-level `surfaces` key retains its current meaning: explicit nested `Skw.Package` roots. Code targets are separate because files and package roots have different selection and checking semantics.
- Selection is explicit and project-relative. A file becomes governed because the project config selects it, not because its content happens to mention `$kw`.
- `agentos-py` initially selects `src/agentos/**/*.py` as Python. The resulting POIs are a migration inventory, not an implicit baseline acceptance.
- Invalid selectors, unsafe paths, unsupported languages, duplicate ownership, and patterns matching no files fail at configuration/model construction rather than disappearing from the lint report.

### Code.Surface.Model

- A language-neutral core owns selector expansion, normalized source-file/comment models, attachment policy evaluation, machinery-span exclusion, and POI production.
- A language backend owns host syntax only: recognized file suffixes, source decoding/tokenization, and the carrier/parser that produces the Skw floor model.
- The Python backend uses the standard tokenizer so `Non.Skw.Annotation` sees full-line and inline comments while ignoring `#` inside strings and docstrings.
- Backend registration is explicit. Adding a language means registering another backend against the shared protocol; it does not add language branches to the lint engine.

### Strict.Code.Policy

- The initial code policy has one sanctioned `Annotation.Point`: exactly one file block opening at line 1, required for every configured file.
- A configured file without a line-1 block emits `missing-header`, even when it contains no Skw machinery.
- Every additional or off-line block emits `illegal-attachment`.
- Every host comment token not wholly occupied by Skw machinery emits `non-skw-annotation`, including shebangs, encoding declarations, tool directives, section headings, separators, inline comments, and prose comments.
- There is no initial allowlist. Exceptional occurrences use exact, content-sensitive POI blessing; changed or moved comments become visible again.
- `non-skw-annotation` is enabled by default. Strictness is the selected surface contract, not an opt-in diagnostic.
- The code carrier recognizes only syntactically plausible named flags after `--`; decorative separator comments are ordinary comments rather than malformed Skw flags.

### Project.Check.Integration

- Project-scope `agentos skw check` evaluates configured code surfaces even when the project root has no `.skw/src` build package.
- The structured and text reports identify code-surface POIs separately from nested package and edition-history POIs while sharing the ordinary POI catalog, diagnostics, selectors, and exit semantics.
- Project code blessings are stored in the project `.skw/lock.json`; an exact `--poi` resolution is supported at project scope. Bulk blessing `Non.Skw.Annotation` is not supported because it would convert a strict review boundary into an accidental baseline.
- Package build/check behavior no longer performs the old content-triggered recursive Python scan. Code linting is driven by explicit project configuration through the shared engine.

## Impl.Agendix

- touched: ^c20260811-66u — autonomous implementation authorization and strict project-surface requirements.
- touched: `index://agentos-pkg/Agentos.Skillware` — codebases are product surfaces within the general Skillware system.
- touched: `index://agentos-pkg/Skw.Backend` — the backend owns carrier and host syntax while the Skw frame and policy engine remain shared.
- touched: `index://agentos-pkg/Annotation.Point` — skw-code begins with one required file point at line 1.
- touched: `index://agentos-pkg/Non.Skw.Annotation` — non-Skw comments are reviewable leak-prevention POIs.
- touched: `index://agentos-pkg/POI.Linter` — the tokenizer/parser model is produced before policy checks emit POI instances.

## Execution.Plan

### Slice 1 — Configured surface model

- Status: completed.
- RED: config tests reject malformed/unsafe entries and prove the current parser cannot represent typed code surfaces.
- GREEN: add `CodeSurfaceConfig` parsing and deterministic project-relative expansion with a backend-neutral registry contract.
- Check: configuration and selector tests.

### Slice 2 — Shared strict engine and Python backend

- Status: completed.
- RED: configured unannotated files, inline comments, separators, shebangs, and malformed machinery expose the missing behavior; strings containing `#` remain clean.
- GREEN: add the shared floor/check engine, Python tokenizer backend, strict attachment rules, parser POIs, and the narrowed code-carrier flag grammar.
- Check: focused backend, policy, POI identity, and blessing tests.

### Slice 3 — Project linter and CLI

- Status: completed.
- RED: a config-only project cannot currently report code POIs or bless an exact project occurrence.
- GREEN: integrate code results into `ProjectCheckReport`, CLI text/JSON domains and diagnostics, default check selection, and project lock suppression/blessing.
- Check: project-check and CLI end-to-end tests.

### Slice 4 — Agentos adoption and closure

- Status: completed.
- GREEN: configure `agentos-py`'s Python source tree, update maintained architecture/guidance, inventory actual POIs, and remove obsolete implicit-scan documentation and tests.
- Check: all Skillware and CLI tests, full suite, Ruff, `git diff --check`, package build, installed CLI smoke, and live `agentos skw check --json` inventory.

## Impl.Log

- 2026-08-11 — Execution authorization resolved through ^c20260811-66u; explicit target configuration replaces content-triggered opt-in.
- 2026-08-11 — Design keeps existing `surfaces` package-root selection intact and introduces typed `code_surfaces` because package discovery and source-file linting are different domains.
- 2026-08-11 — Strict means no automatic comment exceptions. Python tokenization supplies the dependable comment floor; the shared linter decides annotation and attachment policy.
- 2026-08-11 — Mandatory pre-implementation checkpoint created as `ae6944a`; all code-surface implementation remains uncommitted for review.
- 2026-08-11 — RED proved typed config, config-only project checks, unannotated-file coverage, and inline-comment detection were absent. GREEN introduced an immutable backend registry, shared selector/policy model, and Python tokenizer/carrier adapter.
- 2026-08-11 — Python tokenizer-confirmed comment lines now constrain the code carrier, preventing `$kw`-looking lines inside multiline strings from entering the Skw floor model.
- 2026-08-11 — The md-library transcript-linter reference audit confirmed the identity choice is deliberately stricter here: comment text and line/column participate in the POI identity, so both edits and moves reopen review; exact project blessings remain separate from the active report.
- 2026-08-11 — `agentos-py` inventory: 353 configured Python files, 941 active code POIs — 209 `missing-header`, 718 `non-skw-annotation`, and 14 `illegal-attachment`; none were auto-baselined.
- 2026-08-11 — Verification passed: all 1,810 tests, Ruff over `src` and `tests`, `git diff --check`, wheel/sdist build, isolated wheel import, editable reinstall, CLI help/version, and installed project-check inventory.
