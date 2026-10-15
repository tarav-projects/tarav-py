"""The Project Type of tarav-py, the code base of Tarav.

It ships with `tarav` because this is tarav-py's own code base; a consumer of
the library never uses it. Its project.json names it as `harness.type`.
"""

from __future__ import annotations

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP
from tarav.l2.project.dev import PythonPackageProject


# tarav.breadcrumb 024fb771c964b23f4803012c45369261721c22451aeb28c8947f26c29f5beb85
# tarav.breadcrumb ea4b090e3e6e28473491e2665ab4d8745672356f8f2bfd7181881fd644cb5ed6
class TaravPyProject(PythonPackageProject):
    """tarav-py: the Python package of Tarav, developed in the Taravangian workspace."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ca447dcd-7bf6-4858-91d6-c4325d16ff6a"),
                          name="Taravangian.TaravPyProject", workflow=PROJECT_WORKFLOW_SHIP)


__all__ = ["TaravPyProject"]
