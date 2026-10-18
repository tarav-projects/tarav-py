# Skill markers and Project-held skw depots — implementation request

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Status: complete, 2026-10-18.
Knowledge.Surface: wiki.

A skw skill folder keeps only its product plus a small identity marker, `.tarav/skill.json` (a UUID). Its skw depot, today `skills/<name>/.skw/`, moves into the owning Project at `.tarav/skillware/skills/<name>/`, next to the Project's own agents-file source. skw POIs name a skill by its UUID instead of its path.

Non-goals: markers for hand-written skills without a depot; the legacy `miatube-pkg` package (it still uses the retired `skw.json` and does not load today); the `index-archive-2208` snapshot; any change to Project discovery.

## Design

A skill gets an identity of its own, but it stays a skill: it is not a Project and has no action registry. It is important enough to carry a `.tarav/` folder with a `skill.json` marker.
<!-- tarav.breadcrumb d5f299b16e91 -->
<!-- tarav.breadcrumb a66ec8cad197 -->

A skill always belongs to a Project. Its POIs and actions land on that Project.
<!-- tarav.breadcrumb 4511c7c68c72 -->

`.tarav/project.json` marks a Project and `.tarav/skill.json` marks a skill inside one. That is all; the `.tarav/` folder is not itself a marker, and no wider rule about `.tarav/` is implied. Project discovery already looks for `project.json` (`find_agentos_project`, `find_agentos_project_roots_under` in `tarav.l0.project`), so a skill folder is never mistaken for a Project.
<!-- tarav.breadcrumb 930a3955926d -->
<!-- tarav.breadcrumb 3450b4b6be04 -->

A skill is something that gets copied and published, so its folder should be independent of development state. All skw depots move up into their Project; the skill folder keeps only `.tarav/skill.json` to define its ID close to it. Distance between source and product is fine for development, and checks already catch work done outside the skw sources.
<!-- tarav.breadcrumb 861a51096f9b -->
<!-- tarav.breadcrumb 9b03e6603e77 -->

Proposals the User accepted ("good enough"): the depot entry points at the skill (by `skill_id` and the product path), never the reverse; depot folders are named after the skill folder; the owner is the Project whose depot builds the skill, which retires the earlier orphan-POI idea; a published copy keeps the same ID; only skw skills get a marker for now.

### Decisions taken by the Agent during Design

- **Path roots.** A source is named relative to its depot (`src/SKILL.skw.json`); a product, context target or dependency is named relative to the product root (the skill folder for a skill, the Project root for an agents file). Today both are relative to one root that contains the depot; once the depot leaves the skill folder that cannot hold. This applies to every skw `Document`, so the 7 Project agents-file locks are migrated too (`.tarav/skillware/src/AGENTS.skw.json` → `src/AGENTS.skw.json`).
- **Addressing a skill.** `tarav skw skills … --skill <skill-folder>` replaces `--project <skill-folder>`: the folder is a skill, not a Project. Without the flag the nearest `skill.json` above the cwd is used.
- **Suite key.** A skill's check suite keys on its `skill_id`; its display name stays the folder name.
- **One request.** The data migrations in tarav-md, miacad-md and md-library-md only move files and rewrite paths with one script, so they are logged here rather than in separate notes; each repository still gets its own evidence commits.

## Current implementation observations

Inspected 2026-10-18:

- `tarav.l1.skw.depot.SkwDepot`: a `DirectoryRecord`; `depot` is the directory, `root` is its parent.
- `tarav.l2.skw.skills.SkwSkill`: `path()` resolves every manifest path against `root`; `documents()` builds `Document(path, root=self.root)`; `_validate` rejects deployed files inside the depot; the suite keys on `root.name`. `load_skill(root)` loads `root / ".skw"`. `_command` uses `project_root(args.project)` and rejects legacy `skw.json`.
- `tarav.l1.skw.document.Document`: infers `root` as the parent of a `.skw` ancestor when none is given; requires the depot inside `root`; `key = source.relative_to(root)` is the lock key. `project_root(depot=".skw")` and `project_document` discover upward by depot folder.
- `tarav.l1.skw.loading`: `package.loading_file or '.skw/main.json'`.
- `tarav.l2.skw.publication`: lock at `root/.skw/publications.lock.json`; refuses targets inside `root/.skw`.
- `tarav.l2.project.dev.DocsProject.skill_folders`: globs `skills/*/.skw/main.json`.
- skw POI situations name the place as `{"project": str(root), ...}` (`SkwPOI.from_finding`, `GenerationContextResolutionCheck`, `freshness_checks`, the href POI in `tarav.l1.skw.pois`).
- `tarav.l1.project.agents`: the agents-file depot is `<project>/.tarav/skillware`, document `src/AGENTS.skw.json`.
- Live depots: tarav-md `skills/tarav-hugentics`, `skills/tarav-pkg`; miacad-md `skills/miacad-pkg`; md-library-md `skills/md-library-transcript-developer`. Stray legacy file: `tarav-md/.skw/skw.json`. All four packages check clean except tarav-hugentics, which reports StaleContext findings (baseline to compare after the move).
- Stored paths: each skill's `main.json` (`sources`, `loading`), `lock.json` keys, `generations/*.json`, `loading.json`; hand-written skill `AGENTS.md` files mention `.skw/`.

## Impl.Req.Wiki

Product: `tarav-py`. Documentation owner: `tarav-md/notes/wiki/` (topic `skillware.md` if present, else a new `skills.md`; daily `2026-10-18.md`). Supporting turns are attached above. Capture status: done (`skillware.md`, section "Skill identity and Project-held depots (924)"; daily `2026-10-18.md`).

## Execution.Plan

Data shape:

- `SkillMarker` Record at `<skill>/.tarav/skill.json`: `type`, `skill_id` (UUID), `created_at`. Read through the Record registry like `project.json`.
- `SkwSkill` (`main.json`) gains `skill_id` and `product` (Project-relative path of the skill folder). `sources` and `loading` become depot-relative; `files`, `entrypoint`, `dependencies` stay product-relative. `root` is the product folder; `depot` the depot directory; `project` the Project holding the depot.
- `Document(source, root=…, depot=…)`: the depot may lie outside `root`; `key` is relative to the depot.

1. **Refactor — depot-relative source keys.** `Document.key`, `SkwSkill.sources`/`loading`, lock keys and generation records name sources relative to the depot; a `depot_path()` beside `path()`. Migrate the 7 Project locks and the four skill depots in place. Check: full suite; every migrated package and Project agents file compiles byte-identically and reports the same findings as before.
2. **Feature — skill marker and UUID situations.** `SkillMarker`, `skill_id` on the skill; skw POIs name a skill as `{"skill": <skill_id>}` and an agents file as `{"project": project_id(root)}`; the suite keys on `skill_id`. Write `skill.json` into the four skills. Check: tests for the marker and a POI situation carrying the UUID; `tarav status --project` on tarav-md reopens skw actions under UUID situations.
3. **Feature — depots in the Project.** `SkwSkill` loads from `<project>/.tarav/skillware/skills/<name>/main.json`; `load_skill(skill_folder)` finds the nearest Project and the depot entry whose `product` matches, failing clearly when either is missing; `DocsProject.skill_folders` reads the depot entries; publication lock moves into the depot; `--skill` replaces `--project` on `tarav skw skills`; a check flags a depot entry whose product is gone or whose `skill.json` carries another ID. Move the four depots, delete `tarav-md/.skw/`. Check: tests for loading, the mismatch POIs and the CLI; packages compile byte-identically; no `.skw/` left in live skills.
4. **Documentation.** tarav-py AGENTS.md (skw source) and ARCHITECTURE.md; the skill `AGENTS.md` files; Wiki capture.

Risks and deviation triggers: a consumer that resolves source keys relative to the product root (found in slice 1 by the byte-identical check); dependency resolution between skills (`../tarav-pkg`) needing the other skill's depot; external uncommitted work in md-library-md (2 files) goes into its start checkpoint.

## Impl.Log

- 2026-10-18: Designed with the User in this session; Develop, Interactive.
- Start checkpoints: tarav-py `73cb526` (this note); tarav-md `3b0265d`, miacad-md `9da4f2d`, md-library-md `08bafbb` (empty). md-library-md's untracked `.agents/` and `.claude/` are the skill symlink folders the User chose to stop tracking; they stay out of every commit.
- Slice 1 (depot-relative source keys): `Document.key` is relative to the depot, which may now lie outside the root; `SkwSkill.depot_path()` beside `path()` resolves sources, the loading record and publications; `ModelPublication` takes its depot and keeps its lock there; `surface_state` and `ProductDrift` (which now carries its absolute source) follow. Data: `~/.tarav/tmp/migrate_924_keys.py` stripped `.skw/` from 123 stored keys in the four skill depots and `.tarav/skillware/` from the lock key of 7 Project depots (exact JSON strings only, formatting kept, `block-identity-migration.json` left as history).
- Deviation: three more Projects hold an agents-file depot (taravangian-project root, miacad-project root, miacad-py, csc-reactor-cad); they were found by the migration scan after the first edit, so their checkpoints could not precede it. Their only change is the one lock key; miacad-project's external `.tarav/uv.lock` is committed apart.
- Checks: skw tests 19 passed after fixing two fixtures (sources listed as `src/...`); `tests/test_project_dev.py` had 2 failures from the earlier UUID refactor (`2a5eab5`, fixtures without a Project marker), fixed by giving them a marker; full suite 384 passed; ruff clean. Rebuilding the four packages and compiling all 7 agents files changed no product byte. Findings unchanged: tarav-hugentics 6 OutputChanged and 56 StaleContext, the same as the old code on the old data (a temporary worktree run also showed 16 ContextUnresolvable, all from the copy's location); the others 0. The agents-file compiles report the pre-existing StaleProducedOutput of `tarav-system-prompt`.
- Capture: Breadcrumb on `document.py` (the key rule); positions refreshed on the five edited skw modules, audits clean.
- Slice 1 commits: tarav-py `9c81e23`; tarav-md `39f2ea8`, miacad-md `e491da6`, md-library-md `83fffea`, taravangian-project `be1c4db`, miacad-project `81ee036` (its external `.tarav/uv.lock` apart in `80f0b1a`), miacad-py `1ec9783`, csc-reactor-cad `28539f3`.
- Slice 2 (skill marker and UUID situations): `tarav.l1.skills.marker.SkillMarker` (`Tarav.Skills.Marker`, a `TaravEntity` whose Record is `.tarav/skill.json`: `skill_id`, `created_at`; `of()` reads, `create()` never replaces), registered in the runtime; `TaravSkill.skill_id` reads it. skw POI situations name their owner by UUID through `owner(root)` in `tarav.l1.skw.pois` (a skill's marker, else the Project's `project_id`); a skill package's suite keys on `skill_id`. Markers written: tarav-hugentics `5a101100-…`, tarav-pkg `4836ba9a-…`, miacad-pkg `616c9ba5-…`, md-library-transcript-developer `2c5d310a-…`. The name `SKILL_MARKER_FILENAME` (the `SKILL.md` entrypoint) predates this and is left alone; the new file is `SKILL_JSON`.
- Checks: full suite 385 passed, ruff clean; test fixtures get a marker; the link-prose test now asserts the situation carries the skill's UUID; new `test_a_skill_keeps_its_uuid_in_its_marker`; skw and record contract tests pass. `tarav status --project` on tarav-md: the 56 StaleContext and 6 OutputChanged actions reopened under `{"skill": "5a101100-…"}` situations, the path-named ones closed.
- Capture: Breadcrumbs on `marker.py` (2) and `owner` in `tarav/l1/skw/pois.py` (1); positions refreshed on the other edited modules, audits clean.
- Slice 2 commits: tarav-py `89a7094`; tarav-md `2c19154`, miacad-md `85c7255`, md-library-md `ef01ec8`.
- Slice 3 (depots in the Project): `SkwSkill` records `skill_id` and `product`; its depot lives at `<project>/.tarav/skillware/skills/<name>/` (`SKILL_DEPOTS`), `project` is derived from that layout, `root` is the product folder inside the Project, `skill_id` is the depot's claim and `owner` names the skill by it. `load_skill(folder)` finds the nearest Project and the depot whose `product` is that folder, failing with "A skill belongs to a Project" or "No depot … builds …"; `project_skills()` and `load_depot()` serve `DocsProject`, which now reads its depots. New POIs `SkillMarkerMissing` and `SkillMarkerMismatch` (the folder's marker against the depot's `skill_id`). `deploy` copies `.tarav/skill.json` with the files. `Document` takes `root` and `depot` explicitly (no `.skw` inference); `DEFAULT_DEPOT = ".tarav/skillware"` replaces the `.skw` defaults of the document CLI, and `skill_document` returns a skill depot's own document for any skill, so its product resolves in the skill folder. `tarav skw skills … --skill <folder>` replaces `--project`, defaulting to the nearest `.tarav/skill.json` above the cwd; the legacy `skw.json` message is gone. `SkwPOI.from_finding` takes the owner explicitly; slice 2's marker-reading `owner(root)` is removed (its Breadcrumb moved to `SkwSkill.owner`).
- Deviation (design-reality mismatch, Interactive mode, taken without stopping because no User decision is involved): the design said context targets resolve from the product root, but a reference path in a source resolves from the source file. Moving the sources broke 87 such references in tarav-hugentics (86 ContextUnresolvable). The contract was kept and the data migrated instead: `~/.tarav/tmp/repath_924.py` rewrote the 28 distinct paths that leave the depot so each reaches the same file from the source's new place (paths inside the depot moved with it). Rebuilding recompiled the 13 touched sources byte-identically.
- Data: `~/.tarav/tmp/move_924_depots.py` moved the four depots and added `skill_id` and `product` to each `main.json`; `tarav-md/.skw/` (legacy `skw.json`) deleted.
- Checks: tests moved to the Project layout (`test_skw_poi.py` fixtures `_layout`, `_depot`, `_document`; `test_skills.py`; `test_project_dev.py`); new tests `test_a_skill_belongs_to_the_project_above_it`, `test_the_depot_and_the_folder_must_name_the_same_skill`, `test_a_deployed_copy_carries_the_skill_marker`, `test_the_skills_command_selects_a_skill_folder`. The record contract caught `SkwSkill`'s example record missing the new fields; fixed in its `Records.record_example`. Full suite 389 passed; ruff clean. Live: the four skills build with no product byte changed; tarav-hugentics shows its baseline 6 OutputChanged and 56 StaleContext, the others 0; `tarav status --project` on tarav-md keeps the same 68 open actions.
- Slice 3 commits: tarav-py `ebb9589`; tarav-md `e99982c`, miacad-md `efec990`, md-library-md `9b588f2`.
- Slice 4 (documentation): tarav-py AGENTS.md (skw source: a paragraph on skill markers and Project-held depots, `.skw/src/` wording replaced; Breadcrumbs submitted on the product, copied back, rebuild byte-identical, audit clean) and ARCHITECTURE.md (`skw` and `skills` rows). The skill developer notes `skills/tarav-hugentics/AGENTS.md` and `skills/tarav-pkg/AGENTS.md` are hand-written, not deployed, and describe the depot, so they moved into their depots and now give Project-root commands with `--skill` or `--depot`; the stale `.skw/blessings/` sentence now points to the Project's actions. Their commands were run and work; their Breadcrumbs re-audited clean after the move.
- Wiki capture: tarav-md `notes/wiki/skillware.md` (new section) and `notes/wiki/daily/2026-10-18.md`; Breadcrumbs submitted, audits clean.
- Open: `miatube-pkg` still uses the retired `skw.json` and does not load; hand-written skills have no marker yet; tarav-md's `.agents/`-style untracked folders in md-library-md stay untracked as decided.
