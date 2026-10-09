# 881 — Diagram POIs as atomic Types — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive at design time (the User was working elsewhere; ordinary ambiguities are recorded agent choices). Status: complete. Phase: Execute resumed and completed on 2026-10-08 at the User's request.

Replace the Diagram's single coded POI class, `Finding` (`Tarav.Diagram.Finding`, in `src/tarav/l2/unsorted/contracts.py`), with atomic POI Types of the core POI tree. Every case that is a `code` string today becomes one class with its own name, identity and description under a family parent that is never raised. The `code` field and the word "finding" leave the Diagram's code, its JSON output, its retained Draft receipts and the skills that describe them. The 50 retained Drafts that store coded rows are migrated by an explicit operation.

Non-goals: tracked POIs and the notification log; turning Diagram validation into `Check` objects; repairing any POI a Project or the Diagram data reports; other repositories; the other deferred items of request 879 (blessing-store vocabulary, `Document.lint()` dictionaries, `SourceDiagnostic`, session search).

## Design narrative

### What the User decided

POI Types are atomic. Each Type describes one situation with no further degeneracy, and the typing system expresses the semantics.
<!-- tarav.breadcrumb d04272ba67bd05364fc8fea2a20244cc70788ec9a5b536bc5e7c2b3f6a8aca23 -->

The `code` field is to be eliminated.
<!-- tarav.breadcrumb 3774872722dbce615f2be9ae8209edb7dc270ad8c5b7c1dd1e33e5c40ceae60b -->

The POIs that still carry a code after request 877 must follow the same pattern: no code, a Type derived from the core POI tree.
<!-- tarav.breadcrumb de3733c888b51c9c104bbd091b370eb506b7e2273e0342fddac4946b9560797c -->

"Finding" is a legacy name for POIs. There is no finding anymore; every such situation is modelled with the current POI tree.
<!-- tarav.breadcrumb d431275eb4320c9a321b8dc83fed5dfa321e7b3d807111741f2aeb30851fa98e -->

Tarav should converge on fewer primitives: everything that looks like a POI is implemented as a POI, end to end, from the command line to the mechanics. It need not be perfect in the first iteration.
<!-- tarav.breadcrumb 27855a8327f71712962c273e89724d4a0d6adbe1c973e2b60d91993196064b3a -->

The Diagram family was the remaining exception. The User asked for this request, self-contained and with its references, to be executed by another agent.
<!-- tarav.breadcrumb a4e12a3f1a798e61465a17b4c0964850956e0622c4cfecbd0a2797b3ad1fd0d5 -->

### What earlier requests decided that binds this one

- **876** (`notes/live/876-context-command-and-reported-poi-impl-req.md`): `tarav context --id <id> --view reported-poi` is the one place a reader opens a POI. Every POI Type declares `read_first` and `may_do`, read by `guidance_of()` in `src/tarav/l1/poi/reporting.py`; `POIGuidanceCheck` in `src/tarav/l1/checks/poi_contract.py` raises one reminder per Type that declares neither.
- **877** (`notes/live/877-atomic-poi-types-impl-req.md`): no `code` on any POI; one class per case; a family parent that is never raised; names `<family>.<Case>`. The worked pattern is `src/tarav/l1/project/agents.py`.
- **879** (`notes/live/879-one-poi-system-and-rendering-impl-req.md`): POIs are printed through the renderer registry in `src/tarav/l1/poi/rendering.py` (`POISelection`, `POIRenderer`, levels `line`, `record`, `context`, renderers `Tarav.POI.Default.Renderer` and `Tarav.POI.JsonLines.Renderer`); a POI Type owns its line through `POI.summary()`; `POIRenderCoverageCheck` flags Types whose line is empty or only a label. 879 converted `ReferenceFinding` into `ReferenceResolutionPOI` with two cases (`src/tarav/l1/references/__init__.py`), the smallest worked pattern for an `IdentifiedPOI` family that is not raised by a `Check`. 879 left this family as a named exception; see its inventory row and the Diagram paragraph of its Impl.Log.

### Current behavior (inspected 2026-10-08, commit `ee0d8b3`)

`Finding` is a frozen dataclass extending the root `POI`, with three fields: `code`, `path`, `message`. `to_dict()` writes `{"type": "Tarav.Diagram.Finding", "code", "path", "message"}`. It has no identity, no situation, no guidance, and is not an `IdentifiedPOI`, so it cannot be opened with `tarav context` and is not blessable.

- **Construction.** 84 `Finding(...)` calls in 13 files under `src/tarav/l2/unsorted/` and `src/tarav/l2/lines/`. 83 raise a case; one (`capture.py:408`) rebuilds objects from retained rows.
- **Cases.** 81 distinct codes (879 estimated 74). Five sites take the code from a variable: `assessment.py:562` (`_gate_turn`, two codes), `evidence.py:217` and `:222` (`_matched`, four codes), `projection.py:439` (a conditional between two codes), and `views.py:493`, which copies `code` and `message` out of a View's retained `materialization_findings` rows and defaults to `diagram-view-materialization-poi`.
- **Deduplication.** `_dedupe_findings` (`contracts.py:282`), `commands.py:295` and `rendering.py:563` all key on `(code, path, message)`.
- **Carriers.** `GateAssessment.findings`, `LineReview.findings` (`contracts.py`), `CaptureReceipt.findings` (`capture.py`), method names such as `DiagramNamespace.findings()`, `type_findings()`, `mechanical_findings()`, `definition_findings()`, `object_type_definition_findings()`, `_staleness_finding`, `_collection_cycle_findings`, and the View key `materialization_findings` (`views.py:488`, `:1320`, `:1328`).
- **Command output.** JSON key `findings` and text `findings: N` in `l2/unsorted/commands.py` (lines 183, 327, 395, 547, 554, 572, 589), `draft_commands.py` (66–68, 174, 195) and `view_commands.py` (162, 289); `view_commands.py:296` prints `- {code}: {message}`. None of these use the renderer registry.
- **Tests.** No test asserts any Diagram code. Tests importing these packages: `tests/diagram/test_workflow_split.py`, `tests/test_scoped_lines.py`, `tests/scoring/test_assessment_cases.py`, `tests/scoring/test_assertion_objects.py`, `tests/kernel/test_object_record_contract.py`, `tests/test_architecture.py`. The family is effectively uncharacterized.

### Retained data (read-only scan of `~/Documents/tarav/diagram/`)

- 53 Draft files in `drafts/` (`type: Tarav.Diagram.Draft`, `schema_version: 1`); 50 are `Applied` and carry a `receipt`, 3 are `Open` without one. The folder is not a Git repository, so there is no history to fall back on.
- The 50 receipts hold 13,347 rows in `receipt.findings[]`. Every row has exactly the keys `class`, `code`, `message`, `path`, with `class: "Tarav.POI.Instance"`. That is an older writer; no current code writes `class`, and the current writer would produce `type: "Tarav.Diagram.Finding"`. The reader ignores both and reads only `code`, `path`, `message`.
- Only 8 of the 81 codes occur in retained rows: `line-type-missing` 8,200; `model-staleness` 1,971; `impl-req-closed-write` 1,507; `block-type-missing` 960; `semantic-record-unasserted` 418; `archive-grounding-unassessable` 282; `producer-turn-unresolved` 8; `capture-authorization-token-missing` 1.
- No `(code, path)` pair occurs with two different messages, and there are no exact duplicate rows, so an identity built from Type and path loses nothing in this data.
- Nothing under `views/`, `user-touched-chatlas-index/` or `attic/` (5,532 JSON files scanned) holds a row with a `code` key. `materialization_findings` is therefore a schema concern only; no retained View needs rewriting. The executor re-runs this scan before migrating (the script is in the Execution.Plan), because the data moves daily.

### Design

**Type tree.** One root family, `DiagramPOI` (`Tarav.Diagram.POI`), extends `IdentifiedPOI` and is never raised. Twelve sub-families extend it, also never raised, and the 81 cases extend those. All 81 are states of a retained or candidate Diagram object, so all are `IdentifiedPOI`; none is a `NotificationPOI`. Agent choice: they are not `CheckPOI`, because the Diagram raises them from validation methods and not from `Check` objects, and wrapping Diagram validation in Checks is a larger redesign.

**Reuse the retired identity.** `Tarav.Diagram.POI` keeps the TypeShip of `Finding` (`d220cb8c-c05f-493c-8190-21117e2d4f7a`) under its new name. Agent choice; the alternative is a fresh TypeShip. Every other class gets a new UUID.

**Fields.** A case is constructed with keyword arguments only: `path=` (the address string used today) and `message=`. Its situation is `{"path": path}`, so identity is Type plus path. The message is text, not identity. Cases whose message is an exception string (`str(exc)`) keep it as the message and also put it in `evidence`. The family parent offers one constructor so the 83 sites change in a uniform way.

**Dynamic sites.** Functions that take a code string take a POI Type instead (`_gate_turn`, `_matched`); the conditional in `projection.py:439` becomes two explicit constructions.

**View materialization rows.** `views.py:1320` and `:1328` write POI rows into a View's Line entry and `views.py:493` reads them back. They become `materialization_pois` holding the new record shape, and the reader resolves the Type by name. The default code `diagram-view-materialization-poi` disappears: a row without a resolvable Type is reported as `Tarav.Diagram.View.MaterializationRowUnrecognized` and carries the raw row as evidence.

**Record shape.** A stored or printed row is `{"type": "<Type name>", "path": "...", "message": "..."}`. Receipts and command JSON use the key `pois`. The receipt reader resolves `type` through one catalog mapping Type name to class; an unknown name raises a clear error naming the row, because readers never repair retained state.

**Vocabulary.** `findings` becomes `pois` in fields, methods, JSON keys and text output across the listed carriers (`GateAssessment.pois`, `LineReview.pois`, `CaptureReceipt.pois`, `DiagramNamespace.pois()`, `type_pois()`, `mechanical_pois()`, `definition_pois()`). No aliases.

**Deduplication.** The three dedupe sites key on POI identity. This changes behavior only where one Type and path occur with two messages, which the retained data never does.

**Printing.** Diagram commands build a `POISelection.from_pois(...)` and print through the registry, with the keyed options `--renderer` and `--level` that `tarav check` has. Their JSON output keeps its envelope and replaces `findings` with `pois`.

**Guidance and lines.** Each sub-family declares `read_first` and `may_do` once, inherited by its cases; a case overrides only where its response differs. Each case's docstring is the one-sentence statement of its situation, which gives `summary()` and the render-coverage check something better than a label.

**Draft migration.** `DRAFT_SCHEMA_VERSION` goes from 1 to 2. Version 2 means: `receipt.pois[]` with the record shape above and no `receipt.findings`. A migration operation, exposed as a keyed command on the existing draft command group (agent proposal: `tarav diagram draft migrate --to 2 [--dry-run] [--json]`; confirm the group name with `tarav --help`), does this per Draft: map each row's `code` through a frozen legacy table to a Type name, drop `class` and `code`, keep `path` and `message`, rename the key, bump the version, write atomically. The legacy table lives only in the migration module and is the single place a code string survives. `--dry-run` reports, per Draft and in total, rows by target Type and rows with no mapping, and writes nothing. A row whose code has no mapping stops the migration of that Draft: the file is left untouched at version 1 and reported. Drafts without a receipt only get the version bump. Before the first real run the executor copies `drafts/` to a dated sibling backup folder and records its path in Impl.Log, because the folder has no Git history. After migration the version-1 reader is removed; a version-1 Draft then fails to load with a message naming the migration command.

### Informative alternatives

- Keep `code` only inside retained receipts and translate at read time. Rejected: it is a reader repairing retained state and keeps the field alive.
- Drop receipt rows during migration, since they are historical. Not chosen: they are evidence of what a capture reported.
- Collapse the 81 cases into fewer Types. Not chosen: codes are merged only where two sites state the same situation, and the catalog found no two codes that do. Nine codes are raised from several sites and stay one Type each.

### Case catalog

81 codes, 83 raising sites, 12 families. Type names are mechanical proposals (code in CamelCase, family prefix removed); the executor may improve a name and must record it. Messages are abbreviated. Line numbers are as of commit `ee0d8b3`; regenerate the list with the script in Execution.Plan step 1.

**Family `Tarav.Diagram.Annotation.POI`** (7 cases)

| Code today | Proposed Type `Tarav.Diagram.Annotation.<Case>` | Sites (`src/tarav/`…) raised in | Message today |
| --- | --- | --- | --- |
| `annotation-specialization-unavailable` | `AnnotationSpecializationUnavailable` | `l2/unsorted/storage.py:456` DiagramNamespace.findings | (exception text) |
| `annotation-type-not-allowed` | `AnnotationTypeNotAllowed` | `l2/unsorted/storage.py:446` DiagramNamespace.findings | Namespace {self.name} does not allow Annotation type {annotation.type} |
| `archive-grounding-unassessable` | `ArchiveGroundingUnassessable` | `l2/lines/records.py:798` LineGateAnnotation.type_findings; `l2/lines/records.py:365` LineAnnotationRecord.type_findings; `l2/unsorted/storage.py:473` DiagramNamespace.findings | Chatlas-to-Archive grounding is not yet mechanically assessable. |
| `empty-support-set` | `EmptySupportSet` | `l2/unsorted/storage.py:464` DiagramNamespace.findings | Annotation has no rooted User.Turn support. |
| `line-annotation-argument-unresolved` | `LineAnnotationArgumentUnresolved` | `l2/lines/records.py:344` LineAnnotationRecord.type_findings | Line.Annotation argument does not resolve in its Namespace: {reference |
| `line-annotation-producer-missing` | `LineAnnotationProducerMissing` | `l2/lines/records.py:356` LineAnnotationRecord.type_findings | Supported Line.Annotation edition has no producer Turn. |
| `semantic-record-unasserted` | `SemanticRecordUnasserted` | `l2/unsorted/storage.py:489` DiagramNamespace.findings | The semantic record is missing one or more required Assertion scores. |

**Family `Tarav.Diagram.Block.POI`** (7 cases)

| Code today | Proposed Type `Tarav.Diagram.Block.<Case>` | Sites (`src/tarav/`…) raised in | Message today |
| --- | --- | --- | --- |
| `block-declaration-missing` | `DeclarationMissing` | `l2/lines/projection.py:329` DiagramProjectionBuilder._block | Lines name a Block Ship with no Block Edition. |
| `block-has-no-lines` | `HasNoLines` | `l2/lines/rendering.py:419` _render_block | Block contains no Line editions. |
| `block-label-selection-unresolved` | `LabelSelectionUnresolved` | `l2/lines/rendering.py:406` _render_block | Block has no label edition. |
| `block-type-missing` | `TypeMissing` | `l2/lines/projection.py:337` DiagramProjectionBuilder._block | Block Editions do not retain a Block.Type. |
| `block-type-not-allowed` | `TypeNotAllowed` | `l2/lines/projection.py:360` DiagramProjectionBuilder._block | Namespace {self.namespace.name} does not allow Block.Type {selected_id |
| `block-type-unknown` | `TypeUnknown` | `l2/lines/projection.py:347` DiagramProjectionBuilder._block | Block.Type is not registered: {selected_id}. |
| `issue-open` | `IssueOpen` | `l2/lines/block.py:121` IssueBlock.assess | Issue.Block has no reviewed Issue.Line.Resolve with a passing Verbatim |

**Family `Tarav.Diagram.CaptureAuthorization.POI`** (7 cases)

| Code today | Proposed Type `Tarav.Diagram.CaptureAuthorization.<Case>` | Sites (`src/tarav/`…) raised in | Message today |
| --- | --- | --- | --- |
| `capture-authorization-gate-unresolved` | `GateUnresolved` | `l2/unsorted/capture.py:292` CaptureManifest.check; `l2/unsorted/capture.py:311` CaptureManifest.check | Capture.Authorization.Gate does not resolve: {gate_id}. |
| `capture-authorization-permission-not-user` | `PermissionNotUser` | `l2/unsorted/assessment.py:243` CaptureAuthorizationAssertionEvaluator.evaluate | Capture authorization permission evidence is not a User turn. |
| `capture-authorization-permission-unresolved` | `PermissionUnresolved` | `l2/unsorted/assessment.py:223` CaptureAuthorizationAssertionEvaluator.evaluate | (exception text) |
| `capture-authorization-scope-unassessable` | `ScopeUnassessable` | `l2/unsorted/assessment.py:267` CaptureAuthorizationAssertionEvaluator.evaluate | Cross-Namespace authorization scope requires Diagram-level resolution. |
| `capture-authorization-scope-unresolved` | `ScopeUnresolved` | `l2/unsorted/assessment.py:259` CaptureAuthorizationAssertionEvaluator.evaluate | One or more authorization targets do not resolve. |
| `capture-authorization-token-missing` | `TokenMissing` | `l2/unsorted/assessment.py:251` CaptureAuthorizationAssertionEvaluator.evaluate | Authorization token does not occur in its permission evidence. |
| `capture-authorization-unassessable` | `Unassessable` | `l2/unsorted/assessment.py:205` CaptureAuthorizationAssertionEvaluator.evaluate | Capture.Authorization.Gate requires Chatlas evidence. |

**Family `Tarav.Diagram.Collection.POI`** (6 cases)

| Code today | Proposed Type `Tarav.Diagram.Collection.<Case>` | Sites (`src/tarav/`…) raised in | Message today |
| --- | --- | --- | --- |
| `collection-host-cycle` | `HostCycle` | `l2/lines/projection.py:657` DiagramProjectionBuilder._collection_cycle_findings | Diagram.Collection hosting contains a cycle. |
| `collection-host-model-mismatch` | `HostModelMismatch` | `l2/lines/projection.py:520` DiagramProjectionBuilder._collection | Collection host names a different Model. |
| `collection-host-unresolved` | `HostUnresolved` | `l2/lines/projection.py:528` DiagramProjectionBuilder._collection | Parent Diagram.Collection does not resolve in this Model. |
| `collection-reference-unresolved` | `ReferenceUnresolved` | `l2/lines/projection.py:542` DiagramProjectionBuilder._collection | Diagram.Collection reference does not resolve. |
| `collection-type-not-allowed` | `TypeNotAllowed` | `l2/lines/projection.py:507` DiagramProjectionBuilder._collection | Namespace {self.namespace.name} does not allow Collection.Type {select |
| `collection-type-unknown` | `TypeUnknown` | `l2/lines/projection.py:491` DiagramProjectionBuilder._collection | Collection.Type is not registered: {selected_id}. |

**Family `Tarav.Diagram.ImplReq.POI`** (3 cases)

| Code today | Proposed Type `Tarav.Diagram.ImplReq.<Case>` | Sites (`src/tarav/`…) raised in | Message today |
| --- | --- | --- | --- |
| `impl-req-closed-write` | `ClosedWrite` | `l2/lines/projection.py:586` DiagramProjectionBuilder._collection | Normal capture added or revised content in a Closed Impl.Req.Collectio |
| `impl-req-reopen-window-invalid` | `ReopenWindowInvalid` | `l2/lines/collection.py:101` ImplReqCollection.mechanical_findings | Impl.Req.Collection reopening is outside its declared window. |
| `impl-req-state-invalid` | `StateInvalid` | `l2/lines/collection.py:82` ImplReqCollection.mechanical_findings | Impl.Req.Collection state must be Open or Closed. |

**Family `Tarav.Diagram.Line.POI`** (5 cases)

| Code today | Proposed Type `Tarav.Diagram.Line.<Case>` | Sites (`src/tarav/`…) raised in | Message today |
| --- | --- | --- | --- |
| `line-type-missing` | `TypeMissing` | `l2/lines/projection.py:426` DiagramProjectionBuilder._line | Line Editions do not retain a Line.Type. |
| `line-type-not-allowed-by-block` | `TypeNotAllowedByBlock` | `l2/lines/projection.py:439` DiagramProjectionBuilder._line | Block.Type {block_type.id} does not allow Line.Type {selected_id}.' if |
| `line-type-unknown` | `TypeUnknown` | `l2/lines/projection.py:439` DiagramProjectionBuilder._line | Block.Type {block_type.id} does not allow Line.Type {selected_id}.' if |
| `line-unreviewed` | `Unreviewed` | `l2/lines/rendering.py:362` _render_line; `l2/unsorted/storage.py:844` DiagramNamespace.line_review | Line ship has no Annotation with a passing Verbatim.Gate. |
| `line-wording-missing` | `WordingMissing` | `l2/lines/projection.py:418` DiagramProjectionBuilder._line | Line records name a Line Ship with no wording Edition. |

**Family `Tarav.Diagram.Manifest.POI`** (9 cases)

| Code today | Proposed Type `Tarav.Diagram.Manifest.<Case>` | Sites (`src/tarav/`…) raised in | Message today |
| --- | --- | --- | --- |
| `annotation-identity-rebound` | `AnnotationIdentityRebound` | `l2/unsorted/capture.py:227` CaptureManifest.check | One Annotation identity names different content. |
| `capture-model-mismatch` | `CaptureModelMismatch` | `l2/unsorted/capture.py:245` CaptureManifest.check; `l2/unsorted/capture.py:190` CaptureManifest.check | Annotation is not located in the Capture.Manifest Model. |
| `duplicate-annotation-id` | `DuplicateAnnotationId` | `l2/unsorted/capture.py:219` CaptureManifest.check | Capture.Manifest repeats one Annotation identity. |
| `duplicate-ship-id` | `DuplicateShipId` | `l2/unsorted/capture.py:150` CaptureManifest.check | Capture.Manifest repeats one Ship identity. |
| `edition-host-unresolved` | `EditionHostUnresolved` | `l2/unsorted/capture.py:283` CaptureManifest.check | Edition host Collection does not resolve. |
| `ship-edition-in-annotation-collection` | `ShipEditionInAnnotationCollection` | `l2/unsorted/capture.py:211` CaptureManifest.check | Ship editions belong in Capture.Manifest.ships, not annotations. |
| `ship-identity-rebound` | `ShipIdentityRebound` | `l2/unsorted/capture.py:158` CaptureManifest.check | One Ship identity names incompatible content. |
| `ship-specialization-unavailable` | `ShipSpecializationUnavailable` | `l2/unsorted/capture.py:182` CaptureManifest.check | (exception text) |
| `ship-type-not-allowed` | `ShipTypeNotAllowed` | `l2/unsorted/capture.py:172` CaptureManifest.check | Namespace {namespace.name} does not allow Ship type {ship.type}. |

**Family `Tarav.Diagram.Model.POI`** (2 cases)

| Code today | Proposed Type `Tarav.Diagram.Model.<Case>` | Sites (`src/tarav/`…) raised in | Message today |
| --- | --- | --- | --- |
| `model-has-no-blocks` | `HasNoBlocks` | `l2/lines/rendering.py:472` _kernel_model | Model contains no Block Ships. |
| `model-staleness` | `Staleness` | `l2/lines/projection.py:468` DiagramProjectionBuilder._staleness_finding | Model.Staleness.POI: the newest known Line.Ship edition is hosted outs |

**Family `Tarav.Diagram.ObjectType.POI`** (2 cases)

| Code today | Proposed Type `Tarav.Diagram.ObjectType.<Case>` | Sites (`src/tarav/`…) raised in | Message today |
| --- | --- | --- | --- |
| `object-type-definition-block-missing` | `DefinitionBlockMissing` | `l2/lines/types.py:161` DiagramObjectTypeRegistry.definition_findings | Object.Type {object_type.id} has no Definition.Block. |
| `object-type-definition-block-unresolved` | `DefinitionBlockUnresolved` | `l2/lines/types.py:172` DiagramObjectTypeRegistry.definition_findings | Definition.Block does not resolve for Object.Type {object_type.id}: {o |

**Family `Tarav.Diagram.Support.POI`** (9 cases)

| Code today | Proposed Type `Tarav.Diagram.Support.<Case>` | Sites (`src/tarav/`…) raised in | Message today |
| --- | --- | --- | --- |
| `producer-turn-not-agent` | `ProducerTurnNotAgent` | `l2/unsorted/evidence.py:67` ChatlasEvidence.check | Annotation producer is not an Agent turn. |
| `producer-turn-unresolved` | `ProducerTurnUnresolved` | `l2/unsorted/evidence.py:222` ChatlasEvidence._matched; `l2/unsorted/evidence.py:217` ChatlasEvidence._matched | Chatlas Turn reference standing is {resolved.get('standing')}. |
| `support-context-unassessable` | `ContextUnassessable` | `l2/unsorted/evidence.py:101` ChatlasEvidence.check | (exception text) |
| `support-neighborhood-turn-unresolved` | `NeighborhoodTurnUnresolved` | `l2/unsorted/evidence.py:222` ChatlasEvidence._matched; `l2/unsorted/evidence.py:217` ChatlasEvidence._matched | Chatlas Turn reference standing is {resolved.get('standing')}. |
| `support-not-in-producer-context` | `NotInProducerContext` | `l2/unsorted/evidence.py:110` ChatlasEvidence.check | Selected support content was not present before the Annotation produce |
| `support-render-unavailable` | `RenderUnavailable` | `l2/lines/rendering.py:598` _support_details | (exception text) |
| `support-root-not-user` | `RootNotUser` | `l2/unsorted/evidence.py:81` ChatlasEvidence.check | Support.Member root is not a User turn. |
| `support-root-unresolved` | `RootUnresolved` | `l2/unsorted/evidence.py:222` ChatlasEvidence._matched; `l2/unsorted/evidence.py:217` ChatlasEvidence._matched | Chatlas Turn reference standing is {resolved.get('standing')}. |
| `turn-unresolved` | `TurnUnresolved` | `l2/unsorted/evidence.py:222` ChatlasEvidence._matched; `l2/unsorted/evidence.py:217` ChatlasEvidence._matched | Chatlas Turn reference standing is {resolved.get('standing')}. |

**Family `Tarav.Diagram.VerbatimGate.POI`** (9 cases)

| Code today | Proposed Type `Tarav.Diagram.VerbatimGate.<Case>` | Sites (`src/tarav/`…) raised in | Message today |
| --- | --- | --- | --- |
| `line-gate-target-unresolved` | `LineGateTargetUnresolved` | `l2/lines/projection.py:233` DiagramProjectionBuilder.add_line_gate_annotation; `l2/unsorted/assessment.py:155` VerbatimGateAssertionEvaluator.evaluate | Line Gate target does not resolve to a Line Edition. |
| `verbatim-gate-approval-not-user` | `ApprovalNotUser` | `l2/unsorted/assessment.py:486` _assess_verbatim_gate | Verbatim.Gate approval is not a User turn. |
| `verbatim-gate-approval-unresolved` | `ApprovalUnresolved` | `l2/unsorted/assessment.py:562` _gate_turn | (exception text) |
| `verbatim-gate-content-mismatch` | `ContentMismatch` | `l2/unsorted/assessment.py:536` _assess_verbatim_gate | The proposal turn does not contain materially equivalent Line wording. |
| `verbatim-gate-order-mismatch` | `OrderMismatch` | `l2/unsorted/assessment.py:522` _assess_verbatim_gate | Verbatim.Gate approval does not follow its proposal in one chat. |
| `verbatim-gate-proposal-not-agent` | `ProposalNotAgent` | `l2/unsorted/assessment.py:474` _assess_verbatim_gate | Verbatim.Gate proposal is not an Agent turn. |
| `verbatim-gate-proposal-unresolved` | `ProposalUnresolved` | `l2/unsorted/assessment.py:562` _gate_turn | (exception text) |
| `verbatim-gate-token-mismatch` | `TokenMismatch` | `l2/unsorted/assessment.py:500` _assess_verbatim_gate | Gate token is not present in the proposal and explicitly approved by t |
| `verbatim-gate-unassessable` | `Unassessable` | `l2/unsorted/assessment.py:418` _assess_verbatim_gates | Verbatim.Gate requires Chatlas evidence for assessment. |

**Family `Tarav.Diagram.View.POI`** (15 cases)

| Code today | Proposed Type `Tarav.Diagram.View.<Case>` | Sites (`src/tarav/`…) raised in | Message today |
| --- | --- | --- | --- |
| `diagram-view-block-duplicate` | `BlockDuplicate` | `l2/unsorted/views.py:416` DiagramView.check | Block occurs more than once in the View: {block_ship}. |
| `diagram-view-deep-support-unassessable` | `DeepSupportUnassessable` | `l2/unsorted/views.py:1321` _line_entry | Deep support disclosure requires Chatlas evidence. |
| `diagram-view-deep-support-unresolved` | `DeepSupportUnresolved` | `l2/unsorted/views.py:1287` _line_entry | (exception text) |
| `diagram-view-dependency-ambiguous` | `DependencyAmbiguous` | `l2/unsorted/views.py:511` DiagramView.check | Dependency label resolves to several Blocks: {dependency.get('label')} |
| `diagram-view-disclosure-level-invalid` | `DisclosureLevelInvalid` | `l2/unsorted/views.py:429` DiagramView.check | Disclosure level is outside the supported ladder: {level}. |
| `diagram-view-invalid` | `Invalid` | `l2/unsorted/views.py:400` DiagramView.check | (exception text) |
| `diagram-view-line-materialization-mismatch` | `LineMaterializationMismatch` | `l2/unsorted/views.py:468` DiagramView.check | Visible Line material does not match the retained Line selection. |
| `diagram-view-line-selection-duplicate` | `LineSelectionDuplicate` | `l2/unsorted/views.py:444` DiagramView.check | A Line ship occurs more than once in one Block selection. |
| `diagram-view-materialization-poi` | `MaterializationPoi` | `l2/unsorted/views.py:493` DiagramView.check | (exception text) |
| `diagram-view-mention-check-unassessable` | `MentionCheckUnassessable` | `l2/unsorted/views.py:708` SessionDiagramView.check | (exception text) |
| `diagram-view-mentioned-block-absent` | `MentionedBlockAbsent` | `l2/unsorted/views.py:716` SessionDiagramView.check | Session mentions Block {mention['label'] or mention['block_ship']}, bu |
| `diagram-view-session-identity-missing` | `SessionIdentityMissing` | `l2/unsorted/views.py:697` SessionDiagramView.check | Session.Diagram.View has no Chatlas session identity. |
| `diagram-view-source-stale` | `SourceStale` | `l2/unsorted/views.py:544` DiagramView.check | View retains {edition}; Namespace HEAD is {current}. |
| `diagram-view-source-unresolved` | `SourceUnresolved` | `l2/unsorted/views.py:535` DiagramView.check | (exception text) |
| `diagram-view-visible-line-budget-exceeded` | `VisibleLineBudgetExceeded` | `l2/unsorted/views.py:521` DiagramView.check | View contains {visible_lines} visible Lines; configured maximum is {ma |

Nine codes have several raising sites and remain one Type: `line-gate-target-unresolved`, `archive-grounding-unassessable`, `line-unreviewed`, `capture-model-mismatch`, `capture-authorization-gate-unresolved`, and the four codes passed to `ChatlasEvidence._matched`. One Type is new and has no code today: `Tarav.Diagram.View.MaterializationRowUnrecognized`, replacing `diagram-view-materialization-poi`.

### Open questions for the User

1. Should `Tarav.Diagram.POI` reuse the TypeShip of `Tarav.Diagram.Finding`, or get a new one?
2. Receipt rows: migrate all 13,347 (the plan), or drop historical rows and keep only counts?
3. Should Diagram validation later become `Check` objects raising `CheckPOI`s, so it joins `tarav check`? This request leaves it as plain `IdentifiedPOI`s.
4. The proposed command name `tarav diagram draft migrate --to 2` is an agent proposal.

## Impl.Req.Wiki

- Product project: `tarav-py` (`Tarav.Project.PythonPackage`, child of the Taravangian root). Read `tarav-py/AGENTS.md` first; binding parts: "Architecture" (layers; no compatibility aliases or fallback paths), "Editing and tests" (schema changes migrate code and affected data explicitly; readers never repair retained state; preserve unrelated changes in the shared worktree), the last line of "Import entry points" (POI Types are atomic). `ARCHITECTURE.md`: the Diagram, POI and Checks sections.
- Constitution: `tarav-md/skills/tarav-pkg/CONSTITUTION.md` (POIs are signals; validation informs and does not block writing).
- Wiki owner and root: `tarav-md/notes/wiki/`. Relevant notes: `poi-system.md` (the POI tree, atomic Types, rendering), `capabilities-by-subtyping.md` (the Type declares the capability), `context-graph.md` (context views and the `reported-poi` view), `diagram-workflows.md` (Diagram ownership and workflows), `checks-workflow.md`, `daily/2026-10-08.md` (the session narrative).
- Skills that describe the output: `tarav-md/skills/tarav-pkg/tarav-diagram.md` (lines near 100, 482, 528 speak of "findings") and `tarav-md/skills/tarav-hugentics/references/capture.md` (line 63). Both are Skillware products; their sources are under each skill's `.skw/src/`. No skill reads a `code` value or a `findings[]` key from JSON output.
- Supporting chat: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`.
- Capture status: Design Breadcrumbs in this note; Wiki capture pending (skipped at Design because `tarav-md` had someone else's uncommitted changes).

## Execution.Plan

Stop rule: finish the slice in hand, leave the suite passing, commit that slice with the scoped evidence commit, and write in Impl.Log which families are converted, which files still import `Finding`, and the next step. Between slices 3 and 7 the coded class and the new Types coexist; that state is acceptable in a commit only if the suite passes and Impl.Log lists the remaining importers.

1. **Recheck.** Cold-read this note and `AGENTS.md`. Regenerate the site list with an `ast` walk over `src/tarav` collecting every call named `Finding` (file, line, enclosing scope, arguments) and compare with the catalog: 84 calls, 81 codes. Re-run the retained-data scan (walk every JSON file under the Diagram data root for objects holding `code`, `path` and `message`; count by file, key set and code). Record differences in Impl.Log before editing.
2. **Characterization tests** (new `tests/diagram/test_diagram_pois.py`), written against today's behavior and passing before any conversion: a `CaptureReceipt` built with rows, written through `records.to_record()`, reloaded, rows equal; a Draft applied and reloaded with its receipt; at least one test per family that drives the real validation method to raise one case (`CaptureManifest.check`, `DiagramNamespace.findings`, `ChatlasEvidence.check`, `_assess_verbatim_gate`, `CaptureAuthorizationAssertionEvaluator.evaluate`, `DiagramProjectionBuilder`, `DiagramView.check`, `ImplReqCollection.mechanical_findings`, `IssueBlock.assess`, `DiagramObjectTypeRegistry.definition_findings`, the renderer paths in `l2/lines/rendering.py`); the three dedupe sites; a fixture copy of one real version-1 Draft receipt trimmed to a few rows per retained code.
3. **Types and catalog.** New module (proposal: `src/tarav/l2/unsorted/pois.py`): `DiagramPOI`, the 12 family parents, the 81 cases plus `MaterializationRowUnrecognized`, the name-to-class catalog, guidance per family. A test asserts the catalog holds exactly the planned case count, that names and TypeShips are unique, that no family parent is constructible by the raising helper, and that every case has guidance and a non-label line.
4. **Convert family by family**, one commit per family or small group: replace constructions, change dynamic-code helpers to take Types, update that family's characterization tests from codes to Types.
5. **Carriers, receipt and Draft schema.** Rename the carriers; change `CaptureReceipt` to `pois` with typed rehydration; `materialization_pois`; bump `DRAFT_SCHEMA_VERSION`; write the migration module with its frozen legacy table, the command, `--dry-run`, and tests over the fixture (mapped rows, unmapped code stops that Draft, Draft without receipt, idempotence on a version-2 file).
6. **Migrate the data.** Dry run on the real folder; record its totals in Impl.Log and compare with the scan of step 1. Back up `drafts/`. Run. Re-scan: zero rows with `code`, row count unchanged, every Draft at version 2, every Draft loads.
7. **Commands and rendering.** Move the Diagram command output onto `POISelection` and the renderer registry with `--renderer` and `--level`; replace `findings` keys and text. Update CLI tests.
8. **Skills and guidance.** Edit the Skillware sources of `tarav-diagram.md` and `capture.md` to say POIs, rebuild, run `tarav skw skills check`. Update `AGENTS.md` and `ARCHITECTURE.md` where they describe the Diagram's POIs. Commit `tarav-md` with its own scoped evidence commit.
9. **Remove the coded class.** Delete `Finding`, `_dedupe_findings` in its coded form and the version-1 Draft reader. Prove nothing was lost: no `Finding(` call and no import of it remains; `grep` finds no `.code` on a Diagram POI; the catalog test count equals the catalog in this note adjusted by recorded merges or renames.
10. **Verify and close.** Full suite, Ruff, `uv tool install --reinstall --editable .`, `tarav project harness sync --project .` at the root, and `tarav check --project` at the root to confirm it still runs; note the change in `POIGuidanceMissing` and render-coverage counts without repairing anything else. Inlined Capture on each implemented surface per slice, Wiki capture into `poi-system.md` and the daily note, completion commits.

## Impl.Log

- 2026-10-08, completion of resumed Execute. Added characterization coverage that drives the emitting method for each of the twelve Diagram POI families. Audited Diagram object, capture, Draft, View, and content-render command outputs; the content renderer was the remaining gap. `tarav diagram render` now retains its POIs and presents them through the shared POI renderer in text output, with a separate `--poi-renderer` and `--level` because its existing `--renderer` selects the content renderer. Tests cover text context, named JSON-lines record presentation, and JSON payloads. Installed CLI rebuilt and root harness synced. Full Python suite: 232 passed; Ruff: clean. Root Project: 365 Checks completed, zero incomplete, 151 POIs. Skill checks: tarav-pkg 28 POIs and tarav-hugentics 20 POIs, all existing guidance/link/context signals outside this request's repair scope; their presence does not undo the completed code and Draft migration. Rechecked all 53 Drafts at version 2 with 13,347 typed POIs and zero coded rows; dry run reports 53 already-v2, zero unmapped. User-Turn Breadcrumbs attached to the new code and tests, with Wiki and daily capture below.
<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->
<!-- tarav.breadcrumb c60eecb54575e6de557f1ad8baf41979ce8e34599f17c0d73e53d1d8ead01361 -->
- 2026-10-08, paused as incomplete at the User's request. The atomic Types, Draft migration, and core command integration have landed; all 53 retained Drafts are at schema version 2, with 13,347 POIs preserved. The integrated Python suite passed 222 tests and Ruff passed. The root check completed 365 Checks with zero TestSuite POIs and 151 other reported POIs. The migration dry run now reports 53 already-v2 Drafts, zero new rows, and zero unmapped rows.
- **Work identified at the pause, subsequently completed or scoped out:** Characterization tests for all twelve families, CLI renderer/level/JSON coverage, the Diagram content-render audit and fix, root harness sync, CLI reinstall, and repeated Project and Skillware checks. Existing Project and Skillware POIs were left for their owning work because repairing them is outside this request.
- 2026-10-08, Execute recheck. Isolated worktree at `8fb8efa` because the shared checkout holds active unrelated edits and its CLI is temporarily broken. AST scan still finds 84 `Finding(...)` calls; 72 literal codes at calls plus 9 dynamic cases matches the 81-case catalog. Fresh retained-data scan still finds exactly 13,347 coded rows in `drafts/` and none elsewhere; all rows have `class`, `code`, `message`, `path` and the same eight-code distribution recorded below. All six linked User Turns were opened through their Breadcrumbs. Start checkpoint: `571d450`.
- 2026-10-08, Execute migration. Dry run: 53 Drafts, 13,347 rows mapped to eight new Types, zero unmapped. Backed up the entire folder to `/Users/pereiro/Documents/tarav/diagram/drafts.backup-881-20261008-004422` (53 files). Applied version 2 atomically per file; loaded all 53 Drafts and all 50 receipts with the new code and counted all 13,347 rehydrated POIs. Three Open Drafts received only the schema bump.
- 2026-10-08, Execute code. Converted all 83 raising sites to 81 atomic `IdentifiedPOI` cases in 12 families, with the retired `Finding` TypeShip reused on `DiagramPOI`. Removed the coded class and renamed the Diagram carriers to `pois`; only the explicit version-1 migration table retains the legacy code vocabulary. Added `tarav diagram draft migrate --to 2` with dry run and per-Draft unmapped reporting. Diagram object, capture, Draft, and View commands retain and render typed POIs through the shared renderer with `--renderer` and `--level`; the separate Diagram content renderer remains its own CLI contract. The full Python suite passed 212 tests and Ruff passed. The root Project check completed 365 Checks; render coverage found zero missing lines, while it reported existing missing-guidance and Skillware POIs and test failures from the concurrently changing shared checkout. All 23 changed Python/architecture surfaces received User-Turn Breadcrumbs.
- 2026-10-08, Design. Catalog built mechanically from an `ast` walk: 84 `Finding(...)` calls, 83 raising sites, 81 codes, 12 proposed families (View 15, Manifest 9, Support 9, VerbatimGate 9, Annotation 7, Block 7, CaptureAuthorization 7, Collection 6, Line 5, ImplReq 3, Model 2, ObjectType 2).
- Retained data scanned read-only: 53 Drafts, 50 with receipts, 13,347 rows, 8 codes, key `class: Tarav.POI.Instance` on every row, no identity collisions; no coded rows outside `drafts/`. Nothing was modified.
- No source, test, skill or Wiki file was edited. The worktree holds another agent's uncommitted refactor, including edits in `l2/unsorted/commands.py`, `draft_commands.py`, `storage.py` and `view_commands.py`, all of which this plan touches; the executor must preserve those edits and commit only its own hunks.
- Wiki capture: pending.
- Evidence gap: none for the six design passages; the catalog names and the migration command name are agent proposals, marked as such.
