"""Attic checks observe declared metadata and never inspect payloads."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tarav.l0.kernel import entity
from tarav.l1.attic import Attic, AtticSuite, AtticWorkflow, DepositManifest
from tarav.l1.attic.checks import (
    DuplicateUUID, ListingUnreadable, ManifestInvalid, ManifestMissing, ManifestUnreadable,
)
from tarav.l3.runtime import create_runtime


def manifest(**changes):
    return {"class": "tarav.attic.deposit", "schema_version": 1,
            "uuid": "f5d14a79-2166-4490-ae11-d879530949e9",
            "deposited_at": "2026-10-19T00:00:00Z", "sources": ["/former/source"],
            "material": "material", "reason": "Retired compiler, kept for later investigation",
            "dependency_status": "disconnected", **changes}


def deposit(root, name="one", **changes):
    folder = root / "deposits" / name
    folder.mkdir(parents=True)
    (folder / "deposit.json").write_text(json.dumps(manifest(**changes)))
    return folder


# tarav.breadcrumb ac68264776e8
def test_checks_never_inspect_or_require_material(tmp_path, monkeypatch):
    first = deposit(tmp_path, "one", material="missing/opaque/tree")
    second = deposit(tmp_path, "two", uuid="cdfd1bb8-b568-47e0-9c17-2ae78d60db45")
    (second / "material").symlink_to(tmp_path / "nonexistent")
    original_iterdir, original_read = Path.iterdir, Path.read_text
    inspected = []

    def iterdir(path):
        assert path == tmp_path / "deposits", f"Unexpected traversal: {path}"
        return original_iterdir(path)

    def read(path, *args, **kwargs):
        assert path in {first / "deposit.json", second / "deposit.json"}
        inspected.append(path)
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    monkeypatch.setattr(Path, "read_text", read)
    suite = AtticWorkflow.open(tmp_path).checks.run()
    assert isinstance(suite, AtticSuite)
    assert suite.complete
    assert suite.pois() == ()
    assert inspected == [first / "deposit.json", second / "deposit.json"]


def test_manifest_roundtrip_preserves_optional_depositor_claims():
    value = manifest(source_git={"unverified_claim": 123}, material="material/skills")
    assert DepositManifest.model_validate(value).model_dump(by_alias=True) == value


@pytest.mark.parametrize("changes", [
    {"class": "other"}, {"schema_version": 2}, {"schema_version": True},
    {"schema_version": "1"}, {"uuid": "not-a-uuid"},
    {"deposited_at": "2026-10-19"}, {"deposited_at": "2026-10-19T00:00:00-04:00"},
    {"sources": []}, {"sources": [" "]}, {"sources": "source"},
    {"material": "/outside"}, {"material": "../outside"}, {"material": "."},
    {"material": "deposit.json"}, {"reason": " "}, {"dependency_status": "connected"},
])
def test_manifest_rejects_malformed_declarations(changes):
    with pytest.raises(ValidationError):
        DepositManifest.model_validate(manifest(**changes))


def test_claims_are_not_checked_and_retained_text_is_not_repaired(tmp_path):
    path = deposit(tmp_path, sources=["an unavailable source"],
                   reason="An assertion made by the depositor") / "deposit.json"
    before = path.read_bytes()
    assert Attic(tmp_path).checks.run().pois() == ()
    assert path.read_bytes() == before
    # No payload or former source was required to exist.
    assert sorted(path.parent.iterdir()) == [path]


def test_missing_unreadable_invalid_and_historical_manifests_are_separate(tmp_path):
    missing = tmp_path / "deposits" / "missing"
    missing.mkdir(parents=True)
    unreadable = deposit(tmp_path, "unreadable") / "deposit.json"
    unreadable.write_bytes(b"\xff")
    invalid = deposit(tmp_path, "invalid") / "deposit.json"
    invalid.write_text("not JSON")
    old = deposit(tmp_path, "historical") / "deposit.json"
    old.write_text(json.dumps({"uuid": manifest()["uuid"], "former_location": "/old"}))
    before = old.read_bytes()

    pois = Attic(tmp_path).checks.run().pois()
    assert {poi.situation["deposit"]: type(poi) for poi in pois} == {
        "missing": ManifestMissing, "unreadable": ManifestUnreadable,
        "invalid": ManifestInvalid, "historical": ManifestInvalid}
    assert old.read_bytes() == before


def test_duplicate_uuid_is_metadata_only_and_identity_survives_changes(tmp_path):
    deposit(tmp_path, "one")
    deposit(tmp_path, "two", uuid=manifest()["uuid"].upper())
    pois = Attic(tmp_path).checks.run().pois()
    assert len(pois) == 1 and type(pois[0]) is DuplicateUUID
    assert pois[0].situation == {"root": str(tmp_path), "uuid": manifest()["uuid"]}
    assert pois[0].details == {"deposits": ["one", "two"]}
    identity = pois[0].identity
    deposit(tmp_path, "three")
    assert Attic(tmp_path).checks.run().pois()[0].identity == identity


def test_absent_depot_stays_absent(tmp_path):
    root = tmp_path / "absent"
    assert Attic(root).checks.run().pois() == ()
    assert not root.exists()


def test_listing_failure_does_not_certify_absence(tmp_path, monkeypatch):
    deposit(tmp_path)
    original = Path.iterdir

    def unreadable(path):
        if path == tmp_path / "deposits":
            raise PermissionError("depot unavailable")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", unreadable)
    suite = Attic(tmp_path).checks.run()
    assert [type(poi) for poi in suite.pois()] == [ListingUnreadable]
    assert not suite.exhausted


def test_workflow_handlers_and_pois_load_through_runtime(tmp_path):
    runtime = create_runtime()
    deposit(tmp_path)
    attic = AtticWorkflow.open(tmp_path)
    assert runtime.workflows.get("Tarav.Workflow.Attic") is AtticWorkflow
    assert entity(type(attic)).workflow is AtticWorkflow()
    assert runtime.records.from_record(attic.records.to_record()).root == tmp_path
    item = attic.deposits()[0]
    assert runtime.records.from_record(item.records.to_record()).path == item.path
    (item.manifest_path).unlink()
    poi = attic.checks.run().pois()[0]
    loaded = runtime.records.from_record(poi.records.to_record())
    assert type(loaded) is ManifestMissing and loaded.situation == poi.situation
