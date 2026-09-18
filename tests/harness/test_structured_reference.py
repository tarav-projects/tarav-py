import json

from tarav.references.workflow import ReferenceWorkflow


def test_pointer_selection_and_checks_ignore_hints(tmp_path):
    path = tmp_path / "source.json"
    path.write_text(json.dumps({"a/b": {"~key": [None, "value"]}}))
    ref = ReferenceWorkflow().load({"type": "Tarav.Reference.StructuredFile",
        "locator": {"path": "source.json", "pointer": "/a~1b/~0key/1"}})
    ref.source = path
    assert ref.resolve().target == "value"
    ref.record['hints'] = {"path": "missing"}
    assert ref.resolve().ok
    ref.record['check'] = {'sha256': '0' * 64}
    assert ref.resolve().status == 'mismatch'


def test_pointer_errors_and_null_target(tmp_path):
    path = tmp_path / "source.json"
    path.write_text('{"items": [null]}')
    ref = ReferenceWorkflow().load({"type": "Tarav.Reference.StructuredFile",
        "locator": {"path": "source.json", "pointer": "/items/0"}})
    ref.source = path
    assert ref.resolve().ok and ref.resolve().target is None
    for pointer in ('/items/01', '/items/-', '/items/9', '/bad~2', '/missing'):
        ref.record['locator']['pointer'] = pointer
        assert not ref.resolve().ok
