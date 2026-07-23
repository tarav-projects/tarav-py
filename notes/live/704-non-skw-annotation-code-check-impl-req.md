# Non.Skw.Annotation Code Check — Implementation Request

## Impl.Abstract

- **Scope:** add the `Non.Skw.Annotation` drift check — flag a comment on a skw-managed **code** surface that resolves to no `Skw.Annotation` — to `agentos skw check`.
- **Reality:** this is **not** a check that plugs into the existing linter. The only skw backend today is **skw-skills**, which parses markdown `.skw.md` sources whose machinery rides `>` blockquote carrier lines (`src/agentos/skillware/model.py`, `_SkwSurfaceProvider` at `build.py:741`). `agentos skw check` has no concept of a code file, a code comment, or a skw annotation expressed in code. Delivering this check requires standing up a minimal **skw-code backend** first. This matches the index conclusion (107 `Skw.Backend` line 114 marks `skw-code` a *candidate*; `Non.Skw.Annotation` 107 defines the POI).
- **Status:** READY. D1 resolved by the user: **carrier B** (`# $kw: …`, the comment is the carrier). Architecture directed by the user: **reuse one core across surfaces — split into a surface-agnostic `$kw` frame core plus per-surface carrier adapters** (Slice 1). Executing under `--dev --AUTO`.
- **Source context:** session capture of `Non.Skw.Annotation` into `agentos-pkg/design/107` (anchors `^c20260722-20u`, `^c20260722-21u`); `/agentos-hugentics-impl --dev --AUTO develop Non.Skw.Comment check into the skw linter`.
- **Out of scope:** multi-language comment hosts beyond Python for the first cut; directive-annotation vocabulary (`TODO`/`type: ignore` → skw forms) — a follow-up once the carrier exists; the `--from`/design-linking semantics for code annotations (reuse the existing model, do not extend).

## Impl.Index

- **Current state (cited):**
  - `src/agentos/skillware/model.py` — `parse_skw_source(text)` parses the `>` markdown carrier; machinery detection is carrier-coupled (module docstring; `_read_open`, frame machinery). No carrier abstraction.
  - `src/agentos/skillware/build.py:741` — `_SkwSurfaceProvider` is the sole `SurfaceProvider`; `check_skill` drives it. Surface discovery is `.skw/src/**/*.skw.md`.
  - `src/agentos/skillware/commands.py:25` — `POI_LEGEND` is the POI-kind registry (meaning + prescription) `agentos skw check` renders; kinds are markdown-surface kinds.
  - `src/agentos/skwlint.py` — surface-agnostic core: `Poi`, `SurfaceProvider` Protocol, `run_dependency_sync`, `dangling_mention_findings`, the check-selection core. A new backend implements `SurfaceProvider`; the core is already ready for it.
  - `agentos-pkg/design/107` — `Non.Skw.Annotation` (POI def), `Skw.Backend` (`skw-code` candidate, "declarations ride the host language's comments"), `Annotation.Point` (file is the universal host; code adds functions/modules), `Annotation.Authority` (finer points user-gated), `Poi.Bless` (blessable).

- **D1 — code carrier grammar (RESOLVED → carrier B):**
  - the comment **is** the carrier: `# $kw: [address] [--flags]` opens, `# --flag …` belongs, `# $kw. end` closes. No doubled sigil (rejected: `# > $kw:`).
  - a multi-line annotation rides consecutive comment lines; the "body/live fragment" is the code below the annotation, up to the next `Annotation.Point` boundary.

- **D0 — core/surface split (architecture, user-directed):**
  - factor `parse_skw_source` into (a) a surface-agnostic **frame core** — the `$kw` machinery: open/flag/end tokens, frame stack, closure-by-role, addresses — and (b) a **carrier adapter** per surface that tokenizes raw text into `(open | flag | end | body)` and knows the host's comment/body rule.
  - markdown adapter: machinery rides `>` lines, body is column-0 native text. code adapter: machinery rides `#` comment lines (carrier B), body is code up to the next point.
  - the frame core is shared verbatim; only the adapter is surface-specific. skw-skills must stay byte-for-byte green through the refactor.

- **D2 — what counts as a comment / `Annotation.Point` in Python (first host):** line comments (`#…`) and contiguous runs; module/function/class are host points (107 `Annotation.Point`). Module docstrings: treat as prose, not comments (out of first cut). Resolvable deterministically once D1 is set.

- **D3 — resolution rule for the check:** a comment resolves to a `Skw.Annotation` iff it is part of (opens or belongs to) a well-formed skw annotation block in the chosen carrier. Every other comment is a `Non.Skw.Annotation` POI (advisory, blessable per `Poi.Bless`).

## Execution.Plan

D1/D0 resolved. Test-first at each boundary. Loop: `pytest tests/test_skw_carrier.py tests/test_skw_code_backend.py tests/test_skillware*.py`; completion runs full `pytest` + live `agentos skw check` on a fixture code package.

### Slice 1 — core/surface split of the parser (carrier abstraction)
- **Do:** factor `parse_skw_source` into a surface-agnostic frame core plus a `Carrier` that tokenizes raw text into machinery/body tokens (D0). Reimplement the existing markdown behavior as the `MarkdownCarrier`; `parse_skw_source(text)` keeps its signature, now delegating to `core + MarkdownCarrier`.
- **Observable:** every existing skillware test passes unchanged — the refactor is behavior-preserving for skw-skills.
- **RED/GREEN:** the existing `test_skillware*` suite is the RED/GREEN guard (must stay green); add a focused test that the core consumes a token stream independent of any carrier.

### Slice 2 — code carrier (carrier B) + code parse
- **Do:** add `CodeCarrier` (Python first): machinery rides `# $kw:`/`# --flag`/`# $kw. end` comment lines; body is code below the annotation up to the next `Annotation.Point`. Parse into the same `SkwSource`/`SkwConstruct` model via the shared core.
- **Observable:** a `.py` fixture with an inline skw annotation parses to the same construct types as the markdown equivalent.
- **RED/GREEN:** fixture parse test — annotation recognized, its comment lines attributed, body span identified; a malformed carrier is a parse error (`Parse.Floor`).

### Slice 3 — `_SkwCodeSurfaceProvider` + surface discovery
- **Do:** a `SurfaceProvider` for code surfaces; extend `skw.json` `surfaces` discovery to include declared code globs (e.g. `*.py`). Drive it through the existing `check_skill` path.
- **Observable:** `agentos skw check` visits code surfaces listed in `skw.json`.
- **RED/GREEN:** a package with a declared `.py` surface is walked; one with none is not.

### Slice 4 — the `Non.Skw.Annotation` POI
- **Do:** emit a `non-skw-annotation` POI for each comment not resolving to a `Skw.Annotation` (D3); register it in `POI_LEGEND` (meaning + prescription: wrap as `--note`/`--from`/directive, or bless as throwaway); blessable via the existing bless path; **default-off** and opt-in via the check-selection surface (`--check non-skw-annotation`), mirroring `dangling-mention` — a fresh code surface would otherwise wall-of-POI.
- **Observable:** a `.py` fixture with one skw annotation and two bare comments reports exactly two `non-skw-annotation` POIs; blessing one clears it; wrapping one removes it.
- **RED/GREEN:** the count test above; a bless test; a default-off test (no POIs unless `--check`ed).

### Slice 5 — docs
- **Do:** update `AGENTS.md` (skw backends, the new POI kind, code surface discovery) in the same unit of work (AGENTS.md policy).

## Slice Status

- Slice 1 — core/surface split (`Carrier` abstraction), skw-skills green — ✅ 87 skw tests unchanged; `_parse_source(text, carrier)` + `MARKDOWN_CARRIER`/`CODE_CARRIER`
- Slice 2 — code carrier B + code parse — ✅ `parse_skw_code`; 6 backend tests
- Slice 3 — code surface discovery (by-machinery) — ✅ `_code_surface_pois` / `_iter_code_files`, `"$kw"` prefilter
- Slice 4 — `non-skw-annotation` POI, default-off, suppress-blessable — ✅ 4 check tests; live CLI verified
- Slice 5 — AGENTS.md — ✅ carrier split + new POI kind documented

## Impl.Log

- Designed under `--dev --AUTO`. Halted before execution once: the task presupposes a `skw-code` backend that did not exist, and its first slice was a language-design decision (D1, the code carrier grammar) that `--AUTO` must not commit unilaterally. Surfaced to the user; they resolved **D1 → carrier B** and directed the **core/surface split** (D0). Execution then proceeded end-to-end.
- **Deviation — discovery mechanism.** Slice 3 designed "declared code globs in `skw.json`". Implemented instead as **discovery-by-machinery** (a `.py` carrying `# $kw:` is a managed surface), config-free and per-file opt-in, reusing the existing schema. Reason: reusing `surfaces` at package scope would collide with its project-scope package-set meaning, and a 5th config key was unwanted churn for a default-off first cut. Declared globs remain a clean future refinement.
- **Scope note — Python only, full-line comments only.** First host is `.py`; inline trailing comments (`x = 1  # …`) and `#` inside string literals are not distinguished (the `"$kw"` prefilter + machinery-span exclusion keep false positives to shebang/encoding lines, acceptable for a default-off check). Documented as follow-ups.
- Result: full suite **467 passed** (+10). Live `agentos skw check`: `--list-checks` shows `non-skw-annotation [off] reportable`; default run emits none; `--check non-skw-annotation` emits exactly the bare comments (machinery line excluded); suppress-bless clears them.
