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
