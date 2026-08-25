# 762 — Tarav2 Archive Record and Artifact registry

## Impl.Abstract

- **Goal:** maintain the approved Record-and-Artifact kernel under `tarav.tarav2`, including
  the timestamped Record, append-only Locator, and Repository Git Hint amendment: initialize
  a flat Archive, register root Artifacts and Git repositories without copying them, lazily
  materialize repository-contained Artifacts, retain attributed Records and
  External.Descriptors, and expose the system through option-only
  `tarav tarav2 archive` commands.
- **Status:** completed and verified, including the Record/Locator/Git Hint amendment.
- **Scope:** `src/tarav/tarav2/`, focused tests under `tests/tarav2/`, the existing isolated
  umbrella CLI registration, and this implementation record.
- **Out of scope:** real Chatlas registration, eager repository scanning, semantic parsing,
  Diagram integration, non-file substructure, managed Artifact import, automatic location
  recovery, Record reconciliation, and migration compatibility with the superseded
  Manifest/File.Version experiment.
- **Authority:** `tarav-pkg/CONSTITUTION.md` and `tarav-pkg/tarav-archive.md`; execution is
  authorized by user `Chat.Message`
  `dc08c2a93fa591d0cf417e25e4423981cde6c2072cb554e742ddc2446d544e7f`
  in session `01e7143eecc1b00b10b564d8bf26918cdaa0ebec4522d25448140e05abf5cd35`.

## Impl.Index

### Accepted constraints

- [CT] The Archive stores Artifacts and flat Records about them; consumers construct
  organization and meaning.
- [CT] The Archive root contains `records/`, itself a Git repository, and
  `repositories/`, used only for repositories physically hosted by the Archive.
- [CT] All Record directories live at `records/artifacts/<artifact-id>/`; an Artifact ID is
  also its physical Record-directory key.
- [CT] Every Artifact ID occupies the same 256-bit, 64-character lowercase hexadecimal
  space. Root and repoless Artifacts receive cryptographically random IDs.
- [CT] A repository-contained Artifact receives a deterministic SHA-256 identity from a
  versioned, unambiguous encoding of Repository ID, Git object format, exact commit, and
  subpath.
- [CT] A registered repository is a root Artifact with a public name and one or more
  observed locations. Registering an external repository does not copy or modify it.
- [CT] Git is the current containment gate. A root Repository registration is sufficient to
  address any committed file or folder; contained Artifact Records are materialized only
  when requested. There is no default eager scan.
- [CT] Records describe one Artifact. They may contain Archive bureaucracy, locations,
  observations, fingerprints, descriptions, and hints, and they may disagree without the
  Archive reconciling them.
- [CT] Consumers may register one Artifact as an External.Descriptor of another. The
  Archive preserves that attributed declaration as an ordinary Record and does not endorse
  its correctness or create a general semantic graph.
- [CT] Existing Tarav domains and runtime remain independent from `tarav.tarav2`; only the
  umbrella CLI composition adapter may import it.
- [CT] Tarav2 CLI data inputs use named options only.
- [CT] Every Archive Record carries one `recorded_at` timestamp. The Archive is not an
  activity log, and timestamping does not justify retaining transient current-state copies.
  Supported by user `Chat.Message`s
  `00c6caad56de3e82a1485c08078236d0ca23474da7866ce3da0a55ec19f55f72` and
  `fc528f7c79f06649483dd381fbbc98489d9311868c6389f403c5121418491e58`.
- [CT] `locators.jsonl` is an appendable registry of independently timestamped locator
  hints. It contains local paths and admitted Git remote configuration without claiming an
  authoritative or current location. Supported by user `Chat.Message`
  `99d4d277c27c4d888d2191ebd0100af9447e81354e31abbdfa70cc39e960aaff`.
- [CT] The Archive does not sanitize suspicious locator values. An unsupported or
  suspicious Git remote is skipped and warned about without echoing the possibly sensitive
  value. Supported by user `Chat.Message`
  `d4122fc84a3229b56abdb5bf55a77a90fa2f80f738b35204feb5da2fe119e6d7`.
- [CT] Repository registration produces `git-hint.json`, not a stored `HEAD`. It samples
  between one and ten commits across the selected branch beginning with the first commit,
  and retains their Git metadata and messages as repository-recognition hints. Supported
  by user `Chat.Message`s
  `f7a78c12f8e60c129ea06fbe5b5b50ca17193367d049f8472bd228be2c90e09f` and
  `ba01771409f9caf506b87e512dab1df02254a141bbfc813df7fec6daf50e2194`.
- [CT] Re-registering an already registered Repository is a strict no-op. It does not
  refresh its Git Hint, rescan remotes, append locators, or create a Record commit.
  Supported by user `Chat.Message`
  `4f2cdf3c427fb996ec20b969e0148ee654d81a0e552518c8feb2999ee97bb2d4`.

### Implementation decisions

- Use standard-library code plus the existing atomic JSON writer; introduce no dependency
  or import from existing Tarav domains.
- `Archive.create(path)` initializes `records/` and `repositories/`; `Archive.open(path)`
  validates that exact shape. Automatic Record commits use a fixed mechanical Git author
  without changing user Git configuration.
- Root Artifact registration accepts an opaque location, optional public name, and kind.
  Path-like locations are normalized; URI locators remain literal. Repository
  registration performs the additional Git validation and observation required for a
  Repository Record.
- `registration.json` owns Artifact identity and basic Archive bureaucracy;
  `locators.jsonl`, `git-hint.json`, Git-coordinate Records, and
  `external-descriptors.json` are independent flat Records beside it.
- Public names, full IDs, and unambiguous ID prefixes are convenience selectors. A location
  is lookup evidence and cannot rebind identity.
- Git-contained materialization resolves a commit and tree entry mechanically, records its
  Repository/commit/subpath coordinate and Git object facts, and is idempotent. It does not
  parse the Artifact or walk unrelated history.
- External.Descriptor registration requires both Artifacts to exist and records caller
  attribution. Repeating the same attributed declaration is idempotent.
- Repository registration accepts option-only `--branch`, defaulting to `main`. The named
  local branch must exist; Tarav does not guess another branch.
- Commit sampling is deterministic and includes both the earliest and latest commit in the
  registration-time branch history when more than one commit exists. Each sampled commit
  stores the raw Git commit object so all Git-owned metadata and the full message are
  retained without a semantic Archive parser.
- Remote admission accepts bounded common Git locators. Admitted configured values are
  stored verbatim; skipped values produce a count-only warning that never echoes them.
- Re-registering the same Repository name and local locator returns its existing Artifact
  without reading new remote configuration, changing Records, or creating a commit.

## Execution.Plan

### Vertical.Slice 1 — Archive bootstrap and uniform identity

**Status:** completed.

- Replace `manifests/` and per-type catalogs with `records/artifacts/`.
- Add 256-bit random and deterministic Artifact identity primitives.
- Verify bootstrap shape, Git-backed Record history, ID validation, and namespace isolation.

### Vertical.Slice 2 — Root Artifact and Repository registration

**Status:** completed.

- Register repoless root Artifacts and external Git Repository Artifacts.
- Preserve public names, locations, and cheap Git observations as flat Records.
- Verify idempotency, collision handling, and selector resolution.

### Vertical.Slice 3 — Lazy Git-contained Artifact materialization

**Status:** completed.

- Materialize one committed file or folder from `--repository`, `--commit`, and `--path`.
- Verify deterministic identity, exact-version distinction, repeated materialization, and
  absence of eager history enumeration.

### Vertical.Slice 4 — External.Descriptors and Artifact dossiers

**Status:** completed.

- Register attributed descriptor Artifact references as a flat Record on the target.
- Return all retained Records for an Artifact without reconciling them.
- Verify missing locations remain inspectable rather than rebinding identity.

### Vertical.Slice 5 — Option-only CLI and final audit

**Status:** completed.

- Replace the scan command with generic Artifact registration/show, Repository
  registration, Git-contained materialization, and External.Descriptor registration.
- Run focused and maintained tests, Ruff, installed-entrypoint help checks, diff review,
  namespace audit, and Product.Surface capture audit.

### Vertical.Slice 6 — Timestamped Records, Locator registry, and Git Hint amendment

**Status:** completed.

- **RED:** replace focused expectations with universal Record timestamps,
  `locators.jsonl`, remote-locator capture/skip warnings, no stored `HEAD`, deterministic
  1–10 commit sampling, raw commit metadata/messages, and option-only branch selection.
- **GREEN:** replace the superseded Record writers/readers directly; add no compatibility
  aliases or migration path because no real Archive has been initialized through Tarav2.
- **Check:** focused Tarav2 tests and Ruff, then architecture/CLI suites, full project tests,
  editable CLI reinstall, and installed help smoke.
- **Acceptance:** registering a Repository creates `registration.json`, append-only
  `locators.jsonl`, and `git-hint.json`; every Record carries `recorded_at`; the Git Hint
  contains no `HEAD`; and suspicious remotes are omitted with a non-secret warning.

## Impl.Log

- [CT] This implementation deliberately supersedes the eager File.Version experiment.
  The Archive can still materialize every committed Artifact, but demand-driven Records are
  the default because a root Repository Record already makes its committed contents
  addressable.
- [RS] The prior Chatlas estimate of roughly 350,000 changed-file occurrences remains useful
  evidence for retaining lazy materialization and avoiding a million-file default Record
  catalog.
- [IP] The pre-development checkpoint already exists at commit `c582530`; this continuation
  does not create another checkpoint or any final commit.
- [IP] Full-suite collection initially exposed a duplicate generic `test_cli.py` module
  name. Renaming the Tarav2 test module to `test_tarav2_cli.py` removed the collision; no
  product behavior changed.
- [CT] The user authorized amendment execution with `Implement`; evidence is `Chat.Message`
  `58c7882dc387dbac021e4a0706d4f54b9219b329c09dc4c316ec2060f68fcd0c`.
- [IP] The existing pre-development checkpoint at `c582530` remains the checkpoint for this
  continuing Impl.Req. No additional checkpoint or final commit is created.
- [IP] The user-reported stop-hook import failure in `Chat.Message`
  `012fee4933fba5d60f1280cc6074e1c03b148db53decaa2ba29c14992a18fd35` occurred during the
  deliberate delete/add replacement window for `archive.py`. After the new file landed,
  both direct import and the installed `tarav tarav2 archive` command loaded successfully;
  the full suite also exercises the CLI import boundary.
- Final Product.Surface capture audit is empty: the maintenance-relevant constraints live
  in the approved Archive design, focused tests, and this native implementation record; no
  additional product annotation is warranted.

## Outcome

- Replaced the superseded `manifests/` and eager File.Version catalog with the approved
  `records/artifacts/<artifact-id>/` model. The Record surface is its own Git repository;
  `repositories/` remains reserved for physically managed repositories.
- Added one uniform 256-bit lowercase-hex Artifact identity space: root/repoless Artifacts
  use cryptographically random IDs and Git-contained Artifacts use versioned canonical
  SHA-256 derivation from Repository ID, object format, exact commit, and subpath.
- Added generic root Artifact registration, Repository registration, locator hints,
  public-name/full-ID/prefix resolution, flat dossiers, lazy committed file/folder
  materialization, and attributed External.Descriptor Records. No Archive operation parses
  Artifact contents or eagerly walks repository history.
- Replaced `repository scan` with option-only CLI surfaces for Artifact registration/show,
  locator addition, External.Descriptor registration, Repository registration, and exact
  Git Artifact materialization.
- Amended every Record with `recorded_at`; replaced `locations.json` with appendable
  `locators.jsonl`; captured admitted Git remotes verbatim while warning and skipping weird
  values; replaced the Repository `git.json`/`HEAD` snapshot with a deterministic 1–10
  commit `git-hint.json` retaining raw commit metadata and messages; and added option-only
  branch selection defaulting to `main`.
- Repository re-registration is verified as a strict no-op, including after its external
  remote configuration changes.
- Verification passed: 20 focused Tarav2 tests; 107 Tarav2, architecture, and maintained
  CLI tests; all 1,995 project tests; full `src`/`tests` Ruff; `git diff --check`; editable
  CLI reinstall; direct installed import; and installed Repository/Locator help smokes.
- The real Chatlas repository was deliberately not registered or materialized. That remains
  the next operator action after reviewing this implementation.
