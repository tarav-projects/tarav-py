# Agentos Testing Environment - impl-req

## Impl.Abstract

- **scope:** add a shared, pytest-independent `agentos.testing` module in `agentos-py` that constructs isolated Agentos homes and valid current Agentos configuration state, then migrate foundation, CLI, and Chatlas tests away from duplicated schema-writing helpers
- **status:** implemented
- **source context:** research after `agentos-chatlas-py` E2E failures exposed an obsolete copied `agent.instances` fixture; user requested a general and useful test-utils module informed by how Agentos subsystems currently test Agentos
- **owning project:** `agentos-py`
- **migration projects:** `agentos-cli`, `agentos-chatlas-py`
- **primary paths:** `agentos-py/src/agentos/testing.py`, tests under the three migration projects, and their local `tests/_helpers.py` modules
- **related surfaces:** `agentos-py/notes/live/629-agent-profile-ssot-and-account-events-impl-req.md`, `agentos-py/notes/live/630-agent-profile-legacy-cleanout-impl-req.md`
- **pre-flight:** 629 and 630 must be landed before this work locks the public `write_profile(...)` shape; otherwise profile schema continues to move and forces simultaneous lockstep edits across three repositories. If either is still in flight, pause 632 until they merge.
- **stance:** legacy `agent.instances` / `provider_instances` is treated as eradication target across runtime, tests, helpers, and comments — not as a constraint to design around. See `Legacy.Eradication` below for non-negotiable rules.
- **out of scope:** a pytest plugin, shared pytest fixtures, provider-native auth/session artifacts, Chatlas rollout/index fixtures, Canvas artifacts, Iterante mission fixtures, CLI-output capture helpers, and migration of packages that do not currently construct Agentos global state

## Impl.Index

### Test.State.Schema.Authority

- tests across Agentos packages need to construct Agentos homes, profiles, global configuration, project configuration, and project markers
- these filesystem shapes are Agentos-owned schemas and should have one test-construction authority in `agentos-py`
- tests should express intended Agentos state without knowing whether profiles live in global config, split JSON files, or a future storage layout
- `agentos.testing` becomes the shared test-construction surface for current Agentos state
- only `agentos.testing` should encode the normal on-disk shapes of Agentos global config, project config, profile files, and project markers
- production loaders remain the authority for interpreting state; focused `agentos.testing` tests must prove that constructed valid state is accepted by those loaders

Hard.Evidence:

- `agentos-py/tests/_helpers.py`, `agentos-cli/tests/_helpers.py`, and `agentos-chatlas-py/tests/_helpers.py` are near copies
- the `agentos-py` copy writes current profile files, while the CLI and Chatlas copies still expose obsolete inline `provider_instances` / `agent.instances` construction
- the copied Chatlas fixture caused two E2E failures after profiles became the only named-agent source of truth
- several tests bypass even the copied helpers and manually set `HOME`, `AGENTOS_HOME`, or write config JSON

### Agentos.Test.Environment

- provide one small environment object representing an isolated test root
- suggested public shape:
  - `AgentosTestEnvironment.create(root: Path) -> AgentosTestEnvironment`
  - `environment.home`
  - `environment.agentos_home`
  - `environment.environment_variables() -> dict[str, str]`
  - `environment.apply_environment(setenv: Callable[[str, str], object])`
  - `environment.write_global_config(...)`
  - `environment.write_profile(profile_id, ...)`
  - `environment.write_project_marker(project_root, ...)`
  - `environment.write_project_config(project_root, ...)`
- `create(...)` creates isolated `home` and `agentos-home` directories beneath the caller-owned temporary root
- `apply_environment(...)` accepts a setter callback such as `monkeypatch.setenv`; `agentos.testing` must not import or depend on pytest
- paths returned by the environment are explicit so tests can create provider homes and inspect resulting state
- configuration methods should accept complete subsystem sections when needed, rather than growing one keyword for every Agentos subsystem
- environment construction creates directories under a caller-owned root; teardown is the caller's responsibility. Pytest users typically rely on `monkeypatch.undo` for env restoration and `tmp_path` for filesystem cleanup; non-pytest callers undo their own env edits.

### Valid.Builder.And.Raw.Escape.Hatch

- normal builder methods create valid current-schema Agentos state
- `write_profile(...)` writes `profiles/<profile-id>.json`; it must not recreate or accept legacy inline `agent.instances`
- builders include current class and schema-version fields where the corresponding Agentos document requires them
- tests that intentionally exercise malformed or obsolete input still need an explicit raw structured-write path
- the raw path must be clearly named, such as `write_raw_json(path, payload)`, so invalid-state tests are visibly bypassing the valid builder
- do not make valid builders permissive enough to silently generate malformed or legacy state
- do not implement builders solely by calling production writers when doing so would prevent negative tests or make tests verify a writer against itself

### Pytest.Independence

- `agentos.testing` ships inside the `agentos` package because downstream Python feature packages already depend on `agentos`
- the module must have no runtime dependency on pytest and must not expose pytest fixture decorators
- the module may accept simple protocols or callbacks that pytest objects satisfy
- downstream tests may wrap the module in package-local pytest fixtures when useful
- adding `agentos.testing` must not add pytest to `agentos-py` runtime dependencies
- `agentos.testing` ships inside the production package distribution by design; downstream installs carry test-construction code, mirroring `django.test` and `numpy.testing`. This is deliberate, not an accident of packaging.

### Shared.And.Local.Boundary

Move into `agentos.testing`:

- isolated `HOME` and `AGENTOS_HOME` construction
- current global and project config construction
- current profile-file construction
- Agentos project-marker construction
- minimal raw JSON writing needed to construct deliberate invalid state

Keep package-local:

- Codex/Claude/provider-native auth payloads and provider-home artifacts
- Chatlas raw sessions, rollouts, indexes, selectors, and view fixtures
- Canvas-specific artifacts
- Iterante missions, machines, templates, and execution fixtures
- CLI `capsys` parsing helpers such as `captured_json`
- generic helpers whose centralization does not protect an Agentos-owned schema

### Legacy.Eradication

This work treats every surviving legacy `agent.instances` / `provider_instances` artifact — runtime, test, helper, or comment — as a defect to remove. Nothing legacy is preserved, accommodated, or wrapped. The following rules are non-negotiable:

- no valid builder accepts `provider_instances`, `instances`, or any inline `agent.instances` shape; these fields are not even raw-write parameters
- no compatibility wrapper, re-export, deprecated alias, or transitional helper exists at any layer of `agentos.testing` or the migrated test suites
- if a CLI or Chatlas test asserts behavior that only made sense because runtime accepted `agent.instances`, delete the test outright. Do not port its assertion shape onto profile-backed state — that smuggles legacy semantics forward under a new name.
- if a CLI or Chatlas test exercises a scenario that is still meaningful under profile-only runtime, rewrite it from scratch against profile-backed state; do not migrate field-for-field
- if production runtime still reads `agent.instances` at the loader, config, or resolver layer, the runtime is defective. Stop migration, remove the legacy runtime path first, then resume. Do not introduce builder fields, fixtures, or wrappers to keep the legacy runtime path testable.
- the raw escape hatch (`write_raw_json`) exists for *malformed* state tests, not for keeping legacy schemas alive; raw-write sites that reconstruct any legacy Agentos schema are rejected
- every test deletion is recorded in the impl-log with a one-line rationale per deleted test

Migration order is vertical: prove the shared surface in `agentos-py`, then consume it from `agentos-cli`, then from `agentos-chatlas-py`. Migrated local helpers are deleted, not preserved. Local `_helpers.py` retains only genuinely package-local helpers (provider-native auth payloads, CLI capture utilities, Chatlas/tagger fixtures).

### Migration.Inventory

- `agentos-py/tests/_helpers.py` already contains the newest profile-writing behavior and is the initial source to refine into a public API
- `agentos-cli/tests/_helpers.py` and `agentos-cli/tests/test_e2e_agent.py` still construct named agents through `provider_instances`; these tests require semantic migration to profiles, not a mechanical import swap
- `agentos-chatlas-py/tests/_helpers.py` still exposes `provider_instances`; `tests/test_e2e_chatlas.py` now contains a local repaired profile writer that should be replaced by `agentos.testing`
- `agentos-chatlas-py/tests/test_tagger.py` writes Chatlas-specific global config bodies directly; it may use the environment/raw-config surface while keeping tagger fixtures local
- `agentos-canvas-py` currently has no material Agentos-home construction to migrate
- Iterante packages primarily construct project-local mission state and are outside this initial migration

## Execution.Plan

### Slice 1 - Establish `agentos.testing` With Loader-Proven State

- add a public `agentos.testing` module with `AgentosTestEnvironment` and the valid/raw construction boundary
- add focused tests in `agentos-py` for directory isolation, environment-variable application, global config, profile creation, project marker, project config, and raw invalid-state writing
- validate generated state through current production loaders such as `load_global_config(...)`, `load_agent_configs(...)`, and project resolution
- ensure the module imports without pytest installed or imported
- path: temporary root -> `AgentosTestEnvironment` -> constructed Agentos state -> production loader
- observable: one supported API creates a valid profile-backed Agentos environment accepted by current loaders
- check: focused `agentos.testing` tests and `agentos-py` full suite pass
- status: completed

### Slice 2 - Migrate `agentos-py` Tests To Their Public Test Surface

- replace schema-writing and environment-isolation calls from `agentos-py/tests/_helpers.py` with `agentos.testing`
- preserve provider-auth and other domain-specific helpers locally
- delete migrated duplicate helpers from `_helpers.py`
- use the raw escape hatch only for tests intentionally exercising invalid configuration
- path: foundation test -> `agentos.testing` -> foundation runtime behavior
- observable: `agentos-py` tests use the same public test-construction API offered to downstream packages
- check: `agentos-py` full suite passes; search shows no duplicate local home/profile/config/project-marker constructors
- status: completed

### Slice 3 - Migrate `agentos-cli` And Eradicate Legacy Named-Agent Fixtures

- pre-flight: confirm CLI runtime no longer reads `agent.instances` at any layer (loader, config resolver, agent runner). If it does, fix the runtime first under the relevant cleanout impl-req; do not migrate tests against a legacy code path.
- pre-flight: classify every CLI test currently using `provider_instances` as one of:
  - **(a) scenario still valid under profile-only runtime** — rewrite from scratch against profile-backed state using `agentos.testing`. Do not migrate `provider_instances=...` field-for-field.
  - **(b) scenario only meaningful because runtime honored `agent.instances`** — delete the test outright with a one-line rationale in the impl-log.
- import the shared testing surface from the existing `agentos` dependency
- migrate home/config/project-marker construction and delete the migrated local helper copies entirely
- keep CLI-output capture and CLI-specific fixtures local
- path: CLI E2E test -> shared Agentos test environment -> profile-backed CLI execution
- observable: CLI tests no longer encode `agent.instances` in any form, and profile-only runtime behavior is tested end to end
- check: `agentos-cli` full suite passes; grep for `provider_instances`, the literal `agent.instances`, and `"instances"` as an `agent` payload key returns zero matches across `agentos-cli/tests/`; impl-log records each (a) rewrite and each (b) deletion
- status: completed

### Slice 4 - Migrate `agentos-chatlas-py` And Consolidate The Repaired Fixture

- replace `_isolate_chatlas(...)` environment setup and the local `codex-work` profile writer with `agentos.testing`
- migrate reusable Agentos global-state construction from Chatlas tests while keeping Chatlas session/tagger fixtures local
- delete migrated local helper copies and retain only Chatlas-specific helpers
- path: Chatlas E2E test -> shared Agentos test environment -> `codex-work` profile -> Chatlas instance selection
- observable: the repaired Chatlas E2E profile fixture is produced through the shared authority and cannot drift independently
- check: `agentos-chatlas-py` full suite passes, including the previously failing Chatlas E2E tests
- status: completed

### Slice 5 - Cross-Package Grep Gate And Usage Contract

- run full suites for `agentos-py`, `agentos-cli`, and `agentos-chatlas-py`
- add concise module documentation describing the valid-builder/raw-escape-hatch boundary and examples for downstream packages
- do not force migrations in Canvas or Iterante where the shared surface does not currently fit a real use case
- run the audit as a **mechanical grep gate**, not a manual review. Outside `agentos-py/src/agentos/testing.py` and its focused tests, the following patterns must return zero matches across the three repositories' tests and helpers:
  - `provider_instances`
  - `agent.instances` (and `"instances"` as an `agent` payload key)
  - `"class": "agentos.global.config"`
  - `"class": "agentos.project.config"`
  - `"class": "agentos.project"`
  - direct `monkeypatch.setenv("AGENTOS_HOME"` and `monkeypatch.setenv("HOME"` calls in test bodies (must route through `apply_environment(...)`)
- the only permitted exceptions are explicit raw-escape-hatch sites that reconstruct *malformed* state and carry a one-line comment naming the negative-test intent. Raw-write sites that reconstruct any legacy Agentos schema are rejected at review.
- path: shared module -> three consuming repositories -> mechanical grep gate
- observable: Agentos-owned test state has one construction authority across current consumers; every grep above returns zero outside the documented exception sites
- check:
  - all three full suites pass
  - no runtime pytest dependency exists
  - no migrated local compatibility wrappers remain
  - every grep pattern above returns zero matches outside the documented exception sites
  - impl-log enumerates every test deleted under the (b) classification in Slices 3 and 4
- status: completed

## Risks And Deviation Triggers

- if a shared builder cannot represent a current valid Agentos state without subsystem-specific arguments, keep that subsystem state local rather than expanding `agentos.testing` into a feature-package dependency
- if tests need malformed state, use the explicit raw escape hatch; do not weaken valid builders
- if importing `agentos.testing` causes imports of CLI or feature packages, stop and correct the dependency direction
- if migration discovers that production runtime still reads `agent.instances` at any layer, treat the runtime as defective: stop migration, remove the legacy runtime path first, then resume. Do not introduce builder fields, compatibility wrappers, or test helpers to keep the legacy path alive.
- if migration discovers a test that only passes because runtime accepted `agent.instances`, delete the test outright with a one-line rationale in the impl-log. Do not port its assertion shape onto profile-backed state.
- if 629 or 630 have not yet landed when this work starts, pause 632 until they merge; re-running profile schema decisions mid-migration would force lockstep edits across three repositories
- if project-local named profiles are discovered as a current supported concept, realign before encoding them; current production loading treats profiles as global files
- if the initial environment object becomes a broad fixture framework or pytest plugin, reduce scope before continuing

## Acceptance Signals

- `agentos.testing` is importable from the `agentos` runtime package without importing pytest
- a downstream test can create an isolated home, global config, profile, and project marker without knowing their storage paths
- valid constructed state is accepted by current production loaders
- malformed-state tests retain a deliberate, explicit raw-write path; raw-write sites never reconstruct legacy Agentos schemas
- `agentos-py`, `agentos-cli`, and `agentos-chatlas-py` use the shared surface for Agentos-owned state
- provider-, Chatlas-, CLI-, Canvas-, and Iterante-specific fixtures remain in their owning packages
- full suites pass in all three migration repositories
- the Slice 5 mechanical grep gate returns zero matches for `provider_instances`, `agent.instances`, `"class": "agentos.global.config"`, `"class": "agentos.project.config"`, `"class": "agentos.project"`, and stray `monkeypatch.setenv("AGENTOS_HOME"`/`HOME"` calls outside `agentos.testing` and its focused tests
- the impl-log enumerates every CLI or Chatlas test deleted as legacy-only, with a one-line rationale per deletion

## Impl.Log

- 2026-06-06: Impl.Req created after surveying Agentos Python package tests. Research found near-copy helper modules in `agentos-py`, `agentos-cli`, and `agentos-chatlas-py`, with schema drift between profile-file and legacy inline-instance construction.
- 2026-06-06: Scope intentionally limited to Agentos-owned filesystem/configuration state. Provider artifacts, feature-package fixtures, pytest plugin behavior, and unrelated generic test helpers remain out of scope.
- 2026-06-06: Sharpened anti-legacy stance to zero-tolerance: surviving `agent.instances` / `provider_instances` artifacts at any layer are defects, not constraints. Slice 3 adds a pre-classification step distinguishing tests to rewrite against profile-backed state from tests to delete outright. Slice 5 audit lifted from manual review to a mechanical grep gate with explicit forbidden patterns. Pre-flight requirement added: 629 and 630 must land before 632 locks the public `write_profile(...)` shape. Test-environment cleanup contract and intentional in-runtime distribution noted explicitly.
- 2026-06-06: Pre-flight completed. Profile/account tests passed 20/20, active runtime searches found no legacy profile or link-registry paths, and checkpoint `800f313` landed the current 629/630 implementation before 632 edits.
- 2026-06-06: Added pytest-independent `agentos.testing` with valid builders for isolated homes, global/project config, profiles, and project markers, plus explicit `write_raw_json` malformed-state escape hatch. Focused loader-backed and no-pytest-import tests pass.
- 2026-06-06: Migrated `agentos-py` tests and removed duplicated Agentos-state constructors from its local `_helpers.py`.
- 2026-06-06: Migrated `agentos-cli` tests to profile-backed shared state and removed duplicated Agentos-state constructors. Deleted `test_agent_run_uses_explicit_project_target_for_config_resolution`: it only tested removed project-local inline named-agent configuration and has no profile-only runtime equivalent.
- 2026-06-06: Rewrote current CLI account-link scenarios against auth materialization state and absence of `links.json`; removed stale assertions tied to the deleted link registry.
- 2026-06-06: Migrated `agentos-chatlas-py` E2E and tagger tests. The repaired `codex-work` fixture now uses `agentos.testing`; copied Agentos-state constructors were removed.
- 2026-06-06: Execution deviation resolved: broad formatter runs introduced unrelated whitespace churn in migrated test files; the churn was removed while preserving the semantic migration.
- 2026-06-06: Completion audit passed: `agentos-py` 55/55, `agentos-cli` 50/50, `agentos-chatlas-py` 100/100; changed-file lint and diff checks pass; duplicate-constructor search and the full mechanical grep gate return zero matches.
