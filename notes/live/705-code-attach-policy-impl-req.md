# Code Attach-Point Policy + illegal-attachment / missing-header — Implementation Request

## Impl.Abstract

- **Scope:** implement the file-level `Annotation.Point` policy for skw-code and its two linter checks — `illegal-attachment` and `missing-header` — over the code surfaces `agentos skw check` already scans.
- **Design (landed in the index this session):** `agentos-pkg/design/107` — `Annotation.Point` now carries: (a) sanctioned points are a **configurable policy the linter enforces** (allow-set + placement/cardinality/presence, strict defaults `skw.json` relaxes); (b) `illegal-attachment` = an annotation at a point outside the allow-set; (c) skw-code starts strict — file point, **line 1, exactly one, required** — off-line-1 or a second block is `illegal-attachment`, no line-1 block is `missing-header`.
- **Status:** READY. All design decisions are landed in 107 (anchors `^c20260723-4u/5u/6u/7u`); `--dev --auto`.
- **Source context:** session design + capture; `/agentos-hugentics-impl --capture --dev --auto`. Builds directly on 704 (skw-code backend + `non-skw-annotation`), same code-surface scan.
- **Out of scope:** the `skw.json` config surface that *relaxes* the policy (finer points, presence exemptions) — the policy is a **struct with strict defaults** now, config-loading is a future refinement; finer attach points (`def`/`class`/`module`) — not parsed yet, so nothing legally attaches below the file and every non-line-1 block is illegal; multi-language.

## Impl.Index

- **Current state (cited):**
  - `src/agentos/skillware/build.py` — `_code_surface_pois(skill_root)` (line ~863) already iterates managed code files (`_iter_code_files`, `"$kw"` prefilter, `parse_skw_code`, skips parse-error files) and emits `non-skw-annotation`. The new checks fold into this same pass.
  - `SkwSource` exposes `recipes`/`constructs`/`dependencies`, each an annotation block carrying a 1-based `.line` (its open line). A note-only `# $kw: --note` block is a `SkwConstruct(command="text")`; a void `--from` a `SkwDependency`.
  - `src/agentos/skillware/commands.py` — `POI_LEGEND` (kind → meaning+prescription); `_skw_check_kinds` derives `default_on = kind not in _SKW_DEFAULT_OFF_KINDS`; check-selection filters `report.pois` by kind.
  - `SUPPRESSIBLE_KINDS`/`BLESSABLE_KINDS` (build.py ~579) — the bless registry.
- **Design decisions:**
  - **policy as data:** a `CodeAttachPolicy` struct (`file_line=1`, `file_required=True`) with a `DEFAULT_CODE_POLICY` — the strict starting defaults, structured so config later overrides them rather than editing conditionals.
  - **enforcement:** for each managed file, enumerate block open lines. The line-1 block is the only legal attachment; every other block → `illegal-attachment`; a required-but-absent line-1 block → `missing-header`. Cardinality-one falls out (only line 1 is legal, and line 1 is a single line).
  - **defaults:** `illegal-attachment` and `missing-header` are **default-on** (structural policy defects, not advisory noise like `non-skw-annotation`), non-structural (skippable), and **not blessable** (resolution is fix-or-relax-config, not accept). Since nothing is skw-managed today, default-on is safe (no managed files → no POIs).

## Execution.Plan

Test-first at boundaries. Loop: `pytest tests/test_skw_code_check.py tests/test_skw_code_policy.py tests/test_skillware*.py`; completion runs full `pytest` + a live `agentos skw check` proof on a real skw-subsystem file.

### Slice 1 — `CodeAttachPolicy` + block enumeration + the two checks
- **Do:** add `CodeAttachPolicy`/`DEFAULT_CODE_POLICY` and a `_block_open_lines(source)` helper; extend the `_code_surface_pois` pass to emit `illegal-attachment` (each non-`file_line` block) and `missing-header` (required, no `file_line` block) alongside the existing `non-skw-annotation`.
- **Observable:** a managed file with a line-1 header → no policy POI; a mid-file-only block → both `missing-header` and `illegal-attachment`; a line-1 header + a second block → `illegal-attachment` only.
- **RED/GREEN:** `tests/test_skw_code_policy.py` covering the three cases above.

### Slice 2 — register the kinds (legend + defaults)
- **Do:** add `illegal-attachment` and `missing-header` to `POI_LEGEND` (meaning + prescription). They inherit `default_on=True` (not in `_SKW_DEFAULT_OFF_KINDS`), non-structural, non-blessable.
- **Observable:** `--list-checks` shows both as `[on] reportable`; a default `agentos skw check` reports them; `--skip` silences them.
- **RED/GREEN:** a selection test that both are default-on and skippable; the existing `non-skw-annotation` default-off test still holds.

### Slice 3 — realign the existing fixture
- **Do:** the `test_skw_code_check.py` `CODE` fixture has its annotation on line 2; under the new defaults that file is now a `missing-header`/`illegal-attachment`. Move the annotation to a line-1 header so the fixture is a *well-formed* managed file; update the `non-skw-annotation` line-key assertions.
- **Observable:** `test_skw_code_check.py` passes with the fixture clean of policy POIs.

### Slice 4 — prove on the skw subsystem + docs
- **Do:** add a real line-1 `# $kw:` `--note` header to `src/agentos/skillware/model.py` (the file that implements the carrier — best-grounded surface). Run `agentos skw check --skill src/agentos/skillware` (policy checks clean — header at line 1) and `--check non-skw-annotation` (the real comment residual). Update `AGENTS.md` with the two new kinds + the policy.
- **Observable:** the live run shows model.py's header legal (no policy POI) and its non-skw comment residual on opt-in — the first real skw-code annotation, checked end-to-end.

## Slice Status

- Slice 1 — `CodeAttachPolicy` + `_block_open_lines` + two checks — ✅ 5 tests
- Slice 2 — POI_LEGEND + default-on/non-blessable — ✅ 2 selection tests; `--list-checks` shows `[on]`
- Slice 3 — realign existing fixture (header→line 1) — ✅
- Slice 4 — proof on `model.py` + AGENTS.md — ✅ first real skw-code annotation, 0 policy POIs, 22 non-skw residual

## Impl.Log

- Developed under `--capture --dev --auto`. Design fully pre-landed in 107; checkpoint `ef8f48f` is the rollback floor.
- **Discovery bug found + fixed (in-scope).** `missing-header` reasoning over `model.py` exposed that the `"$kw" in text` prefilter is too loose: `build.py`/`commands.py` mention `$kw` in *strings* (the POI prescription text) but carry no machinery, so they would falsely trip `missing-header`. Tightened discovery — a surface is managed iff `parse_skw_code` yields ≥1 real block (`if not block_lines: continue`); mention-only files are skipped. Added a regression test. This also correctly narrowed `non-skw-annotation` (mention-only files no longer flag their comments).
- **Proof.** `model.py` carries the first real skw-code annotation (a line-1 `--note` header, `^c20260722-24u`). Over real `src/agentos/skillware/`: `model.py` managed, **0 policy POIs** (header legal at line 1), 22 `non-skw-annotation` residual (default-off, silent); `build.py`/`commands.py` correctly unmanaged (no false positives). Import intact (docstring survives the leading comment).
- **CLI boundary noted (not a bug).** The code-surface scan rides `check_skill`, which requires a `.skw/` package — so code surfaces are checked as members of a `Skw.Package`, not standalone. `src/agentos/skillware/` isn't itself a package, so the proof ran the library entrypoint directly. Making agentos-py (or a subtree) a package to dogfood via the CLI is a separate adoption step.
- Result: full suite **474 passed** (+7). Slice 4's `model.py` annotation is a real production edit, left uncommitted for review, trivially revertible.
