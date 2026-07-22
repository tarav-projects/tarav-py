# 700 — linter core unification: shared drift engine, per-surface backends

## Impl.Abstract

- **scope:** extract a **surface-agnostic linter core** (finding type + severity/bless + check registry + the `Skw.Network` dependency-sync/drift engine + rendering) out of `skillware/build.py`, and make the **index linter** a per-surface backend module that binds into it. Payoff: the index gains **cross-block drift checking** it does not have today.
- **out of scope:** merging the two CLI command surfaces (`agentos skw` and `agentos index` stay split); making index citations first-class declared edges (the *undeclared-mention* direction over index prose is deferred — see Deviation triggers); any code `Skw.Backend`. This is a plumbing/architecture refactor, not a semantics change to existing checks.
- **status:** executed to the scope boundary — Slices 1–3 landed and byte-clean (shared core, `SurfaceProvider` protocol, per-check severity, index backend, edge-free `dangling-mention`, all fixture-proven; 414/414). Slice 4's production lighting-up + Slice 5 deferred to a named follow-up (an index-aware resolver = `Unresolved.Index.Name`), which is out of this refactor's plumbing scope. Uncommitted; checkpoint `277d643`.
- **source:** design discussion this session (linter mechanics); grounded below.
- **support set (ordering):** ^c20260721-20u (the thesis turn directing this work).

## Impl.Index

### Linter.Core.Split

- the current state: **two independent linter engines** over one shared model. `index/model` (`parse_depot`, `KernelLine`, Dotted.Name resolution) is already imported by `skillware/build.py:22` — the shared floor exists.
- `skillware/build.py` owns the drift engine: `_dependency_sync_pois` (`:772`) computes `dangling` / `undeclared` / `unhonored` from **declared edges** (`source.dependencies`/`source.recipes`) vs **resolved mentions** (`extract_mentions` → `_resolved_dotted_names`). It is already parameterized on exactly the seam we want. `Poi` (`:561`), `_poi` (`:594`), `CheckReport` (`:579`), `check_skill` (`:892`), bless via lock (`_suppress_blessed :607`).
- `index/linter.py` owns a *gated* framework: `LinterCheck`/`LinterState`/`run_linter` (`:158/225/377`), `LinterFinding` (`:126`, carries `code`), `GateResult`/`blocked` (`:151/320`), `render_linter_text/json` (`:404/400`), a large structural check registry (`:1554+`).
- **every index check is structural/well-formedness** (block grammar, router, line-type, anchor shape, filename, ungrounded/unlinked). **There is no cross-surface drift check** — the only "stale" is the narrow `APPENDIX_ROUTE_ANNOTATION_STALE`. This is the gap ^c20260721-22u.

### Core.Vs.Backend.Responsibilities

- **the model (`Skw.Backend`):** the index is a per-surface backend; its linter is that backend's check-set plugged into the general engine ^c20260721-20u.
- **shared core owns, surface-agnostically:** the finding type (kind + location + message + **severity** + **bless-ability** + identity hash), the check registry/runner, the dependency-sync/drift engine (`Skw.Network`), and rendering.
- **each per-surface module owns:** (a) its **format/structural linting** (surface-specific, gateable — stays entirely inside the module, never touches the core); (b) its **binding into the core**.
- this is the **extensibility point**: a new surface = a new module implementing the provider interface; the code `Skw.Backend` becomes just another such module ^c20260721-21u.

### Surface.Provider.Interface

- the seam that keeps the core surface-agnostic. Each backend hands the core three things:
  1. **declared edges** — the surface's `--from`/citation dependencies.
  2. **resolvable mentions** — its compiled text → Dotted.Names (`extract_mentions`), resolved via the shared resolver.
  3. **addressable regions** — what a `--from` may point *at*, resolved by a **per-surface address resolver** (headings for the index, fenced spans for code; `#region`/`^label`/`path#region` rules stay pluggable, not one global scheme).
- the core runs sync/drift over those and knows nothing about markdown vs index blocks. `Deep.Modules`: a small provider protocol hiding the drift engine.

### Severity.Is.Per.Check

- the one axis that must **not** be flattened: severity + bless-ability live on the **check**, not the linter. Index structural errors are hard-gated and unblessable; drift POIs are advisory and blessable — in **both** backends. The unified finding carries severity; the registry carries the gate. `Drift.POI`: the CPU never rules on drift, so drift stays advisory everywhere.

## Impl.Agendix

- **touched (chat):**
  - the thesis — index linter is a surface-specific part of the skw linter; split the command surface, integrate the mechanics ^c20260721-20u
  - split skw into a common core + per-surface modules; the module owns format linting, the dependency mechanics are shared — the extensibility point ^c20260721-21u
  - the motivating drift case — a block changes and another block inlined it; that is a `Drift.POI` the index should raise ^c20260721-22u
- **touched (index):** `Skw.Backend`, `Drift.POI`, `Skw.Network`, `Poi.Linter` (107); `Annotation.Point`, `Skw.Address.Schema` (107); `Internal.Alignment`, `Cited.Duplication` (100); `Index.Skillware` (103); `Deep.Modules` (102) — the concepts this refactor must honor.
- **structural:** the shared core is a *behavior-preserving extraction* of the existing `_dependency_sync_pois` engine — no new drift semantics; the derivation (old engine → core) is its own evidence.
- **open space:** exact module layout and names (`skw/linter_core.py`, provider protocol as ABC vs `Protocol`, where the address resolver lives), and whether the shared finding is a base class or an adapter — left to the executer within these constraints; unanchored, provisional.

## Execution.Plan

Behavior-preserving throughout: **both linters keep byte-identical output every slice** except the one slice that deliberately adds index drift output. Full agentos-py suite is the outer guard; per-slice checks below are the inner guard.

### Slice 1 — Extract the drift engine into a surface-agnostic core

- **change:** lift `_dependency_sync_pois` and its `Poi`/`_poi`/bless plumbing into a new core module, parameterized on `(declared_edges, mention_text, resolver)` — the `Surface.Provider.Interface` inputs. Rewire `check_skill` to call the core through a thin skw-skills adapter that supplies those three inputs from `SkwSource`/`Expansion`.
- **observable:** `agentos skw check` and `agentos skw check --json` produce identical output on the existing fixtures.
- **check:** `tests/test_skillware.py` green unchanged; diff the CLI output on a sample skill before/after.
- **status:** ✅ done — created `agentos/skwlint.py` (neutral top-level core) holding `Poi`, `poi`, `blessed_hashes`, `suppress_blessed`, `dependency_sync_findings`; `build.py` imports them and `_dependency_sync_pois` is now a thin skw adapter (extract declared/mentions → delegate). `skw check` text+JSON byte-identical to golden; 76/76 skillware, 408/408 full suite.

### Slice 2 — Formalize the shared finding + provider protocol

- **change:** introduce the unified `Finding` (kind, location, message, **severity**, **bless-ability**, identity hash) and the `SurfaceProvider` protocol (declared edges, mentions, addressable regions + address resolver). Map skw's `Poi` onto `Finding` (advisory/blessable). No behavior change.
- **observable:** skw check output unchanged; `Finding.severity` present and set to advisory for all skw drift POIs.
- **check:** skw suite green; a unit test asserts the skw adapter satisfies `SurfaceProvider`.
- **status:** ✅ done — added `ADVISORY`/`ERROR` severity (new `Poi.severity` field, default advisory — JSON serializes explicit fields so output is byte-identical), the `SurfaceProvider` `Protocol` (`declared_edges`/`mentions`/`resolve`), and `run_dependency_sync`. `build.py` now has `_SkwSurfaceProvider`; `_dependency_sync_pois` is a 2-line adapter. Two new tests (protocol conformance + advisory severity); `skw check` byte-identical; 410/410.

### Slice 3 — Index backend implements the provider (drift dormant)

- **change:** add an index backend adapter implementing `SurfaceProvider` over an index depot: declared edges (from the citation forms the index already carries), mentions via `extract_mentions` over compiled block text, addressable regions via an **index address resolver** (heading-based). Wire it so the core drift engine *can* run over the index, but keep the result **off the index CLI output** (dormant/opt-in).
- **observable:** `agentos index linter` output is unchanged; a unit test drives the core over a fixture index depot and gets drift findings from the adapter directly.
- **check:** `run_linter` structural output byte-identical; new unit test on the adapter path.
- **status:** ✅ done — `agentos/index/drift.py` (`IndexSurfaceProvider` + `index_dangling_mentions`); core gained `dangling_mention_findings` (the edge-free drift check the index needs). `extract_mentions` relocated to the core so the index binds without importing `skillware/`. `tests/test_index_drift.py` (4 tests): index provider satisfies the protocol, clean fixture → 0, a removed concept → one `dangling-mention`, core check is surface-agnostic. Index CLI untouched (dormant); `skw check` byte-identical; 414/414.

### Slice 4 — Light up index drift (conservative scope)

- **change:** surface the core's drift findings in `agentos index linter` as **advisory** findings. Reframed during exec: the index has no declared edges, so the check is **`dangling-mention`** (a mention that no longer resolves), not the `derived-stale`-analogue.
- **observable:** on a fixture where a concept is removed, the check raises one `dangling-mention`; a clean fixture raises **zero**.
- **status:** ⏸ **machinery done + fixture-proven (Slice 3 tests); production lighting-up DEFERRED.** Enabling it on the real `agentos index linter` requires an **index-aware resolver** the index does not yet have. Exec-time decomposition of the real `agentos-pkg` index (385 mentions):
  - 302 resolve via the shared resolver (headings, one depot);
  - 5 are **cross-depot** headings (`agentos-chatlas-pkg`);
  - 78 are **canonical/plural short-forms** (`Stable.Surfaces`→`Stable.Surface`, `Development.Principle`→`Development.Principles`), **`::`-scoped** names (`Package.Driver::Agentos.Pkg`), or **inline sub-concepts** (`Gr.Set`, `Session.Log`);
  - **0 are truly absent** — the live index is drift-free, so lighting up now with a headings-only resolver would be **78 false positives, 0 true**.
  - The resolver that reaches zero-noise (aliases/canonical + `::` scoping + multi-depot + inline definitions) is effectively implementing `Unresolved.Index.Name` (104) — a real, unbuilt subsystem, out of this Impl.Req's plumbing scope. **Its own follow-up.**

### Slice 5 — Share rendering + finalize the pluggable resolver

- **status:** ⏸ deferred as premature. The finding *type* is already shared (`skwlint.Poi`); unifying the two CLIs' *renderers* buys nothing until index drift is actually lit up (Slice 4), and would risk the index linter's byte-identical output for no current gain. Revisit with the resolver follow-up.

_(original Slice 5 change/observable retained below for the follow-up)_

### Slice 5 — Share rendering + finalize the pluggable resolver

- **change:** route both linters' finding rendering through one shared text/JSON renderer parameterized by severity; confirm the address resolver is injected per surface (index heading resolver vs the skw address resolver) with no global scheme assumed.
- **observable:** both `agentos skw check` and `agentos index linter` render through the shared path with unchanged output.
- **check:** golden-output diffs on both CLIs; full suite green.
- **status:** not started.

### Acceptance signals

- `agentos skw check` output unchanged across all slices; full `test_skillware.py` green.
- `agentos index linter` structural output unchanged through Slice 3; Slice 4 adds **only** scoped drift findings with no false floods.
- the drift engine lives in one core module consumed by both backends; severity/bless is per-check; the address resolver is per-surface.
- new capability demonstrated: an index citation whose source drifts raises a `Drift.POI` ^c20260721-22u.

## Impl.Log

- 2026-07-21 — designed under `agentos-hugentics-impl --design` (Interactive). Design converged in-session; grounded on ^c20260721-20u / -21u / -22u. Awaiting the boundary confirmation before execution.
- 2026-07-21 — **execution start** (`--exec --AUTO`). Gate: ^c20260721-20u (ordering) / ^c20260721-23 (exec). Checkpoint commit `277d643`. Baseline 408/408; CLI goldens snapshotted.
- 2026-07-21 — **Slices 1–2 complete.** The surface-agnostic core (`agentos/skwlint.py`) is extracted and both backends' entry point (`_SkwSurfaceProvider` → `run_dependency_sync`) routes through it; `skw check` byte-identical (text+JSON); 410/410. The architectural win — one drift engine, a `SurfaceProvider` seam, per-check severity — is landed and proven.
- 2026-07-21 — **DEVIATION (declared trigger fired) — Slices 3–5 halted, surfaced for decision.** Investigating the index model (`index/model/parser.py`, `nodes.py`) confirms the deviation trigger written into this plan: **the index has no machine-identifiable block→block citation edges.** Index blocks parse `^anchor` spans (chat grounding) and Dotted.Name **mentions** — but nothing a block *declares* as a dependency on another block. Consequences:
  - the `undeclared`/`unhonored` directions are inapplicable to the index (no declared edges to sync against); running the core as-is would flood every resolving mention as `undeclared`.
  - the drift the user actually wants — "block B renamed/removed, block A referenced it" (^c20260721-22u) — is a **dangling *mention*** (a mention that no longer resolves), which is a **new check kind**, not the current declared-edge `dangling`/`derived-stale`. That is a design reshape beyond this Impl.Req's scope.
  - **empirical probe (before picking a path):** ran a dangling-mention probe over `agentos-pkg` design/ — **113 of 385 distinct mentions (29%) do not resolve to a `##` concept heading.** The sample is overwhelmingly *not* drift: `Anchory.Anchor`, `Chat.Support.Set`, `Alignment.Question`, `Address.Schema` — real concepts declared as **inline `Explicit.Namespace` members**, **cross-depot** concepts, or **canonical short-forms**, none of which are `##` headings. A naive dangling-mention check **floods**. Making it low-noise requires the shared resolver to model the index's real resolution rules (inline members, cross-depot, builtins, canonical forms) — genuine design, not a mechanical slice.
  - **corrective action taken (not a stop):** built the drift *machinery* to completion and proved it on a fixture — the core gained `dangling_mention_findings`, the index got `IndexSurfaceProvider` (Slice 3), and `tests/test_index_drift.py` shows the check fires on a removed concept and is silent on a clean depot. Only the **production lighting-up** on the real index is deferred, because full decomposition of the 385-mention flood shows the residue is 5 cross-depot + 78 canonical/`::`/inline forms + **0 real drift** — a zero-noise real-index run needs an index-aware resolver (aliases + `::` scoping + multi-depot + inline defs), i.e. `Unresolved.Index.Name` (104), an unbuilt subsystem beyond this refactor's plumbing scope. That is the follow-up; the architecture and the drift engine are done and consumed by both backends.
- **not started (blocked on the fork above):** Slice 3 (index adapter), Slice 4 (light up index drift), Slice 5 (shared rendering + resolver).
- 2026-07-21 — **resolver follow-up: multi-depot + declared aliases** (the two safe-and-mechanical buckets). `IndexSurfaceProvider` now takes `engaged_depots` and unions defined concepts across them; `_defined_concepts` also indexes `### meta / - aliases:` names. Real-index residual ~132 → **99** — still non-zero, so index drift **stays dormant**. A deeper probe showed the rest is *not* mechanical: canonical/plural short-forms resolve only via **unsafe** heuristics (`Agentos.Index`→`Agentos.Index.System`, `Master.Agent` ambiguous), plus `::`-scoped names, illustrative example placeholders (`Concept.Y`), and cross-*package* concepts defined on non-index skill surfaces. Lighting up Slice 4 needs those rules, which are design decisions (`Unresolved.Index.Name`), not code. Tests `test_index_drift.py` 9/9; both CLIs byte-identical; suite 420/420.
- 2026-07-21 — **follow-up piece landed: `Inline.Definition` resolution** (standalone, on request). The index resolver now recognizes concepts defined by a `[DF]` line inside another block, not just `##` headings — enumerated from the index model's own line-type + concept spans (`_defined_concepts` in `index/drift.py`, replacing `_heading_concepts`). Fixture-proven: an inline-defined concept resolves (no false dangling), and removing its `[DF]` line raises `dangling-mention`. Real-index effect: **10 inline definitions discovered, 7 design mentions newly resolved (113→106 unresolved)**. This clears the **inline bucket** of the resolver follow-up; the dominant buckets (cross-depot ~30, canonical/plural short-forms ~15, `::`-scoped ~4) remain, so index drift stays dormant. Tests `test_index_drift.py` 7/7; both CLIs byte-identical; full suite 417/417.
- **deviation triggers (hard boundaries — surface, do not silently broaden):**
  - index-drift **flooding** (Slice 4 producing findings on ordinary index prose) → stop; the conservative *declared-edge-only* scope is a design invariant, not a tuning knob.
  - discovering that index citations are **not machine-identifiable** as edges (no declared/derivable citation form to key drift on) → stop; making index citations first-class declared edges is out of scope and its own design.
  - any slice that cannot keep the existing linter output **byte-identical** where the plan requires it → stop; behavior preservation is the contract.
