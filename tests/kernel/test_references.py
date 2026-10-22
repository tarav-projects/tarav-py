from tarav.l0.kernel import entity

import hashlib

import pytest
from pydantic import ValidationError

from tarav.l1.archive.references import DOILocator, DOIReference
from tarav.l1.chatlas.references import ChatlasTurnLocator, EmptyReferenceCheck
from tarav.l0.kernel import TaravObject, isrecordsubclass, issubrecord
from tarav.l1.references import (
    FilePositionCheck,
    FilePositionLocator,
    FilePositionReference,
    FileReference,
    Reference,
    ReferenceTaravMetadata,
    Sha256Check,
)
from tarav.l1.references.git import GitFileLocator, GitFileReference, GitOidCheck
from tarav.l1.references.structured import StructuredFileLocator, StructuredFileReference
from tarav.l1.references.workflow import ReferenceService


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
    reference._fields["hints"] = {"sha256": hashlib.sha256(b"changed").hexdigest()}
    assert reference.resolve().status == "mismatch"
    assert target.read_bytes() == b"changed"
    target.unlink()
    other = tmp_path / "other"
    other.write_bytes(b"original")
    reference._fields["hints"] = {"path": str(other)}
    result = reference.resolve()
    assert result.status == "unresolvable"
    assert result.hints == {"path": str(other)}
    assert not target.exists()


def test_relative_reference_needs_explicit_context(tmp_path):
    (tmp_path / "payload").write_text("x")
    reference = FileReference({"type": entity(FileReference).name, "locator": "payload"})
    assert not reference.resolve().ok
    reference.source = tmp_path / "ref.json"
    assert reference.resolve().target == tmp_path / "payload"


# tarav.breadcrumb f8de67c8f3bf
def test_reference_record_interfaces_and_examples():
    for reference_type in (
        FileReference,
        FilePositionReference,
        GitFileReference,
        StructuredFileReference,
        DOIReference,
    ):
        assert issubrecord(reference_type, Reference)
        assert isrecordsubclass(reference_type, Reference)
        example = reference_type.records.record_example()
        assert reference_type.records.from_record(example).records.to_record() == example

    value = {"type": entity(FileReference).name, "locator": "/example/file.txt"}
    reference = FileReference.records.from_record(value)
    assert reference.check is None
    assert reference.hints is None
    assert reference.records.to_record() == value

    with pytest.raises(ValidationError):
        FileReference.records.from_record({"type": entity(FileReference).name})
    with pytest.raises(ValidationError):
        FileReference.records.from_record({**value, "locator": ""})


def test_embedded_reference_interfaces_share_tarav_object_record_root():
    interfaces = (
        Sha256Check,
        ReferenceTaravMetadata,
        GitFileLocator,
        GitOidCheck,
        StructuredFileLocator,
        DOILocator,
        ChatlasTurnLocator,
        EmptyReferenceCheck,
        FilePositionLocator,
        FilePositionCheck,
    )

    assert all(
        issubclass(interface, TaravObject.RecordInterface) for interface in interfaces
    )
    assert all(not issubclass(interface, TaravObject) for interface in interfaces)


def test_file_position_reference_accepts_cheap_and_rich_file_values(tmp_path):
    target = tmp_path / "surface.md"
    target.write_text("first\nanchor\nlast\n", encoding="utf-8")

    cheap = FilePositionReference.records.from_record(
        {
            "type": entity(FilePositionReference).name,
            "locator": {"file": str(target), "line": 2},
            "check": {"contains": "anchor"},
            "hints": {"previous_line": "wrong"},
        }
    )
    assert cheap.resolve().target.text == "anchor"

    rich = FilePositionReference.records.from_record(
        {
            "type": entity(FilePositionReference).name,
            "locator": {
                "file": {"type": entity(FileReference).name, "locator": str(target)},
                "line": 2,
            },
        }
    )
    assert rich.resolve().target.path == target

    cheap._fields["locator"]["line"] = 1
    assert cheap.resolve().status == "mismatch"

    relative = FilePositionReference.records.from_record(
        {
            "type": entity(FilePositionReference).name,
            "locator": {"file": "surface.md", "line": 2},
        }
    )
    assert relative.resolve().status == "unresolvable"
    relative.source = tmp_path / "position.json"
    assert relative.resolve().target.path == target


def test_reference_workflow_constructs_through_record_interface():
    workflow = ReferenceService()

    assert not workflow.resolve(
        {"type": entity(FileReference).name, "hints": {"name": "missing"}}
    ).ok
