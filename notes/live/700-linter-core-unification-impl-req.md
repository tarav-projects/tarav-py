# 700 — linter core unification: shared drift engine, per-surface backends

## Impl.Abstract

- **scope:** extract a **surface-agnostic linter core** (finding type + severity/bless + check registry + the `Skw.Network` dependency-sync/drift engine + rendering) out of `skillware/build.py`, and make the **index linter** a per-surface backend module that binds into it. Payoff: the index gains **cross-block drift checking** it does not have today.
- **out of scope:** merging the two CLI command surfaces (`agentos skw` and `agentos index` stay split); making index citations first-class declared edges (the *undeclared-mention* direction over index prose is deferred — see Deviation triggers); any code `Skw.Backend`. This is a plumbing/architecture refactor, not a semantics change to existing checks.
- **status:** designed — awaiting execution.
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
- **status:** not started.

### Slice 2 — Formalize the shared finding + provider protocol

- **change:** introduce the unified `Finding` (kind, location, message, **severity**, **bless-ability**, identity hash) and the `SurfaceProvider` protocol (declared edges, mentions, addressable regions + address resolver). Map skw's `Poi` onto `Finding` (advisory/blessable). No behavior change.
- **observable:** skw check output unchanged; `Finding.severity` present and set to advisory for all skw drift POIs.
- **check:** skw suite green; a unit test asserts the skw adapter satisfies `SurfaceProvider`.
- **status:** not started.

### Slice 3 — Index backend implements the provider (drift dormant)

- **change:** add an index backend adapter implementing `SurfaceProvider` over an index depot: declared edges (from the citation forms the index already carries), mentions via `extract_mentions` over compiled block text, addressable regions via an **index address resolver** (heading-based). Wire it so the core drift engine *can* run over the index, but keep the result **off the index CLI output** (dormant/opt-in).
- **observable:** `agentos index linter` output is unchanged; a unit test drives the core over a fixture index depot and gets drift findings from the adapter directly.
- **check:** `run_linter` structural output byte-identical; new unit test on the adapter path.
- **status:** not started.

### Slice 4 — Light up index drift (conservative scope)

- **change:** surface the core's drift findings in `agentos index linter` as **advisory** findings. Scope to the **`derived-stale`-analogue only** — a *known/declared* citation edge whose source changed — **not** undeclared-mention over all index prose (that would flood; index prose mentions concepts everywhere). Render under the index linter's finding model with the advisory severity from Slice 2.
- **observable:** on a fixture where a cited block's source is edited, `agentos index linter` raises a drift finding on the citing block; a normal index depot raises **zero** new findings (no flood).
- **check:** two fixtures (drift-present → one finding; drift-absent → none); full suite green.
- **status:** not started.

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
- **deviation triggers (hard boundaries — surface, do not silently broaden):**
  - index-drift **flooding** (Slice 4 producing findings on ordinary index prose) → stop; the conservative *declared-edge-only* scope is a design invariant, not a tuning knob.
  - discovering that index citations are **not machine-identifiable** as edges (no declared/derivable citation form to key drift on) → stop; making index citations first-class declared edges is out of scope and its own design.
  - any slice that cannot keep the existing linter output **byte-identical** where the plan requires it → stop; behavior preservation is the contract.
