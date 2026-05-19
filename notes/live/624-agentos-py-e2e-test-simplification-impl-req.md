# Agentos Py E2E Test Simplification - impl-req

## Impl.Abstract

- **scope:** simplify the `agentos-py` pytest suite by cutting unit-style and overly granular tests, leaving a smaller set of end-to-end scenario tests that preserve meaningful CLI and artifact coverage.
- **status:** implemented.
- **source:** direct user request after a test-suite research pass on 2026-05-19.
- **goal:** reduce test source from about `14.6k` LOC and about `382` granular tests toward `6k-8k` LOC and `40-80` scenario tests, while keeping coverage focused on externally observable behavior.
- **target project:** `/Users/pereiro/projects/agentos-project/agentos-py`
- **primary test surface:** `tests/`
- **strong constraint:** prefer e2e scenario coverage over private helper/unit coverage. Delete private-helper tests unless they protect a durable file, hash, or output contract.

## Impl.Index

### Accepted.Target.Shape

- Keep total test source under `6k-8k` LOC.
- Keep any single test file under `1k` LOC, preferably under `500`.
- Move repeated setup into a small shared e2e fixture layer.
- Prefer `40-80` scenario tests over about `390` granular tests.
- Delete unit tests for private helpers unless they protect a durable file/hash/output contract.
- Preserve meaningful coverage by asserting:
  - CLI exit codes
  - stdout/stderr JSON or text
  - created files and directories
  - durable config, index, tape, account, and skill artifacts
  - observable behavior of supported commands

### Current.Suite.Shape

- Current test suite has about `14,584` LOC across `25` test files.
- Current test count is about `382`.
- Largest files observed:
  - `tests/test_agent_account_registry_commands.py`: about `4,612` LOC, `105` tests
  - `tests/test_agent_commands.py`: about `2,358` LOC, `49` tests
  - `tests/test_chatlas_commands.py`: about `1,997` LOC, `47` tests
  - `tests/test_skills_commands.py`: about `1,751` LOC, `44` tests
  - `tests/test_forum_commands.py`: about `659` LOC, `13` tests
- Existing tests mostly call `agentos.cli.main([...])` in-process with temp directories. This is acceptable as the baseline e2e style for this cleanup unless the implementation discovers a project convention requiring subprocess invocation.

### E2E.Boundary.Policy

- Keep tests that exercise a command path end-to-end through `agentos.cli.main([...])` or the installed `agentos` executable.
- Favor workflow tests that run multiple related commands against one temp project/home fixture.
- Avoid tests that directly import private helpers, parser internals, provider classes, or implementation functions.
- Direct imports are acceptable only for small shared test setup helpers or when the tested value is a durable external contract with no CLI exposure.
- For this pass, do not add broad coverage tooling or new dependencies.

### Initial.Cut.Targets

- Delete or fold direct unit/internals tests:
  - `tests/test_process_runner.py`
  - `tests/test_refs_ref_path.py`
  - `tests/test_canvas_dependency.py`
  - `tests/test_agent_cli_common.py`
  - `tests/test_chatlas_session_hashes.py`, unless kept as durable hash contract coverage
  - `tests/test_chatlas_session_location_fields.py`, unless folded into Chatlas e2e provider fixtures
- Trim Tara Tapes direct core tests in:
  - `tests/test_tara_tapes.py`
  - `tests/test_tara_tapes_check.py`
  - `tests/test_tara_tapes_archive.py`
- Preserve Tara Tapes coverage through CLI workflows for init, append, scan, commit, check, archive, and dry-run behavior.

### Consolidation.Targets

- `tests/test_agent_account_registry_commands.py`
  - Collapse granular provider/account/status/monitor tests into a smaller number of end-to-end scenarios.
  - Preserve visible behavior for register, link, status, usage refresh/status, monitor selection, and major error paths.
- `tests/test_agent_commands.py`
  - Keep e2e scenarios for `agent run --dry-run`, raw argv, config resolution, list output, and user-facing validation errors.
  - Drop direct capability/spec/provider object assertions unless surfaced through CLI output.
- `tests/test_chatlas_commands.py`
  - Keep e2e flows for index update/query/export, stats/doctor, reset/redo, and selector errors.
  - Avoid one-test-per-small-branch duplication.
- `tests/test_skills_commands.py`
  - Keep e2e flows for import default profile, import explicit source/profile, status, validation errors, and local `.agents` integration.
- `tests/test_stdlib_commands.py`
  - Reduce parser/help assertions to a small routing smoke and command payload coverage only where externally meaningful.

### Target.File.Shape

The final file names may differ if the existing structure makes a smaller diff cleaner, but the preferred shape is:

- `tests/test_e2e_agent.py`
- `tests/test_e2e_agent_accounts.py`
- `tests/test_e2e_chatlas.py`
- `tests/test_e2e_skills.py`
- `tests/test_e2e_stdlib.py`
- `tests/test_e2e_project_system.py`
- `tests/test_e2e_tara_tapes.py`
- `tests/test_e2e_forum.py`

Shared setup belongs in `tests/_helpers.py` or a very small `tests/e2e_helpers.py` if splitting e2e helpers improves clarity.

### No.Legacy.Allowed

- Do not keep old granular tests as aliases, skipped tests, or archived duplicates.
- Do not add compatibility scaffolding only to satisfy deleted tests.
- Do not retain private helper tests just because the helper exists.
- Do not expand implementation code to make the test rewrite easier.
- Do not introduce a separate new test framework or dependency.

## Execution.Plan

### Slice 1 - Establish Shared E2E Fixture Layer

Status: implemented.

- Read `tests/_helpers.py` and the setup blocks in the largest test files.
- Move repeated setup into a small shared e2e fixture/helper layer:
  - fake `HOME`
  - fake `AGENTOS_HOME`
  - project marker/config creation
  - common JSON read/write helpers
  - common CLI invocation/output parsing helpers, only if they reduce real duplication
- Keep helpers concrete and limited. Avoid a large framework.
- Validation:
  - run a focused subset of existing tests that use the touched helpers
  - verify helper changes do not alter production code

### Slice 2 - Remove Pure Unit/Internal Test Files

Status: implemented.

- Delete or fold the direct private/unit tests listed in `Initial.Cut.Targets`.
- If a test protects a durable contract, rewrite it as a small e2e or public-contract scenario instead of keeping private-helper coverage.
- Validation:
  - run `uv run pytest` on the remaining suite
  - record any missing coverage revealed by failures

### Slice 3 - Collapse Tara Tapes Into CLI Scenarios

Status: implemented.

- Replace direct core/check/archive tests with a compact e2e file covering:
  - init with manifest data
  - append staged records
  - scan before and after commit
  - segment read
  - manifest read
  - check conformant and non-conformant tape behavior
  - archive and dry-run archive
- Delete redundant direct function tests after equivalent CLI behavior exists.
- Validation:
  - run the Tara Tapes test file only
  - inspect LOC/test count reduction

### Slice 4 - Consolidate Stdlib, Project, And Small Command Tests

Status: implemented.

- Consolidate smaller command surfaces:
  - stdlib routing/help
  - utils command logger and uuid behavior
  - prefix/tmp-folder/mdblocks/ref-path/project/system smoke coverage
- Keep behavior at command boundaries.
- Prefer scenario tests that run several related commands against one temp project.
- Validation:
  - run the consolidated small-command tests
  - confirm no single file exceeds `1k` LOC

### Slice 5 - Consolidate Chatlas Scenarios

Status: implemented.

- Reshape Chatlas tests around a few durable workflows:
  - index update from provider raw fixture and query results
  - stats and doctor behavior
  - export and view production behavior
  - reset/redo behavior
  - selector and validation errors
- Fold provider session location coverage into raw-fixture e2e where feasible.
- Keep durable hash behavior only if visible in indexed rows or exported artifacts.
- Validation:
  - run Chatlas tests
  - confirm preserved coverage for produced index rows, raw copies, views, and exported artifacts

### Slice 6 - Consolidate Skills Scenarios

Status: implemented.

- Reshape skills tests around a few end-to-end workflows:
  - import using default routing profile
  - import using explicit source/profile
  - status/reporting behavior
  - invalid config/source errors
  - local `.agents` integration
- Move duplicated skill fixture creation into the shared e2e layer if broadly useful.
- Validation:
  - run skills tests
  - verify generated depots, symlinks/copies, and status output

### Slice 7 - Consolidate Agent And Account Scenarios

Status: implemented.

- Reduce agent command tests to scenario coverage for:
  - configured agents list output
  - `agent run --dry-run`
  - raw argv behavior
  - project/global config resolution
  - key validation errors
- Reduce account registry tests to scenario coverage for:
  - register/link/status workflows
  - usage refresh/status artifacts
  - monitor selection and major error behavior
  - provider differences only where externally visible
- Validation:
  - run agent and account tests
  - confirm output artifacts and JSON payloads still cover supported workflows

### Slice 8 - Final Verification And Test-Suite Budget Check

Status: implemented.

- Run the full suite:

```sh
uv run pytest
```

- Measure resulting test size:

```sh
find tests -maxdepth 1 -type f -name 'test_*.py' -print0 | xargs -0 wc -l
for f in tests/test_*.py; do printf '%s\t' "$f"; rg -c '^def test_' "$f"; done
```

- Acceptance signals:
  - total test source is under `8k` LOC, ideally close to `6k`
  - no single test file exceeds `1k` LOC
  - preferably no single test file exceeds `500` LOC unless the scenario surface clearly justifies it
  - test count is between `40` and `80` scenario tests, or any excess is explicitly justified
  - `uv run pytest` passes
  - production code changes are absent or limited to necessary fixes revealed by valid e2e expectations

## Impl.Log

- 2026-05-19: Impl.Req created from accepted test-suite simplification target and initial research findings. No implementation changes made yet.
- 2026-05-19: Implemented the e2e test simplification. Replaced the large Agent, account registry, Chatlas, Skills, Forum, Tara Tapes, and stdlib-heavy granular files with compact scenario tests; deleted private/unit-oriented test files. Final measured test suite: `1,626` LOC, `51` tests, no test file over `218` LOC. Verification: `uv run pytest` passed with `51 passed`.
