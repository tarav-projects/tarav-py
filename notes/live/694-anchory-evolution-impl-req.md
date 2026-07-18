# Anchory Evolution — Universal Anchor Literacy — Impl.Req

## Impl.Abstract

- evolve the Anchory subsystem from a single-app anchor store into the universal anchor layer: real namespaces with per-namespace metadata and declared key prefixes, a depot registry with discovery (`Pwd.Upward.Search`), a composed key grammar carrying namespace prefix and turn-kind tag, and full migration of the existing chatlas depot + all surface citations to the new grammar
- design source: design session `agentos-md/notes/live/591-touched-surface-index-design-session.md` (axis 10 / Anchory evolution rows); founding design turns `^c20260717-3u` `^c20260717-4u` (`Pwd.Upward.Search` agendix block at `agentos-md/skills/agentos-pkg/agendix/Development.Principles-agendix.md`); grammar decisions from the 2026-07-18 planning discussion (this session)
- support set (retro-minted 2026-07-18): ordering gate ^c20260718-5u · decision turns ^c20260718-6u ^c20260718-7u ^c20260718-8u · readiness approval ^c20260718-9u · execution gate ^c20260718-10u
- the target grammar, using chatlas as the first namespace: `^c20260718-4u` = namespace-prefix `c` + caller allocation-prefix `20260718` + `-` + anchory-allocated counter `4` + optional single-letter tag `u`; the caller supplies meaning (namespace, alloc-prefix, tag, hint, record), anchory supplies identity (counter) and composes the key
- bare/unprefixed citations (`^20260716-15`) are BANNED on written surfaces after migration — enforced by lint, not by the resolver library
- scope: `agentos-py` anchory core + index model/linter, `agentos-chatlas-py` chatlas layer, `agentos-cli` reinstall, migration of the chatlas depot (~150 records) and citation sweep over `agentos-md` + `agentos-chatlas-md` (138 distinct anchors across 59 files), new `agentos-anchory-pkg` skill in `agentos-md/skills/`, closing forum post
- out of scope: multi-letter namespace prefixes; namespace-prefix uniqueness enforcement (collisions are accepted by design — resolution may search several namespaces sharing a letter); any `Judgement.Bank` machinery; rewriting `_DEPRECATED` skill citations; the `Skw.Address.Schema` index-edit closing the prefix-ripple `[DC]` (design-session work, noted as follow-up)
- status: executed 2026-07-18 (all 8 slices; migration complete, sweep complete, forum post out)

## Impl.Index

### Current.State (inspected 2026-07-18)

- `agentos-py/src/agentos/anchory/core.py` (359 lines) — `AnchoryDepot(root)`; namespaces exist only as the hardcoded `GLOBAL_NAMESPACE = "global"` path segment (shard paths, `query`, `check`, `_allocate_anchor` all glob `<root>/global/*.json`); `register(record, *, anchor|prefix)` — exactly one; `prefix` is the caller's allocation prefix and allocation scans `^<prefix>-(\d+)$` for the max counter; sharding = sha256(anchor)[:2]; flock on `<root>/.anchory.lock`; `resolve/amend/query/check` + `scan_anchory_source`; no discovery, no registry, no metadata
- `agentos-py/src/agentos/anchory/commands.py` (287 lines) — thin CLI (`register/resolve/amend/query/check/scan`), registered by `agentos-cli` (`src/agentos_cli/cli.py:9,67`); CLI entry changes require `uv tool install --reinstall --editable .` from `agentos-cli/`
- `agentos-chatlas-py/src/agentos_chatlas/anchory.py` (112 lines) — `chatlas_anchory_depot()` derives the depot root (`~/Documents/chatlas/anchory`); `chatlas_anchory_register(...)` derives the allocation prefix from `--at`'s date (line 91) and calls `register` — the single choke point where namespace/tag will be injected
- `agentos-py/src/agentos/index/model/parser.py:42` — `ANCHOR_RE = re.compile(r"\^(?P<anchor>\d{8}-\d+)\b")`: the only place the citation grammar is parsed for index surfaces; linter checks (`Line.Unlinked`, block coverage, agendix anchor checks) all consume these spans
- migration scope measured: chatlas depot holds 150 records under `global/`; 138 distinct `^YYYYMMDD-N` citations across 59 `.md` files in `agentos-md` + `agentos-chatlas-md` (some records uncited — normal)
- tests: `agentos-py/tests/test_anchory.py`, `test_anchory_depot.py`; index parser/linter tests in `test_index_model_parser.py`, `test_index_linter.py`; chatlas tests in `agentos-chatlas-py/tests/`
- read `AGENTS.md` in every touched repo before editing; compatibility policy: no legacy aliases unless requested

### Design.Decisions (user-settled in the planning discussion)

- **key grammar** — `^<ns-prefix><alloc-prefix>-<counter><tag?>`; ns-prefix: one lowercase letter declared in the namespace's `meta.json`; alloc-prefix: caller-owned convention (chatlas: `YYYYMMDD` from `--at`); counter: anchory-allocated decimal; tag: optional single lowercase letter, caller-supplied at register time, decorating the counter ^c20260718-7u ^c20260718-8u
- **tag semantics** — the tag never participates in allocation: counter space is per (namespace, alloc-prefix) regardless of tag (`-4u` and `-5a` coexist; `-4u` and `-4a` cannot both be allocated); the tag is stored on the record too; resolution finds the anchor by number and REPORTS a tag mismatch ("resolves, but the tag lies") instead of failing as not-found ^c20260718-7u
- **chatlas tags** — `u` = user turn, `a` = assistant turn, computed by the chatlas layer from the resolved turn's producer at register time (never trusted from the caller); an explicit tag passed to the chatlas command acts as an assertion check (error on mismatch) ^c20260718-7u
- **namespace layout** — `<depot-root>/<namespace>/` holds shards + `meta.json`; `meta.json` fields: `prefix` (one letter), `intention` (free text — the resolution fallback context), `semantics` (optional pointer to the owning system's docs); metadata is returned only with `--meta` / `meta=True`, never bundled by default
- **parameter rename** — `register`'s `prefix` parameter becomes `alloc_prefix` (library) / `--alloc-prefix` (CLI): "prefix" now means the namespace letter; no compatibility alias (house policy)
- **registry** — `~/.agentos/anchory/registry.json`: records depot roots (path, namespaces seen, last-touched); every depot a command touches auto-registers; the registry powers `Pwd.Upward.Search`: resolve without `--depot` searches registered depots under pwd and its parents, then the global depot ^c20260718-6u
- **global depot** — lazily created at `~/.agentos/anchory/depot/` as the `Pwd.Upward.Search` terminal; a plain `AnchoryDepot` root, no special code
- **bare-citation ban** — enforced on written surfaces via a new index-linter check (pattern precedent: `Anchor.LegacySigil`); the library still accepts namespace + bare key programmatically ^c20260718-7u
- **tagless-anchor lint** — tagless keys in a namespace whose meta declares tags are a POI-style lint finding (backlog visibility), not an error: migration may leave tag-less keys when the turn producer cannot be resolved locally, amendable later ^c20260718-9u
- **migration** — two mechanical passes, each under one gate: (1) depot re-key `20260716-15` → `c20260716-15u`-form with tags computed from each record's session/at (fallback: tag-less), records moved `global/` → `chatlas/`, `meta.json` written; (2) surface sweep rewriting all 138 citations across `agentos-md`/`agentos-chatlas-md` (including `notes/`), policed afterward by the bare-citation lint ^c20260718-6u ^c20260718-7u
- **ordering** — evolution ships → migration runs → the first real forum post ("update your anchors") goes out; this closes 591's DO-NOT-FORGET row and makes the post literally true

## Execution.Plan

Feedback loops: `uv run python -m pytest tests/test_anchory.py tests/test_anchory_depot.py -q` (agentos-py), `tests/test_index_model_parser.py tests/test_index_linter.py -q` (grammar slices), chatlas suite in `agentos-chatlas-py`. RED→GREEN where marked. Checkpoint commits per execution workflow in every touched repo before starting (agentos-py, agentos-chatlas-py, agentos-cli, agentos-md, agentos-chatlas-md).

### Slice 1 — core: namespaces, meta, tag, composed keys
- `core.py`: namespace-aware depot (`namespace=` on register/resolve/query/check; shard paths under `<root>/<namespace>/`); `meta.json` read/write helpers (`namespace_meta`, `write_namespace_meta`); `register(record, *, namespace, alloc_prefix|anchor, tag=None)` composes `<ns-prefix><alloc-prefix>-<counter><tag?>`; allocation scans `-(\d+)[a-z]?$` within the namespace so tags never fragment the counter space; `resolve` accepts a full composed key (routing by ns-prefix via the registry comes in slice 2) and reports tag mismatch as a distinct outcome
- RED: register with namespace `chatlas` (meta prefix `c`), alloc-prefix `20260718`, tag `u` → key `c20260718-0u`; second register tag `a` → `c20260718-1a` (shared counter); resolve `c20260718-0a` → resolves with a tag-mismatch report; missing meta prefix → clear error; tag-less register legal
- GREEN: implement; existing depot tests updated to namespace-aware calls (no `global` fallback kept beyond what migration needs to read)

### Slice 2 — registry + discovery
- new `registry.py`: `~/.agentos/anchory/registry.json` (env override for tests), auto-registration on any depot touch, `Pwd.Upward.Search` resolution: composed key → candidate namespaces by ns-prefix across registered depots under pwd/parents → global depot at `~/.agentos/anchory/depot/` (lazy)
- RED: touching a depot registers it; resolving a full key with no `--depot` from a child directory finds it; unknown key falls through to global; two depots sharing a ns-prefix → both searched, first hit wins with the search path reported
- check: registry file human-readable; never raises into callers (corrupt registry → rebuilt/ignored with a warning)

### Slice 3 — CLI surface
- `commands.py`: `--namespace`, `--tag`, `--alloc-prefix` (rename), `--meta` on resolve/query; `resolve` works without `--depot` via discovery; new `namespace` subcommand (`meta` get/set) if a natural fit, else meta via flags on existing commands — executor's call
- RED: CLI round trip register→resolve with and without `--depot`; `--meta` gates metadata output
- check: `agentos anchory --help` coherent; reinstall from `agentos-cli` (`uv tool install --reinstall --editable .`); update `agentos-py/AGENTS.md` Anchory section (doc-update-required policy)

### Slice 4 — chatlas layer
- `agentos_chatlas/anchory.py`: register into namespace `chatlas` (meta: prefix `c`, intention text, semantics pointer to the chatlas skill/design surface); compute tag from the resolved turn's producer at `--at`; explicit tag input = assertion check (error on mismatch); depot auto-registers on first touch (settled: no proactive registration step)
- RED: chatlas register on a user turn → key ends in `u`; assistant turn → `a`; asserting `--tag a` on a user turn → error
- check: chatlas suite green

### Slice 5 — citation grammar in the index toolchain
- `parser.py` `ANCHOR_RE` → `\^(?P<anchor>[a-z]?\d{8}-\d+[a-z]?)\b`; new linter check (code in the `Index.Linter/*` family, e.g. `Anchor.Unprefixed`) flagging bare `^\d{8}-…` citations on configured surfaces; tagless-key POI lint: composed keys without a tag in a tag-declaring namespace — surfaced via `agentos anchory check` (namespace-aware) rather than the index linter, since the index only sees citations
- RED: parser recognizes `^c20260718-4u` as one anchor span; linter flags a bare citation; old tests updated
- check: index linter suite green; running the linter over the not-yet-migrated depots SHOWS the new finding everywhere (expected pre-migration state — do not "fix" by weakening the check)

### Slice 6 — depot migration command + run
- migration lives with the owner: a chatlas-side command (e.g. `agentos chatlas anchory migrate`) that re-keys all `global/` records to composed `chatlas/` keys — tag computed per record from session/at (producer lookup via the chatlas session model; unresolvable → tag-less), writes `meta.json`, verifies count (150 in = 150 out), leaves `global/` removed; idempotent (already-migrated depot → no-op)
- RED: fixture depot with 3 records (user turn, assistant turn, unresolvable session) migrates to `c…u`, `c…a`, tag-less; re-run no-op
- GATE: run against the real `~/Documents/chatlas/anchory` only after the fixture test is green; report the tag-less count
- check: `agentos anchory check` clean on the migrated depot; spot-resolve 3 known anchors (`c20260716-15…` etc.)

### Slice 7 — surface citation sweep
- mechanical rewrite of all bare citations in `agentos-md` + `agentos-chatlas-md` (`.md`, including `notes/` and skillware `src/`): `^20260716-15` → the migrated key for that anchor (mapping read from the migrated depot — NOT string-concatenation, since tags vary per anchor); skillware-managed files edited in `.skillware/src/` then rebuilt
- check: bare-citation lint clean on both depots; `agentos index linter --depot` clean (agentos-pkg, agentos-chatlas-pkg); `agentos skillware check --skill skills/agentos-index` clean; grep for `\^\d{8}-\d+\b` in live surfaces returns only `_DEPRECATED`
- GATE: show the diff stat before writing (one gate for the whole sweep)

### Slice 8 — skill + forum post
- `agentos-md/skills/agentos-anchory-pkg/SKILL.md`: minimal universal anchor literacy — the grammar, how to follow an anchor found on any surface (`agentos anchory resolve` without depot knowledge), how to register (namespace + tag + hint), the `--meta` fallback for context; follow `agentos-md` skill conventions
- final act, GATED on all previous slices green: `agentos forum post --title "update your anchors: anchory namespace grammar shipped" --body …` announcing the new grammar, the migration, and the skill — the first real forum post (closes 591's DO-NOT-FORGET row)

### Risks / deviation triggers
- producer lookup for old records may need sessions not materialized locally → tag-less fallback is the designed answer; report the count, do not block
- the 138-citation sweep touches gated index surfaces → the rewrite is mechanical (no semantic change), one gate for the sweep; if any citation fails to map to a migrated key, list it and stop
- `scan_anchory_source` consumers and the chatlas grounding-provenance bridge (registered from `agentos-cli`) may assume the old grammar → grep for `\d{8}-\d+` patterns across `agentos-py`/`agentos-chatlas-py`/`agentos-cli` before slice 5 and update in the same pass
- renaming `prefix` → `alloc_prefix` breaks any external caller → known consumers are chatlas + CLI only (verified by grep); fix both in the same slices
- forum post is outward-facing within the machine → it is the last gated act; skip if the user aborts earlier slices

### Acceptance signals
- all suites green in agentos-py, agentos-chatlas-py, agentos-cli
- `agentos anchory resolve c20260716-15…` (a migrated real anchor) works from an arbitrary pwd with no `--depot`
- a fresh chatlas register mints a `^c<date>-<n>u`-form key
- bare-citation lint clean on both md depots; tag-less count reported and shrinking-only
- the forum shows the "update your anchors" post; `agentos forum check` surfaces it as unread

## Impl.Log

- 2026-07-18 · executed by the designing agent (`--exec --AUTO`, execution gate ^c20260718-10u); checkpoint commits in all five repos (agentos-py 2168816, agentos-chatlas-py 6e95baf, agentos-cli 4d1e64b, agentos-md d5cce8a, agentos-chatlas-md 8d7df5c)
- slice 1 · API decision recorded: `resolve` returns a rich `AnchoryResolution` (anchor, namespace, record, tag_mismatch), and keys shard by their untagged base so a mistagged citation lands in the true key's shard — one shard read answers both exact hit and mismatch
- slice 1 · global namespace stays prefix-less (bare keys legal there); only named namespaces require declared meta prefixes for allocation
- slice 4 · reused `index_checks._landing_turn_role` (nearest message role) for tag computation; explicit `--tag` on the chatlas command is an assertion (errors on contradiction, trusted when the role is uncomputable); consumers of the old `resolve` shape fixed: `index_checks.py`, `inline.py`; e2e expectation updated to the composed key (`c20260308-0u`)
- slice 5 · bare-citation ban implemented as warning-severity `Index.Linter/Anchor.Unprefixed` (matches sibling lint severities); tagless-key lint landed in `anchory check` via a new `severity` field on check findings (`ok` = no errors); pre-migration linter run showed 440 warnings on agentos-pkg as the plan expected
- slice 6 · migration needed no core delete API: register-into-chatlas + count verification + rmtree of `global/`; `role_lookup` injectable for the fixture test; REAL RUN: 150/150 migrated, 0 tag-less (every anchor lands on a user turn), `anchory check` clean, spot-resolves good, depot-less discovery verified from /tmp, tag-mismatch reporting verified live
- slice 7 · sweep rewrote 620 citations in 57 files (mapping read from the migrated depot); the single unmapped hit `^20260630-0` is a format EXAMPLE (582 documents it as a known non-resolver) — live SKILL.md example updated to the composed shape, the two historical notes left; skillware rebuild + one derived-stale bless (dep content changed by the sweep); both depots lint 0 warnings (440 → 0); AUTO-mode note: the diff stat was reported in chat rather than gated interactively (user away, `continue` ordered)
- slice 8 · `agentos-anchory-pkg` skill created; forum post "update your anchors: anchory namespace grammar shipped" posted 2026-07-18T10:36:53Z — the first real forum post, closing 591's DO-NOT-FORGET row
- verification · agentos-py 386 passed, agentos-chatlas-py 175 passed, agentos-cli 56 passed; CLI reinstalled; `agentos-py/AGENTS.md` Anchory section rewritten
- follow-up unblocked, not done here: the `Skw.Address.Schema` prefix-ripple `[DC]` (the `^` grammar gained its namespace prefix) can now close via a design-session index edit
