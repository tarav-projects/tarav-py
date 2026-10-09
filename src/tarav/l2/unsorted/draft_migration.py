"""Explicit migration of version-1 Diagram Draft POI rows."""

from __future__ import annotations

# tarav.breadcrumb ba12e8c41336b2ef92a6333ecbf5b12d1662b011cca532f3900b8e09391fb72b

from collections import Counter
from pathlib import Path
from typing import Any

from tarav.l0._core.persistence import atomic_write_json
from tarav.l2.unsorted.io import _read_json

# Frozen version-1 code vocabulary; never used by readers or POI production.
LEGACY_TYPE_NAMES: dict[str, str] = {
    'annotation-identity-rebound': 'Tarav.Diagram.Manifest.AnnotationIdentityRebound',
    'annotation-specialization-unavailable': 'Tarav.Diagram.Annotation.AnnotationSpecializationUnavailable',
    'annotation-type-not-allowed': 'Tarav.Diagram.Annotation.AnnotationTypeNotAllowed',
    'archive-grounding-unassessable': 'Tarav.Diagram.Annotation.ArchiveGroundingUnassessable',
    'block-declaration-missing': 'Tarav.Diagram.Block.DeclarationMissing',
    'block-has-no-lines': 'Tarav.Diagram.Block.HasNoLines',
    'block-label-selection-unresolved': 'Tarav.Diagram.Block.LabelSelectionUnresolved',
    'block-type-missing': 'Tarav.Diagram.Block.TypeMissing',
    'block-type-not-allowed': 'Tarav.Diagram.Block.TypeNotAllowed',
    'block-type-unknown': 'Tarav.Diagram.Block.TypeUnknown',
    'capture-authorization-gate-unresolved': 'Tarav.Diagram.CaptureAuthorization.GateUnresolved',
    'capture-authorization-permission-not-user': 'Tarav.Diagram.CaptureAuthorization.PermissionNotUser',
    'capture-authorization-permission-unresolved': 'Tarav.Diagram.CaptureAuthorization.PermissionUnresolved',
    'capture-authorization-scope-unassessable': 'Tarav.Diagram.CaptureAuthorization.ScopeUnassessable',
    'capture-authorization-scope-unresolved': 'Tarav.Diagram.CaptureAuthorization.ScopeUnresolved',
    'capture-authorization-token-missing': 'Tarav.Diagram.CaptureAuthorization.TokenMissing',
    'capture-authorization-unassessable': 'Tarav.Diagram.CaptureAuthorization.Unassessable',
    'capture-model-mismatch': 'Tarav.Diagram.Manifest.CaptureModelMismatch',
    'collection-host-cycle': 'Tarav.Diagram.Collection.HostCycle',
    'collection-host-model-mismatch': 'Tarav.Diagram.Collection.HostModelMismatch',
    'collection-host-unresolved': 'Tarav.Diagram.Collection.HostUnresolved',
    'collection-reference-unresolved': 'Tarav.Diagram.Collection.ReferenceUnresolved',
    'collection-type-not-allowed': 'Tarav.Diagram.Collection.TypeNotAllowed',
    'collection-type-unknown': 'Tarav.Diagram.Collection.TypeUnknown',
    'diagram-view-block-duplicate': 'Tarav.Diagram.View.BlockDuplicate',
    'diagram-view-deep-support-unassessable': 'Tarav.Diagram.View.DeepSupportUnassessable',
    'diagram-view-deep-support-unresolved': 'Tarav.Diagram.View.DeepSupportUnresolved',
    'diagram-view-dependency-ambiguous': 'Tarav.Diagram.View.DependencyAmbiguous',
    'diagram-view-disclosure-level-invalid': 'Tarav.Diagram.View.DisclosureLevelInvalid',
    'diagram-view-invalid': 'Tarav.Diagram.View.Invalid',
    'diagram-view-line-materialization-mismatch': 'Tarav.Diagram.View.LineMaterializationMismatch',
    'diagram-view-line-selection-duplicate': 'Tarav.Diagram.View.LineSelectionDuplicate',
    'diagram-view-materialization-poi': 'Tarav.Diagram.View.MaterializationRowUnrecognized',
    'diagram-view-mention-check-unassessable': 'Tarav.Diagram.View.MentionCheckUnassessable',
    'diagram-view-mentioned-block-absent': 'Tarav.Diagram.View.MentionedBlockAbsent',
    'diagram-view-session-identity-missing': 'Tarav.Diagram.View.SessionIdentityMissing',
    'diagram-view-source-stale': 'Tarav.Diagram.View.SourceStale',
    'diagram-view-source-unresolved': 'Tarav.Diagram.View.SourceUnresolved',
    'diagram-view-visible-line-budget-exceeded': 'Tarav.Diagram.View.VisibleLineBudgetExceeded',
    'duplicate-annotation-id': 'Tarav.Diagram.Manifest.DuplicateAnnotationId',
    'duplicate-ship-id': 'Tarav.Diagram.Manifest.DuplicateShipId',
    'edition-host-unresolved': 'Tarav.Diagram.Manifest.EditionHostUnresolved',
    'empty-support-set': 'Tarav.Diagram.Annotation.EmptySupportSet',
    'impl-req-closed-write': 'Tarav.Diagram.ImplReq.ClosedWrite',
    'impl-req-reopen-window-invalid': 'Tarav.Diagram.ImplReq.ReopenWindowInvalid',
    'impl-req-state-invalid': 'Tarav.Diagram.ImplReq.StateInvalid',
    'issue-open': 'Tarav.Diagram.Block.IssueOpen',
    'line-annotation-argument-unresolved': 'Tarav.Diagram.Annotation.LineAnnotationArgumentUnresolved',
    'line-annotation-producer-missing': 'Tarav.Diagram.Annotation.LineAnnotationProducerMissing',
    'line-gate-target-unresolved': 'Tarav.Diagram.VerbatimGate.LineGateTargetUnresolved',
    'line-type-missing': 'Tarav.Diagram.Line.TypeMissing',
    'line-type-not-allowed-by-block': 'Tarav.Diagram.Line.TypeNotAllowedByBlock',
    'line-type-unknown': 'Tarav.Diagram.Line.TypeUnknown',
    'line-unreviewed': 'Tarav.Diagram.Line.Unreviewed',
    'line-wording-missing': 'Tarav.Diagram.Line.WordingMissing',
    'model-has-no-blocks': 'Tarav.Diagram.Model.HasNoBlocks',
    'model-staleness': 'Tarav.Diagram.Model.Staleness',
    'object-type-definition-block-missing': 'Tarav.Diagram.ObjectType.DefinitionBlockMissing',
    'object-type-definition-block-unresolved': 'Tarav.Diagram.ObjectType.DefinitionBlockUnresolved',
    'producer-turn-not-agent': 'Tarav.Diagram.Support.ProducerTurnNotAgent',
    'producer-turn-unresolved': 'Tarav.Diagram.Support.ProducerTurnUnresolved',
    'semantic-record-unasserted': 'Tarav.Diagram.Annotation.SemanticRecordUnasserted',
    'ship-edition-in-annotation-collection': 'Tarav.Diagram.Manifest.ShipEditionInAnnotationCollection',
    'ship-identity-rebound': 'Tarav.Diagram.Manifest.ShipIdentityRebound',
    'ship-specialization-unavailable': 'Tarav.Diagram.Manifest.ShipSpecializationUnavailable',
    'ship-type-not-allowed': 'Tarav.Diagram.Manifest.ShipTypeNotAllowed',
    'support-context-unassessable': 'Tarav.Diagram.Support.ContextUnassessable',
    'support-neighborhood-turn-unresolved': 'Tarav.Diagram.Support.NeighborhoodTurnUnresolved',
    'support-not-in-producer-context': 'Tarav.Diagram.Support.NotInProducerContext',
    'support-render-unavailable': 'Tarav.Diagram.Support.RenderUnavailable',
    'support-root-not-user': 'Tarav.Diagram.Support.RootNotUser',
    'support-root-unresolved': 'Tarav.Diagram.Support.RootUnresolved',
    'turn-unresolved': 'Tarav.Diagram.Support.TurnUnresolved',
    'verbatim-gate-approval-not-user': 'Tarav.Diagram.VerbatimGate.ApprovalNotUser',
    'verbatim-gate-approval-unresolved': 'Tarav.Diagram.VerbatimGate.ApprovalUnresolved',
    'verbatim-gate-content-mismatch': 'Tarav.Diagram.VerbatimGate.ContentMismatch',
    'verbatim-gate-order-mismatch': 'Tarav.Diagram.VerbatimGate.OrderMismatch',
    'verbatim-gate-proposal-not-agent': 'Tarav.Diagram.VerbatimGate.ProposalNotAgent',
    'verbatim-gate-proposal-unresolved': 'Tarav.Diagram.VerbatimGate.ProposalUnresolved',
    'verbatim-gate-token-mismatch': 'Tarav.Diagram.VerbatimGate.TokenMismatch',
    'verbatim-gate-unassessable': 'Tarav.Diagram.VerbatimGate.Unassessable',
}


def migrate_drafts(root: Path, *, dry_run: bool) -> dict[str, Any]:
    """Convert each version-1 Draft atomically; leave unmapped Drafts untouched."""
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Diagram Draft repository is missing: {root}")
    reports: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    for path in sorted(root.glob("*.json")):
        record = _read_json(path)
        version = record.get("schema_version")
        if version == 2:
            reports.append({"path": str(path), "status": "already-v2", "rows": 0,
                            "types": {}, "unmapped": {}})
            continue
        if version != 1:
            raise ValueError(f"Unsupported Diagram Draft schema in {path}: {version!r}")
        receipt = record.get("receipt")
        rows = receipt.get("findings", []) if isinstance(receipt, dict) else []
        if not isinstance(rows, list):
            raise ValueError(f"Invalid version-1 receipt findings in {path}")
        mapped: list[dict[str, str]] = []
        types: Counter[str] = Counter()
        unmapped: Counter[str] = Counter()
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                unmapped[f"row[{index}]:non-object"] += 1
                continue
            code = row.get("code")
            type_name = LEGACY_TYPE_NAMES.get(code) if isinstance(code, str) else None
            if type_name is None:
                unmapped[str(code)] += 1
                continue
            if not isinstance(row.get("path"), str) or not isinstance(row.get("message"), str):
                unmapped[f"row[{index}]:invalid-fields"] += 1
                continue
            mapped.append({"type": type_name, "path": row["path"], "message": row["message"]})
            types[type_name] += 1
        status = "unmapped" if unmapped else ("dry-run" if dry_run else "migrated")
        report = {"path": str(path), "status": status, "rows": len(rows),
                  "types": dict(sorted(types.items())), "unmapped": dict(sorted(unmapped.items()))}
        reports.append(report)
        totals.update(types)
        if not dry_run and not unmapped:
            if isinstance(receipt, dict):
                updated_receipt = dict(receipt)
                updated_receipt.pop("findings", None)
                updated_receipt["pois"] = mapped
                record["receipt"] = updated_receipt
            record["schema_version"] = 2
            atomic_write_json(path, record, ensure_ascii=False)
    return {
        "root": str(root), "dry_run": dry_run, "drafts": reports,
        "draft_count": len(reports), "row_count": sum(item["rows"] for item in reports),
        "types": dict(sorted(totals.items())),
        "unmapped_count": sum(sum(item["unmapped"].values()) for item in reports),
    }
