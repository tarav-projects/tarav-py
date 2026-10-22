"""Project-owned Type selection over the existing trusted dispatch registry."""
# tarav.breadcrumb 0c2c0fd5380e

import inspect
from pathlib import Path

from tarav.l0.kernel import NamespaceBase, entity


class TypesManager(NamespaceBase):
    def owns(self, cls):
        """Default ownership follows the defining source, never an imported alias."""
        try:
            source = inspect.getsourcefile(cls)
            return source is not None and Path(source).resolve().is_relative_to(self.obj.root.resolve())
        except (TypeError, OSError):
            return False

    def all(self):
        """Only already registered classes. Override selection for other ownership rules."""
        return tuple({entity(cls).id: cls for cls in self.obj.records.types.types()
                      if self.owns(cls)}.values())
