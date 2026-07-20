# 697 — skw Generalization: `agentos skw`, `.skw/` Packages, Project-Scope Check

## Impl.Abstract

- **Scope**: generalize the skillware toolchain into the skw subsystem it already models. Two movements: (1) a **rename sweep** — `agentos skillware` → `agentos skw`, `.skillware/` → `.skw/`, `skillware.json` → `skw.json` (sources are already `*.skw.md`); (2) a **project scope** — `agentos skw check` with no `--skill` discovers and checks every `.skw/` package under the project, configured by an optional `.agentos`-adjacent `.skw/skw.json` that mirrors the package config. ^c20260720-11u
- **Status**: EXECUTED 2026-07-20 (`--exec --AUTO`, gate `^c20260720-12u`) — Slices 1–5 landed; Slice 6 (ontology mint) deferred by design as gated index-editor work. Full agentos-py suite 405 passed; project-scope `agentos skw check` live; depot linter 0/0. Conceptual model captured in `agentos-pkg` agendix (`Agentos.Skillware/Agendix`, `.../Skw.Package`), anchors `^c20260720-8u..11u`.
- **Source context**: the dependency-sync work (696) made cross-surface bindings checkable per-package; the value is project-wide. The interface generalization was designed turn-by-turn: `agentos skw` as the umbrella verb (skw general, skills = first backend, per landed 591 model), a recursive git-tracked `.skw/` build home at both project and package scope, one mirrored `skw.json` schema, and `Skw.Package` as the recursive unit.
- **Back-compat**: keep `skillware` as a hidden CLI alias and read the legacy `.skillware/` + `skillware.json` names for one deprecation window, so the rename need not land atomically with every consumer.
- **Out of scope** (recorded): materializing `pointer` deps (still routed prose); any new `skw.json` key beyond the v1 four; the ontology re-cut of `Skill.*` as `Skw.*` instances is a **companion index task** (see Slice 6) not code.

## Impl.Index

- **[DF] the two scopes are one problem at different reach** — "check a particular surface" vs "check any surface." They mirror: one `skw.json` schema read at both levels, package extending project via cascade. Absent config → discover every `.skw/` and check all.
- **[DC] recursive unit = `Skw.Package`** — a folder owning a `.skw/` build home (config + optional `src/` + `lock.json`); project root and each skill are instances. `.agentos/` keeps only project identity + runtime; the tracked skw source lives in `.skw/`.
- **[DC] v1 `skw.json` schema — four optional keys**: `depots` (resolution roots), `surfaces` (managed set; absent → discover), `exclude` (trim), `projects` (sibling project roots extending cross-repo resolution). Package-level typically sets only `depots`; project-level sets `projects`/`exclude`.
- **[DC] cascade**: project `depots` + `projects` are defaults; a package's `depots` extend them. Cross-repo names resolve because the project layer supplied the sibling roots.
- **[DC] current code** (`agentos-py/src/agentos/skillware/`):
  - `build.py`: `SETTINGS_NAME = "skillware.json"` (line ~26), `.skillware/` hardcoded in `load_skillware` (lines ~70-74), `_lock_path` (~538), the stamped build-surface `AGENTS.md` (~526). `_resolve_locator` reads depots from settings.
  - `commands.py`: `_cmd_skillware_{build,check,bless,status}`; the prescription strings embed `agentos skillware …` (lines ~30-49) — user-facing, must update.
  - CLI registration (top-level `cli.py` / argparse wiring — locate the `skillware` subparser) is where the `skw` name + `skillware` alias attach.
  - `check_skill(skill_root)` is single-package; project scope needs a discovery walk + aggregation wrapper.
- **[DC] module/dir naming**: keep the `agentos/skillware/` Python package name as-is for this pass (internal, not user-facing) to bound churn; only the CLI surface, on-disk `.skw/` layout, and docs rename. Record as a conscious waiver.

## Execution.Plan

### Slice 1 — CLI verb `agentos skw` with `skillware` alias
- Register the command as `skw`; add `skillware` as a hidden alias routing to the same handlers. Update the four prescription strings and every `"command": "agentos skillware …"` payload to `skw`.
- **Check**: `agentos skw check --skill <fixture>` and `agentos skillware check --skill <fixture>` both work; JSON `command` field reads `agentos skw check`. Unit test asserts alias parity.

### Slice 2 — on-disk `.skw/` + `skw.json` with legacy fallback
- Introduce `BUILD_DIR` (`.skw`) and `SETTINGS_NAME` (`skw.json`) constants; loader prefers `.skw/` then falls back to legacy `.skillware/`, and `skw.json` then `skillware.json`. Lock + stamped AGENTS.md follow the resolved dir.
- **Check**: RED→GREEN — a fixture using legacy `.skillware/skillware.json` still loads (fallback); a fixture using `.skw/skw.json` loads; a fixture with both prefers `.skw/`. Existing tests (which build `.skillware/` fixtures) stay green via fallback.
- **Migration**: do NOT mass-rename existing package dirs in this slice — fallback keeps them working. Physical `git mv` of the repo's own skills is Slice 5, gated behind green fallback.

### Slice 3 — `skw.json` schema parse (four keys) + cascade
- Parse `depots` / `surfaces` / `exclude` / `projects`; implement project→package cascade of `depots`+`projects`. Unknown keys warn, don't fail (forward-compat).
- **Check**: unit tests — package `depots` extend project `depots`; a `projects` root makes a cross-repo name resolve that wouldn't locally; malformed schema yields a clear error, not a stack trace.

### Slice 4 — project-scope `agentos skw check` (discovery)
- New path: `skw check` with no `--skill` resolves the project root (via `.agentos/project.json` marker), reads optional `.skw/skw.json`, discovers every `.skw/` package (honoring `exclude`), runs `check_skill` per package, aggregates POIs into one report keyed by package.
- **Check**: RED→GREEN behavior test — a two-package fixture where package A declares `--from` a block owned by B; rename that block in B without alias; `skw check` (project, no `--skill`) reports the `dangling-dependency` on A **without** targeting A. This is the cross-package payoff. `exclude` drops a package from the run.
- **Observable**: `agentos skw check` at project root lists per-package POIs; exits non-zero on any.

### Slice 5 — migrate this repo's packages + docs
- `git mv` each `skills/*/.skillware` → `.skw`, `skillware.json` → `skw.json`; add a project `.skw/skw.json` (depots + any sibling `projects`). Rebuild all; resolve drift. Sweep the `agentos-skillware` skill (SKILL/doctrine/lang/author/build/check src) and any prose saying "skillware"/".skillware" to the skw names; rebuild that skill.
- **Check**: `agentos skw check` across the project returns to the known pre-existing backlog (no new drift from the move); depot linter 0/0; `agentos skillware …` alias still resolves.

### Slice 6 — companion index concept landing (separate, gated)
- Mint `Skw.Package` (107) + the ladder (`Skw.Build.Surface`, `Skw.Runnable.Surface`, `Skw.Module` as general roots; `Skill.*` re-cut as skills-backend instances/aliases), promoting the `Agentos.Skillware/Agendix/Skw.Package` candidate. This is index-editor work under the project's gates — **not** part of the code execution; flagged here so the concepts land alongside the rename rather than drifting behind it.
- **Check**: agendix candidate promoted, router + namespace members updated, depot linter 0/0.

### Risks / deviation triggers
- Existing tests construct `.skillware/` fixtures directly — Slice 2 fallback must keep them green before Slice 5 renames anything. If fallback proves leaky, split the deprecation window rather than force-migrate.
- CLI alias must not double-register subparsers; if argparse resists a clean hidden alias, accept a visible alias and record it.
- Discovery must not wander outside the project root or into `.git`/`node_modules`; bound the walk.

### Acceptance signals
- `agentos skw` is the verb, `skillware` still works; packages load from `.skw/` or legacy `.skillware/`; `skw check` with no `--skill` checks the whole project and catches a cross-package `dangling-dependency`; this repo migrated with no new drift; depot linter clean.

## Impl.Log

- 2026-07-20 — artifact created under the 591 skw-generalization thread. Decisions (design, user-gated in chat): `agentos skw` umbrella verb; `.skw/` recursive git-tracked build home mirroring at project + package scope; `.agentos/` keeps identity+runtime only; one four-key `skw.json` schema with cascade; discovery default, config = override/exclude/topology; recursive unit named `Skw.Package` (folder grain) with `Skw.Module` reserved for the file grain (avoids the `Skill.Module` collision). Back-compat: `skillware` alias + legacy-path fallback for one window. Python package dir `agentos/skillware/` left unrenamed this pass (internal; conscious waiver). Grounding: `^c20260720-11u` (authorization), model anchors `^c20260720-8u..10u`.
- 2026-07-20 — EXECUTED (`--exec --AUTO`, gate `^c20260720-12u`). Per-slice:
  - **Slice 1**: verb `agentos skw` registered with `skillware` as an argparse alias (both live in the installed binary); all `command` payloads + prescription strings → `skw`. Test `test_skw_verb_with_skillware_alias` asserts alias parity.
  - **Slice 2**: `BUILD_DIR = ".skw"` / `SETTINGS_NAME = "skw.json"` with `resolve_build_root` preferring `.skw/` and falling back to legacy `.skillware/`; `_settings_path` prefers `skw.json` then `skillware.json`. `Skillware` gained a `build_root` field; lock + AGENTS stamp follow it. Fallback RED→GREEN test green.
  - **Slice 3**: `SkwConfig` + `parse_skw_config` (four keys, unknown-key warnings, type validation); `find_project_root` (`.agentos/project.json` marker walk); `resolve_project_depots` (project + one-level sibling `projects`); `load_skillware(extra_depots=…)` cascade. Cross-repo cascade test green.
  - **Slice 4**: `discover_packages` + `check_project` + `ProjectCheckReport`; `check_skill(extra_depots=…)`; CLI `skw check` with no `--skill` → project scope (dispatch in `_cmd_skillware_check`, `--skill` now optional only for check). Cross-package `dangling-dependency` RED→GREEN test + `exclude` test green; verified live on a throwaway project (GREEN → rename → dangling, exit 1).
  - **Slice 5**: `git mv` all 4 agentos-md packages `.skillware/`→`.skw/`, `skillware.json`→`skw.json`; added project `agentos-md/.skw/skw.json` (`depots: ["skills/agentos-pkg"]`); rebuilt all; swept the `agentos-skillware` skill's mechanical tokens (`agentos skillware`→`agentos skw`, `.skillware/`→`.skw/`, `skillware.json`→`skw.json`) and rebuilt.
  - **Deviation A**: the CLI is wired in a third repo (`agentos-cli`, `cli.py:77` calls `register_skillware_commands`); the verb rename stayed inside that function (agentos-py), so `agentos-cli` needed no edit. agentos-py is editable-installed in the tool env, so edits are live.
  - **Deviation B**: Slice 5 prose sweep scoped to the canonical `agentos-skillware` skill's **mechanical** tokens only. The concept name `Agentos.Skillware`/`Skillware` and command/path references in other skills + the 107 ontology are deferred to Slice 6, kept working meanwhile by the `skillware` alias + `.skillware/` fallback.
  - **Deviation C**: the 4 `derived-stale` POIs now visible under project scope are pre-existing backlog in `agentos-hugentics`/`-impl` (src untouched here), not migration-caused; `agentos-skillware` held at exactly 19/0, `agentos-index` clean — the move introduced no new drift.
  - **Slice 6 deferred** by the artifact's own framing (gated index-editor work); conceptual candidate already captured to `Agentos.Skillware/Agendix/Skw.Package`.
  - Verification: `pytest` full agentos-py suite 405 passed; `agentos skw check` project scope live; depot linter 0/0/21.
