# Lines / Unsorted extraction

## Checkpoint

Prior implementation preserved in commit `3af8a2c`.

## Execution plan

- [x] Allocate distinct new workflow and class identities for Lines and Unsorted.
- [x] Retire DiagramWorkflow registration without redirecting its name or Ship.
- [x] Assign Lines Record ownership explicitly; preserve all existing Type Ships.
- [x] Assign remaining legacy TaravObject classes provisionally to Unsorted,
  including Draft and View types that previously inherited Kernel ownership.
- [x] Physically extract Lines and relocate unresolved mechanics to Unsorted.
- [x] Inspect retained class ownership and inventory unknowns; no migration was
  required because no retained `Tarav.Class` records or retired workflow
  references were present in the 5,755 Archive/Diagram JSON files inspected.
- [x] Complete full-suite verification and installed CLI verification.

Ownership-slice checks: 264 Diagram, Kernel, and architecture tests passed;
Ruff and diff whitespace checks passed.

Physical-extraction verification: full suite 1298 passed; the subsequently
added import-order and no-compatibility-export checks passed (8 workflow-split
tests total). Architecture checks including relative module imports passed
(24 tests). Ruff passed. Reinstalled the editable CLI and verified version,
root help, and `tarav diagram --help`.

## Dependency findings

The legacy module has a mutual dependency group across roughly 70 definitions
(including annotation-only references): concrete Lines Records, namespace
storage, projection, capture, evidence, and assertion assessment. A file move
alone cannot establish an acyclic package boundary. Separate Record foundations
and reference contracts before higher-level projection and capture composition.
Do not replace that work with wildcard exports, mutable namespace injection,
or redirects of the retired workflow identity.

Domain implementations now live in `tarav.lines` and `tarav.unsorted` modules.
The mixed CLI adapters also live in `tarav.unsorted`; the `tarav.diagram`
Python package is removed. Callers use explicit owning modules;
there are no compatibility re-exports. Existing concrete class names, CLI
spelling, and storage labels remain unchanged.
No retained user data has been rewritten. Old ownership references remain
inspectable as Ships but do not resolve to either successor automatically.

## Capture

## Retained-data migration

The Archive and Diagram depots were scanned mechanically. All 5,755 JSON files
were readable. No record contained `type: Tarav.Class`, `python_class`, or the
retired Diagram workflow Ship. Historical mentions of old Python paths remain
inside Chatlas evidence and were not rewritten; they are evidence, not current
class records. Therefore identity-preserving migration was a deliberate no-op.

## Capture reconciliation

Draft `4c35ed1e-133b-4d22-8596-ed0a60a5b914` was checked and applied to the
Project Model. It added one `LinesWorkflow` decision Line and one
`UnsortedWorkflow` decision Line under the new block
`2b9d50d4-38e5-4e15-9cb4-0a4496c89f3c`. The capture receipt committed Diagram
changes as `caf59454702f65726292d7594a530a91ec561ce9`; existing Diagram POIs
remain surfaced (413 findings during checking) and were not repaired by this
capture.
