"""Type-model identities compose independently from path labels and storage."""

import pytest

from tarav.l0.kernel import FileRecord, Ship, TaravClass, TaravObject, TypeShip, entity
from tarav.l1.context.models import TypeModel, TypePath
from tarav.l3.runtime import create_runtime, get_runtime, set_runtime


MEMBER_SHIP = Ship("1692ba40-1517-4b9e-850a-66ea7135539b")
EXTERNAL_SHIP = Ship("56a5c6f6-4c05-4c46-a20b-a7cbe49188aa")


class EmptyType(TaravObject):
    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls, id=TypeShip("239b03c2-ad92-483a-91ab-04d065f83501"),
            name="Test.ContextModel.Empty",
        )


class ModeledType(EmptyType):
    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls, id=TypeShip("842e0b5b-c18f-4194-91be-b7aa70d5b110"),
            name="Test.ContextModel.Modeled",
        )

    class Context(EmptyType.Context):
        def model_nodes(self):
            return (*super().model_nodes(), TypePath(MEMBER_SHIP, "contains"))


@pytest.fixture
def runtime(tmp_path):
    old = get_runtime()
    current = create_runtime(archive_root=tmp_path / "archive")
    set_runtime(current)
    try:
        yield current
    finally:
        set_runtime(old)


# tarav.context 473c89a0:0dfbeaeb402e0305
def test_empty_type_model_has_existing_root_and_reading_creates_nothing(runtime):
    model = EmptyType.context.model
    assert isinstance(model, TypeModel)
    assert model.root.id == entity(EmptyType).id
    assert model.at("") is model.root
    assert model.nodes() == ()
    assert [entry.name for entry in model.ls()] == [str(entity(EmptyType).id)]
    assert EmptyType().context.model.root.id == model.root.id
    assert isinstance(EmptyType.context().open("model"), TypeModel)
    assert not runtime.contexts.archive_root.exists()


# tarav.context 473c89a0:3fea6e90a968360c
def test_class_and_external_nodes_compose_lazily_and_dedupe_identical_ships(runtime):
    calls = []

    def external(subject):
        calls.append(subject)
        if subject is ModeledType:
            yield TypePath(MEMBER_SHIP, "contains")
            yield TypePath(EXTERNAL_SHIP, "docs.wiki")

    runtime.contexts.register_model_provider(external)
    runtime.contexts.register_model_provider(external)
    model = ModeledType.context.model
    assert calls == []
    assert model.at("contains").id == MEMBER_SHIP
    assert model.at("docs.wiki").id == EXTERNAL_SHIP
    assert [node.id for node in model.nodes()] == [MEMBER_SHIP, EXTERNAL_SHIP]
    assert calls == [ModeledType]
    assert model.get(str(MEMBER_SHIP)).description == "contains"
    assert model.open(str(MEMBER_SHIP)).id == MEMBER_SHIP
    assert EmptyType.context.model.nodes() == ()


# tarav.context 473c89a0:7ef12f9536d4a790
def test_retained_nodes_round_trip_and_keep_their_own_context(runtime):
    original = TypePath(MEMBER_SHIP, "contains")
    runtime.contexts.put_model_node(EmptyType, original)
    runtime.contexts.create_subject_archive(original, constitution="Member documentation.")
    runtime.contexts.put(original, "guide", FileRecord())
    assert EmptyType.context.model.at("contains").context().open("guide").records.to_record() == {
        "type": "Tarav.FileRecord"
    }

    assert [entry.name for entry in EmptyType.context().ls()].count("model") == 1
    assert EmptyType.context().open("model").at("contains").id == MEMBER_SHIP
    # Existing Archive placement policy remains create-only, without silent overwrite.
    with pytest.raises(FileExistsError):
        runtime.contexts.put_model_node(EmptyType, TypePath(MEMBER_SHIP, "members"))

    # A fresh service can reconstruct retained nodes, without a provider registry.
    fresh = create_runtime(archive_root=runtime.contexts.archive_root)
    set_runtime(fresh)
    assert EmptyType.context.model.at("contains").id == MEMBER_SHIP


def test_provider_path_rename_keeps_ship_and_retained_node_context(runtime):
    path = "contains"
    runtime.contexts.register_model_provider(lambda subject: (TypePath(MEMBER_SHIP, path),))
    original = EmptyType.context.model.at("contains")
    runtime.contexts.create_subject_archive(original, constitution="Member documentation.")
    runtime.contexts.put(original, "guide", FileRecord())
    path = "members"
    model = EmptyType.context.model
    assert model.at("members").id == MEMBER_SHIP
    with pytest.raises(KeyError):
        model.at("contains")
    assert model.at("members").context().open("guide").records.to_record() == {
        "type": "Tarav.FileRecord"
    }


def test_class_stored_and_provider_nodes_can_share_a_model(runtime):
    runtime.contexts.put_model_node(ModeledType, TypePath(EXTERNAL_SHIP, "checks.run"))
    assert {node.path for node in ModeledType.context.model.nodes()} == {"contains", "checks.run"}


def test_same_path_does_not_merge_ships_or_choose_one_silently(runtime):
    runtime.contexts.register_model_provider(
        lambda subject: (TypePath(EXTERNAL_SHIP, "contains"),)
    )
    model = ModeledType.context.model
    assert len(model.nodes()) == 2
    with pytest.raises(ValueError, match="Ambiguous"):
        model.at("contains")
    assert model.open(str(EXTERNAL_SHIP)).id == EXTERNAL_SHIP


def test_conflicting_declarations_of_one_ship_are_visible(runtime):
    runtime.contexts.register_model_provider(
        lambda subject: (TypePath(MEMBER_SHIP, "another.meaning"),)
    )
    with pytest.raises(ValueError, match="Conflicting"):
        ModeledType.context.model.nodes()


def test_runtime_providers_do_not_leak_and_old_views_keep_their_service(runtime, tmp_path):
    runtime.contexts.register_model_provider(
        lambda subject: (TypePath(EXTERNAL_SHIP, "external"),)
    )
    old_view = EmptyType.context.model
    set_runtime(create_runtime(archive_root=tmp_path / "other-archive"))
    assert EmptyType.context.model.nodes() == ()
    assert old_view.at("external").id == EXTERNAL_SHIP


def test_node_records_round_trip_through_trusted_runtime_registry(runtime):
    node = TypePath(MEMBER_SHIP, "context.model")
    record = node.records.to_record()
    loaded = runtime.records.from_record(record)
    assert isinstance(loaded, TypePath)
    assert loaded.id == node.id
    assert loaded.path == node.path
    assert TypePath.records.from_record(TypePath.records.record_example())
    with pytest.raises(ValueError):
        TypePath.records.from_record({**record, "path": ""})
    with pytest.raises(ValueError):
        TypePath(MEMBER_SHIP, "")


def test_incompatible_model_storage_is_reported_without_overwriting_it(runtime):
    runtime.contexts.create_subject_archive(EmptyType, constitution="Unrelated retained data.")
    runtime.contexts.put(EmptyType, "model", FileRecord())
    with pytest.raises(NotADirectoryError):
        runtime.contexts.put_model_node(EmptyType, TypePath(MEMBER_SHIP, "contains"))
    assert runtime.contexts.subject_archive(EmptyType).get("model").open().open().records.to_record() == {
        "type": "Tarav.FileRecord"
    }
