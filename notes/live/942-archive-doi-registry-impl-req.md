# Archive DOI registry

<!-- tarav.sessions
0f5bad01 = codex:01a15483-94e8-7fe0-86ad-ddd83e2bae52 @0f5bad0131260477b4cf3d712a95871496c3db92d67eaa7910243e312f7b552a
-->

## Impl.Abstract

Status: ready for implementation; design only, no product changes made.
Knowledge.Surface: wiki.

Replace the old Artifact registration/retrieval implementation with a small
Archive-owned registry of typed DOI objects. A DOI identifies a resource under
its Type's declared maintenance contract. Reading a DOI returns its maintained
typed information, including locators and compact recognition hints. Consumers
own access, retrieval, interpretation and their response to changes.
<!-- tarav.breadcrumb b2c05ed2e118 -->

## Design

User decisions from the current conversation:

- DOI Types declare identity continuity and maintenance intention. A repository
  DOI can track the continuing repository across checkouts and locations;
  exact-state contracts are separate specializations.
- Locators state where maintainers believe the resource can be reached. Several
  locations may coexist. Updating a location is an explicit maintenance act.
- Hints help assess whether a candidate is the intended resource. Repository
  hints can include a bounded sample of commit hashes and remote information.
  Shared commits do not uniquely distinguish forks; maintainers own that judgment.
- Registry lookup returns information even when an external location is absent.
  It must not fetch, clone, select a replacement, or silently update locations.
- Types can later provide contract-specific change observation. General recovery,
  automatic identity decisions and artifact hosting are outside this pass.
- Archive owns mutable DOI records, not the shape or mutation of external
  artifacts. Clarify the Constitution's immutability wording accordingly, using
  its authoritative SKW source and rebuilding its product.
- Prefer replacement over compatibility layers. Preserve displaced data in the
  Attic with its provenance; remove retired code rather than keeping a parallel API.
<!-- tarav.breadcrumb 646fc272288c -->
<!-- tarav.breadcrumb f2a906cb5979 -->
<!-- tarav.breadcrumb 16f0a51d70ff -->

Proposed implementation shape: a minimal identified DOI base object; a repository
DOI specialization; typed local/remote locator values; bounded repository hints;
and explicit registry register/read/update/list operations. Registry reads never
provision storage or require the resource itself to be accessible. Integrate with
the existing Record registry rather than introducing another serialization system.
Keep direct references distinct from DOI references: the latter return the DOI
object, without locating or opening its external artifact. Existing evidence may
continue to use direct exact-commit references until explicitly migrated.

### Minimal implementation contract

These are engineering choices for the first implementation, not additional
claims about what the User approved verbatim:

- `DOI` is a registered `TaravObject` with `id` (random 64-character lowercase
  hexadecimal identity, retaining the existing DOI space), optional human label,
  and a list of typed locator Records. `RepositoryDOI` specializes its contract
  and adds bounded typed recognition hints. The Type is the contract: do not
  add a second free-form contract language or require a universal fingerprint.
- Local locators carry a path and host; remote locators carry a URI. Neither
  locator checks availability when read. Recognition hints retain Git object
  format and at most ten sampled commit hashes; no raw commit bodies, messages
  or whole-repository snapshots. Registration may read Git to collect these
  facts explicitly; manually supplied locators do not trigger network access.
- `Archive` explicitly creates or opens a standard `RecordMap` partition keyed
  by DOI id, under the existing Archive Workflow Ship. Preserve that Workflow's
  identity. Default to its standard `~/Documents/tarav/records/<workflow-ship>/`
  partition; custom roots and custom Type registries remain supported.
- Registry operations register, read by exact id, replace maintained information
  under that same id, and enumerate entries. Registration never deduplicates by
  sampled commits or silently merges identity. Read/list never create storage.
  Do not provide destructive deletion in this first pass.
- A new `DOIReference` in `archive/references.py` identifies the registry root
  and exact DOI id. Its target is the loaded DOI object. Reuse the generic
  Reference result/error convention; a missing DOI is unresolvable, whereas an
  unreachable resource does not prevent reading its DOI. Never open an external
  resource in this reference's lookup path.
- Consumers can retain a normal Git reference to the DOI Record edition they
  observed, then compare it with the current Record using existing Git tools.
  No required embedded snapshot, automatic drift response, universal comparison
  engine or recovery service is introduced. The reference contract distinguishes
  the amendable registry entry from an exact retained Record edition.
- Keep the CLI thin: explicit registry initialization, DOI register/show/list/
  update and repository registration with optional local Git hint collection.
  Validate serialized objects through the trusted Record registry. Remove old
  materialize, descriptor and exact-file convenience routes from the active CLI;
  exact file access remains available through direct References elsewhere.
- Register new Types and contribute the registry provider to the existing
  runtime. Contextualization can inspect the returned typed object's information;
  do not add a Notebook-specific resolver or require Notebook evidence migration.

Use fresh TypeShips for genuinely new contracts. Do not reuse old
`Tarav.Archive.Reference` or registration TypeShips for records with changed
meaning. Retain ArchiveWorkflow and RecordArchiveWorkflow identities and the
existing `archive.records` public contracts.

## Current implementation observations

- `src/tarav/l1/archive/__init__.py` combines registration, locators, repository
  hints, exact Git coordinates, file hashing, descriptor registration and Git
  commits. `Archive.open` currently requires a hosted-repositories directory.
- `src/tarav/l1/archive/references.py:122` resolves DOI records into actual
  paths or Git bytes, checks availability and sometimes file hashes. This is
  broader than the requested registry lookup contract.
- `artifact_records.py` defines registration and supporting Record Types;
  `workflow.py` exposes their navigation provider. Runtime and CLI compose them.
- `archive/records/` is the general Record Archive used throughout Tarav.
  It must remain functional; replacing artifact registration does not authorize
  deleting this shared persistence foundation. Attic also remains an Archive child.
- Consumer search across maintained Python source/tests/tooling and extension
  scripts/source found artifact-registration API callers in Archive CLI,
  `l3/runtime.py`, `tests/kernel/test_library_runtime.py`,
  `tests/kernel/test_references.py` and `tests/test_architecture.py`.
  `tooling/migrate_793_archive_records.py` imports the old registration registry;
  retire it with that registry. No extension caller was found. Historical skill
  and Wiki references are design evidence, not executable callers.
- The current architecture test explicitly forbids Archive's parent modules
  importing Record Archive. The new DOI store uses `l1.records.registry`, which
  is a different subsystem; maintain directional imports and update the test
  only for the deliberately replaced registration Types.
- The worktree contains unrelated Chatlas and Breadcrumb changes. Preserve them.

### Retained-data inventory (2026-10-22)

Inspected 6,988 JSON files in the current `~/Documents/tarav/archive/` and
`~/Documents/tarav/records/` trees. No `Tarav.Archive.Artifact.Registration.Record`
or nested Archive Reference record was found. The old expected
`archive/records/.git` plus `archive/records/artifacts/` store is absent.
This statement is bounded to those active default roots, not every external
custom root or historical Attic deposit.

Existing Archive partitions contain:

| Workflow partition | Files excluding Git | Bytes | Contents/disposition |
|---|---:|---:|---|
| `84b6d49c-8bba-4af4-a880-c5fa453f80e5` | 162 | 35,796 | Record Archive test objects/entries; leave in place |
| `ae6fb02b-b82f-4f64-82e8-67f28a76d179` | 22 | 2,805 | Context SubjectRoot/Entry and Archive placement records; leave in place |
| `f1589494-1e42-4d12-969a-f167d08b56e4` | 16 | 5,865,342 | Record Archive containers and other retained artifacts; leave in place |

There is no identified live legacy registration store to displace. Do not create
an empty Attic deposit or relocate these partitions merely because they contain
directories called `artifacts`. If execution discovers an actual old custom
store, first checkpoint and deposit its bytes/Git history with original paths,
then explicitly migrate registrations whose contract can be preserved. Never
reclassify an exact-state identity as a continuing-repository DOI silently.

## Impl.Req.Wiki

Product: `tarav-py`. Design ownership: `tarav-md` for constitutional and broad
Archive design changes; Python implementation notes remain with the product.
Read the relevant Archive Wiki/design and SKW guidance before editing those
surfaces. The companion [Markdown request](../../../tarav-md/notes/live/870-archive-doi-contracts-impl-req.md)
owns those changes. Execute that clarification before the Python replacement.

Wiki owner/root: `tarav-md/notes/wiki/`; topical destination
`archive-doi-registry.md`, daily destination `daily/2026-10-22.md`.
The existing topical note already records prior discussion about DOI identity
commitments. Append the new registry-only boundary without erasing its history.
Current evidence comes from exact session `0f5bad01`, declared above. Source
Turns were resolved from its refreshed Normal Model before adding markers.

## Execution.Plan

- [x] Design/inventory: inspect remaining Archive code, tests, configuration,
  external consumers and retained storage; identify exactly which data belongs
  to the retired registration implementation. Check: bounded inventory with
  paths, identities, references and migration disposition.
- [x] Design alignment: finalize the minimal typed records and lookup contract,
  resolve existing Type/Ship continuity, and create the cross-linked Markdown
  request for constitutional clarification. Check: no hidden user decisions.
- [ ] Replacement feature: retire the old retrieval-oriented registration paths
  and migrate their callers to the small registry in one coherent change.
  Check: public registration, maintenance and lookup tests; lookup of an absent
  resource still returns maintained information; reads create nothing.
- [ ] Data migration: preserve old registration data losslessly in an Attic
  deposit and explicitly convert useful registrations, preserving supported
  identities. Leave no legacy reader or dormant legacy store on the active
  path. Check: retained-byte/provenance inventory and reopened new records.
- [ ] Integration feature: compose new Types with runtime, CLI and Context.
  Check: DOI lookup exposes typed information without resource access, and
  existing general Records, Attic and direct-reference consumers still work.
- [ ] Verification/capture: focused tests, architecture checks, Project status
  including required suites; complete Breadcrumb/Wiki capture and record actual
  results. Execute-phase Git checkpoints follow the skill's commit contract.

Frequent Notebook commits, repository witness identity and tarav-change hook
installation remain separate follow-up work; this request supplies the DOI
registry they may use, without inventing those integrations here.

## Impl.Log

- Initial read-only inspection completed; no product implementation or live-data
  migration performed. Draft created from the current conversation.
- Inventory completed over maintained callers and active default data roots;
  no live old registration store was found. No data was moved.
- The old hint sampler's bounded-hash approach is reusable; discard its raw
  commit-body storage. Reuse standard RecordMap and Reference infrastructure.
- Start checkpoints: Python `be2819101d77c4ab719a5bd517222307f77b56ed`;
  Markdown `f1b094513253de84ec23b12d400db1d27b582193`. Existing Python work
  was snapshotted as found under the skill's checkpoint rule, without edits.
- Design evidence captured: four Breadcrumbs on this request, four on the
  companion, five appended to the topical Wiki and three to the daily Wiki.
  All four surface audits passed with no POIs (38 labels including existing
  Wiki labels). Exact current session was refreshed once and reused.
- Relative links in all four changed Markdown files resolve; both repository
  diff whitespace checks passed. Source searches also covered old JSON/JSONL
  registration/reference type names in active roots, with no matches.
- This completes implementation preparation. Product code, live data and the
  Constitution remain unchanged. No implementation tests were run for this
  documentation-only preparation; execution has its own verification plan.
