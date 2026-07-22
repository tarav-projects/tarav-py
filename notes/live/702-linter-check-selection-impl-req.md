# Linter Check Selection — Implementation Request

## Impl.Abstract

- **Scope:** a system to control which checks a linter run performs, with **both include and exclude** semantics, wired to the `agentos index linter` command surface.
- **What:** each `LinterCheck` gains a default enablement and an addressable short selector; a resolver computes the enabled set from a default-on baseline plus caller include/exclude; `run_linter` runs only the enabled set; the CLI grows `--check` (enable, incl. default-off), `--skip` (disable), and `--list-checks`. As the first concrete customer, the correct-but-noisy `dangling-mention` check is registered **default-off**, retiring its DORMANT/uncallable state.
- **Status:** IMPLEMENTED (`--develop --AUTO`). All 5 slices done; full `agentos-py` suite 445 passed; `agentos index linter --list-checks` renders; default run on real `agentos-pkg` unchanged (0/0, 22 passed), `--check dangling-mention` opts into the ~106 advisory dangling findings, `--skip <reportable>` drops it cleanly, structural checks resist `--skip`, unknown selectors error.
- **Source context:** design discussion this session. Grounding: `^c20260722-17u` (the feature — control which checks run or ignore), `^c20260722-18` (ordering — include+exclude semantics, connect to the command surface).
- **Out of scope:** a ruff-style "select replaces defaults" allowlist mode (`--only`); porting selection into the shared `skwlint` core for the skw linter too (noted as the natural follow-up — this cut lands it in the index linter's run machinery, kept as a small reusable helper); closing the `dangling-mention` resolver gap (Impl.Req 700/701, unchanged).

## Impl.Index

- **Current state (cited):**
  - `src/agentos/index/linter.py` — `LinterCheck` (`code`, `title`, `gate`, `run`); the flat `CHECKS` tuple; `run_linter(config, …, *, extra_checks=())` runs `(*CHECKS, *extra_checks)`, each subject only to its `gate`. No selection exists. `warn_unlinked` is the sole precedent: an ad-hoc boolean toggling one check family.
  - `src/agentos/index/commands.py` — `_cmd_linter` + `linter_parser`; existing repeatable append args (`--depot`, `--coverage`, `--scope`) are the pattern to mirror. `--coverage` uses a validated `choices=` allowlist.
  - `src/agentos/index/drift.py` — `index_dangling_mentions(depot_root, engaged_depots=None)`, directed, working, but not in `CHECKS` (DORMANT).
- **Design decisions (grounded):**
  - selection model = **enable/disable over a default-on baseline**: `--check X` force-enables X even if default-off (this is how you opt into `dangling-mention`); `--skip X` force-disables X; on conflict, **skip wins**. `^c20260722-18`
  - **structural vs reportable tier**: some checks produce `LinterState` that later checks' gates/bodies consume (surface validity, discovered files, mdblock syntax, concept inventory). These are `structural` — always run, never disableable; exclude has no effect on them. Only reportable checks are freely toggleable. `^c20260722-17u`
  - selectors are **auto-derived** from each check `code` (kebab slug of the code's last segments), so every check is addressable without hand-naming ~30 checks; uniqueness is asserted.
  - unknown selector passed to `--check`/`--skip` is a hard CLI error (fail fast, like an unknown `--coverage` choice).

## Execution.Plan

Ordered vertical slices. Test-first at boundaries; new tests in `tests/test_index_linter.py` (selection is a linter-run behavior). Loop: `pytest tests/test_index_linter.py`; completion runs full `pytest` + a live `agentos index linter --depot skills/agentos-pkg` from `agentos-md`.

### Slice 1 — Check metadata + selector derivation
- **Do:** add `default_on: bool = True` and `structural: bool = False` to `LinterCheck`. Add `check_selector(code) -> str` deriving a short kebab slug (e.g. `Index.Linter/Check.DepotDependencies` → `depot-dependencies`, `Index.Linter/Line.Unlinked` → `line-unlinked`). Add a registry helper exposing `(selector, title, default_on, structural)` for every check, asserting selector uniqueness.
- **Observable:** `check_selector` maps codes to stable slugs; all `CHECKS` selectors are unique.
- **RED/GREEN:** derivation examples; uniqueness over the real `CHECKS`.

### Slice 2 — Selection resolver
- **Do:** `resolve_enabled_checks(checks, *, include=(), exclude=()) -> list[LinterCheck]`. Baseline = checks with `default_on`. Apply `include` (add, even if default-off), then `exclude` (remove) — skip wins on conflict. Force-keep every `structural` check regardless. Unknown selector in include/exclude → `CliError`.
- **Observable:** the enabled list for a semantics matrix.
- **RED/GREEN:** default → default-on set; `include` a default-off → present; `exclude` a reportable → absent; `exclude` a structural → still present; same selector in both → absent (skip wins); unknown selector → error.

### Slice 3 — Wire into run_linter
- **Do:** `run_linter(..., *, extra_checks=(), include=(), exclude=())`. Build the full check list `(*CHECKS, *extra_checks)`, pass through `resolve_enabled_checks`, iterate only the enabled set (gate/blocked/record bookkeeping unchanged).
- **Observable:** an excluded reportable check does not run; an included default-off check runs.
- **RED/GREEN:** run with `exclude=("router-presence",)` → that check absent from results; run with `include=(<default-off selector>,)` → present.

### Slice 4 — Register dangling-mention as a default-off check
- **Do:** add `_check_index_dangling_mentions(state)` iterating `state.config.depot_paths` and mapping `drift.index_dangling_mentions(depot)` Pois → advisory `LinterFinding`s (`DEPOT_DANGLING_MENTION` code). Register in `CHECKS` with `default_on=False`. Retires the DORMANT note in `drift.py`.
- **Observable:** clean linter run omits it; `include=("dangling-mention",)` surfaces dangling findings on a drifted fixture.
- **RED/GREEN:** drifted temp depot: default run → no dangling findings; included → dangling finding present. Guard: the real `agentos-pkg` depot stays clean under the **default** run (regression floor).

### Slice 5 — Command surface
- **Do:** add `--check` and `--skip` (repeatable `append`) and `--list-checks` (print each selector + title + default state, then exit 0) to `linter_parser`; thread `include`/`exclude` into `_cmd_linter` → `run_linter`. Validate selectors (unknown → `CliError`).
- **Observable:** `agentos index linter --list-checks` lists selectors; `--check dangling-mention` / `--skip <sel>` change the run.
- **RED/GREEN:** drive `_cmd_linter` (or the `_run` harness extended with include/exclude) for include, exclude, list, and unknown-selector-errors.

## Slice Status

- Slice 1 — check metadata + selector derivation — ✅ `LinterCheck.default_on/structural`, `check_selector`, `check_registry`
- Slice 2 — selection resolver — ✅ `resolve_enabled_checks` (enable/disable over default-on baseline, skip-wins, structural force-on, unknown→CliError)
- Slice 3 — wired into `run_linter` — ✅ `include`/`exclude` params
- Slice 4 — `dangling-mention` registered default-off — ✅ retires the `drift.py` DORMANT note
- Slice 5 — command surface — ✅ `--check`/`--skip`/`--list-checks`

## Impl.Log

- **Structural set — extended during execution:** the live matrix showed `--skip router-presence` spuriously *blocking* 4 dependents (router-entries/coverage/targets gate on `state.routers`, which `_check_router_presence` populates). Confirmed router-presence is a state producer and marked it `structural` too (in addition to the 4 planned: config-surfaces, discover-files, mdblocks-syntax, concept-inventory). A reportable exclude (`--skip concept-duplicates`) now drops exactly one check with 0 blocked. `^c20260722-17u`
- **Selection model:** chose enable/disable-over-baseline (not ruff-style select-replaces-defaults) so opting into a default-off check is one flag and defaults are preserved — matches the "default-off, opt-in per depot" framing from the design discussion. A `--only` allowlist mode remains an easy future add. `^c20260722-18`
- **Follow-up (not done):** porting `resolve_enabled_checks` + selectors into the shared `skwlint` core so the skw linter gets `--check`/`--skip` too — the natural generalization, left for a separate pass.
