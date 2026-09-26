import pytest

from tarav.kernel import TaravObject, entity
from tarav.context import ContextEntry, ContextExplorer, ContextFolder, ContextObject, ContextType
from tarav.context import CONTEXT_WORKFLOW_SHIP
from tarav.archive.records import (
    ArchiveEntry, ArchiveExplorer, ArchiveFolder, ArchiveObject, ArchiveRoot, ArchiveType,
)
from tarav.explorer_testing import navigation_state


def test_family_membership_and_ownership():
    assert issubclass(ArchiveExplorer, ArchiveType)
    assert not issubclass(ArchiveExplorer, TaravObject)
    assert issubclass(ArchiveRoot, ArchiveObject)
    assert issubclass(ContextExplorer, ContextType)
    assert issubclass(ContextFolder, ContextObject)
    assert entity(ContextFolder).workflow_ship == CONTEXT_WORKFLOW_SHIP
    assert entity(ContextExplorer).workflow_ship == CONTEXT_WORKFLOW_SHIP


def test_leaf_roots_are_members_but_not_containers():
    archive = ArchiveExplorer(ArchiveEntry("leaf"))
    context = ContextExplorer(ContextEntry("leaf"), lambda subject: None)
    for explorer in (archive, context):
        before = navigation_state(explorer)
        with pytest.raises(NotADirectoryError):
            explorer.ls()
        with pytest.raises(NotADirectoryError):
            explorer.get("anything")
        assert navigation_state(explorer) == before


def test_foreign_roots_rejected(tmp_path):
    folder = ContextFolder(TaravObject, lambda builder: None)
    with pytest.raises(TypeError, match="ArchiveObject"):
        ArchiveExplorer(folder)
    with pytest.raises(TypeError, match="ContextObject"):
        ContextExplorer(ArchiveRoot(tmp_path), lambda subject: folder)


def test_foreign_destinations_do_not_change_history(tmp_path, monkeypatch):
    archive = ArchiveFolder.create(tmp_path / "a", constitution="fixture")
    folder = ContextFolder(TaravObject, lambda b: b.add("foreign", opener=lambda: archive))
    context = ContextExplorer(folder, lambda subject: folder)
    entry = ArchiveEntry("foreign", opener=lambda: folder)
    monkeypatch.setattr(archive, "get", lambda key: entry)
    for explorer in (context, ArchiveExplorer(archive)):
        before = navigation_state(explorer)
        assert explorer.open("foreign") is not None
        with pytest.raises(TypeError):
            explorer.cd("foreign")
        assert navigation_state(explorer) == before


def test_failed_archive_path_restores_history(tmp_path):
    root = ArchiveFolder.create(tmp_path / "a", constitution="fixture")
    root.put_archive("child", ArchiveFolder, constitution="child")
    explorer = ArchiveExplorer(root)
    explorer.cd("child").back()
    before = navigation_state(explorer)
    with pytest.raises(KeyError):
        explorer.cd("child/missing")
    assert navigation_state(explorer) == before
