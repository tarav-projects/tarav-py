# Index.Depot.Dependency — Implementation Request

## Impl.Abstract

- **Scope:** implement the directed `Index.Depot.Dependency` system in `agentos-py` and integrate it into `agentos index linter`, including collision `Drift.POI`s.
- **What:** a depot resolves cross-depot `Dotted.Name` mentions only against depots it *declares* as dependencies (directed, non-transitive). Declaration is two-tier: local depot declares dep depots **by name**; a global `~/.agentos` registry resolves each name → path. Wire the (currently dormant) dangling-mention machinery into the live linter, add collision detection, and surface both as findings.
- **Status:** IMPLEMENTED (`--develop --AUTO`). All 5 slices done; full `agentos-py` suite 431 passed; live `agentos index linter` on the real `agentos-pkg` depot stays clean (0/0, 22 passed checks). Slice-5 scope deviation recorded below.
- **Source context:** design + grounding discussion this session; concept `Index.Depot.Dependency` promoted into `agentos-pkg/design/104-design.md` (routed). Grounding anchors: `^c20260722-15u` (two-tier config design), `^c20260722-16u` (non-transitive + collision decisions).
- **Out of scope:** canonical/plural short-forms, `::`-scoped names, example placeholders, non-index skill-surface concepts (the pre-existing dormant-resolver backlog on 700, unchanged here); config-layering / project-local registry override; a separate authoritative deps config *file* with router-as-mirror — see Impl.Log deviation on the declaration surface.

## Impl.Index

- **Current state (cited):**
  - `src/agentos/index/drift.py` — `IndexSurfaceProvider`, `_defined_concepts`, `_engaged_concepts` (flat undirected union), `index_dangling_mentions`. Marked DORMANT, not CLI-wired.
  - `src/agentos/skwlint.py` — `dangling_mention_findings`, `Poi`, `SurfaceProvider`, `extract_mentions` (the reusable core).
  - `src/agentos/index/linter.py` — `LinterConfig.depot_paths`, `LinterState`, `LinterCheck`, `CHECKS` tuple, `LinterFinding`; findings carry `severity/code/message/path/line/details`.
  - `src/agentos/_core/project.py` — `agentos_home_dir()` (honors `AGENTOS_HOME`), `global_config_path()`, `load_global_config()`. Global `~/.agentos/config.json` already carries a `skills.routing.sources` name→location map (the registry-shape precedent).
- **Design decisions (grounded):**
  - directed + **non-transitive**: visibility set = own concepts ∪ *directly declared* deps' concepts; a dep's own deps are not visible through it. `^c20260722-16u`
  - two-tier declaration: local names + global `~/.agentos` registry name→path; no absolute paths in local declaration. `^c20260722-15u`
  - collision (a mention resolving against a name defined in ≥2 *visible* depots) is an advisory `Drift.POI`; the linter reports, never repairs. `^c20260722-16u`
  - registry reuses the `skills.routing.sources` shape as a sibling global-config key; no config-layering machinery is introduced (start simple). `^c20260722-16u`
- **Concept authority:** `Index.Depot.Dependency` (`agentos-pkg/design/104-design.md`) — this implementation is its `Current.Implementation`.

## Execution.Plan

Ordered vertical slices. Test-first (`RED.GREEN.Test.Suite`) at module boundaries (`Test.At.Boundaries`); new tests in `tests/test_index_drift.py` unless noted. Feedback loop: `python -m pytest tests/test_index_drift.py` per slice; full `pytest` + `agentos index linter --depot <fixture>` at completion.

### Slice 1 — Global depot registry reader
- **Do:** add a reader that returns the depot registry (name → `Path`) from the global agentos config. New module `src/agentos/index/depot_deps.py`. Read `~/.agentos/config.json` via existing `agentos_home_dir()`/`global_config_path()`; expected key shape mirrors `skills.routing.sources` — a sibling map, e.g. `{"index": {"depots": {"<name>": {"path": "..."}}}}`. Resolve `project`/`path` entry forms defensively; missing config or key → empty map (never raise).
- **Observable:** `load_depot_registry(home=…) → {name: Path}`.
- **RED/GREEN:** temp `AGENTOS_HOME` with a config carrying two depots → both resolve; missing key / missing file → empty dict.

### Slice 2 — Local dependency declaration reader
- **Do:** parse a depot's declared dependency depot **names** from its `000-INDEX.md` router. Declaration form mirrors the existing router directive line (`> \`Appendix.Discovery\`: …`): a `> \`Index.Depot.Dependency\`: name-a, name-b` line. Add `declared_dependency_names(depot_root) → list[str]` in `depot_deps.py`. No router directive → empty list.
- **Observable:** the names list from a router.
- **RED/GREEN:** router with the directive → parsed names (order preserved, deduped); router without it → `[]`.

### Slice 3 — Directed, non-transitive visibility resolution
- **Do:** resolve a depot's dependency **paths** = registry-lookup of its declared names (Slice 1 ∘ Slice 2), non-transitive. Rewire `IndexSurfaceProvider` so its visibility set is `own ∪ direct-deps` computed from the declaration+registry, not a caller-supplied flat `engaged_depots`. Keep an explicit-override parameter for tests. A declared name absent from the registry is retained for Slice 5 to flag.
- **Observable:** provider resolves a mention defined only in a declared dep; does **not** resolve one defined only in a dep-of-a-dep.
- **RED/GREEN:** depot D declares B (registry-resolved); B defines `Foo`, C defines `Bar`, B declares C. D mentions `Foo`→resolved, `Bar`→unresolved (non-transitive).

### Slice 4 — Collision detection
- **Do:** add resolution that maps a name → the set of *visible* depots defining it; a mention whose name is defined in ≥2 visible depots yields a collision `Poi` (advisory). Add `depot_collision_findings(...)` in `drift.py` (or `depot_deps.py`) reusing the `skwlint.Poi` shape/severity.
- **Observable:** a collision `Poi` for a doubly-defined visible name; none when unique.
- **RED/GREEN:** D and its declared dep B both define `Shared`; D mentions `Shared` → one collision Poi. Name defined in only one → no Poi.

### Slice 5 — Linter integration
- **Do:** wire into `agentos index linter`: for each linted depot, run directed dangling-mention (Slice 3) + collision (Slice 4), plus a package-level finding when a declared dep name does not resolve in the registry (unresolved dependency). Add `LinterCheck`(s) with new `Index.Linter/…` codes, mapped to `LinterFinding`s (advisory/warning severity — collisions and dangling mentions are advisory `Drift.POI`s, not gate errors). Register in `CHECKS` behind a gate that requires a discovered index surface.
- **Observable:** `agentos index linter --depot <fixture>` surfaces dangling-mention, collision, and unresolved-dependency findings; a clean fixture stays at 0.
- **RED/GREEN:** end-to-end linter run over a temp depot pair exercising each finding; a self-consistent depot with no deps → no new findings (guards the real `agentos-pkg` depot from regressing to noise).

## Slice Status

- Slice 1 — registry reader — ✅ `depot_deps.load_depot_registry`
- Slice 2 — local declaration reader — ✅ `depot_deps.declared_dependency_names`
- Slice 3 — directed non-transitive resolution — ✅ `depot_deps.resolve_dependency_depots` + `IndexSurfaceProvider` rewired
- Slice 4 — collision detection — ✅ `drift.index_depot_collisions` / `IndexSurfaceProvider.collisions`
- Slice 5 — linter integration — ✅ `linter._check_depot_dependencies` (collision + unresolved-dependency wired live); dangling-mention deliberately not CLI-wired (deviation below)

## Impl.Log

- **Deviation (Slice 5 — dangling-mention not wired live) — resolved autonomously:** the plan called for wiring directed dangling-mention into the live linter too. Doing so regresses the real `agentos-pkg` depot to ~99 false positives — the documented resolver gap (canonical/plural short-forms, `::`-scoped names, example placeholders, non-index skill-surface concepts) carried over from Impl.Req 700, which is why that path was DORMANT. Most faithful action: wire only the **precise** pieces live — collision `Drift.POI`s (explicitly requested) and unresolved-dependency findings — both adoption-gated (a depot declaring no deps emits nothing). Directed dangling-mention stays available via `drift.index_dangling_mentions` (now fed by directed resolution) but not CLI-wired, pending the resolver-gap design work. Verified: the real `agentos-pkg` depot stays at 0/0 (22 passed) after integration.
- **Deviation (declaration surface) — resolved autonomously:** the promoted concept says a *local config* is the machine source the linter reads, with the router as a *mirror*. To avoid inventing a second config-file location for standalone skill-dir depots (a depot is not always an agentos project), this cut makes the depot's `000-INDEX.md` router the single authoritative local declaration (`router-as-config`, an option raised in the design discussion). The separate authoritative deps *file* with router-mirror is deferred; recorded here as the doctrinal end-state. `^c20260722-15u`
- Registry key shape (`index.depots`) is chosen to sit beside `skills.routing.sources`; if a canonical key is later fixed, it is a one-line change in `depot_deps.py`.
