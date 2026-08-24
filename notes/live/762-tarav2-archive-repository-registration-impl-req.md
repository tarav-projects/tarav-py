# 762 — Tarav2 Archive repository registration

## Impl.Abstract

- **Goal:** implement the first `Tarav.Archive` slice as an isolated Python API under
  `tarav.tarav2`: initialize an Archive root, register an external Git repository, persist
  its primary and secondary Manifests, and resolve the resulting Repository by its human
  name, UUID or UUID prefix, and registered location.
- **Status:** ready for execution.
- **Scope:** a new `src/tarav/tarav2/` namespace and focused tests under `tests/tarav2/`.
- **Out of scope:** CLI/runtime integration, imports from existing Tarav domains into
  `tarav.tarav2`, File.Version enumeration, Diagram integration, managed artifact
  repositories, importing free files, automatic repository recognition, and non-Git data.
- **Source context:** current Codex session
  `01e7143eecc1b00b10b564d8bf26918cdaa0ebec4522d25448140e05abf5cd35`;
  constraining user `Chat.Message` addresses:
  `533a4f7a0e382ac5f82b965c7833b92810c8f7ba30fc9da85048d506330701ef`,
  `ec940cc59c88a95dcc75774e973e76a50f5433ddad5e6255677ddf0e0bf55c2f`,
  `b1b14ab13e0b648dcae4c163e5f76eeb394f40131a5b4fd25ea4c9770cf9a589`,
  `79f789a42965247c3514add9417ad6824bb9cadb8c03bd62e0c2d9c421f5ef6c`, and
  `d7163b2a224d0b44327eeb681a868c934304beba245e5f0663f45dbdae0267eb`.

## Impl.Index

### Accepted constraints

- [CT] `~/Documents/tarav-archive/manifests/` is its own Git repository and contains
  Archive records; `repositories/` contains only repositories physically hosted by the
  Archive.
- [CT] Registering an external repository does not copy or modify it.
- [CT] A Repository has one plain UUID identity plus a unique, human-facing name such as
  `tarav.chatlas`; prefixes are convenience selectors only when unambiguous.
- [CT] Each Archive object folder is flat: `registration.json` is the primary Manifest and
  secondary Manifests such as `locations.json` and `git.json` sit beside it.
- [CT] `locations.json` connects a Repository UUID to observed host/path locations; a path
  is lookup evidence and cannot redefine the Repository identity.
- [CT] Archive code records cheap mechanical Git facts and does not interpret repository
  contents.
- [CT] The implementation remains internal to `tarav.tarav2`: no existing Tarav module,
  runtime, or CLI imports or exposes it.

### Implementation decisions

- Use a small standard-library domain module plus the existing dependency-free atomic JSON
  writer. No new dependency or cross-domain policy is introduced.
- `Archive.create(path)` owns initialization of the `manifests` Git repository and the empty
  `repositories` container. `Archive.open(path)` fails closed when that shape is absent.
- Repository registration resolves and validates the caller's Git top-level, returns an
  existing registration for the same host/path, rejects name collisions, assigns a UUID,
  writes the three approved Manifest files, and commits them together.
- The first `git.json` records only cheap observations required by this slice: object format,
  current HEAD when present, and root commits. Richer Git Manifest producers remain future
  independent files or qualified producer variants.
- Resolution accepts an explicit `Path` for a location and a string for exact name, full
  UUID, or unique UUID prefix. It never guesses that an unknown location is an existing
  Repository.
- The Manifest repository uses a fixed mechanical Git author for automatic Archive commits;
  it does not mutate global or repository-local user configuration.

## Execution.Plan

### Vertical.Slice 1 — Archive bootstrap and repository registration

- **RED:** add a focused test that creates a source Git repository, creates an Archive,
  registers the source as `tarav.chatlas`, and asserts the exact root split, flat Manifest
  files, plain UUID identity, external location, Git facts, untouched source repository,
  clean Manifest worktree, and committed Manifest history.
- **GREEN:** add `tarav.tarav2.archive` with the minimum API and persistence needed for that
  path.
- **Check:** `uv run pytest tests/tarav2/test_archive.py -q`.
- **Acceptance:** one call produces a committed Repository registration without copying the
  source into the Archive's `repositories/` directory.

### Vertical.Slice 2 — Idempotency and convenience resolution

- **RED:** add tests for repeat registration at the same location, name lookup, full UUID
  lookup, unique-prefix lookup, location lookup, duplicate-name rejection, unknown selector,
  and ambiguous prefix rejection.
- **GREEN:** add only the lookup/catalog behavior required by those tests.
- **Check:** `uv run pytest tests/tarav2/test_archive.py -q`.
- **Acceptance:** physical location and convenient selectors consistently resolve to the
  same immutable UUID without creating duplicate records.

### Vertical.Slice 3 — Namespace isolation and final audit

- Add a boundary test proving no maintained module outside `tarav.tarav2` imports the new
  namespace and that no CLI/runtime surface was changed.
- Run `uv run pytest tests/tarav2/test_archive.py tests/test_architecture.py -q`.
- Run `uv run ruff check src/tarav/tarav2 tests/tarav2`.
- Review the diff and Manifest schemas against the accepted flat-folder design.

## Impl.Log

- [IP] File.Version objects are deliberately deferred. Repository registration is the first
  complete boundary and gives later file-version producers a stable Repository UUID to
  target.
- Product-surface capture is expected to be empty: the new code and tests directly express
  the accepted boundary, and the removed capture landing pipeline cannot place a separate
  Capture.Manifest.
