"""Small typed-Record write boundary shared by independent stores."""
# tarav.breadcrumb 6e3337650744

from pathlib import Path

from tarav.l0._core.persistence import atomic_write_json
from tarav.l0.kernel import TaravObject, TypeRegistry
from tarav.l0.kernel.current import current_records


def write_typed_record(
    path: Path, obj: TaravObject, *, records: TypeRegistry[TaravObject] | None = None,
) -> None:
    """Write the exact registered Type after its own Record validation."""
    record = obj.records.to_record()
    selected = records if records is not None else current_records()
    if selected.resolve(record) is not type(obj):
        raise ValueError("Stored object must have its exact registered Type")
    atomic_write_json(path, record)


__all__ = ["write_typed_record"]
