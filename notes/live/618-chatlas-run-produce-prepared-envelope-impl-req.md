# Chatlas Run Produce Prepared Envelope - impl-req

## Impl.Abstract

- **scope:** update `agentos chatlas run-produce` so deterministic view preparation stays in the parent CLI and the child agent only writes the required staged artifact.
- **status:** implemented
- **source:** direct design discussion after testing `zip-transcript-agent-summary` production for session `019e386b-bb36-7343-b5cf-3c2078f90dae`
- **target project:** `agentos-py`
- **primary files:** `src/agentos/chatlas/views/core.py`, `tests/test_chatlas_commands.py`

## Impl.Index

### RunProduce.Prepared.Envelope

- `chatlas_run_produce` currently checks freshness, builds a broad workflow prompt, and launches an agent.
- For `zip-transcript-agent-summary`, the broad prompt asks the child agent to ensure `zip-transcript`, stage the target view, write `summary.json`, commit, and return the final path.
- This caused high token use and unsafe behavior in the failed test run: the child agent searched for missing references, edited the committed target slot directly, copied into staging, and retried commit failures.
- The new behavior must make `run-produce` prepare the deterministic envelope before launching the agent.
- The deterministic envelope includes dependency availability, source artifact path, target stage, exact staged output path, and final target path.
- The child agent should only read the exact source transcript and write the exact staged `summary.json` path.

### View.Owned.Dependency.Preparation

- Keep the current view architecture: each view owns its own dependency preparation.
- Do not introduce a generic dependency graph or global external-view production engine.
- Add a small workflow hook for external views to prepare agent production.
- Shared primitives may be provided for common operations, but the view composes them.
- `run-produce` must not know that `zip-transcript-agent-summary` depends on `zip-transcript`; it should only ask the workflow to prepare.

### Production.Primitives

- Existing primitives already cover most of the required behavior:
  - `_ensure_available` can produce or validate an internal dependency.
  - `chatlas_views_stage` creates staging metadata for external views.
  - `chatlas_views_commit` validates staged artifacts and installs them into the target slot.
  - the `zip-transcript-agent-summary` linter enforces session equality, turn count, role alignment, verbatim user text, and nonblank assistant text.
- Implementation may factor internal helper versions so prepared production can use an existing `ChatlasViewContext` without re-querying.
- Avoid changing the public CLI shape unless needed for correctness.

### Prompt.Narrowing

- The prepared prompt should be specific and low-token.
- It should include:
  - exact source `zip-transcript.json` path
  - exact staged output `summary.json` path
  - final artifact shape
  - compression rules for assistant turns
  - instruction to preserve every user turn verbatim
  - instruction not to run `agentos chatlas views stage`
  - instruction not to run `agentos chatlas views commit`
  - instruction not to write any committed target slot
- The prompt may still tell the agent to load `chatlas-usage` and read `references/producer-zip-transcript-agent-summary.md`, but only for compression rules and artifact contract context.

### Commit.Owner

- Parent `run-produce` should commit the stage after the child exits successfully.
- A successful child exit is not sufficient for final success; final success requires `chatlas_views_commit` to pass.
- If the child exits nonzero, do not commit the stage.
- If commit fails, return a failed run result with the commit error message and leave the stage directory for inspection.
- If commit succeeds, return the final committed artifact path or commit view payload in the run result.

### DryRun.Semantics

- `--dry-run` should remain non-mutating.
- Dry-run must not create a staging directory.
- Dry-run should show the prepared prompt shape and enough deterministic context to verify behavior.
- If exact stage paths require mutation, use placeholder paths in dry-run rather than creating a real stage.

## Execution.Plan

### Slice 1 - Add prepared production data model

- add a small internal dataclass such as `ChatlasPreparedAgentProduction`
- include at least: `prompt`, `stage_id`, `stage_path`, `output_artifact_path`, `final_artifact_path`, and `diagnostics`
- keep the type local to `src/agentos/chatlas/views/core.py` unless reuse elsewhere is clearly needed
- observable: code can represent a prepared production without launching an agent
- check: targeted unit test or direct construction through a workflow method
- status: completed

### Slice 2 - Add view-owned preparation hook

- extend the internal workflow protocol with a preparation hook for agent production
- implement the hook for `ZipTranscriptAgentSummaryWorkflow`
- for unsupported workflows, raise a clear `CliError`
- preserve the existing `build_produce_prompt` behavior if still used by `chatlas produce` or dry-run surfaces, or route it through the prepared prompt only where safe
- observable: `zip-transcript-agent-summary` can prepare exact source/stage/output paths from a `ChatlasViewContext`
- check: unit test the prepared object without launching a real agent
- status: completed

### Slice 3 - Factor staging primitive for existing context

- factor `chatlas_views_stage` so staging metadata can be created from an already resolved `ChatlasViewContext`
- keep the public `chatlas_views_stage(...)` function behavior unchanged
- ensure stage metadata still includes source rows, parameters, cache key, target slot, artifact contract, and production instructions
- observable: public `agentos chatlas views stage` remains stable while `run-produce` can stage without re-querying
- check: existing stage tests plus a new context-based staging test if current coverage is insufficient
- status: completed

### Slice 4 - Prepare zip-transcript-agent-summary envelope

- in the `ZipTranscriptAgentSummaryWorkflow` preparation hook:
  - ensure the `zip-transcript` dependency through existing internal view machinery
  - resolve the dependency primary artifact path
  - stage `zip-transcript-agent-summary`
  - set the exact staged output path to `<stage>/summary.json`
  - set the final artifact path to the target slot `summary.json`
  - build the narrow prompt
- observable: the prompt tells the agent to write only the exact staged `summary.json`
- check: test prompt text includes source path and staged output path, and excludes instructions to run stage or commit
- status: completed

### Slice 5 - Update run-produce execution flow

- change `chatlas_run_produce` so non-dry runs:
  - skip fresh views unless `--force`
  - call the workflow preparation hook for stale or missing external views
  - run the agent with the prepared prompt
  - commit the prepared stage only when the child exits `0`
  - report child failures without committing
  - report commit failures as failed runs
- keep provider resolution and agent execution behavior otherwise unchanged
- observable: `run-produce` owns final commit and returns failure if commit validation fails
- check: unit tests using a fake agent provider or monkeypatched runtime
- status: completed

### Slice 6 - Preserve dry-run behavior

- make dry-run show the prepared prompt shape without creating a stage
- include deterministic context such as target view, source dependency view, final artifact path, and placeholder staged output path
- if current dry-run is used by tests, update assertions to the new prompt shape
- observable: dry-run remains side-effect-free and explains what would be prepared
- check: test no staging directory is created during dry-run
- status: completed

### Slice 7 - Validate with focused tests and CLI refresh

- run targeted tests for Chatlas view production and run-produce behavior
- run ruff on touched files
- after CLI changes, run `uv tool install --reinstall --editable .`
- optionally rerun the real production command against the known session after deleting only the target summary view
- observable: missing/stale summary production succeeds with one child-agent write path and parent-owned commit
- check:
  - `uv run python -m pytest tests/test_chatlas_commands.py::<targeted tests> -q`
  - `uv run ruff check src/agentos/chatlas/views/core.py tests/test_chatlas_commands.py`
  - `agentos chatlas run-produce --session-id 019e386b-bb36-7343-b5cf-3c2078f90dae --view zip-transcript-agent-summary`
- status: completed

## Acceptance.Signals

- `run-produce` does not ask the child agent to stage or commit `zip-transcript-agent-summary`.
- the child prompt includes exact source and exact staged output paths.
- parent `run-produce` commits the stage after child success.
- parent `run-produce` does not commit when the child exits nonzero.
- commit linter failures surface as `failed_count: 1` with a clear error.
- fresh target views still skip without launching an agent.
- dry-run does not create a stage.
- existing public `views stage`, `views commit`, and `views status` behavior remains compatible.

## Risks.And.Deviation.Triggers

- If the workflow protocol becomes awkward for internal views, keep the new hook optional and only call it from external production paths.
- If dry-run needs exact real stage IDs, stop and ask for a product decision because that conflicts with side-effect-free dry-run.
- If tests require extensive fake provider setup, prefer monkeypatching `resolve_agent` or a thin helper rather than introducing a new provider abstraction.
- If the implementation starts becoming a generic dependency graph, stop and realign; the accepted design is view-owned dependency preparation with small shared primitives.

## Impl.Log

- 2026-05-18: Impl.Req created from user-approved design direction. Execution not started.
- 2026-05-18: Implemented prepared agent production for `zip-transcript-agent-summary`. `run-produce` now asks the view to prepare its envelope, launches the agent with exact source/output paths, commits the prepared stage in the parent after child success, reports commit linter failures, and keeps dry-run side-effect-free. Focused tests and ruff passed.
