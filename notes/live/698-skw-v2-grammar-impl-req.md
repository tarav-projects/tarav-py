# 698 — skw v2 Grammar: the Annotation as a Named Block

## Impl.Abstract

- **Scope**: implement the full captured skw-annotation redesign — the **v2 grammar**, where an annotation is a *named block* identified by a `Skw.Address.Schema` address, the binding mode is a *flag* (not the command), and features are additive flags (`--note`, `--from`, `--derived`/`--copy`/`--pointer`, `--intent`, `--supp`, `--cont`). Ontology is promoted first, then the parser/linter is rewritten, then the live packages are migrated, then it is tested on current skw surfaces. ^c20260720-25u
- **Status**: designed under `/agentos-hugentics-impl --design --AUTO`, rescoped from the additive v1 to the full breaking grammar at the user's direction (`^c20260720-25u`). Cross-repo: ontology + skills in `agentos-md`, parser/linter in `agentos-py`.
- **Source context**: the skw-annotation rethinking captured this session on the agendix (`Skw.Annotation/Agendix`, `Skw.Language/Agendix`, `Skw.Address.Schema/Agendix`, `Touched.Surface.Index/Agendix`, anchors `^c20260720-15u..23u`).
- **Breaking change, sequenced for safety**: this replaces the current `$kw: <command> … end-<command>` grammar. It is landed **authority-first** — the design is promoted from zero-authority agendix into the 107/108 ontology (Phase 0) *before* any code, so the parser rewrite implements gated concepts, not chat sketches. Only 4 packages use skw today (all in agentos-md), so the migration is bounded and atomic.
- **Out of scope** (recorded): the computed project-wide "all notes" view over the TSI (a later feature); any non-skills skw backend; `Skw.Package`/project-scope changes (already shipped in 697).

## The v2 Grammar (target)

- **Block = named annotation**: `# $kw: <address>` opens; the address is the sole identity — declared relative (`#fragment`, resolved against the current surface), cited absolute (`path#fragment`). The `^label` second-id is retired; a nameless span uses `#^label` as its address.
- **`$kw` marks the fence, `--` fills it**: `# $kw: <address>` open, `# --flag value` belonging lines (each self-marked by `--`), `# $kw. end` close (bare `end` now legal, replacing `end-<command>`). The sigil appears only on the two fence lines.
- **Features are flags**:
  - `--note [TYPE] <text> ^anchor` — documentation as an `Index.Line` (typed + grounded)
  - `--from <address>` — a dependency edge (`Skw.Dependency`)
  - `--derived` / `--copy` / `--pointer` — the binding mode (was the command)
  - `--intent <text>` — derivation context
  - `--supp <text> ^anchor` — the annotation's own touched lines
  - `--cont <text>` — continues the previous flag generically (POI if orphaned)
- **Fence the target**: content between open and close is the block's materialized/generated body (a `def`, a `.md` region). When the fence wraps a named element, its name must match the declared address — a mismatch is a POI; the fenced element checks the name, it is not the source of it.
- **Carrier-agnostic**: `>` in `.skw.md`, `#` in code — as today.

## Impl.Index

- **[DF] one block model** — `SkwBlock`: `address`, `binding` (`none`/`pointer`/`copy`/`derived`), ordered `flags` (notes, froms, supp, intent), optional fenced `body`. Replaces the `SkwRecipe`/`SkwConstruct`/`SkwDependency` split — the old three were *kinds*; v2 has one kind with feature flags.
- **[CT] the verb→flag map preserves every current capability** — `text` → a block with a fenced body, no binding; `copy --from X` → `--copy --from X`; `derived --from X --intent I` → `--derived --from X --intent I`; `depends --from X` → `--from X`, no body. Nothing the current grammar expresses is lost; it is re-spelled.
- **[DC] current parser** (`agentos-py/src/agentos/skillware/model.py`): `parse_skw_source`, `_read_declaration`, `_parse_flags`, `_is_end_content`; `COMMANDS`/`RECIPE_VERBS`/`VOID_COMMANDS` (lines ~23-27); the closer discipline forbids bare `end` (must become legal). This is a grammar-core rewrite, not an extension.
- **[DC] current linter/build** (`build.py`): `check_skill`, `_dependency_sync_pois`, expansion/derivation, `_resolve_locator`. Binding is currently read off `recipe.verb`/`dependency`; v2 reads it off the block's `--`flags. The dangling/undeclared/unhonored/derived-stale POI logic is preserved but re-sourced from `SkwBlock`.
- **[DC] address resolution** — `Skw.Address.Schema`: a bare `#fragment` resolves against the current surface; `path#fragment` is absolute. `_resolve_locator` already handles locator forms; extend it for the relative/absolute split and for the address-as-block-identity.
- **[DC] the 4 live packages** — `agentos-md/skills/{agentos-skillware,agentos-index,agentos-hugentics,agentos-hugentics-impl}/.skw/src/**/*.skw.md` — all in v1 grammar; every `derived`/`copy`/`depends` construct is migrated. The `agentos-skillware` skill additionally *teaches* the grammar (`lang.skw.md`), so its content changes too.

## Execution.Plan

### Phase 0 — promote the design to ontology (gated index-editor work, no code)
- **Slice 0.1**: rewrite `Skw.Annotation` (107) for the named-block model — one block, binding-as-flag, additive features, `--note` = `Index.Line`, `Index.Block ≡ Skw.Annotation`. Promote from `Skw.Annotation/Agendix`.
- **Slice 0.2**: rewrite `Skw.Language` (107) for the v2 grammar — `$kw`-fence/`--`-fill, self-marked lines, `--cont`, bare-`end`, fence-the-target. Promote from `Skw.Language/Agendix`.
- **Slice 0.3**: extend `Skw.Address.Schema` (108) — address as block identity, relative-declare / absolute-cite. Promote from its agendix.
- **Check**: depot linter 0/0; agendix candidates removed; router/members updated. This phase is the **authority gate** — code in later phases cites these blocks.

### Phase 1 — parser rewrite to v2 (`model.py`)
- **Change**: replace the declaration reader with the v2 grammar — parse `$kw: <address>`, `--`-marked belonging flags, `--cont`, bare `# $kw. end`, and an optional fenced body captured between open and close. Produce `SkwBlock`. Keep `SkwFinding` structural checks (well-formed lines, closed blocks, unique addresses).
- **Check**: RED→GREEN unit tests over v2 fixtures — a note block, a `--derived --from` block with a fenced body, a `--from`-only (ex-`depends`) block, `--cont` continuation, address relative vs absolute, a mismatched fenced-name, an orphan `--cont`. Bare `end` now parses; `end-derived` legacy is a clear finding directing to migration.
- **Observable**: `parse_skw_source` returns `SkwBlock`s for v2 sources.

### Phase 2 — linter/build over `SkwBlock` (`build.py`)
- **Change**: re-source binding mode from block flags; port `copy`/`derived` materialization and the dependency-sync POIs (undeclared/unhonored/dangling) to `SkwBlock`. Add v2 POIs: `malformed-note` (a `--note` missing its `[TYPE]` or `^anchor`), `address-mismatch` (fenced name ≠ declared address), `orphan-cont`.
- **Check**: RED→GREEN — malformed note raises exactly one `malformed-note`; a fenced `def` renamed away from its address raises `address-mismatch`; existing dangling/derived-stale behavior reproduced on v2 fixtures.
- **Observable**: `agentos skw check` reports the v2 POI set.

### Phase 3 — migrate the 4 packages (atomic v1→v2)
- **Change**: convert every `.skw.md` construct in the 4 skills to v2 (`derived`→`--derived`, `copy`→`--copy`, `depends`→`--from`, `end-*`→`end`, add block addresses). Update the `agentos-skillware` skill's taught grammar (`lang.skw.md` + doctrine). Rebuild all; resolve/bless drift.
- **Check**: `agentos skw check` project-scope returns to the known pre-existing backlog, no new drift beyond the grammar move; depot linter 0/0.
- **Observable**: all skills parse and build under v2; `agentos skillware` alias still runs.

### Phase 4 — test on current skw surfaces + first real note
- **Change**: add a genuine `--note` documentation annotation to a real agentos skill; confirm the linter validates it (typed+anchored) and catches a deliberately broken one; keep the good note.
- **Check**: project-scope `agentos skw check` clean with the note present; a temporary break reproduces `malformed-note` and clears.
- **Observable**: a real skill carries the first v2 documentation annotation.

### Risks / deviation triggers
- **Atomicity**: Phases 1-3 must land together — a v2 parser cannot read v1 sources. Either keep a short-lived v1-read shim to migrate incrementally, or land parser+migration in one uninterrupted execution. Recommend the latter (4 packages, bounded); if execution is interrupted mid-migration, the shim is the fallback.
- **The skill that teaches the grammar**: `agentos-skillware/lang.skw.md` documents v1 syntax *and* is itself a v1 source — migrate its form and its content in the same pass, or it will describe a grammar it no longer uses.
- **Address model depth**: if relative/absolute resolution proves larger than `_resolve_locator` accommodates, scope Phase 1 to declared addresses + Phase 2 to resolution, and record the split.
- **Bless discipline**: the migration will re-derive many blocks; distinguish genuine drift (re-derive) from grammar-only reshaping (bless) and do not silently bless real drift.

### Acceptance signals
- The ontology carries the v2 model; `parse_skw_source` implements the v2 grammar; the linter reports the v2 POI set; all 4 packages run on v2 with no new drift; a real skill carries a linted documentation annotation; the full agentos-py suite passes.

## Impl.Log

- 2026-07-20 — **Phase 0 LANDED** (ontology promotion, `^c20260720-13u`-family + design anchors `^c20260720-15u..23u`): `Skw.Annotation` rewritten to the named-block model (binding-as-flag, additive features, `Index.Block ≡ Skw.Annotation`, address-as-identity); `Skw.Language` recut to design-value lines (named-block form, binding-mode-as-flag) with the **grammar itself moved to a fenced v2 code example** in the `Skw.Annotation/Construct.Grammar` appendix (13 v1 grammar lines superseded, git-kept); `Skw.Address.Schema` gained the address-as-block-identity line (relative-declare / absolute-cite). Three agendix candidates promoted out. Depot linter 0/0/21. **One `derived-stale` left unblessed on purpose**: doctrine "The Model" derives from `Skw.Annotation` and still teaches v1 — correct for the current v1 parser, and the standing POI is the honest Phase-3 marker (it resolves when the skill's teaching migrates with the parser, not before). Re-deriving now would teach an unimplemented grammar; blessing would hide real drift.
- 2026-07-20 — created under `--design --AUTO` as the additive v1 (documentation annotation only), then **rescoped to the full v2 grammar** at the user's direction (`^c20260720-25u`). Sequencing decision: authority-first — promote the agendix design to the 107/108 ontology (Phase 0) before any parser code, so the breaking change implements gated concepts rather than zero-authority chat material. Migration is atomic across the 4 live packages (Phases 1-3 land together; a v1-read shim is the only fallback if execution is interrupted). `note`-as-command (the v1 compromise) is dropped — v2 uses the address-named block throughout. Grounding `^c20260720-25u`; design source anchors `^c20260720-15u..24u`.
