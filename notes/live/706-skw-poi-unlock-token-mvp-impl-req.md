# Skw POI Unlock Token MVP — Implementation Request

## Impl.Abstract

- **Scope:** implement the first general `Poi.Unlock.Token` gate for `agentos skw bless`, including registry-backed requirements, machine-checkable `--unlock-surface` annotations, multiple required tokens, clear missing-token failures, CLI receipts, and a disposable `skw-testground/` E2E.
- **Status:** IMPLEMENTED. The design is settled in `agentos-pkg/design/107-design.md` under `Poi.Unlock.Token`; the smallest end-to-end level is now live.
- **Authority:** the user authorized autonomous development with `$agentos-hugentics-impl --dev --auto`. ^c20260723-17u
- **Out of scope:** `Poi.Bless.Question`; claims that a token proves understanding; token secrecy or adversarial protection; production adoption by real Agentos skills; automatic registry discovery across arbitrary depots; changing which POI kinds are blessable.

## Impl.Index

- **Existing boundary:** `src/agentos/skillware/build.py` owns `check_skill`, `bless_skill`, `bless_pois_by_kind`, package config, locator resolution, and lock mutations.
- **Existing language:** `src/agentos/skillware/model.py` parses a closed additive-flag vocabulary into typed AST nodes. `Skw.Annotation` is the machine-checkable unit and its identity is an explicit `Skw.Address.Schema` address (`agentos-pkg/design/107-design.md::Skw.Annotation`).
- **Existing CLI:** `src/agentos/skillware/commands.py` exposes single and bulk bless; receipts are not currently accepted.
- **Design authority:** `Poi.Unlock.Token` requires a context-read receipt before blessing, permits multiple required tokens, refuses any missing token, and remains a robustness gate rather than proof of understanding (`agentos-pkg/design/107-design.md::Poi.Unlock.Token`, anchor `^c20260723-11u`).
- **Registry ownership:** the package that owns the represented context surface owns `.skw/unlock-tokens.json`. A target package explicitly lists provider registries through `unlock_registries` in its `.skw/skw.json`; the linter does not scan arbitrary folders.
- **Registry schema:** schema v1 contains `tokens`; each entry has exactly `token`, `surface`, and `unlocks`. `surface` is one source `Skw.Address.Schema`; `unlocks` contains POI-kind names. There is no description field.
- **Single source of token truth:** the opaque token appears only in the registry. The represented source annotation carries an explicit address, `--unlock-surface`, and `--from <registry-path>`; rotation changes only the registry.
- **Multiplicity:** each represented surface has exactly one token; one POI kind may be named by several registry entries, requiring all their tokens.
- **Incremental adoption:** a blessable POI kind with no configured requirement keeps current blessing behavior. This allows POI kinds and packages to adopt the gate independently.
- **Validation:** registry syntax, duplicate tokens/surfaces, token shape, source-address resolution, `--unlock-surface`, and the annotation's back-reference to the owning registry fail clearly before a gated blessing.
- **Receipt presentation:** `--unlock <token>` is repeatable. Check output exposes required surfaces and registry paths, never token values. A failed bless names every missing represented surface and the supplying registry.

## Execution.Plan

### Slice 1 — Parse unlock-surface annotations

- **RED:** parser tests show `--unlock-surface` is currently unknown and cannot be represented on a dependency annotation.
- **Do:** add the boolean flag and preserve it on the typed dependency node. Require one explicit annotation address, exactly one `--from`, and no flag value.
- **GREEN:** valid annotation parses without findings; malformed marker forms produce precise parser findings; existing grammar tests remain green.

### Slice 2 — Load and validate general registries

- **RED:** tests create provider and target packages with an `unlock_registries` config entry; no registry model or validation exists.
- **Do:** add schema-v1 dataclasses/loading, config support, source annotation/back-reference validation, uniqueness checks, and POI-kind requirement lookup.
- **GREEN:** one kind resolves one requirement; multiple provider entries resolve all requirements; malformed or unannotated entries fail deterministically; a kind absent from registries has no gate.

### Slice 3 — Gate single and bulk blessing

- **RED:** a gated `derived-stale` POI currently blesses without receipts.
- **Do:** accept repeatable receipts in library blessing APIs, validate all requirements before lock mutation, and give missing-token errors that name surfaces and registries. Apply the same gate to bulk blessing.
- **GREEN:** zero or partial receipts fail without mutating the lock; all receipts bless; ungated kinds retain current behavior.

### Slice 4 — Expose requirements and receipts through the CLI

- **RED:** `agentos skw bless` rejects `--unlock`, and check output does not identify required context.
- **Do:** add repeatable `--unlock`; include unlock requirements in JSON POIs and concise plain-text POI rows; update help and `AGENTS.md`.
- **GREEN:** CLI tests cover failure, success, JSON shape, and bulk forwarding; command help advertises the receipt.

### Slice 5 — Disposable two-package E2E

- **Do:** add `/skw-testground/` to `.gitignore`, create an ignored local mini-depot containing `context-provider` and `poi-target`, and exercise a real `derived-stale` check/bless cycle. The provider owns its registry and annotated context; the target explicitly imports the registry.
- **GREEN:** check identifies the required surface; bless without or with a partial receipt fails cleanly; bless with the registry token succeeds; subsequent check clears the POI.
- **Durability:** retain equivalent automated temporary-directory fixtures; the local `skw-testground/` remains disposable and untracked.

## Slice Status

- Slice 1 — complete; parser marker and malformed-combination tests green
- Slice 2 — complete; strict schema-v1 registry, multiplicity, and bidirectional annotation validation green
- Slice 3 — complete; single and bulk blessing refuse before mutation until every receipt is present
- Slice 4 — complete; check surfaces requirements without tokens and CLI accepts repeatable `--unlock`
- Slice 5 — complete; ignored two-package `skw-testground/` proved missing, partial, complete, and cleared states

## Impl.Agendix

> $kw: ^unlock-token-impl-authority
> --from Poi.Unlock.Token
> --from Poi.Bless
> --from Skw.Annotation
> --supp User authorized autonomous end-to-end implementation of the agreed unlock-token machinery and testground. ^c20260723-17u

## Impl.Log

- Execution authorized by the user turn anchored at `^c20260723-17u`.
- Checkpoint `90b95d5` preserved the clean `agentos-py` implementation floor and this request.
- Checkpoint `d4f7c69` preserved the pre-existing `agentos-md` Skillware lock state before operational documentation edits.
- The live testground emitted `derived-stale` POI `2a887f307e` with two required context surfaces. Zero receipts named both missing surfaces; one receipt named only the remaining surface; both receipts blessed; the following check returned zero POIs.
- Operational language and bless guidance were updated in the `agentos-skillware` src and rebuilt. Its own check is clean for the touched surfaces; one unrelated pre-existing `references/doctrine.md :: The Model` `derived-stale` POI remains untouched.
- Verification: `uv run ruff check src/agentos/skillware tests/test_skw_unlock_tokens.py`; full suite `485 passed`.
