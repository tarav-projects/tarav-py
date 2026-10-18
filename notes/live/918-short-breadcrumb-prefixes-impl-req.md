# Short Breadcrumb prefixes — implementation request

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->

## Impl.Abstract

Status: ready for implementation; no product code changed.
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

Do not bulk-rewrite existing surfaces as part of this request. Do not shorten registry identities or Chatlas session/Turn references. These are implementation boundaries, not changes to those identity contracts.

## Current implementation observations

Inspected on 2026-10-18:

- `src/tarav/l1/breadcrumbs/model.py`: `BreadcrumbId` requires 64 lowercase hexadecimal characters; retain that internal identity contract.
- `src/tarav/l1/breadcrumbs/store.py`: `breadcrumb_label`, `parse_breadcrumb_label`, and `BreadcrumbStore.load` currently assume full IDs. Store lookup uses the full ID as a directory name.
- `src/tarav/l1/breadcrumbs/auditing.py`: marker recognition currently requires 64 characters.
- Inspect consumers in `surfaces.py`, `commands.py`, `integrations.py`, `src/tarav/l2/breadcrumb_workflows/chatlas_context/`, and `src/tarav/l2/git/breadcrumbs.py` during execution. These are integration targets, not claims that every file needs an edit.
- Existing focused tests include `tests/breadcrumbs/test_audit_command.py` and `tests/breadcrumbs/test_typescript_surface.py`.

## Impl.Req.Wiki

Product: `tarav-py`. Documentation owner: `tarav-md/notes/wiki/`.
The exact supporting User Turns are attached above; this note is self-contained.
This handoff is limited to the requested live note. Wiki capture and skill-guide changes are deferred to implementation; no Wiki files or commits are part of this task.

The implementation must update the full-length-only instructions in
`tarav-md/skills/tarav-hugentics/references/inline-capture.md` through their authoritative SKW source, with a linked documentation request if following the multi-repository execution workflow.

## Execution.Plan

Data shape: retain full `BreadcrumbId`; distinguish a surface prefix (12–64 lowercase hexadecimal characters) from a resolved registry ID. Centralize unique-prefix resolution at the registry boundary. Remove full-ID-only assumptions from surface parsers, not from retained identity validation.

1. **Feature — prefix lookup.** Implement unique/missing/ambiguous resolution and explicit candidate diagnostics. Verify controlled IDs sharing 12 characters, including cases needing 13 and 14 characters, plus full-ID lookup. Ensure metadata cannot select a candidate.
2. **Feature — surface integration.** Default newly emitted labels to 12 characters and route CLI, submission, audit, and position lookup through the shared resolution rule. Cover Markdown, Python, and TypeScript native conventions, existing full labels, and a later registry addition causing ambiguity. Verify collision failure leaves existing markers untouched and does not leave a partially replaced surface.
3. **Documentation — usage contract.** Update maintained instructions and examples through SKW sources. Explain explicit extension after collision and preserve full-label support. Compile affected packages and verify real submission → resolution → audit with an isolated registry.

All slices pending. Run the focused Breadcrumb tests first (`uv run pytest tests/breadcrumbs`), then affected Chatlas-context and Git integration tests discovered during execution. Use deterministic synthetic collisions; do not search for accidental real collisions. Recheck current code before editing and surface any design mismatch rather than silently adapting the contract.

## Impl.Log

- 2026-10-18: Drafted the implementation request from the User's short-prefix proposal, explicit no-disambiguation decision, and request for this live note. Product implementation is pending.
- Breadcrumb submission and audit passed: five registered labels, five resolved, no POIs. This note uses the current full-length marker format until the requested implementation exists.
