# $kw: --from POI.Linter
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Literal

from .model import EvidenceNeighborhood, IndexRecord, MessageRef
from .projection import ProjectionError, fold_records
from .touch import Resolution, TouchContext, TouchMessage, UserTouchSource
from .workspace import CargoDefect, RecordStore


FindingStanding = Literal["failed", "blocked"]


@dataclass(frozen=True, slots=True)
class LintFinding:
    """One addressable computation result; operands replace prose interpretation."""

    identity: str
    poi_class: str
    subject: dict[str, object]
    operands: dict[str, object]
    status: FindingStanding
    surface: dict[str, object]
    source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "poi_class": self.poi_class,
            "subject": self.subject,
            "operands": self.operands,
            "status": self.status,
            "surface": self.surface,
            "source": self.source,
        }


# $kw: --note [DC] no single success boolean: clean means nothing failed and verified means nothing failed and nothing was blocked, and collapsing those into one flag is what three-valued verdicts exist to prevent --note [DC] a short-circuited run is reported as such so an empty reportable set is never read as evidence of health
@dataclass(frozen=True, slots=True)
class LintReport:
    """The result of one run."""

    findings: tuple[LintFinding, ...]
    short_circuited: bool = False

    @property
    def clean(self) -> bool:
        return not any(item.status == "failed" for item in self.findings)

    @property
    def verified(self) -> bool:
        return not self.findings and not self.short_circuited

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "tarav.indexlab-lint-report.v1",
            "clean": self.clean,
            "verified": self.verified,
            "short_circuited": self.short_circuited,
            "counts": {
                "failed": sum(item.status == "failed" for item in self.findings),
                "blocked": sum(item.status == "blocked" for item in self.findings),
            },
            "findings": [finding.to_dict() for finding in self.findings],
        }


# $kw: --note [DC] the structural tier runs first and stops the run, because linting past unreadable cargo examines a silently truncated corpus and reports the remainder as clean
def lint_store(store: RecordStore, *, source: UserTouchSource) -> LintReport:
    """Lint a stored corpus, reporting unloadable cargo instead of raising."""

    records, defects = store.load()
    structural = tuple(_check_record_unloadable(defect) for defect in defects)
    if structural:
        return LintReport(findings=structural, short_circuited=True)
    return lint_records(records, source=source)


# $kw: IndexLab.Linter/Record.Unloadable --from POI.Linter
def _check_record_unloadable(defect: CargoDefect) -> LintFinding:
    return _structural_finding(
        "IndexLab.Linter/Record.Unloadable",
        subject={"record_id": defect.record_id or "<unidentified>"},
        operands={"expected": "LOADABLE", "actual": defect.error},
        check=_check_record_unloadable,
    )


def lint_records(
    records: Iterable[IndexRecord],
    *,
    source: UserTouchSource,
) -> LintReport:
    ordered = tuple(sorted(records, key=lambda record: (record.ordinal, record.id)))
    findings: list[LintFinding] = []

    for record in ordered:
        context_error: str | None = None
        try:
            context = source.resolve_context(record.context)
        except Exception as exc:
            context = Resolution[TouchContext](standing="MISSING", value=None)
            context_error = str(exc)
        _append(findings, _check_context_unresolved(record, context, context_error))
        _append(findings, _check_context_malformed(record, context))
        _append(findings, _check_context_amended(record, context))
        _append(findings, _check_support_empty(record))

        for neighborhood_index, neighborhood in enumerate(
            record.support.neighborhoods
        ):
            _append(
                findings,
                _check_neighborhood_empty(record, neighborhood, neighborhood_index),
            )
            for role, refs in (
                ("grounding", neighborhood.grounding),
                ("context", neighborhood.context),
            ):
                for ref in refs:
                    findings.extend(
                        _lint_support_ref(
                            record=record,
                            source=source,
                            context=context,
                            session=neighborhood.session,
                            ref=ref,
                            role=role,
                        )
                    )

    _, projection_errors = fold_records(ordered)
    by_id = {record.id: record for record in ordered}
    for error in projection_errors:
        target = by_id.get(error.record_id or "")
        findings.append(_check_projection(target, error))
    return LintReport(findings=tuple(findings))


# $kw: IndexLab.Linter/Context.Unresolved --from POI.Linter
def _check_context_unresolved(
    record: IndexRecord,
    resolution: Resolution[TouchContext],
    error: str | None,
) -> LintFinding | None:
    if resolution.standing != "MISSING":
        return None
    operands = {
        "expected": "MATCHED",
        "actual": "ERROR" if error is not None else "MISSING",
    }
    if error is not None:
        operands["error"] = error
    return _finding(
        record,
        "IndexLab.Linter/Context.Unresolved",
        "blocked",
        operands=operands,
        check=_check_context_unresolved,
    )


# $kw: IndexLab.Linter/Context.Malformed --from POI.Linter
def _check_context_malformed(
    record: IndexRecord,
    resolution: Resolution[TouchContext],
) -> LintFinding | None:
    if resolution.standing != "MALFORMED":
        return None
    operands: dict[str, object] = {"expected": "MATCHED", "actual": "MALFORMED"}
    if resolution.detail is not None:
        operands["detail"] = resolution.detail
    return _finding(
        record,
        "IndexLab.Linter/Context.Malformed",
        "blocked",
        operands=operands,
        check=_check_context_malformed,
    )


# $kw: IndexLab.Linter/Context.Amended --from POI.Linter
def _check_context_amended(
    record: IndexRecord,
    resolution: Resolution[TouchContext],
) -> LintFinding | None:
    if resolution.standing != "AMENDED":
        return None
    return _finding(
        record,
        "IndexLab.Linter/Context.Amended",
        "failed",
        operands={"expected": "MATCHED", "actual": "AMENDED"},
        check=_check_context_amended,
    )


# $kw: IndexLab.Linter/Support.Empty --from POI.Linter
def _check_support_empty(record: IndexRecord) -> LintFinding | None:
    actual = len(record.support.neighborhoods)
    if actual:
        return None
    return _finding(
        record,
        "IndexLab.Linter/Support.Empty",
        "failed",
        operands={"expected_minimum": 1, "actual": actual},
        check=_check_support_empty,
    )


# $kw: IndexLab.Linter/Support.NeighborhoodEmpty --from POI.Linter
def _check_neighborhood_empty(
    record: IndexRecord,
    neighborhood: EvidenceNeighborhood,
    neighborhood_index: int,
) -> LintFinding | None:
    actual = len(neighborhood.grounding)
    if actual:
        return None
    return _finding(
        record,
        "IndexLab.Linter/Support.NeighborhoodEmpty",
        "failed",
        operands={"expected_minimum": 1, "actual": actual},
        target={"neighborhood": neighborhood_index},
        check=_check_neighborhood_empty,
    )


def _lint_support_ref(
    *,
    record: IndexRecord,
    source: UserTouchSource,
    context: Resolution[TouchContext],
    session: str,
    ref: MessageRef,
    role: str,
) -> tuple[LintFinding, ...]:
    error: str | None = None
    try:
        resolution = source.resolve_message(session, ref)
    except Exception as exc:
        resolution = Resolution[TouchMessage](standing="MISSING", value=None)
        error = str(exc)
    target = {"session": session, "message": ref.address, "role": role}
    findings: list[LintFinding] = []
    malformed = _check_support_malformed(record, resolution, target)
    _append(findings, malformed)
    unresolved = None
    if malformed is None:
        unresolved = _check_support_unresolved(record, resolution, target, error)
        _append(findings, unresolved)
    if malformed is not None or unresolved is not None or resolution.value is None:
        return tuple(findings)
    _append(findings, _check_support_amended(record, resolution, target))
    if role == "grounding":
        _append(findings, _check_grounding_side(record, resolution.value, target))
    else:
        _append(findings, _check_context_side(record, resolution.value, target))
    _append(
        findings,
        _check_outside_visible_context(
            record,
            context,
            resolution.value,
            session,
            target,
        ),
    )
    return tuple(findings)


# $kw: IndexLab.Linter/Support.Unresolved --from POI.Linter
def _check_support_unresolved(
    record: IndexRecord,
    resolution: Resolution[TouchMessage],
    target: dict[str, object],
    error: str | None,
) -> LintFinding | None:
    if resolution.standing != "MISSING" and resolution.value is not None:
        return None
    operands = {
        "expected": "MATCHED",
        "actual": "ERROR" if error is not None else "MISSING",
    }
    if error is not None:
        operands["error"] = error
    return _finding(
        record,
        "IndexLab.Linter/Support.Unresolved",
        "blocked",
        operands=operands,
        target=target,
        check=_check_support_unresolved,
    )


# $kw: IndexLab.Linter/Support.Malformed --from POI.Linter
def _check_support_malformed(
    record: IndexRecord,
    resolution: Resolution[TouchMessage],
    target: dict[str, object],
) -> LintFinding | None:
    """The referenced material is present but unreadable."""

    if resolution.standing != "MALFORMED":
        return None
    operands: dict[str, object] = {"expected": "MATCHED", "actual": "MALFORMED"}
    if resolution.detail is not None:
        operands["detail"] = resolution.detail
    return _finding(
        record,
        "IndexLab.Linter/Support.Malformed",
        "blocked",
        operands=operands,
        target=target,
        check=_check_support_malformed,
    )


# $kw: IndexLab.Linter/Support.Amended --from POI.Linter
def _check_support_amended(
    record: IndexRecord,
    resolution: Resolution[TouchMessage],
    target: dict[str, object],
) -> LintFinding | None:
    if resolution.standing != "AMENDED":
        return None
    return _finding(
        record,
        "IndexLab.Linter/Support.Amended",
        "failed",
        operands={"expected": "MATCHED", "actual": "AMENDED"},
        target=target,
        check=_check_support_amended,
    )


# $kw: IndexLab.Linter/Support.GroundingSide --from POI.Linter
def _check_grounding_side(
    record: IndexRecord,
    message: TouchMessage,
    target: dict[str, object],
) -> LintFinding | None:
    if message.side == "user":
        return None
    return _finding(
        record,
        "IndexLab.Linter/Support.GroundingSide",
        "failed",
        operands={"expected": "user", "actual": message.side},
        target=target,
        check=_check_grounding_side,
    )


# $kw: IndexLab.Linter/Support.ContextSide --from POI.Linter
def _check_context_side(
    record: IndexRecord,
    message: TouchMessage,
    target: dict[str, object],
) -> LintFinding | None:
    if message.side == "agent":
        return None
    return _finding(
        record,
        "IndexLab.Linter/Support.ContextSide",
        "failed",
        operands={"expected": "agent", "actual": message.side},
        target=target,
        check=_check_context_side,
    )


# $kw: IndexLab.Linter/Support.OutsideVisibleContext --from POI.Linter
def _check_outside_visible_context(
    record: IndexRecord,
    context: Resolution[TouchContext],
    message: TouchMessage,
    session: str,
    target: dict[str, object],
) -> LintFinding | None:
    if (
        session != record.context.session
        or context.value is None
        or message.turn_ordinal <= context.value.horizon_ordinal
    ):
        return None
    return _finding(
        record,
        "IndexLab.Linter/Support.OutsideVisibleContext",
        "failed",
        operands={
            "expected_turn_maximum": context.value.horizon_ordinal,
            "actual_turn": message.turn_ordinal,
        },
        target=target,
        check=_check_outside_visible_context,
    )


# $kw: IndexLab.Linter/Projection.Invalid --from POI.Linter
def _check_projection(
    record: IndexRecord | None,
    error: ProjectionError,
) -> LintFinding:
    """Attribute a fold failure to the record the fold itself named."""

    operands = {"expected": "VALID", "actual": str(error)}
    if record is None:
        return _structural_finding(
            "IndexLab.Linter/Projection.Invalid",
            subject={"record_id": error.record_id or "<unattributed>"},
            operands=operands,
            check=_check_projection,
        )
    return _finding(
        record,
        "IndexLab.Linter/Projection.Invalid",
        "failed",
        operands=operands,
        check=_check_projection,
    )


def _structural_finding(
    poi_class: str,
    *,
    subject: dict[str, object],
    operands: dict[str, object],
    check: Callable[..., object],
) -> LintFinding:
    """A finding about the corpus itself, with no readable Record.Context to cite."""

    surface: dict[str, object] = {"session": None, "horizon": None}
    return LintFinding(
        identity=_identity(poi_class, subject, surface),
        poi_class=poi_class,
        subject=subject,
        operands=operands,
        status="failed",
        surface=surface,
        source=_source_of(check),
    )


def _finding(
    record: IndexRecord,
    poi_class: str,
    status: FindingStanding,
    *,
    operands: dict[str, object],
    check: Callable[..., object],
    target: dict[str, object] | None = None,
) -> LintFinding:
    subject = {"record_id": record.id, **(target or {})}
    surface = {
        "session": record.context.session,
        "horizon": record.context.horizon.to_dict(),
    }
    return LintFinding(
        identity=_identity(poi_class, subject, surface),
        poi_class=poi_class,
        subject=subject,
        operands=operands,
        status=status,
        surface=surface,
        source=_source_of(check),
    )


def _identity(
    poi_class: str,
    subject: dict[str, object],
    surface: dict[str, object],
) -> str:
    """Stable POI identity over class, subject, and surface; operands excluded."""

    payload = json.dumps(
        [poi_class, subject, surface],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"poi-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _source_of(check: Callable[..., object]) -> str:
    code = check.__code__  # type: ignore[attr-defined]
    return f"{Path(code.co_filename).name}:{code.co_firstlineno}"


def _append(findings: list[LintFinding], finding: LintFinding | None) -> None:
    if finding is not None:
        findings.append(finding)


__all__ = [
    "FindingStanding",
    "LintFinding",
    "LintReport",
    "lint_records",
    "lint_store",
]
