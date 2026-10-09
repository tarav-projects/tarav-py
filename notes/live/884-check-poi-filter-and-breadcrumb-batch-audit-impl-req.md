# 884 — Check POI filtering and batch Breadcrumb audits — Impl.Req

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: ready. Phase: Design complete.

Improve two general Tarav CLI primitives: filter a Project check report by POI Type including subtypes, and audit or refresh Breadcrumb positions for a declared set of files in one invocation. These are independent conveniences for existing workflows; no implementation-specific checkpoint command is introduced.
<!-- tarav.breadcrumb 8517f1975c0259313635bd92d7d282feb5cdea15e764eace5203419a21c3da95 -->
<!-- tarav.breadcrumb 459e47ac0ac22a5c1cb4d9b787900219cabc5e49f18444eef1f133bc0ac233c7 -->

## Design narrative

The User found repeated broad check reports noisy and repeated per-file Breadcrumb audits costly. Following relevant User Turns still requires judgment; mechanically applying the same audit to a known file list does not. The User explicitly rejected a combined `tarav impl checkpoint` as overfitted.
<!-- tarav.breadcrumb 089081a819cc89da8e6a7559c6a2888a71a81b6add473cde0d1ce28579a81f1c -->

Current `tarav check --type NAME` filters only exact emitted Type names. `CheckRun.report()` groups after filtering but keeps the full run summary, while the text renderer does not state the selected POI count. `--check` also filters reported POIs by exact Check Type name; it does not narrow which checks run. The CLI retains and tracks the whole run and exits according to `run.clean()`.

Extend `--type` to match the named POI Type or any subtype, based on the emitted object's Python Type ancestry and Tarav Type names. Preserve full-run summary, retention, tracking and exit behavior. Add a selected-POI count and an explicit “showing X of Y POIs” line when report filters are active; JSON must expose the same counts and applied filters. Group limit/offset remain pagination over matching groups. Path/project filtering and baseline comparisons are deferred.
<!-- tarav.breadcrumb 9d811918c53293dee85c9df4726caf6bbb5b36d9c6c6c061f3e36dd91f3b2efc -->

Current `tarav breadcrumbs audit chatlas-context --surface FILE [--refresh-positions]` audits one file. The generic Breadcrumb audit command owns file auditing; the Chatlas Context command also dispatches commit audits. Add a repeatable `--surface` and `--files-from MANIFEST` to file audits. A manifest is plain UTF-8, one path per line; blank lines are ignored and relative paths resolve from the command's working directory, matching `--surface` and the output of `git diff --name-only`. Combine and deduplicate paths in input order. Reject an empty selection and prohibit file-selection options with `--commit`. Run each file through the existing audit, continue after one file fails, and return per-file JSON results and an aggregate status. `--refresh-positions` applies independently to each selected file; it still never edits source files. Preserve the current single-file JSON response when exactly one `--surface` is used without a manifest. These format and path choices are Agent implementation decisions.
<!-- tarav.breadcrumb ecdaa8248522da04ba9c4b2a01672421ecea10f1d98299ab938219661aafb193 -->

## Impl.Req.Wiki

Product Project: `tarav-py/`. Wiki owner: `tarav-md/notes/wiki/`, principally `poi-system.md` and its daily note. Supporting User Turns: `fed80248f6c70da5` and `362e396c72e1c369` in the declared Codex session. Capture status: pending.

## Execution.Plan

1. Cold-read this request, project instructions, and the relevant Check and Breadcrumb commands. Preserve unrelated shared-worktree edits; use scoped evidence commits.
2. Extend `CheckRun.report()` and the existing check CLI renderer/help. Test Type ancestry, exact Type selection, mixed POIs, full totals, pagination, and unchanged exit/tracking semantics.
3. Add batch file selection to the generic Breadcrumb audit command and route it through the Chatlas Context dispatcher without affecting commit audits. Test repeated surfaces, manifest paths, duplicates, missing files, refresh, and JSON/text results.
4. Run focused tests, Ruff, and proportionate Project checks. Capture User-Turn Breadcrumbs on implemented surfaces, audit them, and record any gaps. Capture the supported outcome in the Wiki and daily note; close with scoped commits in each affected repository.

## Impl.Log

- 2026-10-08, Design. Confirmed `tarav check --type` exists but matches exact emitted names; `CheckRun.report()` and the Check renderer are the needed boundary. Confirmed Breadcrumb `--surface` is singular and the generic audit command can be reused for each selected file. The `l3/check.py` file has a concurrent unrelated Project-index change in the shared checkout; do not absorb it into this request's commits.
