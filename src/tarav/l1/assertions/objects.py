"""Shallow root for assertion objects."""

from tarav.l0.kernel import Ship, TaravClass, TaravEntity, TypeShip

from .workflow import ASSERTIONS_WORKFLOW_SHIP


class TaravAssertion(TaravEntity):
    """An identifiable assertion; particular workflows supply its semantics."""
    # tarav.context 6734aba0:434e3f65fc9c6be5

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip('35f13b22-fb0d-4361-b40e-bff14e62c560'),
            name='Tarav.Assertions.Assertion',
            workflow=ASSERTIONS_WORKFLOW_SHIP,
        )

    class Records(TaravEntity.Records):
        def record_example(self):
            cls = self._owner
            return cls(Ship('f7b8c72f-a76e-4c50-a80c-d3dc92332218')).records.to_record()
