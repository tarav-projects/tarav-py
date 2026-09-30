"""Stable identified SKW blocks for test fixtures."""

from uuid import NAMESPACE_URL, UUID, uuid5


def identify_blocks(document, *, scope):
    for block in document["blocks"]:
        try:
            UUID(block["id"])
        except ValueError:
            label = block["id"]
            block["id"] = str(uuid5(NAMESPACE_URL, f"skw-test:{scope}:{label}"))
            block["label"] = label
    return document
