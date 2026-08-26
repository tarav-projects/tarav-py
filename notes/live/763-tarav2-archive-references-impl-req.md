# 763 — Tarav2 Archive references

## Impl.Abstract

- **Goal:** implement portable, flat JSON `Archive.Reference`s for registered Git
  repositories, exact Git-contained file versions, and exact repoless file versions.
- **Status:** completed and verified.
- **Scope:** the candidate Archive design, `tarav.tarav2` Archive API and option-only CLI,
  focused Tarav2 tests, and this implementation record.
- **Out of scope:** reference consumption or schema policing, automatic recovery, semantic
  Artifact relationships, folders, non-file URLs, eager materialization, and registering
  the real Chatlas repository.
- **Authority:** `tarav-pkg/CONSTITUTION.md`, `tarav-pkg/tarav-archive.md`, and the current
  reference-design discussion in Chatlas session
  `01e7143eecc1b00b10b564d8bf26918cdaa0ebec4522d25448140e05abf5cd35`.

## Impl.Index

### Accepted constraints

- [CT] An `Archive.Reference` is portable JSON containing the Archive identity, a locator,
  validation evidence, and very cheap recovery hints. Consumers may extend or modify their
  copies, so supplied reference fields remain claims rather than authoritative Archive
  Records. Supported by user `Chat.Message`
  `bd23907ec164913f49c7e5720effc254bed117b29846e803d0b48e2b1bda088f`.
- [CT] References are flat. Their Artifact `kind` selects the documentation and semantics
  of the remaining fields instead of nested validator and hints objects. Supported by user
  `Chat.Message` `9f1913807a7ba84794c1830716e82b1811574276386ab6e2cace963c0682c664`.
- [CT] A Git Repository reference uses only its first commit hash as deliberately cheap,
  weak validation evidence. Supported by user `Chat.Message`
  `166616d5acbe50ee098440490f85d51d4c62f9567ad87a2ea954b75ced451032`.
- [CT] A file reference identifies one exact file version. For a Git-contained file its
  locator is the path relative to the registered repository. Supported by user
  `Chat.Message` `3ad4583ea760ef77ee99fe33ad444e6c08af628c80aad3e102f7b8ef87247791`.
- [CT] A repoless file-version reference includes the Artifact registration time as a
  recovery hint. Supported by user `Chat.Message`
  `414bcbeb555aeff0c852e71e3b878329ed18fef30d743a3de014730f527054c7`.
- [CT] Implementation is explicitly authorized by user `Chat.Message`
  `02414803a4b3797df926dade6fb48e28f32614717e73f639ef642428c9f1c580`.

### Implementation decisions

- Core reference kinds are `git-repository`, `git-file-version`, and `file-version`.
  Core Artifact registrations use the same kind values so `kind` genuinely describes the
  referenced Artifact and serves as the reference-schema discriminator.
- Repository references contain `kind`, `archive_id`, the caller-supplied `locator`, public
  `name`, and `first_commit` from the retained Git Hint.
- Git file-version references contain `kind`, deterministic `archive_id`, `repository_id`,
  repository-relative `locator`, exact `commit`, `git_oid`, and `size`.
- Repoless file-version references contain `kind`, random `archive_id`, caller-supplied
  `locator`, registration `recorded_at`, `sha256`, `size`, and `name`. Their Archive Record
  retains the hash and size beside the registration and canonical local locator.
- Reference production may materialize the exact Artifact Records it needs. Repeating a
  repoless file request with the same canonical locator and bytes reuses that Artifact;
  changed bytes at the same locator produce a new file-version Artifact.
- Reference generation is exposed through kind-specific `archive reference` commands.
  Their output is the bare reference JSON, suitable for direct consumer storage.

## Execution.Plan

### Vertical.Slice 1 — Reference model and repository reference

**Status:** completed.

- Amend the candidate Archive design with the flat reference contract and the three core
  kinds.
- Add a repository-reference producer using the registered locator and first Git Hint
  commit.
- **Check:** focused API and CLI tests assert exact flat JSON and no Archive mutation.

### Vertical.Slice 2 — Git-contained file-version reference

**Status:** completed.

- Produce a reference from a repository selector, exact commit, and repository-relative
  locator while reusing lazy Git Artifact materialization.
- **Check:** the reference contains the deterministic Artifact ID and Git blob evidence;
  another commit produces another reference.

### Vertical.Slice 3 — Repoless file-version reference

**Status:** completed.

- Hash and register one exact local file version with its timestamped File Version Record.
- Reuse an unchanged version and issue a new Artifact ID after content changes.
- **Check:** focused API and CLI tests cover reference shape, idempotency, version changes,
  and exact Record contents.

### Vertical.Slice 4 — Final integration audit

**Status:** completed.

- Run focused Tarav2 tests and Ruff, maintained architecture/CLI checks, the full suite,
  editable CLI reinstall, installed help smokes, diff checks, and Product.Surface audit.

## Impl.Log

- [CT] The user authorized execution with `IMPLEMENT references`; evidence is
  `Chat.Message` `02414803a4b3797df926dade6fb48e28f32614717e73f639ef642428c9f1c580`.
- [IP] Reference validation and resolution are deliberately deferred. This slice produces
  references and the Archive Records necessary to support them without inventing consumer
  policy.
- [IP] The required pre-execution checkpoints are `3033b9c` in `tarav-py` and `d200975`
  in `tarav-md`; no final implementation commit was created.
- [IP] The final Product.Surface audit found no additional maintenance-relevant annotation
  beyond the candidate Archive design, these focused boundary tests, and this native
  implementation record. Capture.Manifest placement remains unavailable because its
  recording-kernel landing pipeline has not yet been implemented.

## Outcome

- Added flat JSON Reference production for the `git-repository`, `git-file-version`, and
  `file-version` Artifact kinds.
- Repository References echo the requested locator and retain only the public name and
  first commit as cheap hints. Exact local and already-recorded Git remote locators resolve
  without mutating Archive Records.
- Git file References reuse lazy materialization and contain the Repository ID, exact
  commit, repository-relative locator, Git blob object ID, and size.
- Repoless file References register a random-ID exact file version with one timestamped
  `file-version.json` Record containing SHA-256 and size. Unchanged bytes at the same
  canonical locator reuse the Artifact; changed bytes create another Artifact version.
- Added option-only `tarav tarav2 archive reference repository|git-file|file` commands.
  Each prints the bare Reference JSON for direct consumer storage.
- Verification passed: 24 focused Tarav2 tests; 111 Tarav2, architecture, and maintained
  CLI tests; all 1,999 project tests; full `src`/`tests` Ruff; diff checks; editable CLI
  reinstall; and installed Reference help smokes.
