# 802 — Tarav Breadcrumbs — implementation request

<!-- tarav.sessions
3dbc7074 = codex:01a0baed-f147-77e2-b298-ed15249a9410 @3dbc7074117a70b90f57c98b25690d3ea15a519f0da6e05043e59b8add00d3c4
-->

## Impl.Abstract

- **Status:** Ready for execution.
- **Alignment.Mode:** Interactive.
- **Objective:** implement `Tarav.Breadcrumbs` as opaque in-surface attachment points backed by typed directory records, append-only locator observations, and workflow-owned attachments; provide the first Chatlas-context submission path for Markdown and Python surfaces.
- **Starting state:** the RecordInterface and Diagram object migration in request 801 is complete and supplies the typed-object, DirectoryRecord, Reference, registry, and surface-normalization foundations.
- **Boundary:** a Breadcrumb owns stable anchor identity and position observations. It neither interprets nor indexes attachment semantics. The first attachment workflow owns Chatlas context records and provisional-marker parsing.
- **Storage:** default to `~/Documents/tarav/breadcrumbs/records/<breadcrumb-id>/`, with an explicit root override for tests and alternate workflows.
- **Identity:** generate opaque random 256-bit lowercase hexadecimal Breadcrumb IDs. The canonical core label is `tarav.breadcrumb <id>`; surface adapters own comment syntax.

The invocation authorizes design and execution of this bounded implementation.
<!-- tarav.context 3dbc7074:0de05dfc6f56ecd9 -->

## Impl.Req.Diagram

- **Namespace:** `User.Touched.Chatlas.Index` — `1c99092c-ba46-4006-adc3-9ada50c00abd`
- **Project Model:** `Tarav` — `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- **Grounded View:** existing focused `Tarav.Record` View `7674a926-b123-4dc1-8f55-4be1d6c8624b`; a fresh bootstrap exposed a retryable incomplete-View POI and was cleaned without retained mutation
- **Semantic Block:** new `Tarav.Breadcrumbs` — `9811eb15-08d0-4f43-86d9-9262cc0ea490`
- **Impl.Req.Collection:** `802.Impl.Req` — `3eaf5aa8-4664-4713-8f30-070955b4f70a` (`Open`)
- **Diagram.Draft:** `d58c4824-0d36-42dd-b1e6-cf0fb569ea03` — `/Users/pereiro/Documents/tarav/diagram/drafts/d58c4824-0d36-42dd-b1e6-cf0fb569ea03.json`
- **Capture.Authorization.Gate:** `ed646723-fe37-4dae-8d90-ec6f56b4f300`

## Execution.Plan

### Slice 1 — Position Reference and Breadcrumb records

- Add `FilePositionReference` with a one-based line locator whose file value accepts either a path string or `FileReference.RecordInterface`.
- Add typed Breadcrumb, locator-observation, and Chatlas-context attachment records with exact JSON round trips.
- Keep neighborhood fragments under `hints`; Reference resolution and checks never use them as fallback locators.
- **Observable:** registered classes validate the cheap and rich file representations and resolve an exact file line.
- **Check:** focused Reference and Breadcrumb record tests.
- **Status:** Not started.

### Slice 2 — Directory-backed Breadcrumb store

- Create, load, and resolve `records/<id>/main.json` directories.
- Append typed observations to `locator-observations.jsonl` and store arbitrary independently typed attachment JSON under `attachments/`.
- Resolve a Breadcrumb position only when a recorded file and line contains its exact canonical label; missing and duplicated active positions produce POIs without hint-based repair.
- **Observable:** a temporary store persists one Breadcrumb, retains observation history and attachment records, and resolves its surface occurrence.
- **Check:** storage and resolution tests using temporary roots and surfaces.
- **Status:** Not started.

### Slice 3 — Chatlas context surface submission

- Add the first named Breadcrumb surface workflow for provisional `tarav.context <session-alias>:<turn-prefix>` markers.
- Parse active Markdown comments and Python comments, resolve selected User Turns through Chatlas, create durable Breadcrumb records before rewriting surfaces, attach typed Chatlas context records, and emit surface-native canonical labels.
- Keep submission bounded to explicitly selected files. Existing surfaces are migrated only when submitted.
- **Observable:** one Markdown and one Python fixture complete provisional marker → durable records → opaque label → exact resolution.
- **Check:** focused workflow tests with a controlled Chatlas resolver.
- **Status:** Not started.

### Slice 4 — CLI, workflow guidance, and closure

- Register `tarav breadcrumbs submit`, `resolve`, and `show` commands with explicit surface, session, and store-root inputs.
- Update the maintained Hugentics Wiki and implementation-capture source guidance to submit explicit provisional markers through Breadcrumbs, then rebuild and check the skill products.
- Run focused tests, Ruff, architecture checks, the complete suite, reinstall the editable CLI, and smoke the new commands.
- Reconcile the durable Draft, close `802.Impl.Req`, check and apply the Draft once, and retain its Capture.Receipt.
- **Observable:** the public CLI performs the first end-to-end workflow and the maintained skills route future Wiki/implementation annotations through it.
- **Check:** CLI vertical tests, skill lint/build checks, full project validation.
- **Status:** Not started.

## Risks and deviation triggers

- If one stored attachment needs Breadcrumb-owned semantics, stop and keep it workflow-owned rather than growing the core record implicitly.
- If nested `FileReference` resolution requires a general recursive-reference framework, implement only the explicit `FileReference` union selected by the design and defer generalization.
- If surface rewriting cannot ensure durable-record-first behavior, retain the provisional marker and report the failure instead of deleting capture input.
- If a native parser cannot distinguish active comments from strings or fenced examples, stop that adapter rather than using an unsafe text-wide replacement.
- Existing Diagram assertion, Archive-grounding, Model-staleness, and View-performance POIs do not block product mutation.

## Acceptance signals

- Breadcrumb identity is stable, opaque, and present on both surface and record sides.
- `main.json` contains stable identity only; location changes append typed observations.
- Workflows can add independent typed attachments without changing Breadcrumb semantics.
- File-position locator mechanics use file and line; neighborhood fragments remain non-mechanical hints.
- Top-level records are typed while nested file representation remains application-owned and accepts either selected form.
- Markdown and Python context submissions preserve provisional input until durable records exist and leave canonical opaque labels.
- Focused checks, Ruff, architecture validation, skill checks, and the complete suite pass.

## Impl.Log

- The current Model has no `Tarav.Breadcrumbs` Block; the Draft introduces one rather than attaching the complete primitive and workflow semantics dishonestly to `Tarav.Record`.
- A fresh Session View bootstrap created an incomplete untracked View directory and failed before `view.json`; the exact generated directory was removed and the View repository returned clean. Existing focused View `7674a926-b123-4dc1-8f55-4be1d6c8624b` remains the grounded context. This is a retryable Diagram.View POI.
- The completed request 801 worktree is the baseline and will be included in Execute's mandatory checkpoint before Breadcrumb product edits.

