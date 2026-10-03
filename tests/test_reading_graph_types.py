import inspect

import pytest

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.project import TaravProject
from tarav.l1.project.workflow import ProjectWorkflow
from tarav.l1.skw.code import CodeWorkflow, ReadingGraph
from tarav.l1.skw.loading import SkillReadingGraph
from tarav.l2.project.reading import ProjectReadingGraph
from tarav.l2.skw.skills import SkillsWorkflow


# tarav.breadcrumb dfbdeb52726ec48e74c2a2a0632f3095db177928131dfd87e9922e29c7f3eec8
def test_reading_graph_specializations_declare_distinct_ownership() -> None:
    assert issubclass(SkillReadingGraph, ReadingGraph)
    assert issubclass(ProjectReadingGraph, ReadingGraph)
    assert entity(ReadingGraph).workflow_ship == CodeWorkflow().id
    assert entity(SkillReadingGraph).workflow_ship == SkillsWorkflow().id
    assert entity(ProjectReadingGraph).workflow_ship == ProjectWorkflow().id
    assert not inspect.isabstract(SkillReadingGraph)
    assert inspect.isabstract(ProjectReadingGraph)


def test_concrete_project_reading_graph_binds_one_project() -> None:
    class ExampleProjectReadingGraph(ProjectReadingGraph):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("5925125b-2a6e-4b73-b26e-d8f16c783de2"),
                name="Test.Project.ReadingGraph",
            )

        def analyze(self, **options: object) -> dict[str, object]:
            return {"project": self.project, "options": options}

    project = TaravProject.from_record(TaravProject.record_example())
    graph = ExampleProjectReadingGraph(project)

    assert graph.analyze(limit=5) == {
        "project": project,
        "options": {"limit": 5},
    }
    with pytest.raises(TypeError, match="project must be a TaravProject"):
        ExampleProjectReadingGraph(object())
