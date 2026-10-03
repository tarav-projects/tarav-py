# 850 — Unified Tarav Python run CLI

<!-- tarav.sessions
1ae20f8c = codex:01a0ff32-0ec2-7b72-8850-fa795135f3c9 @1ae20f8c8159f12d2402ea702cf49c876ec46a72f71ce12423ae1dbdf2a91871
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: Design ready; Execute pending. Phase: Develop.

Make `tarav run [--project PATH] -- <python arguments>` the single user-facing Python runner. The separator assigns all following words to Python, including `script.py`, `-c`, `-m`, `-`, and their arguments. Without `--project`, use Tarav's current interpreter; with it, use the selected Project's configured interpreter and working directory. Remove the `tarav project harness run` and `tarav python run` CLI leaves. Keep `tarav project harness` setup/inspection commands and `tarav python path`.
<!-- tarav.breadcrumb 40f0c902aa010a0b870d59f4c5d5e74cc1f7efc54d731d49d2a6bd8b2adc27c3 -->

This is a CLI composition change. Preserve the existing runner, Project configuration, and trusted typed-Project bootstrap library APIs. Do not add implicit `project` or `runtime` globals to the general runner, change Project records, or alter environment installation.

## Design narrative

The user chose a single short command with `--` separating Tarav options from the Python invocation, then explicitly asked to remove `project harness run` and defer library restructuring. Today root `tarav run` already chooses current or Project configuration but requires `--file`/`--src`; two other run leaves expose overlapping UI. Root `run` should hand the exact post-separator argument vector to the existing `run_python` primitive. It should reject a missing separator or empty Python invocation rather than guessing whether a word is a Tarav option or script argument. A relative script path is interpreted from the runner's selected working directory, as Python normally does.
<!-- tarav.breadcrumb a6f6b104fb42728c3cf4a3198f4217f95a4101a59465d15795c306bdc5570b57 -->

The Project flag selects environment and cwd, not a specialized injected namespace. Scripts may import and use library operations directly. The existing typed Project bootstrap remains available as a library API and can be reconsidered separately.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant design: Project harness and Python runner contracts in `ARCHITECTURE.md`; relevant source: `src/tarav/l3/run.py`, `src/tarav/l3/project/commands.py`, `src/tarav/l1/python_env/commands.py`. Supporting discussion: current User Turns requesting `tarav run --project PATH -- ...`, removal of `project harness run`, CLI-only scope, and the Python-library-first interface. Exact Chatlas/Breadcrumb capture is pending.

## Execution.Plan

1. Check the shared worktree and make a scoped start evidence checkpoint before product edits.
2. Replace root `run` argument parsing with one explicit `--` boundary and forward its Python vector through the existing runner configuration. Remove only the duplicate CLI leaves; leave their library helpers intact.
3. Update Tarav CLI documentation and examples, plus directly affected md-library caller guidance, without changing Python library structure.
4. Verify current and Project selection, script/`-c`/`-m`/stdin forwarding, exact argument and exit-code propagation, and rejection of missing/empty separator. Run focused tests and CLI help checks; capture Product.Surface Breadcrumbs and Wiki context in the Hugentics workflow.

Acceptance: the two proposed command forms work; `project harness run` and `python run` are absent from help; setup commands and `python path` remain; no typed Project bootstrap library API changes.

## Impl.Log

- Design only so far. No product code or library structure changed.
- The Tarav worktree contains extensive concurrent unrelated changes; the declared work scope is limited to the CLI adapters, focused tests, directly affected guidance, and this request.
