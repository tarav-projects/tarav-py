# 850 — Unified Tarav Python run CLI

<!-- tarav.sessions
1ae20f8c = codex:01a0ff32-0ec2-7b72-8850-fa795135f3c9 @1ae20f8c8159f12d2402ea702cf49c876ec46a72f71ce12423ae1dbdf2a91871
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: Implemented and verified. Phase: Develop.

Make `tarav run [--project [PATH]] -- <python arguments>` the single user-facing Python runner. The separator assigns all following words to Python, including `script.py`, `-c`, `-m`, `-`, and their arguments. Without `--project`, use Tarav's current interpreter even inside a Project. Bare `--project` discovers the nearest Project from the current directory upward and errors if none exists; `--project PATH` starts discovery at PATH. A selected Project supplies its configured interpreter and working directory. Remove the `tarav project harness run` and `tarav python run` CLI leaves. Keep `tarav project harness` setup/inspection commands and `tarav python path`.
<!-- tarav.breadcrumb 40f0c902aa01 -->
<!-- tarav.breadcrumb 7b2eee03f681 -->

This is a CLI composition change. Preserve the existing runner, Project configuration, and trusted typed-Project bootstrap library APIs. Do not add implicit `project` or `runtime` globals to the general runner, change Project records, or alter environment installation.

## Design narrative

The user chose a single short command with `--` separating Tarav options from the Python invocation, then explicitly asked to remove `project harness run` and defer library restructuring. Today root `tarav run` already chooses current or Project configuration but requires `--file`/`--src`; two other run leaves expose overlapping UI. Root `run` should hand the exact post-separator argument vector to the existing `run_python` primitive. It should reject a missing separator or empty Python invocation rather than guessing whether a word is a Tarav option or script argument. A relative script path is interpreted from the runner's selected working directory, as Python normally does.
<!-- tarav.breadcrumb a6f6b104fb42 -->

The Project flag selects environment and cwd, not a specialized injected namespace. Scripts may import and use library operations directly. The existing typed Project bootstrap remains available as a library API and can be reconsidered separately.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant design: Project harness and Python runner contracts in `ARCHITECTURE.md`; relevant source: `src/tarav/l3/run.py`, `src/tarav/l3/project/commands.py`, `src/tarav/l1/python_env/commands.py`. Supporting discussion: current User Turns requesting `tarav run --project PATH -- ...`, removal of `project harness run`, CLI-only scope, and the Python-library-first interface. Exact Chatlas/Breadcrumb capture is attached in this request and the implemented surfaces.

## Execution.Plan

1. Check the shared worktree and make a scoped start evidence checkpoint before product edits.
2. Replace root `run` argument parsing with one explicit `--` boundary and forward its Python vector through the existing runner configuration. Remove only the duplicate CLI leaves; leave their library helpers intact.
3. Update Tarav CLI documentation and examples, plus directly affected md-library caller guidance, without changing Python library structure.
4. Verify current and Project selection, bare `--project` upward discovery and missing-Project error, script/`-c`/`-m`/stdin forwarding, exact argument and exit-code propagation, and rejection of missing/empty separator. Run focused tests and CLI help checks; capture Product.Surface Breadcrumbs and Wiki context in the Hugentics workflow.

Acceptance: the command forms work; `project harness run` and `python run` are absent from help; setup commands and `python path` remain; no typed Project bootstrap library API changes.

## Impl.Log

- Scoped start evidence checkpoint: `2d76220f7a3e0e5852b0069533249712a7e33bfc`. Concurrent unrelated work remains outside the declared scope.
- Root `run` forwards post-`--` Python arguments through the existing runner; duplicate CLI leaves are removed. The trusted library bootstrap and Project Records were not changed. A bare `--project` uses existing upward discovery; no flag selects the installed Tarav interpreter.
- Installed CLI checks covered script, `-c`, `-m`, stdin heredoc, explicit Project, parent Project discovery, global execution within a Project, missing Project, error handling, and removed leaves. `uv run pytest -q tests/cli/test_run_unified.py tests/test_architecture.py` passed 46 tests; Ruff and diff checks passed. The md-library transcript example ran cleanly through `tarav run --project . -- examples/check_transcript.py ...`.
- Product.Surface Breadcrumbs were submitted for every edited Tarav code, test, and guidance surface and audited clean after refreshing shifted older file positions. Tarav Wiki capture is in `notes/wiki/daily/2026-10-03.md` and `notes/wiki/tarav-harness.md`, committed as `be7bad5a8897a3579f24c32a9dcbd57f8818a43c`; commit-message audit passed. Md-library caller guidance is tracked separately in request 592.
