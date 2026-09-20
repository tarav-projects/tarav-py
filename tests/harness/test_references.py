import hashlib

import pytest
from pydantic import ValidationError

from tarav.harness import isrecordsubclass, issubrecord
from tarav.references import FileReference, Reference
from tarav.references.git import GitFileReference
from tarav.references.structured import StructuredFileReference
from tarav.references.workflow import ReferenceWorkflow


def test_reference_checks_identity_and_hints_never_repair(tmp_path):
    target = tmp_path / "payload"
    target.write_bytes(b"original")
    reference = FileReference(
        {
            "locator": str(target),
            "check": {"sha256": hashlib.sha256(b"original").hexdigest()},
        }
    )
    assert reference.resolve().ok
    target.write_bytes(b"changed")
    reference.record["hints"] = {"sha256": hashlib.sha256(b"changed").hexdigest()}
    assert reference.resolve().status == "mismatch"
    assert target.read_bytes() == b"changed"
    target.unlink()
    other = tmp_path / "other"
    other.write_bytes(b"original")
    reference.record["hints"] = {"path": str(other)}
    result = reference.resolve()
    assert result.status == "unresolvable"
    assert result.hints == {"path": str(other)}
    assert not target.exists()


def test_relative_reference_needs_explicit_context(tmp_path):
    (tmp_path / "payload").write_text("x")
    reference = FileReference(
        {"type": FileReference.type_name, "locator": "payload"}
    )
    assert not reference.resolve().ok
    reference.source = tmp_path / "ref.json"
    assert reference.resolve().target == tmp_path / "payload"


def test_reference_record_interfaces_and_examples():
    for reference_type in (FileReference, GitFileReference, StructuredFileReference):
        assert issubrecord(reference_type, Reference)
        assert isrecordsubclass(reference_type, Reference)
        example = reference_type.json_example()
        assert reference_type.from_json(example).to_json() == example

    value = {"type": FileReference.type_name, "locator": "/example/file.txt"}
    reference = FileReference.from_json(value)
    assert reference.check is None
    assert reference.hints is None
    assert reference.to_json() == value

    with pytest.raises(ValidationError):
        FileReference.from_json({"type": FileReference.type_name})
    with pytest.raises(ValidationError):
        FileReference.from_json({**value, "locator": ""})


def test_reference_workflow_constructs_through_record_interface():
    workflow = ReferenceWorkflow()

    assert not workflow.resolve(
        {"type": FileReference.type_name, "hints": {"name": "missing"}}
    ).ok
