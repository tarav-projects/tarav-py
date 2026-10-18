"""Project-owned specialization point for reader-route analysis."""

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.project import TaravProject
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP
from tarav.l1.skw.code import ReadingGraph


class ProjectReadingGraph(ReadingGraph):
    """Abstract reading graph bound to one Project.

    Concrete Project Types decide which surfaces form the graph and how their
    declared routes are analyzed. The base only establishes Project ownership.
    """
    # tarav.breadcrumb e2ef05c1dc36
    # tarav.breadcrumb f5337864b808

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("44480706-aceb-4985-bf40-c128895dff8d"),
            name="Tarav.Project.ReadingGraph",
            workflow=PROJECT_WORKFLOW_SHIP,
        )

    def __init__(self, project: TaravProject) -> None:
        if not isinstance(project, TaravProject):
            raise TypeError("project must be a TaravProject")
        self.project = project
