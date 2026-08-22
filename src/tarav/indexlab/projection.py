# $kw: --from User.Touched
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Iterable

from .model import EvidenceNeighborhood, IndexRecord, SupportSet


PROJECTION_SCHEMA = "tarav.indexlab-projection.v1"


# $kw: --note [DC] the offending record travels on the exception itself; attributing a fold failure by parsing its message text is not an identity relation
class ProjectionError(ValueError):
    """A record stream cannot be folded into a coherent semantic projection."""

    def __init__(self, message: str, *, record_id: str | None = None) -> None:
        super().__init__(message)
        self.record_id = record_id

    def to_dict(self) -> dict[str, object]:
        return {"record_id": self.record_id, "error": str(self)}


@dataclass(frozen=True, slots=True)
class ProjectedBlock:
    id: str
    isoblock_id: str
    name: str
    line_ids: tuple[str, ...]
    active: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "isoblock_id": self.isoblock_id,
            "name": self.name,
            "line_ids": list(self.line_ids),
        }


@dataclass(frozen=True, slots=True)
class ProjectedLine:
    id: str
    isoline_id: str
    block_id: str
    label: str
    text: str
    support: SupportSet
    active: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "isoline_id": self.isoline_id,
            "block_id": self.block_id,
            "label": self.label,
            "text": self.text,
            "support": self.support.to_dict(),
        }


class SemanticProjection:
    def __init__(
        self,
        *,
        blocks: dict[str, ProjectedBlock],
        lines: dict[str, ProjectedLine],
    ) -> None:
        self._blocks = dict(blocks)
        self._lines = dict(lines)

    @property
    def blocks(self) -> tuple[ProjectedBlock, ...]:
        return tuple(block for block in self._blocks.values() if block.active)

    @property
    def lines(self) -> tuple[ProjectedLine, ...]:
        return tuple(line for line in self._lines.values() if line.active)

    def block(self, block_id: str) -> ProjectedBlock:
        try:
            return self._blocks[block_id]
        except KeyError as exc:
            raise KeyError(f"unknown Block.Id: {block_id}") from exc

    def line(self, line_id: str) -> ProjectedLine:
        try:
            return self._lines[line_id]
        except KeyError as exc:
            raise KeyError(f"unknown Line.Id: {line_id}") from exc

    def line_by_label(self, label: str) -> ProjectedLine:
        matches = [line for line in self._lines.values() if line.label == label]
        if len(matches) != 1:
            raise KeyError(f"line label must resolve exactly once: {label}")
        return matches[0]

    def isoline_support(self, isoline_id: str) -> SupportSet:
        return union_support(
            *(
                line.support
                for line in self._lines.values()
                if line.isoline_id == isoline_id
            )
        )

    def block_support(self, block_id: str) -> SupportSet:
        block = self.block(block_id)
        return union_support(
            *(
                self.isoline_support(self.line(line_id).isoline_id)
                for line_id in block.line_ids
            )
        )

    def to_dict(self) -> dict[str, object]:
        active_blocks = self.blocks
        isolines = tuple(dict.fromkeys(line.isoline_id for line in self.lines))
        return {
            "schema": PROJECTION_SCHEMA,
            "blocks": [block.to_dict() for block in active_blocks],
            "lines": [line.to_dict() for line in self.lines],
            "isolines": [
                {
                    "isoline_id": isoline_id,
                    "support": self.isoline_support(isoline_id).to_dict(),
                }
                for isoline_id in isolines
            ],
        }


def union_support(*sets: SupportSet) -> SupportSet:
    seen: set[str] = set()
    neighborhoods: list[EvidenceNeighborhood] = []
    for support in sets:
        for neighborhood in support.neighborhoods:
            key = json.dumps(
                neighborhood.to_dict(),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            if key in seen:
                continue
            seen.add(key)
            neighborhoods.append(neighborhood)
    return SupportSet(neighborhoods=tuple(neighborhoods))


def project_records(records: Iterable[IndexRecord]) -> SemanticProjection:
    """Fold records into the current projection, raising on the first bad record."""

    projection, errors = fold_records(records)
    if errors:
        raise errors[0]
    return projection


# $kw: --note [DC] the fold collects every inapplicable record and continues rather than raising on the first, so one run reports all independently broken records instead of forcing a serial repair loop --note [DC] each record applies against a staged copy so a record rejected partway leaves no partial mutation in the projection
def fold_records(
    records: Iterable[IndexRecord],
) -> tuple[SemanticProjection, tuple[ProjectionError, ...]]:
    """Fold records, skipping and collecting every record that cannot be applied."""

    ordered = sorted(records, key=lambda record: (record.ordinal, record.id))
    ordinals: set[int] = set()
    blocks: dict[str, ProjectedBlock] = {}
    lines: dict[str, ProjectedLine] = {}
    errors: list[ProjectionError] = []

    for record in ordered:
        if record.ordinal <= 0:
            errors.append(
                ProjectionError(
                    f"record {record.id}: persisted ordinal must be greater than zero",
                    record_id=record.id,
                )
            )
            continue
        if record.ordinal in ordinals:
            errors.append(
                ProjectionError(
                    f"record {record.id}: duplicate ordinal {record.ordinal}",
                    record_id=record.id,
                )
            )
            continue
        ordinals.add(record.ordinal)
        staged_blocks = dict(blocks)
        staged_lines = dict(lines)
        try:
            _apply_record(record, staged_blocks, staged_lines)
        except ProjectionError as exc:
            errors.append(
                ProjectionError(f"record {record.id}: {exc}", record_id=record.id)
            )
            continue
        blocks = staged_blocks
        lines = staged_lines

    return (
        SemanticProjection(blocks=blocks, lines=lines),
        tuple(errors),
    )


def _apply_record(
    record: IndexRecord,
    blocks: dict[str, ProjectedBlock],
    lines: dict[str, ProjectedLine],
) -> None:
    operation = record.operation.type
    parameters = record.operation.parameters
    if operation == "block.create":
        block_id = _required_text(parameters, "block_id")
        isoblock_id = _required_text(parameters, "isoblock_id")
        name = _required_text(parameters, "name")
        _require_new(blocks, block_id, kind="Block.Id")
        if any(block.active and block.isoblock_id == isoblock_id for block in blocks.values()):
            raise ProjectionError(
                f"active Isoblock.Id {isoblock_id} already exists; use block.rename"
            )
        blocks[block_id] = ProjectedBlock(
            id=block_id,
            isoblock_id=isoblock_id,
            name=name,
            line_ids=(),
        )
        return

    if operation == "block.rename":
        source_id = _required_text(parameters, "block_id")
        new_id = _required_text(parameters, "new_block_id")
        isoblock_id = _required_text(parameters, "isoblock_id")
        name = _required_text(parameters, "name")
        source = _active_block(blocks, source_id)
        _require_new(blocks, new_id, kind="Block.Id")
        if source.isoblock_id != isoblock_id:
            raise ProjectionError(
                f"block.rename Isoblock.Id {isoblock_id} does not match {source.isoblock_id}"
            )
        if source.name == name:
            raise ProjectionError("block.rename must change the block name")
        blocks[source_id] = replace(source, line_ids=(), active=False)
        blocks[new_id] = ProjectedBlock(
            id=new_id,
            isoblock_id=isoblock_id,
            name=name,
            line_ids=source.line_ids,
        )
        for line_id in source.line_ids:
            lines[line_id] = replace(lines[line_id], block_id=new_id)
        return

    if operation == "line.capture":
        line_id = _required_text(parameters, "line_id")
        isoline_id = _required_text(parameters, "isoline_id")
        block_id = _required_text(parameters, "block_id")
        label = _required_text(parameters, "label")
        text = _required_text(parameters, "text")
        _require_new(lines, line_id, kind="Line.Id")
        if any(line.label == label for line in lines.values()):
            raise ProjectionError(f"line label {label} already exists")
        if not label.startswith("^"):
            raise ProjectionError("line label must begin with '^'")
        block = _active_block(blocks, block_id)
        lines[line_id] = ProjectedLine(
            id=line_id,
            isoline_id=isoline_id,
            block_id=block_id,
            label=label,
            text=text,
            support=record.support,
        )
        blocks[block_id] = replace(
            block,
            line_ids=(*block.line_ids, line_id),
        )
        return

    if operation == "support.add":
        line_id = _required_text(parameters, "line_id")
        line = _line(lines, line_id)
        combined = union_support(line.support, record.support)
        if combined == line.support:
            raise ProjectionError("support.add must contribute new support")
        lines[line_id] = replace(
            line,
            support=combined,
        )
        return

    if operation == "line.reblock":
        source_id = _required_text(parameters, "line_id")
        isoline_id = _required_text(parameters, "isoline_id")
        block_id = _required_text(parameters, "block_id")
        source = _active_line(lines, source_id)
        destination = _active_block(blocks, block_id)
        if source.isoline_id != isoline_id:
            raise ProjectionError(
                f"line.reblock Isoline.Id {isoline_id} does not match {source.isoline_id}"
            )
        if source.block_id == block_id:
            raise ProjectionError("line.reblock destination must differ from its current block")
        source_block = _active_block(blocks, source.block_id)
        blocks[source.block_id] = replace(
            source_block,
            line_ids=tuple(value for value in source_block.line_ids if value != source_id),
        )
        lines[source_id] = replace(source, block_id=block_id)
        blocks[block_id] = replace(
            destination,
            line_ids=(*destination.line_ids, source_id),
        )
        return

    if operation == "isoline.group":
        raw_line_ids = parameters.get("line_ids")
        if not isinstance(raw_line_ids, list) or len(raw_line_ids) < 2:
            raise ProjectionError("isoline.group line_ids must contain at least two ids")
        line_ids = tuple(_plain_text(value, "line_ids member") for value in raw_line_ids)
        if len(set(line_ids)) != len(line_ids):
            raise ProjectionError("isoline.group line_ids must be unique")
        isoline_id = _required_text(parameters, "isoline_id")
        if all(_line(lines, line_id).isoline_id == isoline_id for line_id in line_ids):
            raise ProjectionError("isoline.group must change Isoline membership")
        for line_id in line_ids:
            line = _line(lines, line_id)
            lines[line_id] = replace(line, isoline_id=isoline_id)
        return

    raise ProjectionError(f"unsupported operation type: {operation}")


def _required_text(parameters: dict[str, object], field: str) -> str:
    return _plain_text(parameters.get(field), field)


def _plain_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectionError(f"operation parameter {field} must be a non-empty string")
    return value


def _require_new(values: dict[str, object], key: str, *, kind: str) -> None:
    if key in values:
        raise ProjectionError(f"{kind} {key} already exists")


def _active_block(
    blocks: dict[str, ProjectedBlock],
    block_id: str,
) -> ProjectedBlock:
    try:
        block = blocks[block_id]
    except KeyError as exc:
        raise ProjectionError(f"Block.Id {block_id} does not exist") from exc
    if not block.active:
        raise ProjectionError(f"Block.Id {block_id} is not current")
    return block


def _line(lines: dict[str, ProjectedLine], line_id: str) -> ProjectedLine:
    try:
        return lines[line_id]
    except KeyError as exc:
        raise ProjectionError(f"Line.Id {line_id} does not exist") from exc


def _active_line(lines: dict[str, ProjectedLine], line_id: str) -> ProjectedLine:
    line = _line(lines, line_id)
    if not line.active:
        raise ProjectionError(f"Line.Id {line_id} is not current")
    return line


__all__ = [
    "PROJECTION_SCHEMA",
    "ProjectedBlock",
    "ProjectedLine",
    "ProjectionError",
    "SemanticProjection",
    "fold_records",
    "project_records",
    "union_support",
]
