"""Real committed bytes, explicit decisions, and persistent mapping history."""

import json
import subprocess
from uuid import uuid4

import pytest

from tarav.l1.product_mapping import ContinuityDecision, ProductMapper
from tarav.l3.runtime import create_runtime


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.fixture
def mapper(tmp_path):
    create_runtime()
    repo = tmp_path / "product"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    return ProductMapper(repo, "test-repository", root=tmp_path / "maps")


def commit(mapper, files):
    for name, content in files.items():
        path = mapper.product.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if content is None:
            path.unlink()
        else:
            path.write_bytes(content)
    git(mapper.product.root, "add", "-A")
    git(mapper.product.root, "commit", "-qm", "Change product")
    return git(mapper.product.root, "rev-parse", "HEAD")


def decisions(mapper, proposal, reason="Maintainer inspected endpoint diff"):
    return [ContinuityDecision(source_ids=[c["id"]] if c["before"] else [],
                               target_ids=[c["id"]] if c["after"] else [], reason=reason)
            for c in mapper.changes(proposal)]


def confirm(mapper, proposal):
    return mapper.confirm(proposal, decisions=decisions(mapper, proposal), actor="test-user",
                          reason="Explicit mapping transition")


# tarav.breadcrumb e51271c6d0fa
def test_initial_full_coverage_is_committed_and_reads_do_not_provision(mapper):
    assert mapper.track() is None
    assert not mapper.store.root.exists()
    head = commit(mapper, {"a.txt": b"alpha\nbeta\ngamma\n", "empty": b"",
                           "binary": b"\x00\xff\x01"})
    mapper.create(target_bytes=7, boundary_bytes=2)
    (mapper.product.root / "a.txt").write_text("uncommitted replacement")
    proposal = mapper.propose(head)
    assert [(c.start, c.end) for c in proposal.typed.chunks if c.path == "a.txt"] == [(0, 7), (7, 14), (14, 17)]
    assert mapper.audit(proposal) == {"files": 3, "chunks": 5, "bytes": 20,
                                      "skipped": 0, "commit": head}
    with pytest.raises(ValueError, match="explicit decision"):
        mapper.confirm(proposal, decisions=[], actor="test", reason="missing")
    saved = confirm(mapper, proposal)
    assert mapper.history() == (saved.typed.id,)
    assert mapper.load(saved.typed.id).records.to_record() == saved.records.to_record()


def test_move_expand_retire_and_stale_proposal(mapper):
    commit(mapper, {"a": b"one\ntwo\nthree\n", "gone": b"old"})
    mapper.create(target_bytes=8, boundary_bytes=0)
    first = confirm(mapper, mapper.propose())
    old_ids = [c.id for c in first.typed.chunks if c.path == "a"]
    (mapper.product.root / "a").rename(mapper.product.root / "moved")
    commit(mapper, {"gone": None})
    proposal = mapper.propose()
    assert [c.id for c in proposal.typed.chunks] == old_ids
    assert {c["kind"] for c in mapper.changes(proposal)} == {"moved", "retired"}
    second = confirm(mapper, proposal)
    with pytest.raises(ValueError, match="Stale proposal"):
        confirm(mapper, proposal)
    commit(mapper, {"moved": b"intro\none\ntwo\nthree\n"})
    expanded = mapper.propose()
    assert [c.id for c in expanded.typed.chunks] == old_ids
    assert sum(c.end - c.start for c in expanded.typed.chunks) == 20
    confirm(mapper, expanded)
    assert mapper.load(first.typed.id).typed.chunks[0].path == "a"
    assert second.typed.base == first.typed.id


def test_corrupt_ranges_hashes_and_missing_files_reject_before_persistence(mapper):
    commit(mapper, {"a": b"abcdef", "b": b"xyz"})
    mapper.create(target_bytes=3, boundary_bytes=0)
    proposal = mapper.propose()
    original = proposal.typed.chunks[0]
    proposal.typed.chunks[0] = original.model_copy(update={"start": 1})
    with pytest.raises(ValueError, match="range"):
        confirm(mapper, proposal)
    proposal.typed.chunks[0] = original.model_copy(update={"sha256": "0" * 64})
    with pytest.raises(ValueError, match="fingerprint"):
        confirm(mapper, proposal)
    proposal.typed.chunks = [original]
    with pytest.raises(ValueError, match="exactly"):
        confirm(mapper, proposal)
    assert mapper.history() == ()


def test_split_merge_and_retired_identity_cannot_be_rebound(mapper):
    from tarav.l1.product_mapping.alignment import chunk

    commit(mapper, {"a": b"abcdefgh"})
    mapper.create(target_bytes=20)
    first = confirm(mapper, mapper.propose())
    old = first.typed.chunks[0]
    proposal = mapper.propose()
    content = b"abcdefgh"
    proposal.typed.chunks = [chunk("a", old.blob, content, 0, 4),
                            chunk("a", old.blob, content, 4, 8)]
    split_ids = [c.id for c in proposal.typed.chunks]
    second = mapper.confirm(proposal, decisions=[{
        "source_ids": [old.id], "target_ids": split_ids, "reason": "Split for finer coordinates"}],
        actor="user", reason="Explicit split")
    merge = mapper.propose()
    merge.typed.chunks = [chunk("a", old.blob, content, 0, 8)]
    merged = mapper.confirm(merge, decisions=[{
        "source_ids": split_ids, "target_ids": [merge.typed.chunks[0].id],
        "reason": "Merge adjacent coordinates"}], actor="user", reason="Explicit merge")
    assert second.typed.decisions[0].source_ids == [old.id]
    assert merged.typed.decisions[0].source_ids == split_ids
    reuse = mapper.propose()
    reuse.typed.chunks[0].id = old.id
    with pytest.raises(ValueError, match="retired chunk ID"):
        confirm(mapper, reuse)


def test_ambiguous_identical_files_do_not_share_chunk_ids(mapper):
    commit(mapper, {"a": b"same content", "b": b"same content"})
    mapper.create()
    first = confirm(mapper, mapper.propose())
    commit(mapper, {"a": None, "b": None, "c": b"same content", "d": b"same content"})
    # Git's rename suggestions are proposals, not confirmation.
    proposal = mapper.propose()
    assert len({c.id for c in proposal.typed.chunks}) == 2
    assert mapper.latest().typed.id == first.typed.id
    with pytest.raises(ValueError, match="explicit decision"):
        mapper.confirm(proposal, decisions=[], actor="user", reason="No judgment yet")


def test_symlinks_are_listed_never_followed_and_scope_is_explicit(mapper):
    commit(mapper, {"a": b"content", "excluded": b"ignore"})
    (mapper.product.root / "link").symlink_to("/unavailable/target")
    git(mapper.product.root, "add", "link")
    git(mapper.product.root, "commit", "-qm", "Add symlink")
    mapper.create(exclude=["excluded"])
    proposal = mapper.propose()
    assert [c.path for c in proposal.typed.chunks] == ["a"]
    assert [(s.path, s.mode) for s in proposal.typed.skipped] == [("link", "120000")]
    assert mapper.audit(proposal)["bytes"] == 7
    confirm(mapper, proposal)


# tarav.breadcrumb 8f966443e2a4
def test_project_config_controls_manager_and_cli_scope_without_reinterpreting_old_maps(mapper, capsys):
    from hashlib import sha256
    from tarav.l1.git.hooks import GitConfig
    from tarav.l1.product_mapping.checks import MappingFreshnessCheck
    from tarav.l1.project.config import ProjectConfig
    from tarav.l2.project import Project
    from tarav.l2.project.product_mapping import ProductMappingConfig
    from tarav.l3.cli.cli import main

    head = commit(mapper, {
        "src/direct.py": b"x=1\n", "src/nested/core.py": b"y=2\n",
        "tests/test_core.py": b"assert True\n", "tests/generated/test_auto.py": b"assert False\n",
        "src/readme.md": b"docs", "notes/hidden.py": b"notes",
        "_DEPRECATED/old.py": b"old", "srcish/no.py": b"outside", "tests/test.txt": b"text"})
    root = mapper.product.root
    (root / ".tarav").mkdir()
    (root / ".tarav/project.json").write_text(json.dumps({
        "type": "Tarav.Project", "project_id": str(uuid4()), "created_at": "2026-10-22T00:00:00Z"}))
    config = ProjectConfig(root)
    rid = sha256(str(root).encode()).hexdigest()
    config.write_section("git", GitConfig(repository=rid))
    config.write_section("product_mapping", ProductMappingConfig(enabled=True))
    project = Project.from_path(root)
    broad = project.mapping.open()
    broad.create()
    original = confirm(broad, broad.propose(head))
    stale_scope = broad.propose(head)
    config.write_section("product_mapping", ProductMappingConfig(
        enabled=True, include=["src/*.py", "tests/*.py"], exclude=["tests/generated/*"]))
    selected = project.mapping.open()
    with pytest.raises(ValueError, match="file scope"):
        selected.confirm(stale_scope, decisions=[], actor="user", reason="Old selection")
    proposal = selected.propose(head)
    assert {c.path for c in proposal.typed.chunks} == {
        "src/direct.py", "src/nested/core.py", "tests/test_core.py"}
    assert selected.audit(original)["files"] == 9
    assert original.typed.include == ["*"]
    assert len(MappingFreshnessCheck(mapper=selected).run().pois()) == 1
    latest = confirm(selected, proposal)
    assert selected.audit(latest)["files"] == 3
    assert MappingFreshnessCheck(mapper=selected).run().pois() == ()
    capsys.readouterr()
    assert main(["product-map", "propose", "--repo", str(root), "--repository-id", rid]) == 0
    output = json.loads(capsys.readouterr().out)
    assert {c["path"] for c in output["chunks"]} == {
        "src/direct.py", "src/nested/core.py", "tests/test_core.py"}


def test_checkpoints_skip_intermediates_include_final_and_resume(mapper):
    history = [commit(mapper, {"a": str(i).encode()}) for i in range(24)]
    assert mapper.product.checkpoints(every=10) == (history[0], history[10], history[20], history[23])
    assert mapper.product.checkpoints(every=10, after=history[10]) == (history[20], history[23])
    assert mapper.product.checkpoints(every=10, after=history[23]) == ()
    with pytest.raises(ValueError, match="positive"):
        mapper.product.checkpoints(every=0)


def test_decision_cannot_consume_unrelated_or_duplicate_id(mapper):
    commit(mapper, {"a": b"text"})
    mapper.create()
    proposal = mapper.propose()
    ds = decisions(mapper, proposal)
    with pytest.raises(ValueError, match="duplicate"):
        mapper.confirm(proposal, decisions=ds + ds, actor="user", reason="bad")
    with pytest.raises(ValueError, match="unrelated"):
        mapper.confirm(proposal, decisions=[{"source_ids": [str(uuid4())],
                       "target_ids": [], "reason": "bad"}], actor="user", reason="bad")
    assert json.loads(mapper.store.path(mapper.track_key).read_text())["maps"] == []


def test_retaining_an_id_requires_one_consistent_continuity_decision(mapper):
    commit(mapper, {"a": b"old content"})
    mapper.create()
    confirm(mapper, mapper.propose())
    commit(mapper, {"a": b"new content"})
    proposal = mapper.propose()
    identity = proposal.typed.chunks[0].id
    with pytest.raises(ValueError, match="Retained IDs"):
        mapper.confirm(proposal, decisions=[
            {"source_ids": [identity], "target_ids": [], "reason": "Retire"},
            {"source_ids": [], "target_ids": [identity], "reason": "Create again"}],
            actor="user", reason="Contradictory identity assertions")


def test_chunk_coordinates_resolve_exact_versions_and_expose_retirement(mapper):
    commit(mapper, {"a": b"old content"})
    mapper.create()
    first = confirm(mapper, mapper.propose())
    identity = first.typed.chunks[0].id
    commit(mapper, {"a": b"new content"})
    second = confirm(mapper, mapper.propose())
    assert mapper.read_chunk(identity, at=first.typed.id) == b"old content"
    assert mapper.read_chunk(identity, at=second.typed.id) == b"new content"
    commit(mapper, {"a": None, "b": b"replacement"})
    confirm(mapper, mapper.propose())
    with pytest.raises(ValueError, match="absent"):
        mapper.locate(identity)
    history = mapper.chunk_history(identity)
    assert len(history) == 3
    assert history[0]["map"] == first.typed.id
    assert history[-1]["chunk"] is None
    assert history[-1]["decisions"][0]["source_ids"] == [identity]


def test_cli_requires_explicit_decisions_and_roundtrips_real_records(mapper, tmp_path, capsys):
    from tarav.l3.cli.cli import main

    head = commit(mapper, {"a": b"a real product\n"})
    common = ["--repo", str(mapper.product.root), "--repository-id", "test-repository",
              "--store", str(mapper.store.root)]
    assert main(["product-map", "init", *common]) == 0
    capsys.readouterr()
    path = tmp_path / "proposal.json"
    assert main(["product-map", "propose", *common, "--output", str(path)]) == 0
    capsys.readouterr()
    from tarav.l1.product_mapping import MappingProposal
    proposal = MappingProposal.records.from_record(json.loads(path.read_text()))
    decision_path = tmp_path / "decisions.json"
    decision_path.write_text("[]")
    command = ["product-map", "confirm", *common, "--proposal", str(path),
               "--decisions", str(decision_path), "--actor", "user", "--reason", "Explicit review"]
    assert main(command) != 0
    assert mapper.history() == ()
    capsys.readouterr()
    decision_path.write_text(json.dumps([d.model_dump() for d in decisions(mapper, proposal)]))
    assert main(command) == 0
    assert json.loads(capsys.readouterr().out)["commit"] == head
    assert main(["product-map", "audit", *common, "--all"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["bytes"] == 15
    assert main(["product-map", "show", *common, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["actor"] == "user"


# tarav.breadcrumb a421d5af5f32
def test_freshness_only_reports_due_changes_and_never_writes(mapper):
    from datetime import datetime, timedelta
    from tarav.l1.product_mapping.checks import MappingFreshnessCheck

    commit(mapper, {"a": b"first"})
    missing = MappingFreshnessCheck(mapper=mapper).run()
    assert len(missing.pois()) == 1
    assert not mapper.store.root.exists()
    mapper.create()
    first = confirm(mapper, mapper.propose())
    now = datetime.fromisoformat(first.typed.confirmed_at)
    commit(mapper, {"a": b"second"})
    before = {p: p.read_bytes() for p in mapper.store.records_dir.iterdir()}
    assert MappingFreshnessCheck(mapper=mapper, now=now + timedelta(days=4)).run().pois() == ()
    due = MappingFreshnessCheck(mapper=mapper, now=now + timedelta(days=5)).run()
    assert len(due.pois()) == 1
    assert missing.pois()[0].identity == due.pois()[0].identity
    assert before == {p: p.read_bytes() for p in mapper.store.records_dir.iterdir()}
    confirm(mapper, mapper.propose())
    assert MappingFreshnessCheck(mapper=mapper, now=now + timedelta(days=10)).run().pois() == ()


def test_project_manager_opens_closes_and_reopens_one_update_action(mapper, monkeypatch):
    from tarav.l2.project import Project
    from tarav.l1.project.config import ProjectConfig
    from tarav.l2.project.product_mapping import ProductMappingConfig

    commit(mapper, {"a": b"first"})
    root = mapper.product.root
    (root / ".tarav").mkdir()
    (root / ".tarav/project.json").write_text(json.dumps({
        "type": "Tarav.Project", "project_id": str(uuid4()),
        "created_at": "2026-10-22T00:00:00Z"}))
    project = Project.from_path(root)
    monkeypatch.setattr(Project.Mapping, "open", lambda self: mapper)
    config = ProjectConfig(root)
    config.write_section("product_mapping", ProductMappingConfig(enabled=True, max_age_days=0))
    # Exercise the real status/action loop with just this integration's checks.
    monkeypatch.setattr(Project.Checks, "suite", lambda self: self.obj.mapping.suite())
    project.status()
    action = project.actions.list()[0]
    assert action.data["action"] == "Tarav.ProductMapping.Update.Action"
    assert action.state == "running"
    project.status()
    assert len(project.actions.list()) == 1
    mapper.create()
    confirm(mapper, mapper.propose())
    project.status()
    assert project.actions.list()[0].state == "closed"
    commit(mapper, {"a": b"second"})
    project.status()
    updated = project.actions.list()[0]
    assert updated.id == action.id
    assert updated.state == "running"
    # Disabling or losing an integration is not evidence that its finding vanished.
    config.write_section("product_mapping", ProductMappingConfig(enabled=False))
    project.status()
    assert project.actions.list()[0].state == "running"


def test_unknown_revision_does_not_create_a_map(mapper):
    commit(mapper, {"a": b"first"})
    mapper.create()
    with pytest.raises(ValueError, match="unknown|revision|single revision|valid object"):
        mapper.propose("not-a-commit")
    assert mapper.history() == ()


def test_historical_driver_is_explicit_agent_work_and_checks_every_checkpoint(mapper, tmp_path, capsys):
    from pathlib import Path
    import runpy

    driver = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tooling/map_product_history.py"))
    commit(mapper, {"a": b"first body\n"})
    commit(mapper, {"a": b"first body\nmore detail\n"})
    final = commit(mapper, {"a": b"entirely different product\n", "new": b"new file\n"})
    common = ["--repo", str(mapper.product.root), "--repository-id", mapper.repository_id,
              "--store", str(mapper.store.root), "--commit", final, "--every", "2"]
    assert driver["main"](common) == 0
    assert not mapper.store.root.exists()
    capsys.readouterr()
    real = subprocess.run(["tarav", "run", "--", str(Path(__file__).resolve().parents[1] /
                            "tooling/map_product_history.py"), *common], capture_output=True, text=True)
    assert real.returncode == 0, real.stderr
    assert json.loads(real.stdout)["target"] == final
    report = tmp_path / "report.json"
    assert driver["main"]([*common, "--apply", "--actor", "agent:test", "--report", str(report)]) == 0
    data = json.loads(report.read_text())
    assert len(data["checkpoints"]) == 2
    assert data["actor"] == "agent:test"
    assert data["checkpoints"][-1]["commit"] == final
    assert mapper.latest().typed.actor == "agent:test"
    assert mapper.audit(mapper.latest())["bytes"] == 36
    # Resume neither duplicates maps nor changes the pinned endpoint.
    assert driver["main"]([*common, "--apply", "--actor", "agent:test", "--report", str(report)]) == 0
    assert len(mapper.history()) == 2
