"""External anchors retain identity and evidence without changing their source."""
# tarav.breadcrumb 11c910768ff8

import pytest

from tarav.l1.breadcrumbs import BreadcrumbError, BreadcrumbStore


def anchor(tmp_path, text='one\n  "name": "important"\nthree\n'):
    path = tmp_path / "source.json"
    path.write_text(text)
    store = BreadcrumbStore(tmp_path / "registry")
    breadcrumb = store.create_external(file=path, line=2, fragment='"name": "important"')
    return path, store, breadcrumb.records.to_record()["id"]


def test_external_anchor_leaves_bytes_unchanged_and_resolves_moved_line(tmp_path):
    original = 'one\n  "name": "important"\nthree\n'
    path, store, identity = anchor(tmp_path, original)
    assert path.read_bytes() == original.encode()
    assert store.show(identity)["breadcrumb"]["placement"] == "external"
    assert store.resolve(identity).position.line == 2
    before = store.observations(identity)
    path.write_text("inserted\n" + original)
    assert store.resolve(identity).position.line == 3
    assert store.observations(identity) == before
    assert store.observations(identity)[0]["fragment"] == '"name": "important"'


@pytest.mark.parametrize("deleted_file", [False, True])
def test_missing_external_anchor_keeps_identity_and_attachments(tmp_path, deleted_file):
    path, store, identity = anchor(tmp_path)
    attachment = {"type": "Example.Attachment", "text": "Retained evidence"}
    store.attach(identity, attachment)
    if deleted_file:
        path.unlink()
    else:
        path.write_text("The selected line is gone.\n")
    result = store.resolve(identity)
    assert result.status == "unresolvable"
    assert result.pois[0].records.to_record()["type"].endswith("ExternalAnchorMissing")
    assert store.attachments(identity) == (attachment,)
    assert store.load(identity).records.to_record()["id"] == identity


def test_duplicate_fragments_after_movement_are_ambiguous(tmp_path):
    path, store, identity = anchor(tmp_path)
    path.write_text('"name": "important"\nother\n"name": "important"\n')
    result = store.resolve(identity)
    assert result.status == "ambiguous"
    assert result.pois[0].records.to_record()["type"].endswith("ExternalAnchorAmbiguous")


def test_recorded_line_takes_priority_over_copies_elsewhere(tmp_path):
    path, store, identity = anchor(tmp_path)
    path.write_text(path.read_text() + '"name": "important"\n')
    assert store.resolve(identity).position.line == 2


def test_maintainer_can_append_a_replacement_without_reusing_old_locations(tmp_path):
    path, store, identity = anchor(tmp_path)
    replacement = tmp_path / "replacement.txt"
    replacement.write_text("Replacement selection\n")
    store.observe_external_position(identity, file=replacement, line=1, fragment="Replacement")
    assert store.resolve(identity).position.path == replacement
    assert store.resolve(identity).position.line == 1
    assert len(store.observations(identity)) == 2
    assert path.read_text() == 'one\n  "name": "important"\nthree\n'
    with pytest.raises(BreadcrumbError):
        store.observe_external_position(identity, file=replacement, line=1, fragment="absent")
    assert len(store.observations(identity)) == 2


@pytest.mark.parametrize("line,fragment", [(0, "value"), (3, "value"), (1, ""), (1, "\n"), (1, "absent")])
def test_invalid_external_selection_does_not_create_records(tmp_path, line, fragment):
    path = tmp_path / "source.json"
    path.write_text('{"value": 1}\n')
    store = BreadcrumbStore(tmp_path / "registry")
    with pytest.raises(BreadcrumbError):
        store.create_external(file=path, line=line, fragment=fragment)
    assert not store.root.exists()
