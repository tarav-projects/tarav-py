# Selective context navigation

## Impl.Abstract

Autonomous Develop, impact input: recent agent-directed context discussion.
Default context output lists entries without target bodies. Agents select
an entry to preview or read; paths and pointers allow native tooling too.
Dependency checking remains independent of presentation and retains existing
fingerprint contracts. No reference repair or automatic recursive expansion.

## Impl.Req.Diagram

Model: b7b78eab-e5c2-4610-9bf5-1b704a106f34.
Namespace: 1c99092c-ba46-4006-adc3-9ada50c00abd.
Draft: 0cd1a3cf-bd19-4158-af4a-60d798f6d52b.
Collection: 8ecb1479-ad32-4970-8d95-c1ba6ec69a55.
Gate: 87550a7c-3ccb-4588-b083-3d41ad3e6c01.
Draft applied; receipt commit: 0b6c3b58061a62aa10799447397d02b7cc8deec4.
Support: User Turns 04b91894a22b75d0, 6be996c821a77156,
1e6e002c3e5aea1d in session 5626cd5f.

## Execution.Plan

- Separate address inspection from payload resolution in structured references.
- Provide compact context listings and explicit selected head/tail/cat reads.
- Preserve private full resolution for checks; prepare returns compact listings.
- Test read isolation, bounds, errors, stale checks, and real Hugentics output.
- Update docs, reinstall CLI, and close capture with remaining POIs explicit.

## Impl.Log

Checkpoint: 221a16a. Source schema and lock fingerprints need no migration.
Navigation uses zero-based context indices, matching JSON array positions.
Listings use stat/address inspection only; pointer/check validation occurs on
explicit reads or lint. Previews bound lines and characters; cat is explicit
full content. Context dependencies are not recursively expanded.

Status: implemented and verified. 35 focused tests passed, followed by 4
navigation tests including CLI dispatch. Ruff/diff checks passed. Installed
CLI head/tail smoke passed. Routing listing ~4 KB versus prior ~109 KB.
Existing Hugentics locks lint clean; no source or baseline migration.
Capture POIs remain: missing assertion scores, archive grounding unassessable,
Model staleness, and overlay lifecycle/type findings. Product-context
annotations are not supplied; code/tests and this note retain verification.
