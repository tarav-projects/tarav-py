"""The same public contract suite works for retained and runtime explorers."""

from __future__ import annotations

from pathlib import Path

import pytest

from tarav.explorer_testing import ExplorerCase, ExplorerContractTests, check_collection
from tarav import get_runtime
from tarav.kernel import (
    ContextBuilder,
    ContextEntry,
    ContextExplorer,
    ContextFolder,
    ExplorerEntry,
    ExplorerFolder,
    TaravClass,
    TypeShip,
    ContextList,
)
from tarav.record_archive import (
    ArchiveExplorer,
    ArchiveFolder,
    ArchiveList,
    ArchiveRoot,
)
from tarav.test_workflow import TestItem as WorkspaceItem


def _archive_folder(root: Path) -> ExplorerCase:
    folder = ArchiveFolder.create(root / "archive", constitution="Explorer fixture")
    folder.put("leaf", WorkspaceItem("one"))
    folder.put_archive("child", ArchiveFolder, constitution="Child")
    folder.put_archive("other", ArchiveFolder, constitution="Other")
    return ExplorerCase(
        folder,
        ("leaf", "child", "other"),
        ArchiveExplorer(folder),
        child="child",
        leaf="leaf",
        other_child="other",
    )


def _archive_root(root: Path) -> ExplorerCase:
    workflow = get_runtime().workflows.get("test")
    archive = ArchiveRoot(root / "archive")
    archive.for_workflow(workflow).create_directory("run")
    key = str(workflow.id)
    return ExplorerCase(
        archive,
        (key,),
        ArchiveExplorer(archive),
        child=key,
    )


def _archive_partition(root: Path) -> ExplorerCase:
    workflow = get_runtime().workflows.get("test")
    partition = ArchiveRoot(root / "archive").for_workflow(workflow)
    partition.create_directory("child")
    partition.create_directory("other")
    return ExplorerCase(
        partition,
        ("child", "other"),
        ArchiveExplorer(partition),
        child="child",
        other_child="other",
    )


def _archive_list(root: Path) -> ExplorerCase:
    values = ArchiveList.create(root / "archive", constitution="Explorer fixture")
    values.append(WorkspaceItem("one"))
    values.append_archive(ArchiveFolder, constitution="Child")
    values.append_archive(ArchiveFolder, constitution="Other")
    return ExplorerCase(
        values,
        (0, 1, 2),
        ArchiveExplorer(values),
        child=1,
        leaf=0,
        other_child=2,
    )


def _context_folder(root: Path) -> ExplorerCase:
    del root
    leaf = WorkspaceItem("one")
    child = ContextFolder(WorkspaceItem, lambda builder: None)
    other = ContextFolder(WorkspaceItem, lambda builder: None)

    def populate(builder: ContextBuilder) -> None:
        builder.add("leaf", opener=lambda: leaf)
        builder.add("child", opener=lambda: child)
        builder.add("other", opener=lambda: other)

    folder = ContextFolder(WorkspaceItem, populate)
    return ExplorerCase(
        folder,
        ("leaf", "child", "other"),
        ContextExplorer(folder, lambda subject: folder),
        child="child",
        leaf="leaf",
        other_child="other",
    )


def _context_list(root: Path) -> ExplorerCase:
    del root
    leaf = WorkspaceItem("one")
    child = ContextList(WorkspaceItem, lambda builder: None)
    other = ContextList(WorkspaceItem, lambda builder: None)

    def populate(builder: ContextBuilder) -> None:
        builder.add(0, opener=lambda: leaf)
        builder.add(1, opener=lambda: child)
        builder.add(2, opener=lambda: other)

    values = ContextList(WorkspaceItem, populate)
    return ExplorerCase(
        values,
        (0, 1, 2),
        ContextExplorer(values, lambda subject: values),
        child=1,
        leaf=0,
        other_child=2,
    )


class ArchiveContractTests(ExplorerContractTests):
    def assert_value(self, case, key, value):
        if key == case.leaf:
            assert value.to_record() == WorkspaceItem("one").to_record()
        elif isinstance(case.value, (ArchiveFolder, ArchiveList)):
            assert isinstance(value, ArchiveFolder)
            assert value.constitution == ("Child" if key == case.child else "Other")
        else:
            assert value.directory == case.value.directory / str(key)


class TestArchiveFolder(ArchiveContractTests):
    make_case = staticmethod(_archive_folder)


class TestArchiveList(ArchiveContractTests):
    make_case = staticmethod(_archive_list)


class TestArchiveRoot(ArchiveContractTests):
    make_case = staticmethod(_archive_root)


class TestArchivePartition(ArchiveContractTests):
    make_case = staticmethod(_archive_partition)


class ContextContractTests(ExplorerContractTests):
    def assert_value(self, case, key, value):
        if key == case.leaf:
            assert value.to_record() == WorkspaceItem("one").to_record()
        else:
            assert isinstance(value, type(case.value))
            assert value.subject is WorkspaceItem
            assert value.ls() == ()


class TestContextFolder(ContextContractTests):
    make_case = staticmethod(_context_folder)


class TestContextList(ContextContractTests):
    make_case = staticmethod(_context_list)


def test_empty_collections_obey_the_same_contract(tmp_path: Path) -> None:
    from tarav.explorer_testing import check_collection

    check_collection(ArchiveRoot(tmp_path / "missing"), ())
    check_collection(ArchiveFolder.create(tmp_path / "named", constitution="Empty"), ())
    check_collection(ArchiveList.create(tmp_path / "ordered", constitution="Empty"), ())
    check_collection(ContextFolder(WorkspaceItem, lambda builder: None), ())
    check_collection(ContextList(WorkspaceItem, lambda builder: None), ())


def test_independent_folder_can_register_without_repository_test_helpers() -> None:
    class IndependentEntry(ExplorerEntry):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("701c6c67-0dc4-4c68-8431-1c6d92ce45a4"),
                name="Test.Explorer.IndependentEntry",
            )

        def __init__(self, name: str, value: WorkspaceItem) -> None:
            super().__init__()
            self._name = name
            self.value = value

        @property
        def name(self) -> str:
            return self._name

        def open(self) -> WorkspaceItem:
            return self.value

    class IndependentFolder(ExplorerFolder):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("9df356d7-7d6d-4b33-b063-d43a6cb2a8f5"),
                name="Test.Explorer.IndependentFolder",
            )

        def __init__(self) -> None:
            super().__init__()
            self.entry = IndependentEntry("item", WorkspaceItem("independent"))

        def ls(self) -> tuple[IndependentEntry, ...]:
            return (self.entry,)

        def get(self, name: str) -> IndependentEntry:
            if not isinstance(name, str):
                raise TypeError("Folder keys are names")
            if name != "item":
                raise KeyError(name)
            return self.entry

    check_collection(IndependentFolder(), ("item",))


def test_context_explorer_preserves_specialized_entry_type_and_parent_history() -> None:
    class SpecializedEntry(ContextEntry):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("d64ddaa2-e832-4dcc-a350-609e81376c3b"),
                name="Test.Explorer.SpecializedEntry",
            )

    child = ContextFolder(WorkspaceItem, lambda builder: None)

    def populate(builder: ContextBuilder) -> None:
        builder.add_entry(SpecializedEntry("child", opener=lambda: child))

    explorer = ContextExplorer(
        ContextFolder(WorkspaceItem, populate), lambda subject: child
    )
    assert type(explorer.get("child")) is SpecializedEntry
    explorer.cd("child").cd("..")
    assert explorer.pwd() == "/"
    assert explorer.back().pwd() == "/child"
    assert explorer.forward().pwd() == "/"


def test_archive_parent_navigation_is_distinct_from_visit_history(
    tmp_path: Path,
) -> None:
    root = ArchiveFolder.create(tmp_path / "archive", constitution="Navigation fixture")
    root.put_archive("child", ArchiveFolder, constitution="Child")
    explorer = ArchiveExplorer(root)
    explorer.cd("child").cd("..")
    assert explorer.pwd() == "/"
    assert explorer.back().pwd() == "/child"
    assert explorer.forward().pwd() == "/"


def test_suite_detects_broken_listing_and_cleans_fixture_directory() -> None:
    class BrokenContext(ContextFolder):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("efeea913-3317-4c83-8776-ac56bcf299e6"),
                name="Test.Explorer.Broken",
            )

        def ls(self):
            return ()

    created: list[Path] = []

    def fixture(root: Path) -> ExplorerCase:
        created.append(root)
        root.joinpath("marker").write_text("fixture")
        value = BrokenContext(
            WorkspaceItem,
            lambda builder: builder.add("item", opener=lambda: WorkspaceItem("one")),
        )
        return ExplorerCase(value, ("item",))

    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as directory:
        case = fixture(Path(directory))
        with pytest.raises(AssertionError):
            check_collection(case.value, case.keys)
    assert created and not created[0].exists()


def test_abstract_support_is_required():
    with pytest.raises(TypeError, match="abstract"):
        ExplorerContractTests()


def test_inherited_checks_reject_failed_navigation_mutation(tmp_path, monkeypatch):
    case = _context_folder(tmp_path)
    original = case.explorer.cd

    def broken_cd(key):
        if key == case.leaf:
            case.explorer._visit(case.explorer.current)
            raise NotADirectoryError(key)
        return original(key)

    monkeypatch.setattr(case.explorer, "cd", broken_cd)
    tests = TestContextFolder()
    monkeypatch.setattr(tests, "make_case", lambda path: case)
    with pytest.raises(AssertionError):
        tests.test_navigation_contract(tmp_path)


def test_inherited_checks_reject_wrong_value(tmp_path, monkeypatch):
    case = _context_folder(tmp_path)
    monkeypatch.setattr(case.value, "open", lambda key: WorkspaceItem("wrong"))
    tests = TestContextFolder()
    monkeypatch.setattr(tests, "make_case", lambda path: case)
    with pytest.raises(AssertionError):
        tests.test_collection_contract(tmp_path)


def test_inherited_checks_reject_history_mutation(tmp_path, monkeypatch):
    case = _context_folder(tmp_path)
    original = case.explorer.open

    def broken_open(key):
        case.explorer._visit(case.explorer.current)
        return original(key)

    monkeypatch.setattr(case.explorer, "open", broken_open)
    tests = TestContextFolder()
    monkeypatch.setattr(tests, "make_case", lambda path: case)
    with pytest.raises(AssertionError):
        tests.test_navigation_contract(tmp_path)
