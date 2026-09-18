import hashlib

from tarav.references import FileReference


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
    reference = FileReference({"locator": "payload"})
    assert not reference.resolve().ok
    reference.source = tmp_path / "ref.json"
    assert reference.resolve().target == tmp_path / "payload"
