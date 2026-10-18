"""The record loading workflow: the official road from a Record to an instance.

A Record is input material, not runtime state. Loading fills one
``RecordLoadingContext`` step by step (read, resolve the Type, check its
reference, parse, build) and hands the Type's builder a ``LoadedRecord``: the
parsed data and the loading metadata this workflow chose to give. Nothing else
about the loading reaches the instance; the context is discarded once it is
built.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from .records import TaravObject
    from .types import TypeRegistry


# tarav.breadcrumb 6ecc299ebaed
# tarav.breadcrumb b548804330bb
# tarav.breadcrumb b40281463c5c
CHECK_LEVELS = ("none", "lite", "default", "full")


@dataclass(frozen=True, slots=True)
class RecordLoadingConfig:
    """What the loading steps react to; shared by every load that uses it.

    ``level`` selects how much the parse step checks: ``none`` builds the
    typed data without checks, ``lite`` and ``full`` are the Type's own
    levels, ``default`` its RecordInterface. The level stays in the loading
    phase; whoever lowers it answers for what was loaded.
    """

    level: str = "default"
    source: bool = True

    def __post_init__(self) -> None:
        if self.level not in CHECK_LEVELS:
            raise ValueError(f"Record check level must be one of {', '.join(CHECK_LEVELS)}")


DEFAULT_LOADING = RecordLoadingConfig()


# tarav.breadcrumb 1d23d4edca03
@dataclass(frozen=True, slots=True)
class LoadingMetadata:
    """Facts about the loading the workflow gives to builders."""

    source: Path | None = None


# tarav.breadcrumb df5c3c33c6cb
# tarav.breadcrumb ed9390e3b28f
@dataclass(frozen=True, slots=True)
class LoadedRecord:
    """What a builder receives: the parsed data, not copied, and metadata."""

    data: BaseModel
    metadata: LoadingMetadata = LoadingMetadata()


# tarav.breadcrumb 7affdc9e1988
# tarav.breadcrumb 587865c2e96c
@dataclass(slots=True)
class RecordLoadingContext:
    """One load in progress: configuration plus whatever the steps filled."""

    config: RecordLoadingConfig = DEFAULT_LOADING
    path: Path | None = None
    record: Mapping[str, Any] | None = None
    record_type: type[TaravObject] | None = None
    data: BaseModel | None = None
    instance: TaravObject | None = None
    stage: str = "start"
    error: BaseException | None = None

    def loaded(self) -> LoadedRecord:
        if self.data is None:
            raise RuntimeError("A Record is only loaded once it was parsed")
        source = self.path if self.config.source else None
        return LoadedRecord(self.data, LoadingMetadata(source=source))


Step = Callable[[RecordLoadingContext], None]


def run_steps(context: RecordLoadingContext, steps: tuple[tuple[str, Step], ...]) -> RecordLoadingContext:
    """The internal path: run the steps in order and stop at the first failure."""
    for stage, step in steps:
        context.stage = stage
        try:
            step(context)
        except Exception as exc:  # the context keeps it; the public path raises
            context.error = exc
            break
    return context


def raise_failure(context: RecordLoadingContext) -> TaravObject:
    """The public path: return the instance or raise what stopped the load."""
    if context.error is None:
        assert context.instance is not None
        return context.instance
    where = str(context.path) if context.path is not None else "an in-memory Record"
    context.error.add_note(f"Record loading stopped at {context.stage!r} for {where}")
    raise context.error


def read_step(path: Path) -> Step:
    def read(context: RecordLoadingContext) -> None:
        from .records import InvalidRecordJSON

        context.path = path
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
        if not isinstance(value, Mapping):
            raise InvalidRecordJSON("Tarav JSON root must be an object")
        context.record = value

    return read


def resolve_step(registry: TypeRegistry) -> Step:
    def resolve(context: RecordLoadingContext) -> None:
        context.record_type = registry.resolve(_record(context))

    return resolve


def check_type(context: RecordLoadingContext) -> None:
    _record_type(context)._check_record_type(_record(context))


def parse(context: RecordLoadingContext) -> None:
    records = _record_type(context).records
    record, level = _record(context), context.config.level
    if level == "none":
        context.data = records._owner.RecordInterface.model_construct(**record)
    elif level == "lite":
        context.data = records._parse_lite(record)
    elif level == "full":
        context.data = records._parse_full(record)
    else:
        context.data = records.parse_record(record)


def build(context: RecordLoadingContext) -> None:
    record_type = _record_type(context)
    result = record_type._from_record(context.loaded())
    if type(result) is not record_type:
        raise TypeError(f"{record_type.__name__}._from_record() must return exact class")
    if record_type.keeps_source:
        result.source = context.loaded().metadata.source
    result._record = context.record
    context.instance = result


def bind_loader_step(registry: TypeRegistry) -> Step:
    def bind_loader(context: RecordLoadingContext) -> None:
        # tarav.breadcrumb 468893297110
        bind = getattr(context.instance, "_bind_record_loader", None)
        if bind is not None:
            bind(registry.from_record)

    return bind_loader


TYPED_STEPS: tuple[tuple[str, Step], ...] = (
    ("check type", check_type),
    ("parse", parse),
    ("build", build),
)


def _record(context: RecordLoadingContext) -> Mapping[str, Any]:
    if context.record is None:
        raise RuntimeError("No Record was read")
    return context.record


def _record_type(context: RecordLoadingContext) -> type[TaravObject]:
    if context.record_type is None:
        raise RuntimeError("No Type was resolved")
    return context.record_type


__all__ = [
    "CHECK_LEVELS",
    "DEFAULT_LOADING",
    "LoadedRecord",
    "LoadingMetadata",
    "RecordLoadingConfig",
    "RecordLoadingContext",
]
