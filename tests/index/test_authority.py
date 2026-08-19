from __future__ import annotations

import pytest

from tarav.index.authority import (
    Attribution,
    EditionRelation,
    ManifestError,
    ManifestRegistry,
    TouchAuthorityManifest,
    home_owner,
)


def _manifest(**overrides) -> TouchAuthorityManifest:
    kwargs = {
        "surface_type": "chat",
        "git_backed": True,
        "edition_relation": EditionRelation.COMMIT_RECORDS_EDITION,
        "attribution": Attribution.MESSAGE_ROLE,
        "predicate": "a user-role message in a committed session",
    }
    kwargs.update(overrides)
    return TouchAuthorityManifest(**kwargs)


class TestGitBackingCriterion:
    def test_non_git_backed_surface_cannot_carry_touch_authority(self):
        with pytest.raises(ManifestError, match="not git-backed"):
            _manifest(surface_type="journal", git_backed=False)

    def test_manifest_without_predicate_is_refused(self):
        with pytest.raises(ManifestError, match="no qualification predicate"):
            _manifest(predicate="   ")

    def test_git_backed_surface_with_predicate_is_accepted(self):
        assert _manifest().surface_type == "chat"


class TestManifestRegistry:
    def test_unregistered_surface_is_not_a_source_of_touched_data(self, geo):
        registry = ManifestRegistry(geo)
        with pytest.raises(ManifestError, match="not registered"):
            registry.get("journal")

    def test_register_then_get_roundtrips(self, geo):
        registry = ManifestRegistry(geo)
        registry.register(_manifest())
        loaded = registry.get("chat")
        assert loaded.edition_relation is EditionRelation.COMMIT_RECORDS_EDITION
        assert loaded.attribution is Attribution.MESSAGE_ROLE

    def test_bootstrap_registers_builtins_idempotently(self, geo):
        registry = ManifestRegistry(geo)
        registry.bootstrap()
        registry.bootstrap()
        types = {m.surface_type for m in registry.list()}
        assert types == {"chat", "journal", "vault"}

    def test_chat_and_journal_differ_in_edition_relation(self, geo):
        registry = ManifestRegistry(geo)
        registry.bootstrap()
        assert (
            registry.get("chat").edition_relation
            is EditionRelation.COMMIT_RECORDS_EDITION
        )
        assert (
            registry.get("journal").edition_relation
            is EditionRelation.COMMIT_IS_EDITION
        )


class TestHomesPathGuard:
    def test_home_owner_is_the_segment_after_homes(self, tmp_path):
        target = tmp_path / "skills" / "pkg" / "homes" / "ceo" / "chapters" / "a.md"
        assert home_owner(target) == "ceo"

    def test_path_outside_any_home_has_no_owner(self, tmp_path):
        assert home_owner(tmp_path / "skills" / "pkg" / "000-INDEX.md") is None

    def test_a_user_home_is_named_but_not_walled_off(self, tmp_path):
        """`home_owner` reports who governs a path; it licenses nothing.

        A user home is User.Gated, not agent-forbidden: the agent is the only
        writer of the index, and a landing gate is what licenses the write.
        There is deliberately no path predicate, because one would refuse the
        very write that promotion consists of.
        """
        target = tmp_path / "homes" / "ceo" / "chapters" / "100-design.md"
        assert home_owner(target) == "ceo"
