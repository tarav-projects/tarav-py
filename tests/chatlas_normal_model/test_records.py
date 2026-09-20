from __future__ import annotations

from tarav.chatlas.normal_model.records import CHATLAS_SEMANTIC_RECORD_TYPES
from tarav.harness import TaravObject
from tarav.runtime import create_runtime


def test_chatlas_semantic_records_are_registered_tarav_objects() -> None:
    runtime = create_runtime()

    for record_type in CHATLAS_SEMANTIC_RECORD_TYPES:
        assert issubclass(record_type, TaravObject)
        assert runtime.records.resolve({"type": record_type.type_name}) is record_type

    assert len({record_type.type_ship for record_type in CHATLAS_SEMANTIC_RECORD_TYPES}) == len(
        CHATLAS_SEMANTIC_RECORD_TYPES
    )
