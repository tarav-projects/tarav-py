# 877 — Atomic POI types — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: complete. Phase: Develop (Execute complete).

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
- Design note capture: five User-Turn Breadcrumbs submitted; design commit `73174a1`. Scoped start checkpoint `eb029cf`.
- Execute (2026-10-08): `IdentifiedPOI`, `CheckPOI`, `NotificationPOI` and `SituationCheck.finding` no longer take a code, and `as_dict()` records have none. `CheckRun.summary()` lost `by_code`; `CheckRun.report()` lost `by="code"`, the `code` filter and row `codes`; `tarav check` lost `--by code` and `--code`. The retained check report and the `reported-poi` view carry no code.
- Fourteen families were split into 88 atomic case types, each an explicit class with its own TypeShip, Tarav type name and docstring: Tarav System Prompt (4), Project System Prompt (4), agents product (12 lint kinds plus one unrecognized-kind case), agents alias (3), Project package skill (2), skill folders (3), test failure (2), Workspace (12), Generation (8), skill depot status (5), tribunal score (3), POI context round trip (4), CLI command metadata (3, with a new family), and Breadcrumb audit (16 plus one unrecognized-concern case, with a new family). The refreshed-position notification became `BreadcrumbPositionUpdated`. Copied codes left the situations of the agents, skills, workspace, Breadcrumb audit, generation, tribunal and round-trip checks.
- Guidance: for the bootstrap families, `may_do` now sits on each case where the action differs (source unavailable, missing, duplicated, stale or empty prompt; alias missing, not a symlink, wrong target; package skill undeclared or missing; skill folders diverging); `read_first` stays inherited from the family.
- Registration: the runtime registers the cases of `WorkspacePOI`, `TribunalScorePOI`, `GenerationPOI`, `SkillsStatusPOI` and the Breadcrumb audit family beside their families; the agents and skills cases are in their modules' record-type tuples. The CLI metadata, test failure and round-trip families were not registered before and still are not.
- Method: every edit was a replayable text transform, verified to apply both to the shared worktree and to the committed version of each file, so that files carrying unrelated uncommitted edits (`ARCHITECTURE.md`, `l3/runtime.py`, `l2/skw/pois.py`, `l2/project/root.py`, `tests/test_workspaces.py` and the skills routing module, which is renamed in the worktree) were committed as "committed version plus this request's edits". The pre-existing staged rename of the routing module was updated with the same edits so it still shows no content difference.
- A scan of every POI construction in `src` and `tests` found one site the first pass had missed (`ProvisionalMarkerPOI`), where the stale code argument made the check fail silently; it is fixed. A new test asserts that no `IdentifiedPOI` or `NotificationPOI` subclass accepts or exposes a code.
- Verification: shared worktree 208 tests passed and Ruff clean; the exact commit tree in an isolated checkout passed 198 tests and Ruff. Running every test file, the committed tree has the same four failures as before this request (three obsolete tests in `tests/cli/test_check.py` and one in `tests/test_scoped_lines.py`), none new. CLI reinstalled and the root harness resynced.
- Root check after the change: 364 checks, 0 incomplete, 157 POIs. The 64 earlier POIs are unchanged in number and now appear under atomic types: `TaravSystemPrompt.SourceUnavailable` 2, `ProjectSystemPrompt.SourceUnavailable` 2, `Product.SourceInvalid` 2, `ProjectPackageSkill.Undeclared` 3, Skillware `StaleContext` 14, `UnannotatedOutputLink` 18, `UnreachableBlock` 12, `ProvisionalMarker` 11. Guidance reminders went from 48 to 93: the 45 extra are atomic leaf types without guidance (Workspace +11, Generation +7, skill depot status +4, tribunal +2, CLI metadata +3, Breadcrumb audit +17, test failure +1). The header example opens the `reported-poi` view; no `code` appears in the report, its JSON, the retained report or the view.
- Product completion commit `9559db7`, built from a temporary index, so it carries no commit-message Breadcrumb evidence. Inlined Capture: three Breadcrumbs, in `ARCHITECTURE.md` and `tests/test_poi_primitives.py`. Breadcrumb positions: 22 existing labels in 11 touched files moved to other lines and will report `breadcrumb-position-missing` where they resolved before; there is no re-observe command.
- Not done: `BreadcrumbFinding`, `ReferenceFinding` and the Diagram `Finding` still carry their own `code` (non-goal). No blessing, decision or tracked POI existed, so none needed carrying over.
- Other repositories that use the changed POI API and will fail until their maintainers adapt: `md-library-py` (about 57 POI constructions or `finding` calls) and `g70203-py` (about 3, with many code reads). `telegram-archive-py` and `tarav-extension-py` do not use it.
