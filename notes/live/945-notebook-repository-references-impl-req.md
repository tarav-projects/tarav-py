# Notebook adoption of repository DOI references

<!-- tarav.sessions
0f5bad01 = codex:01a15483-94e8-7fe0-86ad-ddd83e2bae52 @0f5bad0131260477b4cf3d712a95871496c3db92d67eaa7910243e312f7b552a
-->

## Impl.Abstract

Status: implemented; full verification running. Knowledge.Surface: wiki.

Adopt the repository DOI/Change-ID infrastructure from request 943 for Notebook
subject/context recording. Preserve exact wording, context, support sets and
review evidence while replacing local-path locators. Configure the Notebook,
Grounding and Review repositories for frequent tarav-change commits, owned by
the System Project by default. No general lineage, new approval, scoring or
external fetching is introduced.

## Design

The User requested Notebook adoption immediately after repository references
were integrated with tarav-change. Previous decisions require Git-backed
context, frequent commits, stable repository identity and distinct Project
ownership. This Develop call authorizes design, implementation and migration.
<!-- tarav.breadcrumb 9aa2bd1d5687 -->

Data shape first: keep the Notebook State Reference's Type/Ship and exact
subject semantics, but its locator becomes the existing RepositoryLocator:
registry, DOI, commit, tree, optional Change-ID and required records/<Ship>.json.
The specialized consumer resolves a RepositoryReference through l2.git.archive,
then reconstructs the Line and all authoring ancestors from the one verified
commit. It lives in l2.notebook_references because it composes workflows; delete
the old l1 module and update all imports. No runtime legacy schema reader.

Capture checkpoints explicitly bind/install tarav-change and commit only the
store's records and owned repository metadata. Shared repositories belong to
the System Project by default, with an explicit owner override for other hosts.
Support/review writes commit their evidence and final Notebook links. Read-only
inspection never binds, installs or commits. Old commits may legitimately have
no Change-ID; pin their exact commit/tree without inventing one.

Inventory: 15 SupportSets and two ReviewFrames contain 30 path-based Notebook
references pointing into the shared Notebook store. Both evidence repositories
are clean. Migration first resolves every old reference with the existing
reader and records its exact SubjectState digest. Register the three repository
identities, translate each reference at its original commit and compare all
resolved digests before replacing records. Conserve original records in an
explicit Attic deposit and commit the migrated records. Preserve evidence IDs,
token/proposal/approval, source references and state fingerprints. Historical
Git snapshots retain older schemas naturally; current readers do not.

Subtract before adding: remove local-path state-reference construction and the
old implementation module. Base Lines, Block structure, evidence policies and
review protocol remain unchanged. Any failed exact-state comparison stops
migration before replacement; report the gap rather than invent evidence.

## Impl.Req.Wiki

Python owns the implementation; tarav-md owns notes/wiki/line-notebook.md,
archive-doi-registry.md and daily/2026-10-22.md. Append a bounded outcome and
supporting User Turn, retaining existing history. Reuse this pass's exact
Chatlas refresh and session identity.

## Execution.Plan

- [x] Feature/refactor: replace the state locator and integrate explicit
  repository setup/checkpoints. Prove exact state reconstruction, relocation,
  matching-tree recovery, changed-tree rejection, custom registry loading,
  support staleness and token review through focused Notebook/reference tests.
- [x] Migration: inventory and snapshot original references/digests; bind the
  three live stores; translate/verify/replace 30 references, conserving originals
  in Attic. Prove unchanged digests and review presentations and new witness
  updates after real commits. No fallback readers.
- [ ] Capture/verification: update architecture/guidance and Wiki, attach/audit
  source evidence, run full Project checks and evidence commits. Preserve
  concurrent work; record all findings outside scope.

## Impl.Log

- Inspected Notebook storage, capture, draft, state References, Grounding,
  Review and repository-reference code and tests. Existing state reader uses
  only one Git commit for its bounded context; retain that invariant.
- Current Chatlas session refreshed once; supporting User Turn is
  `0f5bad01:a443ccd3f09781dd`. No additional refresh during this pass.
- Current external work: request 944 belongs to another session.
- Cold reread completed before product edits. Start checkpoints: Python
  `cdd3fa88ce515f3f84eb284aea99c62a3b1b63e9`, Markdown
  `d936fb599998e4c1409eb76fe7f23b400ceb785b`.
- Baseline: 23 Notebook evidence tests passed. First combined integration run:
  88 passed, one expected old-contract failure. It expected an absent commit
  hash to fail even with a matching Change-ID/tree; updated that test to verify
  recovery and then reject a mismatched tree. Both affected tests passed.
- New behavior checks: relocation/read-only access, same-tree rewrite recovery,
  changed-tree rejection and three independently committed/witnessed stores:
  four tests passed. Bound custom Record registry reconstruction: one passed.
  Ruff passed. Full Project status is running.
- Live migration completed: 17 records, 30 translated references, all SubjectState
  digests and both review presentations unchanged. Original records are conserved
  with byte-hash verification in Attic deposit
  `20261022T175003Z-notebook-path-references`. No current legacy locators remain.
- Repository DOI / committed migration:
  Notebook `dfc5f3557530e6a7de7884dfc07dc341ae5db68afb1a619b27b6e36af803fe3a`
  / `aa6a7187617a4ac35af8538128e7e98fd3ed1a65`;
  Grounding `4b5839aeda95ab74f5310808a642a07fda47ff53b055c26b5b37a42e5490086a`
  / `6e5908ab827d8008d80d046b7be4484c60e5ee4e`;
  Review `d236ecbbec20d935a43b48175a4478146882a5d8094d24f9ed00e19bfceb2227`
  / `d522db347c9b3f232871cc38f428d842b56c372c`.
  All three new witnesses match the tracked markers; their Change checks are clean.
- The shared authoritative AGENTS source, compiled output and lock contain
  concurrent Project Attic changes. They will be retained as found in this
  workflow's commits; separate Attic code is outside this workflow's scope.
