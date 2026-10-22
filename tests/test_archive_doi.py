"""The DOI registry is readable independently of resource reachability."""
# tarav.breadcrumb 64102300c8c9
# tarav.breadcrumb d9ec25a9ee09

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import subprocess
from threading import Thread

import pytest
from pydantic import ValidationError

from tarav.l0.kernel import TaravObject, TypeRegistry, entity
from tarav.l1.archive import Archive
from tarav.l1.archive.checks import ArchiveLocatorSuite, LocatorCheck, LocatorMissing
from tarav.l1.archive.model import DOI, DOI_RECORD_TYPES, LocalLocator, RemoteLocator, RepositoryDOI, RepositoryHints
from tarav.l1.archive.references import DOIReference
from tarav.l3.runtime import create_runtime


def test_lookup_does_not_access_or_create_resource_and_location_is_maintained(tmp_path):
    archive = Archive.create(tmp_path / "registry")
    missing = tmp_path / "absent"
    doi = archive.register(RepositoryDOI(label="Notebook", locators=[LocalLocator(missing)]))
    ref = DOIReference(doi.id, registry=archive.root)
    assert ref.resolve().target.locators[0].path == str(missing)
    assert not missing.exists()
    moved = tmp_path / "elsewhere"
    doi.locators = [LocalLocator(moved), RemoteLocator("https://example.org/repo.git")]
    archive.update(doi)
    assert ref.resolve().target.locators[0].path == str(moved)
    assert not moved.exists()
    assert archive.read(doi.id).id == doi.id


def test_reads_do_not_initialize_anything(tmp_path):
    archive = Archive(tmp_path / "absent")
    assert archive.ids() == ()
    assert not DOIReference("a" * 64, registry=archive.root).resolve().ok
    assert not archive.root.exists()
    suite = ArchiveLocatorSuite(archive).run()
    assert list(suite.pois()) == []
    assert not archive.root.exists()


def test_duplicate_identity_type_rebinding_and_bad_record_key_are_rejected(tmp_path):
    archive = Archive.create(tmp_path / "registry")
    doi = archive.register(DOI())
    with pytest.raises(FileExistsError):
        archive.register(doi)
    with pytest.raises(ValueError, match="Type"):
        archive.update(RepositoryDOI(id=doi.id))
    payload = doi.records.to_record()
    payload["id"] = "b" * 64
    archive.store.path(doi.id).write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="key"):
        archive.read(doi.id)


def test_custom_registry_round_trip_and_bound_reference(tmp_path):
    records = TypeRegistry(TaravObject, (*DOI_RECORD_TYPES, DOIReference))
    archive = Archive.create(tmp_path / "registry", records=records)
    doi = archive.register(RepositoryDOI(locators=[LocalLocator(tmp_path / "repo")],
                                        hints=RepositoryHints(object_format="sha1", commits=["a" * 40])))
    ref = records.from_record(DOIReference(doi.id, registry=archive.root).records.to_record())
    assert ref.resolve().target.records.to_record() == doi.records.to_record()


def test_git_record_edition_preserves_observed_location(tmp_path):
    archive = Archive.create(tmp_path / "registry")
    doi = archive.register(DOI(locators=[LocalLocator(tmp_path / "first")]))
    archive.commit("First declaration")
    before = archive.store.head_reference(doi.id)
    doi.locators = [LocalLocator(tmp_path / "second")]
    archive.update(doi)
    archive.commit("Move declaration")
    assert json.loads(before.resolve().target["content"])["locators"][0]["path"] == str(tmp_path / "first")


def test_repository_hints_are_bounded_without_commit_bodies(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args]).decode().strip()
    git("init", "-q")
    for i in range(12):
        git("-c", "user.name=Test", "-c", "user.email=test@example.org", "commit", "--allow-empty", "-qm", str(i))
    hints = RepositoryHints.collect(tmp_path)
    all_commits = git("rev-list", "--reverse", "HEAD").splitlines()
    assert len(hints.commits) == 10
    assert hints.commits[0] == all_commits[0]
    assert hints.commits[-1] == all_commits[-1]
    assert set(hints.records.to_record()) == {"type", "object_format", "commits"}
    with pytest.raises(ValidationError):
        RepositoryHints(object_format="sha1", commits=["x"])


def test_local_locator_reports_missing_and_then_recovers(tmp_path):
    locator = LocalLocator(tmp_path / "missing")
    check = LocatorCheck(situation={"doi": "a" * 64}, locator=locator)
    assert type(check.run().pois()[0]) is LocatorMissing
    Path(locator.path).write_text("now present")
    assert check.run().pois() == ()
    other_host = LocalLocator(tmp_path / "missing", host=socket.gethostname() + "-other")
    assert LocatorCheck(situation={}, locator=other_host).run().status == "incomplete"
    assert LocatorCheck(situation={}, locator=RemoteLocator("ssh://example.org/repo")).run().status == "incomplete"


def test_http_checks_distinguish_missing_auth_and_redirect_without_fetching_body():
    class Handler(BaseHTTPRequestHandler):
        def do_HEAD(self):
            self.send_response({"/ok": 200, "/missing": 404, "/auth": 403, "/redirect": 302}[self.path])
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def run(path):
            return LocatorCheck(situation={}, locator=RemoteLocator(
                f"http://127.0.0.1:{server.server_port}{path}")).run()
        assert run("/ok").pois() == ()
        assert type(run("/missing").pois()[0]) is LocatorMissing
        assert run("/auth").status == "incomplete"
        assert run("/redirect").status == "incomplete"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_registered_types_all_round_trip_examples():
    runtime = create_runtime()
    for cls in (*DOI_RECORD_TYPES, DOIReference):
        sample = cls.records.record_example()
        assert runtime.records.from_record(sample).records.to_record() == sample
        assert entity(cls).workflow_ship == entity(DOI).workflow_ship
