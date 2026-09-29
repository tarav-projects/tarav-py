import pytest
import json

from tarav.l0._core.project import initialize_project_layout
from tarav.l0.kernel import entity
from tarav.l2.models import Model, ModelsWorkflow
from tarav.l2.project import Project
from tarav.l2.project.models import ProjectModels
from tarav.l2.models.records import ModelShipRecord, ModelEditionRecord
from tarav.l3.runtime import create_runtime
from tarav.l2.unsorted.storage import DiagramConfiguration, DiagramNamespace
from tarav.l2.unsorted.primitives import DiagramError


def test_models_have_independent_ownership_and_preserved_types():
    runtime = create_runtime()
    assert runtime.workflows.get('models') is ModelsWorkflow
    for cls in (Model, ModelShipRecord, ModelEditionRecord):
        assert entity(cls).workflow is ModelsWorkflow()
    assert str(entity(ModelShipRecord).id) == '990807e6-2348-466e-9c12-dba6673755c1'
    assert str(entity(ModelEditionRecord).id) == '213b526c-cdd1-4d9b-a39d-650eee709354'


def test_model_project_association_is_shared_and_read_only(tmp_path):
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / 'diagram')
    model = namespace.create_model(label='Shared')
    assert isinstance(model, Model)
    diagram = DiagramConfiguration.load(tmp_path / 'config.json', create=True).mount(
        namespace, default=True).diagram()
    roots = [tmp_path / name for name in ('one', 'two')]
    for root in roots:
        root.mkdir()
        initialize_project_layout(root)
        with pytest.raises(DiagramError, match='no Diagram main Model'):
            ProjectModels(Project.from_path(root), diagram=diagram).main()
        diagram.set_project_main_model(root, model.ship)
        sub = root / 'src'
        sub.mkdir()
        marker = root / '.tarav/project.json'
        before = marker.read_bytes()
        resolved = ProjectModels(Project.from_path(sub), diagram=diagram).main()
        assert resolved.ship == model.ship
        assert resolved.record.class_entity().workflow is ModelsWorkflow()
        assert marker.read_bytes() == before


def test_project_models_default_resolver(tmp_path, monkeypatch):
    monkeypatch.setattr(DiagramConfiguration, "default_path", staticmethod(lambda: tmp_path / "config.json"))
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "diagram")
    model = namespace.create_model(label="Main")
    diagram = DiagramConfiguration.load(create=True).mount(namespace, default=True).diagram()
    initialize_project_layout(tmp_path)
    diagram.set_project_main_model(tmp_path, model.ship)
    assert Project.from_path(tmp_path).models().main().ship == model.ship


def test_missing_model_configuration_is_not_created(tmp_path, monkeypatch):
    config = tmp_path / "missing.json"
    monkeypatch.setattr(DiagramConfiguration, "default_path", staticmethod(lambda: config))
    initialize_project_layout(tmp_path)
    project = Project.from_path(tmp_path)
    handler = project.models()
    with pytest.raises(DiagramError, match="configuration not found"):
        handler.main()
    assert not config.exists()


def test_named_models_are_live_read_only_and_independent_of_main(tmp_path):
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "diagram")
    main = namespace.create_model(label="Main")
    other = namespace.create_model(label="Research")
    diagram = DiagramConfiguration.load(tmp_path / "config.json", create=True).mount(
        namespace, default=True).diagram()
    initialize_project_layout(tmp_path)
    diagram.set_project_main_model(tmp_path, main.ship)
    handler = ProjectModels(Project.from_path(tmp_path), diagram=diagram)
    assert handler.ls() == ()
    assert handler.main().ship == main.ship
    marker = tmp_path / ".tarav/project.json"
    record = json.loads(marker.read_text())
    record["diagram"]["models"] = {"research": other.ship, "alias": other.ship}
    marker.write_text(json.dumps(record))
    before = marker.read_bytes()
    assert handler.ls() == ("alias", "research")
    assert handler.get("research").ship == other.ship
    assert handler.get("alias").ship == other.ship
    assert handler.main().ship == main.ship
    with pytest.raises(KeyError):
        handler.get("absent")
    with pytest.raises(TypeError):
        handler.get(3)
    assert marker.read_bytes() == before


def test_listing_and_missing_names_do_not_resolve_storage(tmp_path):
    initialize_project_layout(tmp_path)
    handler = ProjectModels(Project.from_path(tmp_path), diagram=object())
    assert handler.ls() == ()
    with pytest.raises(KeyError):
        handler.get("missing")


@pytest.mark.parametrize("mapping", [None, [], {"": "bad"}, {"research": 3}, {"research": "bad"}])
def test_invalid_named_mapping_is_reported_not_repaired(tmp_path, mapping):
    initialize_project_layout(tmp_path)
    marker = tmp_path / ".tarav/project.json"
    record = json.loads(marker.read_text())
    record["diagram"] = {"models": mapping}
    marker.write_text(json.dumps(record))
    before = marker.read_bytes()
    with pytest.raises(ValueError):
        Project.from_path(tmp_path).models().ls()
    assert marker.read_bytes() == before
