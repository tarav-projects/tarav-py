"""The neighborhood of an object: the objects it is shown with, for documentation.

An object's context says who its neighbors are with `NEIGHBOR` triples,
`(object, NEIGHBOR, other)`. The neighborhood of every object starts with
itself, so by default it is just the object; that one needs no triple. A
class adds its neighbors in its own context hook::

    class Context(TaravObject.Context):
        def _obj_context_hook(self, cxt):
            super()._obj_context_hook(cxt)
            cxt.triplets.append((self.obj, NEIGHBOR, self.obj.poi))

Nothing decides anything from a neighborhood: no check, identity or
blessing reads it. Where a neighbor's Type lives is not part of it; a reader
finds that by following the Type's `workflow` link.
"""

from __future__ import annotations

from tarav.l0.kernel import TaravClass, TaravType, TaravWorkflow, TypeShip, WorkflowShip

NEIGHBORHOOD_WORKFLOW_SHIP = WorkflowShip("3c547a67-c3ef-4b46-b807-ea2618aeddd6")

#: The predicate of a neighbor: `(object, NEIGHBOR, other)`.
NEIGHBOR = "urn:tarav:neighborhood:neighbor"


class NeighborhoodWorkflow(TaravWorkflow):
    constitution = (
        "Say which objects an object is shown with: NEIGHBOR triples in its context, "
        "the object itself by default. For documentation only."
    )

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("9804910d-94d9-49ea-af18-451b1bd2ae23"),
                          name="Tarav.Workflow.Neighborhood", workflow=NEIGHBORHOOD_WORKFLOW_SHIP)

    @classmethod
    def _workflow_id(cls):
        return NEIGHBORHOOD_WORKFLOW_SHIP


def neighborhood(obj: TaravType) -> tuple[object, ...]:
    """The object itself, then the neighbors its context names, in the order they were added."""
    cxt = obj.context.build()
    found = [cxt.subject]
    for subject, predicate, target in cxt.triplets:
        if (subject is cxt.subject and predicate == NEIGHBOR
                and not any(target is seen for seen in found)):
            found.append(target)
    return tuple(found)


__all__ = ["NEIGHBOR", "NEIGHBORHOOD_WORKFLOW_SHIP", "NeighborhoodWorkflow", "neighborhood"]
