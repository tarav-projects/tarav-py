# 877 — Atomic POI types — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: ready. Phase: Develop (Design).

Remove the `code` field from Tarav POIs and make POI types atomic. Today a POI carries a required `code`, a short label that distinguishes cases inside one POI type. After this request the type alone says which situation was found: every type that was raised with several codes is split into one class per case under a family parent that is never raised, the base types lose the argument, and reports stop grouping or filtering by code.

Non-goals:

- The three older finding classes that subclass the bare `POI` as dataclasses with their own `code` field: `BreadcrumbFinding` (`l1/breadcrumbs/store.py`), `ReferenceFinding` (`l1/references`) and the Diagram `Finding` (`l2/unsorted/contracts.py`, about ninety call sites in the disconnected Diagram code). They are not `IdentifiedPOI`s and do not pass through check reports. They are a follow-up.
- Guidance (`read_first`, `may_do`) for POI types other than the seven bootstrap families. Existing POIs stay as a test bench; nothing is repaired.
- Other repositories that use Tarav's POI API. They will fail on the removed argument and their maintainers handle it.

## Design narrative

### Why

While reading a reported POI through the new context command, the User met `code: "no-source"` and asked what the field is for.
<!-- tarav.breadcrumb 8f32b9c93fedf8868ecbcac86e00f2980d855704a73c857b853224fbd4e4e4b6 -->
<!-- tarav.breadcrumb 416dbd41e7e46cbe2422a0594c53599b66bc46dac7e0e291116acb0873c696b2 -->

The User asked for it to be eliminated and for a report on whether anything they had said justifies it.
<!-- tarav.breadcrumb db9e30bd2cf92be8f2f0a8e6086bc76283a8798ac91d62e36a0fb974c066a1df -->

The report found no such justification. The field began in the index linter (commit `c888d31`, 2026-05-22) as a linter-style rule label. Request 832 (commit `5a28361`, 2026-09-30) made it a required constructor argument of the neutral POI base without discussing it, and request 834 moved identity to "type plus situation" while leaving `code` outside identity. No User turn in the five sessions declared on `tarav-md/notes/wiki/poi-system.md` asks for a POI code. The nearest is turn `7b53cdbe73f54d75` in `codex:01a0d86c-9538-7be1-af96-014cd4203d61`, where the User confirmed that identity policy belongs to the kind of POI being modeled.

The User agreed that the field is an inherited linter habit duplicating the type system, and decided: POIs are atomic, each type describes one situation, and there is no further degeneracy inside a type.
<!-- tarav.breadcrumb f66f9f57f5bee2ab3cc470aa642d938f1367288b25fd0268fb6f251061f2f3d7 -->

A family parent class that is never raised itself may remain, so related cases belong to one family and can be selected together. In Tarav the typing system expresses semantics. The User approved the three parts of the change: the base type loses the argument and the record, retained report and context view lose the field; every type that uses several codes is split into one class per case, with checks no longer copying the code into the situation; and the report drops `--by code` and `--code` in favour of the existing type grouping.
<!-- tarav.breadcrumb 08ccea5d0c0327c6ef7ae4ee5e82267cf5a8f657af2c490ff838a33d2253e4f1 -->

### Inventory (inspected 2026-10-08)

Introspection of the loaded library finds 68 POI classes. 41 are Skillware classes in `l2/skw/pois.py`, which already have one class per finding kind through a kind-to-class table and only pass the kind along as `code`.

Classes raised with more than one code, and therefore split:

| Family (kept as parent) | Codes today |
| --- | --- |
| `TaravSystemPromptPOI` | `no-source`, `missing`, `multiple`, `stale` |
| `ProjectSystemPromptPOI` | `no-source`, `missing`, `multiple`, `empty` |
| `AgentsMdProductPOI` | the `Document.lint()` kind: `invalid-source`, `source-uncompiled`, `product-unavailable`, `product-drift`, `missing-content`, `stale-generation`, `context-unresolvable`, `context-unobserved`, `stale-context`, `output-changed`, `invalid-annotation`, `invalid-produced-output` |
| `AgentsAliasPOI` | `missing`, `not-symlink`, `wrong-target` |
| `ProjectPackageSkillPOI` | `undeclared`, `missing` |
| `SkillFoldersPOI` | `agents-skills-absent`, `claude-skills-absent`, `claude-skills-diverges` |
| `TestFailurePOI` | `failed`, `error` |
| `WorkspacePOI` | twelve integrity, reset and removal codes plus `workspace-reference` |
| `GenerationPOI` | eight generation kinds |
| `SkillsStatusPOI` | `missing`, `broken`, `unsynced`, `conflicts`, `extra` |
| `TribunalScorePOI` | `Scoring.Unassessed`, `Scoring.LowRelativeSupport`, `Scoring.SparseCoverage` |
| `POIContextRoundTripPOI` | `no-instruction`, `unparsable`, `unresolved`, `empty-view` |
| bare `CheckPOI` in the CLI metadata check | `cli.missing-help`, `cli.missing-source`, `cli.missing-usage-descriptor` |
| bare `CheckPOI` in the Breadcrumb audit check | fourteen audit concern codes |

Classes raised with one code, which only drop it: `TaravPackageSkillPOI`, `ProvisionalMarkerPOI`, `POIGuidanceMissingPOI`, `ProviderError`, `ArchiveNotificationPOI`, `SkillsSelectionNotification`, the bare `NotificationPOI` for a refreshed Breadcrumb position (which gets its own type), and the 41 Skillware classes. `ChildProjectPOI` passes the child's POI type name as its code; that name is already in its situation, so it drops the argument too.

Readers of the field: `l1/poi/primitives.py`, `l1/poi/reporting.py` (retained report and the `reported-poi` view), `l1/checks/__init__.py` (`summary()["by_code"]`, `report(by="code", code=...)`, row `codes`), `l3/check.py` (`--by code`, `--code`), `l1/breadcrumbs/commands.py` and `l2/breadcrumb_workflows/chatlas_context/commands.py` (printed lines), and tests.

Checks that copy the code into the situation only to separate cases: the agents checks, the skills checks, the workspace checks, the Breadcrumb audit check, `GenerationPOI` (`kind`), the tribunal check and the round-trip check.

Stores: the tracked-POI store and board do not read the code. No blessing, decision or tracked-POI folder exists in any Taravangian project or under `/Users/pereiro/projects`, so no retained standing is affected by the identity changes. Retained check reports under `~/.tarav/check-reports/` are replaced on the next run.

### Design

**Base types.** `IdentifiedPOI(message, *, situation, subject, evidence)`, `CheckPOI(check, message, *, situation, ...)`, `NotificationPOI(message, *, details)` and `SituationCheck.finding(poi_type, *, message, ...)`. Records from `as_dict()` have no `code`.

**Splits.** Each case is an explicit class statement with its own TypeShip, Tarav type name and one-line docstring, subclassing the family. The family keeps its Python name, TypeShip and Tarav type name and is not raised. Checks choose the class in the branch that detects the case. Where a check receives a string kind from a non-POI producer (a `Document.lint()` finding, a Breadcrumb audit concern, a skills status category), a small kind-to-class table selects the class, as Skillware already does; these strings are internal keys of those producers, not POI fields.

**Identity.** Identity stays "type plus situation". The copied code leaves the situation, so every split case gets a new identity. No retained standing exists to carry over.

**Guidance.** For the seven bootstrap families the `read_first` and `may_do` declarations move to the case classes where the action differs by case, and stay inherited from the family otherwise.

**Reports.** `CheckRun.summary()` loses `by_code`; `CheckRun.report()` loses `by="code"`, the `code` filter and row `codes`; `tarav check` loses `--by code` and `--code`. Lines that printed a code print the POI type's last name component instead.

### Agent choices

- The three bare-`POI` dataclass finding classes are left for a follow-up, as stated under non-goals.
- An unrecognised kind arriving from a non-POI producer raises a clearly named "unrecognized" case of the family rather than failing the check, with the kind in its details.
- Type names follow `<family name>.<Case>` under the family's existing Tarav name.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes: `poi-system.md`, `checks-workflow.md`, `agents-bootstrap.md`, daily `2026-10-08.md`. Supporting session: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: see Impl.Log.

## Execution.Plan

1. Base types, `SituationCheck.finding`, report grouping, `tarav check` options, the retained report and the `reported-poi` view.
2. Split the families listed above, register the new Types where the families were registered, and remove copied codes from situations.
3. Move bootstrap guidance to case classes.
4. Update tests; add a test that no loaded POI type or record exposes `code`.
5. Guidance: `ARCHITECTURE.md` and the agents file through its Skillware source, where they mention codes.
6. Verification: full suite and Ruff in the worktree, the exact commit tree in isolation, CLI reinstall and root harness resync, then `tarav check --project .` on the Taravangian root with the POI totals by type compared against the previous 112.
7. Inlined Capture where practical, scoped completion commit, Wiki capture.

## Impl.Log

- Design inspection (2026-10-08): library introspection of POI subclasses, every construction site, the readers listed above, and a search for retained blessings, decisions and tracked POIs.
