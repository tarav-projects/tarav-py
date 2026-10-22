# Archive DOI registry

## Impl.Abstract

Status: design draft; consumer and retained-data inventory still required before execution.
Knowledge.Surface: wiki.

Replace the old Artifact registration/retrieval implementation with a small
Archive-owned registry of typed DOI objects. A DOI identifies a resource under
its Type's declared maintenance contract. Reading a DOI returns its maintained
typed information, including locators and compact recognition hints. Consumers
own access, retrieval, interpretation and their response to changes.

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

Proposed implementation shape: a minimal identified DOI base object; a repository
DOI specialization; typed local/remote locator values; bounded repository hints;
and explicit registry register/read/update/list operations. Registry reads never
provision storage or require the resource itself to be accessible. Integrate with
the existing Record registry rather than introducing another serialization system.
Keep direct references distinct from DOI references: the latter return the DOI
object, without locating or opening its external artifact. Existing evidence may
continue to use direct exact-commit references until explicitly migrated.

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
- Initial import search found direct artifact consumers in Archive CLI, runtime,
  reference tests and architecture tests. This is not an exhaustive consumer audit.
- `~/Documents/tarav/archive/` contains existing UUID directories. Their ownership
  and contents have not yet been established. Do not move this whole directory:
  it may contain active general Record storage.
- The worktree contains unrelated Chatlas and Breadcrumb changes. Preserve them.

## Impl.Req.Wiki

Product: `tarav-py`. Design ownership: `tarav-md` for constitutional and broad
Archive design changes; Python implementation notes remain with the product.
Read the relevant Archive Wiki/design and SKW guidance before editing those
surfaces. A separate cross-linked Markdown request is required for changes
owned by `tarav-md`.

Evidence status: current user instructions are available in this conversation;
exact Chatlas turn resolution, Breadcrumb submission and Wiki capture are pending.
No approval or supporting turn hashes are manufactured in this draft.

## Execution.Plan

- [ ] Design/inventory: inspect remaining Archive code, tests, configuration,
  external consumers and retained storage; identify exactly which data belongs
  to the retired registration implementation. Check: bounded inventory with
  paths, identities, references and migration disposition.
- [ ] Design alignment: finalize the minimal typed records and lookup contract,
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
- Readiness gaps: full consumer/data inventory, final concrete Type contracts,
  supporting turn capture, Wiki capture and Markdown-owned request.
