"""The Projects suite: the checks of one Project, run as a whole."""

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.actions.suites import Suite

from .workflow import PROJECT_WORKFLOW_SHIP


# tarav.breadcrumb 03c73855440405f15bc3e360c2d0ce1b475572848af4be838b48f63cc48ca9f6
class ProjectsSuite(Suite):
    """Whatever a Project's checks examine. Its target is the Project.

    The identity does not name a list of checks: it says that running a
    Project's checks again tests the same thing on that Project.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("def86b0d-ca6e-4000-82d1-d0655784aac7"),
                          name="Tarav.Project.Suite", workflow=PROJECT_WORKFLOW_SHIP)


__all__ = ["ProjectsSuite"]
