import pytest

from tarav._core.project import initialize_project_layout
from tarav.kernel import entity
from tarav.models import Model, ModelsWorkflow
from tarav.project import Project
from tarav.project.models import ProjectModels
from tarav.models.records import ModelShipRecord, ModelEditionRecord
from tarav.runtime import create_runtime
from tarav.unsorted.storage import DiagramConfiguration, DiagramNamespace
from tarav.unsorted.primitives import DiagramError


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
