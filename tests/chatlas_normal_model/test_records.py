from __future__ import annotations

from tarav.l0.kernel import entity

from tarav.l1.chatlas.normal_model import ChatlasNormalModel
from tarav.l1.chatlas.normal_model.records import CHATLAS_SEMANTIC_RECORD_TYPES
from tarav.l0.kernel import TaravObject
from tarav.l3.runtime import create_runtime


def test_chatlas_semantic_records_are_registered_tarav_objects() -> None:
    runtime = create_runtime()

    for record_type in (ChatlasNormalModel, *CHATLAS_SEMANTIC_RECORD_TYPES):
        assert issubclass(record_type, TaravObject)
        assert runtime.records.resolve({"type": entity(record_type).name}) is record_type

    record_types = (ChatlasNormalModel, *CHATLAS_SEMANTIC_RECORD_TYPES)
    assert len({entity(record_type).id for record_type in record_types}) == len(record_types)
