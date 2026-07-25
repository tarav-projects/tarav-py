# Edition history required support - impl-req

## Impl.Abstract

- **scope:** replace optional generic edition-history `evidence` with one required embedded `chatlas.support-set.v1` record across the public library, CLI, tests, and maintainer guidance
- **status:** implemented and verified
- **source:** autonomous develop request to implement the accepted edition/session support invariant
- **support set:** design and execution authorization ^c20260725-14u
- **target projects:** `agentos-py` owns the schema and command domain; `agentos-cli` owns umbrella CLI coverage; `agentos-md` owns the generated Skillware maintainer module

## Impl.Agendix

- **touched (index):** `Skw.Edition.History.Service` requires every edition/session association to carry a nonempty resolvable `Chat.Support.Set` ^c20260725-12u
- **touched (index):** `Skw.Edition.History.Service/Skw.Edition.Session.Support` defines direct embedding, associated-session membership, and the maintainer-versus-linter judgment split ^c20260725-12u
- **touched (chat):** replace optional generic `evidence` directly with required structured `support` ^c20260725-14u
- **structural:** `agentos-py` remains independent of `agentos-chatlas-py`; this slice validates the Chatlas-owned record shape but does not import its parser or resolver
- **implementation:** service, command, and test file annotations ground the required-support contract in `Skw.Edition.History.Service` ^c20260725-12u
- **implementation:** the schema migration across the owning packages is authorized by the develop invocation ^c20260725-14u
- **open space:** exact helper decomposition and diagnostic wording remain implementation-owned within the contracts below

## Impl.Index

### Current.State

- `EditionHistoryService.record` accepts optional `evidence`, normalizes it as an arbitrary JSON object, and persists it under `evidence`
- `EditionSession` projects the same arbitrary object
- the CLI exposes optional `--evidence-json` or `--evidence-file`
- tests and the Skillware developer module still demonstrate evidence rather than a proof-bearing support set
- the accepted ontology now makes a nonempty support set an association invariant, so the implementation is stale

### Support.Record

- replace `evidence` with `support`; no old field, alias, fallback, or migration reader remains
- support is an exact object with `app`, `schema`, `hint`, and `members`
- `app` is exactly `chatlas`; `schema` is exactly `chatlas.support-set.v1`
- `hint` is a nonempty string describing what the support set establishes
- `members` is a nonempty list of exact `{session, event_id, at}` objects
- every member field is a nonempty string; `at` is an ISO 8601 timestamp with timezone and is preserved verbatim for later exact Chatlas resolution
- duplicate `{session, event_id}` members are rejected
- `session.id` is the neutral Chatlas identity hash used by support members, and at least one member must name that associated session
- structural validation occurs on record input and record reading

### Boundary.Split

- this slice establishes data consumers can store and inspect without depending on discovery mechanics
- `agentos-py` does not import Chatlas and therefore does not prove that a session/event currently exists
- live support resolution belongs to a later injected or composition-root boundary
- semantic judgment that a fragment proves editing remains in the maintainer workflow

### Public.Surface

- `EditionSession.support` replaces `EditionSession.evidence`
- `EditionHistoryService.record(..., support=<object>)` requires support
- `agentos skw edition-history record` requires exactly one of `--support-json` or `--support-file`
- list output returns the normalized embedded support record
- malformed or missing support makes a persisted association invalid and therefore visible through list/check behavior

### Maintainer.Surface

- update the Skillware source module rather than its compiled target
- candidate discovery uses a battery of heuristics, including broad tool/transcript matching; no discovery signals are persisted
- the maintainer inspects transcript fragments, builds the embedded support set from exact Chatlas session/event/timestamp data, then records the association
- build the Skillware package to refresh generated files and lock state

### Scope.Boundary

- no Chatlas dependency in `agentos-py`
- no live event resolution or semantic proof audit in this slice
- no historical depot migration or amendment command
- no change to Bloberia persistence semantics
- no compatibility support for `evidence`

## Execution.Plan

### Slice 1 - Required support schema

- add RED boundary tests for omitted support, malformed outer and member shapes, empty members, duplicate members, mismatched associated session, and valid projection
- replace the evidence field and argument with required support
- validate and normalize the embedded record without changing exact event timestamps
- update the public value object and service record reader
- observable: only structurally valid support-bearing associations can be recorded or projected
- check: `uv run pytest tests/test_edition_history.py`
- status: completed

### Slice 2 - CLI and maintainer workflow

- make `--support-json` or `--support-file` required and remove evidence flags
- update command tests and umbrella CLI coverage with a valid support record
- update `AGENTS.md` and the Skillware source maintainer module for the new contract and heuristic discovery workflow
- build and check the Skillware package
- observable: the CLI refuses support-less records and the developer module produces the supported command shape
- checks: `uv run pytest tests/test_edition_history.py tests/test_skillware.py`; `cd ../agentos-cli && uv run pytest tests/test_e2e_edition_history.py`; `agentos skw build --skill ../agentos-md/skills/agentos-skillware`; `agentos skw check --skill ../agentos-md/skills/agentos-skillware`
- status: completed

### Slice 3 - Full regression

- run full tests and Ruff in `agentos-py` and `agentos-cli`
- refresh the editable umbrella executable because CLI behavior changed
- smoke the required-support record/list/check flow through installed `agentos`
- run the Agentos index linter and Skillware checks for touched managed code
- observable: all owning packages agree on the required support contract with no legacy evidence surface
- status: completed

## Risks And Deviation Triggers

- stop rather than import Chatlas into the foundation package
- preserve exact support-member timestamps because Chatlas resolution compares them with source events
- preserve unrelated work present in `agentos-md` when creating the mandatory execution checkpoint
- if the actual Chatlas support-set shape differs from the accepted ontology, use the implemented `chatlas.support-set.v1` shape and record the deviation

## Acceptance Signals

- `rg evidence` finds no edition-history evidence API, CLI flag, persisted field, or maintainer instruction
- support is mandatory at both library and CLI boundaries
- invalid support-bearing records produce deterministic service errors/findings
- valid list output preserves the complete embedded support set
- focused and full tests, Ruff, Skillware checks, installed CLI smoke, and index lint pass

## Impl.Log

- 2026-07-25: autonomous design selected the exact existing Chatlas support-set record shape: `app`, `schema`, `hint`, and nonempty `members`
- 2026-07-25: `session.id` now denotes the neutral Chatlas identity hash so associated-session membership is mechanically checkable
- 2026-07-25: live support resolution remains deferred at the foundation dependency boundary; this slice implements intrinsic structural validity only
- 2026-07-25: execution gate anchored at `^c20260725-14u`
- 2026-07-25: mandatory checkpoints created in `agentos-py` (`3654cc2`), `agentos-cli` (`2eaa256`), and `agentos-md` (`51c530c`); the markdown checkpoint preserved unrelated `POI.Catalog` work
- 2026-07-25: required support replaced evidence directly in the library and CLI, including exact support-set/member validation, duplicate rejection, associated-session membership, and timestamp preservation
- 2026-07-25: the maintainer module now uses a battery of candidate heuristics, requires transcript-fragment inspection, and persists exact support without discovery signals
- 2026-07-25: verification passed 528 `agentos-py` tests, 62 `agentos-cli` tests, maintained `src`/`tests` Ruff checks, 8 Skillware surfaces with zero POIs, and 23 index checks
- 2026-07-25: repository-root `agentos-py` Ruff remains blocked by 584 pre-existing findings under `_DEPRECATED/` and `dev/`; no touched-file or maintained-scope finding remains
- 2026-07-25: installed CLI smoke passed create-versus-existing idempotency, exact support projection, and a clean explicit-target check
