# $kw: --from POI.Linter --note [DC] IndexLab owns its Floor.Model and checks while the shared POI runtime owns selection, execution, standings, and reporting
from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Iterable, Mapping

from tarav._core.errors import CliError
from tarav.poi.runtime import (
    Check,
    Finding,
    LintReport,
    Status,
    Tier,
    run_checks,
)

from .model import IndexRecord, MessageRef
from .projection import fold_records
from .touch import Resolution, TouchContext, TouchMessage, UserTouchSource
from .workspace import CargoDefect, RecordStore


@dataclass(slots=True)
class IndexLabLintContext:
    """One resolved IndexLab linter run over a stable record corpus."""

    source: UserTouchSource
    records: tuple[IndexRecord, ...]
    defects: tuple[CargoDefect, ...] = ()
    subjects: frozenset[str] | None = None
    tripwires: tuple[str, ...] = ()
    workspace_id: str | None = None
    workspace_root: str | None = None
    touch_adapter: str | None = None
    produced: set[str] = field(default_factory=set)
    _contexts: dict[str, tuple[Resolution[TouchContext], str | None]] = field(
        default_factory=dict
    )
    _messages: dict[
        tuple[str, str, str], tuple[Resolution[TouchMessage], str | None]
    ] = field(default_factory=dict)

    def selected_records(self) -> tuple[IndexRecord, ...]:
        if self.subjects is None:
            return self.records
        return tuple(record for record in self.records if record.id in self.subjects)

    def is_selected(self, record_id: str | None) -> bool:
        return self.subjects is None or record_id in self.subjects

    def resolve_context(
        self, record: IndexRecord
    ) -> tuple[Resolution[TouchContext], str | None]:
        cached = self._contexts.get(record.id)
        if cached is not None:
            return cached
        try:
            result = (self.source.resolve_context(record.context), None)
        except Exception as exc:  # adapters are external read boundaries
            result = (
                Resolution[TouchContext](standing="MISSING", value=None),
                str(exc),
            )
        self._contexts[record.id] = result
        return result

    def resolve_message(
        self, session: str, ref: MessageRef
    ) -> tuple[Resolution[TouchMessage], str | None]:
        key = (session, ref.address, ref.hash)
        cached = self._messages.get(key)
        if cached is not None:
            return cached
        try:
            result = (self.source.resolve_message(session, ref), None)
        except Exception as exc:  # adapters are external read boundaries
            result = (
                Resolution[TouchMessage](standing="MISSING", value=None),
                str(exc),
            )
        self._messages[key] = result
        return result


# $kw: --note [DC] the structural tier runs first and stops the run because linting past unreadable cargo examines a silently truncated corpus
def lint_store(
    store: RecordStore,
    *,
    source: UserTouchSource,
    check: Iterable[str] | None = None,
    skip: Iterable[str] | None = None,
    dev: bool = False,
    subjects: Iterable[str] | None = None,
    tripwires: Iterable[str] | None = None,
) -> LintReport:
    records, defects = store.load()
    selected_tripwires = _tripwires(tripwires)
    context = IndexLabLintContext(
        source=source,
        records=_ordered(records),
        defects=tuple(defects),
        subjects=_subjects(subjects, records),
        tripwires=selected_tripwires,
        workspace_id=store.workspace.id,
        workspace_root=str(store.workspace.root),
        touch_adapter=store.workspace.touch_adapter,
    )
    return _run(context, check=check, skip=skip, dev=dev)


def lint_records(
    records: Iterable[IndexRecord],
    *,
    source: UserTouchSource,
    check: Iterable[str] | None = None,
    skip: Iterable[str] | None = None,
    dev: bool = False,
    subjects: Iterable[str] | None = None,
    tripwires: Iterable[str] | None = None,
) -> LintReport:
    ordered = _ordered(records)
    selected_tripwires = _tripwires(tripwires)
    context = IndexLabLintContext(
        source=source,
        records=ordered,
        subjects=_subjects(subjects, ordered),
        tripwires=selected_tripwires,
    )
    return _run(context, check=check, skip=skip, dev=dev)


def _run(
    context: IndexLabLintContext,
    *,
    check: Iterable[str] | None,
    skip: Iterable[str] | None,
    dev: bool,
) -> LintReport:
    selected_checks = _checks_for_run(check, context.tripwires)
    return run_checks(
        context,
        CHECK_REGISTRY,
        check=selected_checks,
        skip=skip,
        dev=dev,
        targeted=context.subjects is not None,
        execution=_execution,
    )


def _execution(context: IndexLabLintContext) -> dict[str, object]:
    payload: dict[str, object] = {
        "records_loaded": len(context.records),
        "records_selected": len(context.selected_records()),
        "cargo_defects": len(context.defects),
    }
    if context.tripwires:
        payload["tripwires"] = list(context.tripwires)
    for key, value in (
        ("workspace_id", context.workspace_id),
        ("workspace_root", context.workspace_root),
        ("touch_adapter", context.touch_adapter),
    ):
        if value is not None:
            payload[key] = value
    return payload


# $kw: IndexLab.Linter/Record.Unloadable --from POI.Linter
class RecordsLoadableCheck(Check[IndexLabLintContext]):
    name = "records-loadable"
    tier = Tier.STRUCTURAL

    def run(self) -> list[Finding]:
        """Every stored cargo item must decode before corpus checks are meaningful."""

        return [
            Finding(
                "IndexLab.Linter/Record.Unloadable",
                {"record_id": defect.record_id or "<unidentified>"},
                {"expected": "LOADABLE", "actual": defect.error},
                surface={"workspace": self.context.workspace_root},
            )
            for defect in self.context.defects
        ]


# $kw: IndexLab.Linter/Tripwire.Hit --from POI.Linter
class TripwireCheck(Check[IndexLabLintContext]):
    name = "tripwire"
    default_on = False
    resolutions = (
        "remove the runtime tripwire when the probe has served its purpose",
        "narrow the run when only one record should exercise the report path",
    )

    def run(self) -> list[Finding]:
        """Emit one POI for every literal tripwire occurrence in record strings."""

        findings: list[Finding] = []
        for record in self.context.selected_records():
            for field_path, value in _string_leaves(record.to_dict()):
                for tripwire in self.context.tripwires:
                    for occurrence, offset in enumerate(
                        _substring_offsets(value, tripwire), start=1
                    ):
                        findings.append(
                            _finding(
                                record,
                                "IndexLab.Linter/Tripwire.Hit",
                                {
                                    "offset": offset,
                                    "excerpt": _excerpt(value, offset, tripwire),
                                },
                                target={
                                    "field_path": field_path,
                                    "tripwire": tripwire,
                                    "occurrence": occurrence,
                                },
                            )
                        )
        return findings


# $kw: IndexLab.Linter/Context.Unresolved --from POI.Linter
# $kw: IndexLab.Linter/Context.Malformed --from POI.Linter
# $kw: IndexLab.Linter/Context.Amended --from POI.Linter
class ContextResolvesCheck(Check[IndexLabLintContext]):
    name = "context-resolves"

    def run(self) -> list[Finding]:
        """Each producer context must remain resolvable and unamended."""

        findings: list[Finding] = []
        for record in self.context.selected_records():
            resolution, error = self.context.resolve_context(record)
            if resolution.standing == "MISSING":
                operands: dict[str, object] = {
                    "expected": "MATCHED",
                    "actual": "ERROR" if error else "MISSING",
                }
                if error:
                    operands["error"] = error
                findings.append(
                    _finding(
                        record,
                        "IndexLab.Linter/Context.Unresolved",
                        operands,
                        status=Status.BLOCKED,
                    )
                )
            elif resolution.standing == "MALFORMED":
                operands = {"expected": "MATCHED", "actual": "MALFORMED"}
                if resolution.detail is not None:
                    operands["detail"] = resolution.detail
                findings.append(
                    _finding(
                        record,
                        "IndexLab.Linter/Context.Malformed",
                        operands,
                        status=Status.BLOCKED,
                    )
                )
            elif resolution.standing == "AMENDED":
                findings.append(
                    _finding(
                        record,
                        "IndexLab.Linter/Context.Amended",
                        {"expected": "MATCHED", "actual": "AMENDED"},
                    )
                )
        return findings


# $kw: IndexLab.Linter/Support.Empty --from POI.Linter
# $kw: IndexLab.Linter/Support.NeighborhoodEmpty --from POI.Linter
class SupportPresentCheck(Check[IndexLabLintContext]):
    name = "support-present"

    def run(self) -> list[Finding]:
        """Every record and neighborhood must carry grounding material."""

        findings: list[Finding] = []
        for record in self.context.selected_records():
            if not record.support.neighborhoods:
                findings.append(
                    _finding(
                        record,
                        "IndexLab.Linter/Support.Empty",
                        {"expected_minimum": 1, "actual": 0},
                    )
                )
            for index, neighborhood in enumerate(record.support.neighborhoods):
                if not neighborhood.grounding:
                    findings.append(
                        _finding(
                            record,
                            "IndexLab.Linter/Support.NeighborhoodEmpty",
                            {"expected_minimum": 1, "actual": 0},
                            target={"neighborhood": index},
                        )
                    )
        return findings


# $kw: IndexLab.Linter/Support.Unresolved --from POI.Linter
# $kw: IndexLab.Linter/Support.Malformed --from POI.Linter
# $kw: IndexLab.Linter/Support.Amended --from POI.Linter
class SupportResolvesCheck(Check[IndexLabLintContext]):
    name = "support-resolves"

    def run(self) -> list[Finding]:
        """Every referenced support message must remain readable and unamended."""

        findings: list[Finding] = []
        for record, session, ref, role in _support_refs(
            self.context.selected_records()
        ):
            resolution, error = self.context.resolve_message(session, ref)
            target = {"session": session, "message": ref.address, "role": role}
            if resolution.standing == "MALFORMED":
                operands: dict[str, object] = {
                    "expected": "MATCHED",
                    "actual": "MALFORMED",
                }
                if resolution.detail is not None:
                    operands["detail"] = resolution.detail
                findings.append(
                    _finding(
                        record,
                        "IndexLab.Linter/Support.Malformed",
                        operands,
                        target=target,
                        status=Status.BLOCKED,
                    )
                )
            elif resolution.standing == "MISSING" or resolution.value is None:
                operands = {
                    "expected": "MATCHED",
                    "actual": "ERROR" if error else "MISSING",
                }
                if error:
                    operands["error"] = error
                findings.append(
                    _finding(
                        record,
                        "IndexLab.Linter/Support.Unresolved",
                        operands,
                        target=target,
                        status=Status.BLOCKED,
                    )
                )
            elif resolution.standing == "AMENDED":
                findings.append(
                    _finding(
                        record,
                        "IndexLab.Linter/Support.Amended",
                        {"expected": "MATCHED", "actual": "AMENDED"},
                        target=target,
                    )
                )
        return findings


# $kw: IndexLab.Linter/Support.GroundingSide --from POI.Linter
# $kw: IndexLab.Linter/Support.ContextSide --from POI.Linter
class SupportRolesCheck(Check[IndexLabLintContext]):
    name = "support-roles"
    requires = ("support-resolves",)

    def run(self) -> list[Finding]:
        """Grounding refs must be user-side and contextual refs agent-side."""

        findings: list[Finding] = []
        for record, session, ref, role in _support_refs(
            self.context.selected_records()
        ):
            resolution, _ = self.context.resolve_message(session, ref)
            if resolution.value is None:
                continue
            expected = "user" if role == "grounding" else "agent"
            if resolution.value.side == expected:
                continue
            poi_class = (
                "IndexLab.Linter/Support.GroundingSide"
                if role == "grounding"
                else "IndexLab.Linter/Support.ContextSide"
            )
            findings.append(
                _finding(
                    record,
                    poi_class,
                    {"expected": expected, "actual": resolution.value.side},
                    target={
                        "session": session,
                        "message": ref.address,
                        "role": role,
                    },
                )
            )
        return findings


# $kw: IndexLab.Linter/Support.OutsideVisibleContext --from POI.Linter
class SupportVisibleCheck(Check[IndexLabLintContext]):
    name = "support-visible"
    requires = ("context-resolves", "support-resolves")

    def run(self) -> list[Finding]:
        """Same-chat support must not occur after the producer horizon."""

        findings: list[Finding] = []
        for record, session, ref, role in _support_refs(
            self.context.selected_records()
        ):
            producer, _ = self.context.resolve_context(record)
            message, _ = self.context.resolve_message(session, ref)
            if (
                session != record.context.session
                or producer.value is None
                or message.value is None
                or message.value.turn_ordinal <= producer.value.horizon_ordinal
            ):
                continue
            findings.append(
                _finding(
                    record,
                    "IndexLab.Linter/Support.OutsideVisibleContext",
                    {
                        "expected_turn_maximum": producer.value.horizon_ordinal,
                        "actual_turn": message.value.turn_ordinal,
                    },
                    target={
                        "session": session,
                        "message": ref.address,
                        "role": role,
                    },
                )
            )
        return findings


# $kw: IndexLab.Linter/Projection.Invalid --from POI.Linter
class ProjectionValidCheck(Check[IndexLabLintContext]):
    name = "projection-valid"

    def run(self) -> list[Finding]:
        """The complete ordered corpus must fold into one coherent projection."""

        _, errors = fold_records(self.context.records)
        records = {record.id: record for record in self.context.records}
        findings: list[Finding] = []
        for error in errors:
            if not self.context.is_selected(error.record_id):
                continue
            record = records.get(error.record_id or "")
            operands = {"expected": "VALID", "actual": str(error)}
            if record is None:
                findings.append(
                    Finding(
                        "IndexLab.Linter/Projection.Invalid",
                        {"record_id": error.record_id or "<unattributed>"},
                        operands,
                        surface={"workspace": self.context.workspace_root},
                    )
                )
            else:
                findings.append(
                    _finding(
                        record,
                        "IndexLab.Linter/Projection.Invalid",
                        operands,
                    )
                )
        return findings


CHECK_REGISTRY: tuple[type[Check[IndexLabLintContext]], ...] = (
    RecordsLoadableCheck,
    TripwireCheck,
    ContextResolvesCheck,
    SupportPresentCheck,
    SupportResolvesCheck,
    SupportRolesCheck,
    SupportVisibleCheck,
    ProjectionValidCheck,
)


def _support_refs(
    records: Iterable[IndexRecord],
) -> Iterable[tuple[IndexRecord, str, MessageRef, str]]:
    for record in records:
        for neighborhood in record.support.neighborhoods:
            for role, refs in (
                ("grounding", neighborhood.grounding),
                ("context", neighborhood.context),
            ):
                for ref in refs:
                    yield record, neighborhood.session, ref, role


def _string_leaves(
    value: object,
    path: tuple[str, ...] = (),
) -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        yield _json_pointer(path), value
        return
    if isinstance(value, Mapping):
        for key in sorted(value):
            yield from _string_leaves(value[key], (*path, str(key)))
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _string_leaves(item, (*path, str(index)))


def _json_pointer(path: tuple[str, ...]) -> str:
    return "/" + "/".join(part.replace("~", "~0").replace("/", "~1") for part in path)


def _substring_offsets(value: str, tripwire: str) -> Iterable[int]:
    start = 0
    while True:
        offset = value.find(tripwire, start)
        if offset < 0:
            return
        yield offset
        start = offset + 1


def _excerpt(value: str, offset: int, tripwire: str) -> str:
    start = max(0, offset - 24)
    end = min(len(value), offset + len(tripwire) + 24)
    return value[start:end]


def _finding(
    record: IndexRecord,
    poi_class: str,
    operands: dict[str, object],
    *,
    target: dict[str, object] | None = None,
    status: Status = Status.FAILED,
) -> Finding:
    return Finding(
        poi_class,
        {"record_id": record.id, **(target or {})},
        operands,
        status=status,
        surface={
            "session": record.context.session,
            "horizon": record.context.horizon.to_dict(),
        },
    )


def _subjects(
    values: Iterable[str] | None,
    records: Iterable[IndexRecord],
) -> frozenset[str] | None:
    if values is None:
        return None
    selected = frozenset(values)
    known = {record.id for record in records}
    unknown = selected - known
    if unknown:
        raise CliError("unknown Index.Record id(s): " + ", ".join(sorted(unknown)))
    return selected


def _tripwires(values: Iterable[str] | None) -> tuple[str, ...]:
    selected: list[str] = []
    for value in values or ():
        if not isinstance(value, str) or not value:
            raise CliError("tripwire substring must not be empty")
        if value not in selected:
            selected.append(value)
    return tuple(selected)


def _checks_for_run(
    checks: Iterable[str] | None,
    tripwires: tuple[str, ...],
) -> tuple[str, ...] | None:
    if checks is None:
        if not tripwires:
            return None
        return tuple(
            entry.name
            for entry in CHECK_REGISTRY
            if entry.default_on or entry.name == "tripwire"
        )

    selected = tuple(checks)
    if "tripwire" in selected and not tripwires:
        raise CliError("tripwire check requires at least one --tripwire substring")
    if tripwires and "tripwire" not in selected:
        selected = (*selected, "tripwire")
    return selected


def _ordered(records: Iterable[IndexRecord]) -> tuple[IndexRecord, ...]:
    return tuple(sorted(records, key=lambda record: (record.ordinal, record.id)))


__all__ = [
    "CHECK_REGISTRY",
    "IndexLabLintContext",
    "LintReport",
    "lint_records",
    "lint_store",
]
