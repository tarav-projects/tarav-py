"""Populate the existing Context Explorer from an explicit Lines subtree."""

from tarav.l1.context import ContextExplorer

from . import Block, Line


# tarav.breadcrumb 63fe86e5c67c
def explore(root: Block) -> ContextExplorer:
    """Collect the subtree and ancestor Lines, keeping the focus at root.

    Ancestor hooks expose their direct structural edges, including sibling
    targets. Those siblings' own contexts and descendant text are not opened.
    """
    if not isinstance(root, Block):
        raise TypeError("A Lines subtree starts at a Block")
    explorer = root.context()

    def collect(obj):
        explorer.open(obj)
        if isinstance(obj, Block):
            for member in obj.contents:
                collect(member)

    collect(root)
    for parent in reversed(root.ancestors()):
        explorer.open(parent)
        for member in parent.contents:
            if isinstance(member, Line):
                explorer.open(member)
    return explorer
