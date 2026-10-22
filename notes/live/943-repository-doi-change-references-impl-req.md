# Repository DOI references and Change-ID

<!-- tarav.sessions
0f5bad01 = codex:01a15483-94e8-7fe0-86ad-ddd83e2bae52 @0f5bad0131260477b4cf3d712a95871496c3db92d67eaa7910243e312f7b552a
-->

## Impl.Abstract

Status: complete. Knowledge.Surface: wiki.

Integrate Archive repository-specialized references with tarav-change before
Notebook adopts them. Archive returns maintained repository declarations and
Git coordinates; an explicit Git consumer performs local candidate lookup and
exact-state verification. Rekey witnesses by repository DOI and branch, retaining
responsible Project metadata independently. Preserve existing witness data through
an explicit migration without legacy runtime readers.

## Design

The User requested Archive repository references already integrated with
tarav-change. Prior discussion established that Archive lookup returns typed
information, consumers perform access, and history recovery must not silently
change captured evidence. The Develop invocation authorizes this bounded pass.
<!-- tarav.breadcrumb 8eee1c8a8a39 -->

Core shape and access paths:

- `RepositoryReference` specializes DOIReference. Its locator embeds the registry
  and repository DOI plus an exact commit, optional Change-ID and relative path,
  and required Git tree OID. Lookup returns a repository declaration with those
  coordinates; it neither opens Git nor downloads the external resource.
- `l2.git.archive` composes Archive declarations with existing Git mechanics.
  Capture reads an explicitly supplied local repository and pins its commit/tree
  and any Change-ID actually carried by that commit; it never invents a marker
  for an older commit. Resolution tries declared local locations on this host,
  preferring the exact commit. If absent, it discovers Change-ID candidates and
  accepts only an unambiguous candidate matching the entire captured tree.
  Tree mismatches and ambiguity are explicit unsuccessful results. Optional file
  selection reads from the verified commit, so later Notebook consumers can also
  reconstruct all context from the same state.
- The tree includes `.tarav/changes`. An amend that adds a marker is therefore a
  different exact tree even if another file is unchanged. A Change-ID is a
  navigation aid, not evidence that changed tree contents are equivalent.
- GitConfig retains repository DOI and optional registry location separately
  from optional owning Project root. A lower-level hook installer remains
  explicit; the CLI composes DOI registration/binding with it when tarav-change
  is selected. Support ordinary Git repositories through `--repo`, without
  making them Projects. Project ownership defaults to the repository's Project
  marker, else an explicitly supplied owner or existing System Project.
- The witness and overrule schemas require repository DOI; Project id is
  optional metadata. Storage is `git-changes/repositories/<doi>/...`. Missing
  binding is reported by a check and never silently uses Project identity.
  Hook refusals/overrules retain their existing behavior and route actions to
  the separately declared owner. Detached HEAD remains unwitnessed.

Keep Archive registry access and direct exact Git references unchanged. Do not
migrate Notebook support/review, create a lineage workflow, fetch remotes,
automatically equate forks, or infer semantic equivalence of changed states.

## Current implementation evidence

- `l1.archive.references.DOIReference` reads a typed declaration; `l1.archive`
  uses a standard RecordMap partition. RepositoryDOI locators/hints are already
  available from request 942.
- `l1.git.change.find` finds all commits carrying a marker via trailer or tracked
  `.tarav/changes` additions. Hook installation and config live in `l1.git.hooks`;
  `l3.git.commands` currently requires a Project for its install command.
- `l1.git.witness` currently keys schemas and paths by Project and branch.
  `change._witnessed` reads the Project marker and action routing assumes that
  the repository root is the owning Project. Those are the paths to replace.
- Inventory found one live witness directory, for tarav-py Project
  `e308d11f-d709-4f23-b8c7-f214e28b3f11`, with one branch and no overrules.
  tarav-py already uses tarav-change; tarav-md does not. Preserve that baseline
  when binding tarav-py's repository DOI and move its original bytes to an Attic
  deposit after migration verification. Do not rewrite commit history.

## Impl.Req.Wiki

Wiki owner: `tarav-md`; root `notes/wiki/`. Read `archive-doi-registry.md`,
`tarav-change.md` and the current daily Note. Append implementation design and
outcome with exact supporting Chatlas User Turns. The request itself also gets
Breadcrumbs. No compiled skill contract needs changing for this Python-first API.

## Execution.Plan

- [x] Feature: add the typed declarative RepositoryReference and explicit Git
  capture/resolution integration. Tests: repository relocation, exact commits,
  absent originals with equivalent trees, mismatched trees, ambiguous candidates,
  optional file content and custom Type registries; lookup does no Git work.
- [x] Feature/refactor: introduce DOI binding and rekey witness/overrule records,
  update hooks/CLI and callers. Tests: two repositories sharing a Project remain
  independent, ordinary non-Project repositories work, missing bindings surface,
  branch/amend/rebase/refusal/overrule and action ownership remain correct.
- [x] Explicit migration: register/bind tarav-py's repository, preserve its live
  witness baseline under the new key, conserve original records in Attic, verify
  the next real commit updates the new witness. No fallback schema reader.
- [x] Capture/verification: source Breadcrumbs, focused tests, installed CLI smoke,
  required full Project checks, Wiki capture and evidence commits. Keep unrelated
  work intact and record every material gap.

## Impl.Log

- Current code, tests, Wiki and live witness metadata inspected. Design separates
  declaration lookup, candidate discovery and exact-state acceptance deliberately.
- Todo order is the Execution.Plan above. No Notebook adoption in this pass.
- Start checkpoints: Python `b89da4c99196f97f6bccd1375ccdb32e59c2b914`;
  Markdown `e1200cef964d36e95b61fe860c814ab97ab26e34`.
- Implemented the declarative reference, explicit Git capture/resolution, DOI
  hook binding, repository-keyed witnesses and owner routing. Added
  `OwnedRepositorySuite` so normal owner status can revisit ordinary repositories
  and close recovered findings. Discovery conservatively remains incomplete if
  any declared local repository cannot be inspected.
- Architecture verification caught a subsystem cycle from the proposed
  `l2.archive_git` placement; the integration lives in `l2.git.archive` instead.
  This preserves the existing layering and public behavior.
- Focused integration: 47 tests passed (references, hooks, change, Archive,
  Project). Architecture and reference recheck: 62 passed. Ruff passed.
- Migrated the one live tarav-py witness, preserving its branch and changes under
  repository DOI `03618818cfd4c94c87ddca4bfbb26f4bd1f31c86069b0865b1d3bfb0f074848b`.
  Original bytes are hash-verified in Attic deposit
  `20261022T172653Z-project-keyed-git-witness`; the migrated check has no findings.
  A real commit must still verify the new witness update.
- Installed editable CLI refreshed and authoritative AGENTS source rebuilt.
  Product and Wiki capture submitted successfully; the request already carried
  its registered Breadcrumb. JSON config and SKW source use external placement.
- ARCHITECTURE.md also contains concurrent external Breadcrumb work; that shared
  file will be committed as found. Other session changes remain outside scope.
- Verified slice committed as `5932b1aa8d51942e23d972944129cc6b5c9fdc59`.
  The next real commit updated the repository-keyed witness: all 159 marker
  lines matched the tracked file and TaravChangeCheck reported no findings.
- Full `tarav status --project . --all --json`: 82 completed checks, none
  incomplete; all 64 pytest suites passed. Five unrelated findings remain:
  the existing Gitleaks flag, two synthetic test markers and two missing summary
  renderers on concurrent external-Breadcrumb POI Types. No failing tests.
- All 15 audited source/request/Wiki surfaces passed evidence audit after
  position refresh. Both JSON external attachments submitted successfully.
  Shared Wiki files contain concurrent work and are retained as found.
