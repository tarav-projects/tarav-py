# 866 — Project capability paths — Impl.Req

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: Complete. Phase: Develop (Execute).

Make Project capabilities readable as `project.docs.wiki.daily(date)`, `project.models.ls()`, and `project.checks.run()`. Migrate maintained callers and declarations so these are actual paths, not examples beside the old method API.
<!-- tarav.breadcrumb b82908d4b73c1eea771d28f975b7058003e01cce5326ac865b6e3421b921edc1 -->

## Design narrative

The User wants top-level objects to carry concrete meaning while abstract or shared capabilities sit under semantic namespaces. `docs` is the Project documentation namespace; `models` is its own bound capability and should be accessed as an attribute; `checks` is a shared namespace on `CheckProvider`, not a Project-only method. The suite remains constructible without running, and `checks.run()` performs execution.
<!-- tarav.breadcrumb 3fc92308fc3e7f3a55165015e7c9d497302efd577936e4343fcb6af1536563db -->
<!-- tarav.breadcrumb 343d75f062f5db6a0407eb3efff114b6e57ded1d79c8b59aa77fc5e1b6e7caa7 -->

Current code has `Project.models()` returning `ProjectModels`, `Project.wiki()` returning `Wiki`, and `CheckProvider.checks()` returning a `CheckSuite`. Concrete providers override that method. The CLI, tests, and documentation use the old calls. Design: expose a bound `Project.Docs` view with a `wiki` property, expose `ProjectModels` at `project.models`, and put `suite()` plus `run()` on `CheckProvider.Checks`. Providers specialize `Checks.suite()` and callers use `checks.suite()` or `checks.run()` as appropriate. There is no automatic suite merger; a composed provider defines it explicitly.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`; topical `projects.md` and `checks-workflow.md`, daily `2026-10-07.md`. Supporting session: `codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8`. New User-Turn Breadcrumbs submitted; commit attachment audits passed. Topical surface audits timed out on older dense Notes.

## Execution.Plan

1. Add the Project docs and models paths; update maintained Project users.
2. Move the CheckProvider declaration into a bound Checks namespace and update concrete providers and consumers.
3. Verify explicit path behavior, check suite composition, CLI execution, and import boundaries; update architecture documentation.
4. Capture product surface Breadcrumbs, commit only this request's hunks, and complete Wiki capture. A companion documentation request in `tarav-md` owns skill source updates.

## Impl.Log

- Design inspection: current Project, ProjectModels, ProjectWiki, CheckProvider, concrete check providers, caller grep, and shared worktree status. Numerous unrelated edits exist, including overlapping Project and architecture files; preserve them.
- Design note capture: three User-Turn Breadcrumbs submitted; design commit `de47b65a1360a3fc46d6ba1134d1292d1049c299`.
- Execute start checkpoint `e79539db3be149d1537dddb0b813c5fa69fd622e` was empty and scoped to clean Project/Checks files.
- `Project` now exposes `docs.wiki` and `models` as bound attributes. `ProjectModels.ls()` reads marker names; `get()` and `main()` still gate on the disconnected Models backend. The path itself no longer raises at construction.
- `CheckProvider.Checks` supplies `suite()` and `run()`; concrete Project, Workspace, Command, and SKW skill providers declare their suites under that class. Maintained Python callers and the CLI were migrated. Explicit suite composition remains the responsibility of a composed provider.
- Verification: 46 focused migration tests and the full 178-test Python suite passed; the two new path tests passed after the final doc capture; Ruff on changed Python files passed. The installed CLI was refreshed with `uv tool install --reinstall --editable .`. Both modified Hugentics SKW documents compiled and linted with no findings.
- Product capture: new Breadcrumbs submitted in all 20 changed Python, test, and Markdown guidance surfaces. Full surface audits on files with many older labels were slow and not all completed; the scoped product commit audit resolved its two message Breadcrumbs without POIs. JSON SKW sources have no native Inlined Capture convention, so capture was placed in the authored Wiki and evidence commit rather than in JSON comments.
- Scoped product completion commit `811e9a485627f4100267b927cb6f83c575cf8ffa` includes only this request's hunks. Unrelated edits in `ARCHITECTURE.md`, Project Models/Root, SKW skills, architecture tests, and Workspace tests were restored and remain uncommitted in the worktree.
- Follow-up documentation correction `2d7d0222e253d1eb74f2cd90ff3608288ef372b5` fixes the Project import path in the Models README and labels backend-dependent calls as intended future resolution; its commit Breadcrumb was submitted.
- Companion `tarav-md` request `865` updated the Hugentics skill sources and captured the discussion in daily/Projects/Checks Wiki Notes. Skill commit `0d9691d9380ebd7cb1d9002162d4ca0b1ab8673a`; Wiki commit `e242b8146220fc87b789e223eaea3400799e4dcf`. Their commit Breadcrumb audits passed. Wiki daily surface audit passed; Projects and Checks topical surface audits timed out while scanning older labels.
