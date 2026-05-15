# Chatlas Raw Partition Manifest - impl-req

## Impl.Abstract

- **scope:** make `agentos chatlas update` create immutable raw partition manifests that preserve original provider source metadata, especially provider home paths
- **status:** implemented
- **source:** user request after discovering that externally recovered Codex homes must become normal Chatlas capture behavior for future provider instances
- **target:** when Chatlas first creates a raw provider partition, write `raw/<provider>/<fingerprint>/manifest.json` from the current update input/configured source path; later reads must use that manifest to preserve original homes during index rebuilds
- **non-goals:** do not rewrite existing manifests during normal update; do not derive manifest data from session index rows; do not merge from the external manifests created during investigation; do not add transient session counts or session timestamp ranges

## Impl.Index

### Raw.Partition.Manifest.Ownership

- The raw partition owns provider-instance provenance.
- The manifest belongs at `raw/<provider>/<fingerprint>/manifest.json`.
- It is partition-level metadata, not a per-session artifact and not a derived index row.
- The manifest should describe the original source path that Chatlas ingested and the raw archive path where that source was copied.
- The manifest should be created only when missing.
- If the manifest already exists, normal update must be a no-op for the manifest, even if the configured provider path has since changed.

#### appendix

Evidence from current code:

- `src/agentos/chatlas/delta_scan.py` has `ChatlasProviderInstance.partition_key` and `raw_home(raw_root)`.
- `_process_provider_instance(...)` receives the configured `ChatlasProviderInstance` and `raw_root`.
- `_copy_delta_session_sources(...)` only runs for changed sessions and is too narrow for partition metadata.
- The session index is derived data, so it cannot be the only storage location for original provider home provenance.

#### meta

- status: accepted implementation target

### Manifest.Creation.Source

- Manifest creation must use only data available from the current Chatlas update input for the provider instance.
- For home-backed providers, the source of truth is `instance.agent.home` from the configured provider instance being scanned.
- The implementation must not inspect or copy values from the external recovery manifests created during the design investigation.
- The implementation must not use current session index rows as manifest input.
- If a provider instance has no configured home, the manifest may still record provider, fingerprint, instance, and an empty or explicit `source_roots` set, but should not invent a home.

#### appendix

Accepted user constraint:

- "do not get contaminated by the external write we did"
- "if the manifest exist, this should be noop"
- "it is only the first time we create the instance folder"

#### meta

- status: accepted implementation target

### Manifest.Shape

- The initial manifest should be minimal and stable.
- Required fields:
  - `class`: `agentos.chatlas.raw_partition_manifest`
  - `schema_version`: `1`
  - `provider`
  - `provider_instance_fingerprint`
  - `instance`
  - `home`: original configured provider home string when known, otherwise `null`
  - `raw_home`: raw archive home path when applicable, otherwise `null`
  - `home_source`: `configured_agent_home` when `home` comes from `instance.agent.home`, otherwise `null`
  - `source_roots`: mappings from source roots to raw roots
- For a home-backed provider, `source_roots` should include one row:
  - `role`: `home`
  - `source_root`: original configured provider home
  - `raw_root`: raw archive home path
- Do not include session-derived fields such as `session_count` or `session_updated_at_range`.
- Avoid fields that change on every update. If a timestamp is added, it must be first-write-only and preserved forever unless an explicit repair command is introduced.

#### appendix

The manually written Codex manifests demonstrated the shape, but implementation must generate the same kind of data from configured provider instances, not by reading those external files.

#### meta

- status: accepted implementation target

### Index.Redo.Manifest.Consumption

- `chatlas index redo` currently reconstructs provider instances from archived raw partitions.
- For home-backed raw archives, redo must keep using the raw home path for scanning archived artifacts.
- Redo must not use the raw home path as the original indexed `home`.
- When a raw partition manifest exists, redo should read manifest `home` and pass it into `_session_index_row(..., provider_home=...)`.
- If no manifest exists, redo should keep current honest fallback behavior and leave `home` as `null` or the existing behavior only if no better data is available.

#### appendix

Evidence from current code:

- `_agent_from_raw_partition(...)` sets archived `AgentConfig.home` to `partition_dir / "home"` so provider discovery can scan copied raw artifacts.
- `_redo_provider_instance_index(...)` currently calls `_session_index_row(session)` without overriding provider home.
- `_derive_delta_index_rows_from_chatlas_raw(...)` already demonstrates the correct pattern by passing the configured provider home into `_session_index_row(...)` while scanning copied raw artifacts.

#### meta

- status: accepted implementation target

## Execution.Plan

### Slice 1 - Add raw partition manifest helpers

- add small helpers in `src/agentos/chatlas/delta_scan.py`:
  - `_raw_partition_manifest_path(raw_root, instance)`
  - `_load_raw_partition_manifest(path_or_partition)`
  - `_raw_partition_manifest_payload(instance, raw_root)`
  - `_create_raw_partition_manifest_if_missing(instance, raw_root)`
- use existing `write_text_if_changed(...)` for JSON writing
- keep helper behavior deterministic and side-effect-free except for the create-if-missing writer
- path: configured provider instance -> manifest payload -> raw partition manifest
- observable: a missing manifest can be created with stable provider/home/source-root metadata
- check: focused helper or command test verifies payload fields for a configured Codex home
- status: implemented

### Slice 2 - Create manifest during Chatlas update

- call `_create_raw_partition_manifest_if_missing(...)` from `_process_provider_instance(...)`
- place the call before the `if not delta_sessions:` early return
- ensure it runs even when all sessions are cache hits and no raw files are copied
- if `manifest.json` already exists, return immediately without reading external values into the new payload and without rewriting the file
- path: `agentos chatlas update` -> configured instance scan -> raw partition manifest creation
- observable: first update for a new provider fingerprint creates `raw/<provider>/<fingerprint>/manifest.json`
- check: command test runs update twice; first run creates manifest, second run leaves existing manifest content unchanged
- status: implemented

### Slice 3 - Preserve original home during index redo

- update redo indexing so it reads manifest `home` from the raw partition when present
- keep archived provider discovery pointed at `raw/<provider>/<fingerprint>/home`
- pass manifest home into `_session_index_row(..., provider_home=manifest_home)`
- do not make the manifest mandatory for old raw partitions
- path: raw partition manifest -> `chatlas index redo` -> rebuilt session index row -> `agentos chatlas query`
- observable: after reset and redo, indexed `home` is the original provider home from the manifest, not the raw archive home path
- check: extend the existing redo test to assert `rows[0]["home"] == str(codex_home)` after native source files are removed and redo scans only Chatlas raw
- status: implemented

### Slice 4 - Verify behavior and installed CLI

- run focused Chatlas command tests
- run full test suite if focused tests pass
- reinstall editable CLI because Chatlas update/index behavior changed:
  - `uv tool install --reinstall --editable .`
- smoke check a real or fixture-backed update/redo path when practical
- observable: new provider partitions get immutable manifests and redo preserves original home values
- check:
  - `uv run python -m pytest tests/test_chatlas_commands.py -q`
  - `uv run python -m pytest -q`
  - installed CLI smoke check
- status: implemented

## Impl.Log

- 2026-05-15: Created implementation request from the accepted design: Chatlas should create raw partition manifests the first time a provider fingerprint is captured, sourcing the data only from the current update input/configured path, treating existing manifests as immutable during normal update, and using the manifest later to preserve original homes during `chatlas index redo`.
- 2026-05-15: Implemented raw partition manifest creation in `src/agentos/chatlas/delta_scan.py`. `agentos chatlas update` now creates `raw/<provider>/<fingerprint>/manifest.json` only when missing, using the configured provider instance as input and leaving existing manifests untouched. `chatlas index redo` now reads manifest `home` and passes it into rebuilt session index rows while continuing to scan copied raw artifacts from the raw home path. Added focused coverage in `tests/test_chatlas_commands.py` for manifest shape, no transient fields, first-write no-op behavior, and redo home preservation. Verified with `uv run python -m pytest tests/test_chatlas_commands.py -q`, `uv run python -m pytest -q`, `uv tool install --reinstall --editable .`, `agentos --version`, and `agentos chatlas index --help`.
