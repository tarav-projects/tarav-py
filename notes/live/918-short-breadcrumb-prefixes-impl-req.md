# Short Breadcrumb prefixes — implementation request

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Status: in execution (Develop, Interactive), 2026-10-18.
Knowledge.Surface: wiki.

Make Breadcrumb markers on product surfaces default to 12 hexadecimal characters while retaining full 64-character IDs in the registry. Support longer prefixes when a collision requires them. This request records the design for later execution.
<!-- tarav.breadcrumb bb6cbe68ee4249ed84b93ff89c238503709c4ac393dd1146d3181c252dc99f53 -->
<!-- tarav.breadcrumb bd1b6b025809dd56d6a276a01bee9232c8acfb96bc2dabcdfddf7dfcf05724d1 -->

## Design

Full hashes obscure the surrounding text without improving routine navigation. The surface should carry a prefix of the existing identity, not a new identity. Keep full registry IDs, attachment identities, and stored observation identities unchanged. Existing full-length markers remain valid.

Resolve a supplied prefix against the selected Breadcrumb registry:

- One match: resolve to that full ID.
- No matches: report an unresolved reference.
- Multiple matches: raise an ambiguity error and show the colliding full IDs.

Never choose a candidate using surface location, attachments, hints, or other contextual metadata. Such data may help an agent or user investigate, but the system must only report the collision. No automatic disambiguation or marker repair.
<!-- tarav.breadcrumb c1e4e622c2d1f958c5edd0111669b44549c2b399f5bff906a8f37c2b948651f5 -->

After explicitly selecting the intended Breadcrumb, an agent or user extends its prefix one character at a time—13, 14, 15, and so on—until unique. Use 12 characters by default. Submission must not write a marker known to be ambiguous; report the collision rather than silently extending it. Resolution and audit must also detect a formerly unique prefix made ambiguous by a later registry addition.
<!-- tarav.breadcrumb a6a17793816d8c95d3b167c2b4690add7939db409957248c5ce85292b8489b28 -->
<!-- tarav.breadcrumb b1e8672728c9b82b37340fe05b9ad2345c6be688bc0705c0900bd6be9ad3491e -->

Do not shorten registry identities or Chatlas session/Turn references. These are implementation boundaries, not changes to those identity contracts.

### Review decisions, 2026-10-18

The draft excluded a bulk rewrite of existing surfaces. In the review session the User confirmed the design (12 characters on surfaces, full IDs in the registry; a prefix matching several IDs raises an error listing them) and that "no automatic disambiguation" concerns markers already registered. Tarav, not the Agent, writes `tarav.breadcrumb` markers at submission.
<!-- tarav.breadcrumb 18e1b0121ae54694decb58f6034efc0fe1cf6e42f8b51bcf1f5c486362c0587a -->

An alternative was proposed and declined: drawing a new random ID whenever its first 12 characters are taken, so that 12-character prefixes stay unique by construction. The chance of a collision is low (about 1 in 17 million at today's 5,736 Breadcrumbs) and its effect narrow, so the system stays simple: submission reports a collision as the draft says.
<!-- tarav.breadcrumb 38383b84b4815b82d4f09094b2b6ffa268ea2957e0a092357ae7adb998ec9da6 -->

This request now also migrates every full-length marker found on surfaces to its 12-character prefix, superseding the draft's exclusion.
<!-- tarav.breadcrumb 053d3fd180d868f726a349d97a66d0ded539c00b63b58ab53377d10870fdbdca -->

Scope of that migration: all 29 places that carry markers, inside and outside the workspace, each Git repository with a start checkpoint of the work found there and a migration commit.
<!-- tarav.breadcrumb f73c62384c7b981f925a0b3df970b413079bb1230085df7fba008953ae0f994f -->

Found while reviewing (an Agent observation, not a User decision): resolution checks that the observed line *contains* `tarav.breadcrumb <full id>`, for files (`BreadcrumbStore.resolve`) and commit messages (`_resolve_commit_label`, and the check `observe_commit_position` stores). A short marker never contains the full label, so these checks must look for the 12-character label, which every valid marker of that Breadcrumb contains.

## Current implementation observations

Inspected on 2026-10-18:

- `src/tarav/l1/breadcrumbs/model.py`: `BreadcrumbId` requires 64 lowercase hexadecimal characters; retain that internal identity contract.
- `src/tarav/l1/breadcrumbs/store.py`: `breadcrumb_label`, `parse_breadcrumb_label`, and `BreadcrumbStore.load` currently assume full IDs. Store lookup uses the full ID as a directory name.
- `src/tarav/l1/breadcrumbs/auditing.py`: marker recognition currently requires 64 characters.
- Inspect consumers in `surfaces.py`, `commands.py`, `integrations.py`, `src/tarav/l2/breadcrumb_workflows/chatlas_context/`, and `src/tarav/l2/git/breadcrumbs.py` during execution. These are integration targets, not claims that every file needs an edit.
- Existing focused tests include `tests/breadcrumbs/test_audit_command.py` and `tests/breadcrumbs/test_typescript_surface.py`.
- `BreadcrumbStore.resolve` overrides each observation's check with `contains: tarav.breadcrumb <full id>`; `l2/git/breadcrumbs.py` does the same in `_resolve_commit_label`.
- Commit messages carry a `tarav.commit-evidence` envelope listing full IDs; `_breadcrumb_lines` matches message labels to those IDs by equality. The envelope keeps full IDs; labels must match an envelope ID by prefix.
- The Chatlas-context audit compares each attachment's `breadcrumb_id` with the audited label's ID (`workflow.py`), so audits must carry the resolved full ID, not the prefix.
- Registry (2026-10-18): 5,736 Breadcrumbs, records as one directory per full ID, no two sharing 12 characters. Surfaces: 4,279 full labels in 620 files across 29 places, all registered; 117 of them in `.skw.json` sources whose products are compiled.

## Impl.Req.Wiki

Product: `tarav-py`. Documentation owner: `tarav-md/notes/wiki/`.
The exact supporting User Turns are attached above; this note is self-contained.
This handoff is limited to the requested live note. Wiki capture and skill-guide changes are deferred to implementation; no Wiki files or commits are part of this task.

The implementation must update the full-length-only instructions in
`tarav-md/skills/tarav-hugentics/references/inline-capture.md` through their authoritative SKW source, with a linked documentation request if following the multi-repository execution workflow.

## Execution.Plan

Data shape: retain full `BreadcrumbId`; distinguish a surface prefix (12–64 lowercase hexadecimal characters) from a resolved registry ID. Centralize unique-prefix resolution at the registry boundary. Remove full-ID-only assumptions from surface parsers, not from retained identity validation.

- `store.py`: `LABEL_PREFIX = 12`; `parse_breadcrumb_label` returns a prefix; `BreadcrumbStore.find(prefix)` returns the one full ID or raises `BreadcrumbNotFound` / `BreadcrumbAmbiguous` (the latter carrying the candidates); `load` and everything built on it accept prefixes; `BreadcrumbStore.label(id)` renders `tarav.breadcrumb <id[:12]>` and raises `BreadcrumbAmbiguous` when that prefix is not unique. Resolution checks contain the 12-character label.
- Surfaces and commit messages carry what `label(id)` renders; audits resolve each label to its full ID once.

1. **Feature — prefix lookup.** Done. Implement unique/missing/ambiguous resolution and explicit candidate diagnostics. Verify controlled IDs sharing 12 characters, including cases needing 13 and 14 characters, plus full-ID lookup. Ensure metadata cannot select a candidate.
2. **Feature — surface integration.** Done. Default newly emitted labels to 12 characters and route CLI, submission, audit, commit messages and position lookup through the shared resolution rule. Cover Markdown, Python, and TypeScript native conventions, existing full labels, and a later registry addition causing ambiguity (a new audit POI naming the colliding IDs). Verify collision failure leaves existing markers untouched and does not leave a partially replaced surface.
3. **Documentation — usage contract.** Update maintained instructions and examples through SKW sources. Explain explicit extension after collision and preserve full-label support. Compile affected packages and verify real submission → resolution → audit with an isolated registry.
4. **Migration — existing markers.** In each of the 29 places: start checkpoint, rewrite every registered full label to its 12-character prefix (`.skw.json` sources together with their products, then recompile and verify the products unchanged by compilation), audit a sample of surfaces, commit. Check: no full label remains outside commit messages and fixtures; audits of migrated surfaces resolve as before.

All slices pending. Run the focused Breadcrumb tests first (`uv run pytest tests/breadcrumbs`), then affected Chatlas-context and Git integration tests discovered during execution. Use deterministic synthetic collisions; do not search for accidental real collisions. Recheck current code before editing and surface any design mismatch rather than silently adapting the contract.

## Impl.Log

- 2026-10-18: Drafted the implementation request from the User's short-prefix proposal, explicit no-disambiguation decision, and request for this live note. Product implementation is pending.
- Breadcrumb submission and audit passed: five registered labels, five resolved, no POIs. This note uses the current full-length marker format until the requested implementation exists.
- 2026-10-18 (claude-code `abd0372d`): Develop started from the review decisions above. Start checkpoints: tarav-py `0794820` (this note and work found uncommitted), tarav-md `9ab40be` (Constitution and skill edits found uncommitted). The other repositories get theirs in slice 4.
- Slice 1 (prefix lookup): `BreadcrumbStore.find`, `label`, `BreadcrumbNotFound`, `BreadcrumbAmbiguous` (carrying `prefix` and sorted `candidates`); `load` and everything built on it take prefixes; resolution checks contain the 12-character label. `tests/breadcrumbs/test_prefixes.py` (6 tests, added to testpaths) failed at import before the change and passes after; it covers prefixes needing 13 and 14 characters, a later addition, and retained observations and attachments not selecting a candidate. `uv run pytest tests/breadcrumbs`: 21 passed; ruff clean. Breadcrumbs on `store.py` (2) and the test (1); audits ok. Submission still writes full labels until slice 2.
- Slice 2 (surface integration): submission settles every label through `BreadcrumbStore.label` before observing or writing, so a collision raises `BreadcrumbAmbiguous` with the surface and the new Breadcrumbs' positions untouched. Audits read 12–64 character labels, resolve each to its full ID once (`find_label`), and raise the new `Tarav.Breadcrumbs.Audit.POI.LabelAmbiguous` naming the colliding IDs. Commit messages carry `store.label` output; `_label_lines` maps each message label to exactly one envelope ID by prefix (the envelope keeps full IDs); the commit-message check contains the 12-character label. `tests/breadcrumbs/test_short_labels.py` (7 tests): 6 failed before (full labels written, no ambiguity POI) and the full-label case passed; all pass after. Full suite: 330 passed; ruff clean. Real CLI with an isolated registry: submit wrote `tarav.breadcrumb 51335b338b37`, audit resolved it, `show`/`resolve` took the prefix, and after adding a colliding directory `show` failed naming both IDs. Breadcrumbs: `surfaces.py` (1), `auditing.py` (1), the test (2); audits of the touched modules ok after refreshing moved positions. `l2/git/breadcrumbs.py` carries no new Breadcrumb: the commit-message check was an Agent finding, not a User Turn.
