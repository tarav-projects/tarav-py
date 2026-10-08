# 866 — Project capability paths — Impl.Req

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: Ready. Phase: Develop.

Make Project capabilities readable as `project.docs.wiki.daily(date)`, `project.models.ls()`, and `project.checks.run()`. Migrate maintained callers and declarations so these are actual paths, not examples beside the old method API.
<!-- tarav.breadcrumb b82908d4b73c1eea771d28f975b7058003e01cce5326ac865b6e3421b921edc1 -->

## Design narrative

The User wants top-level objects to carry concrete meaning while abstract or shared capabilities sit under semantic namespaces. `docs` is the Project documentation namespace; `models` is its own bound capability and should be accessed as an attribute; `checks` is a shared namespace on `CheckProvider`, not a Project-only method. The suite remains constructible without running, and `checks.run()` performs execution.
<!-- tarav.breadcrumb 3fc92308fc3e7f3a55165015e7c9d497302efd577936e4343fcb6af1536563db -->
<!-- tarav.breadcrumb 343d75f062f5db6a0407eb3efff114b6e57ded1d79c8b59aa77fc5e1b6e7caa7 -->

Current code has `Project.models()` returning `ProjectModels`, `Project.wiki()` returning `Wiki`, and `CheckProvider.checks()` returning a `CheckSuite`. Concrete providers override that method. The CLI, tests, and documentation use the old calls. Design: expose a bound `Project.Docs` view with a `wiki` property, expose `ProjectModels` at `project.models`, and put `suite()` plus `run()` on `CheckProvider.Checks`. Providers specialize `Checks.suite()` and callers use `checks.suite()` or `checks.run()` as appropriate. There is no automatic suite merger; a composed provider defines it explicitly.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`; topical `projects.md` and possibly checks. Supporting session: `codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8`. Capture status: pending.

## Execution.Plan

1. Add the Project docs and models paths; update maintained Project users.
2. Move the CheckProvider declaration into a bound Checks namespace and update concrete providers and consumers.
3. Verify explicit path behavior, check suite composition, CLI execution, and import boundaries; update architecture documentation.
4. Capture product surface Breadcrumbs, commit only this request's hunks, and complete Wiki capture. A companion documentation request in `tarav-md` owns skill source updates.

## Impl.Log

- Design inspection: current Project, ProjectModels, ProjectWiki, CheckProvider, concrete check providers, caller grep, and shared worktree status. Numerous unrelated edits exist, including overlapping Project and architecture files; preserve them.
