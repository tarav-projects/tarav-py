"""Deliberately bounded candidate generation; identity decisions belong to maintainers."""

from difflib import SequenceMatcher
from hashlib import sha256
from itertools import accumulate
from uuid import uuid4

from .model import Chunk


# tarav.breadcrumb b5c7eb63929b
def partition(content: bytes, target: int, flexibility: int):
    """Cover all bytes once, preferring nearby whitespace for initial boundaries."""
    if not content:
        return [(0, 0)]
    spans = []
    start = 0
    while start < len(content):
        end = min(start + target, len(content))
        if end < len(content):
            limit = min(end + flexibility, len(content))
            boundary = next((pos + 1 for pos in range(end, limit)
                             if content[pos] in b"\n\r\t "), None)
            if boundary is not None:
                end = boundary
        spans.append((start, end))
        start = end
    return spans


def chunk(path, blob, content, start, end, identity=None):
    return Chunk(id=identity or str(uuid4()), path=path, blob=blob, start=start,
                 end=end, sha256=sha256(content[start:end]).hexdigest())


def aligned_boundaries(old: bytes, new: bytes, boundaries):
    """Map old boundaries through a line diff; edited spans are proportional candidates.

    Large or single-line surfaces use bounded block alignment. This supplies
    coordinates only: it cannot certify that a chunk's meaning continues.
    """
    old_units, new_units = old.splitlines(keepends=True), new.splitlines(keepends=True)
    if max(len(old_units), len(new_units)) > 20000 or max(
            (len(line) for line in old_units + new_units), default=0) > 65536:
        old_units = [old[i:i + 256] for i in range(0, len(old), 256)]
        new_units = [new[i:i + 256] for i in range(0, len(new), 256)]
    a = [0, *accumulate(map(len, old_units))]
    b = [0, *accumulate(map(len, new_units))]
    opcodes = SequenceMatcher(None, old_units, new_units, autojunk=True).get_opcodes()
    result = []
    for point in boundaries:
        candidate = len(new)
        for tag, i, j, k, last in opcodes:
            left, right, nleft, nright = a[i], a[j], b[k], b[last]
            if left <= point < right:
                candidate = (nleft + point - left if tag == "equal" else
                             nleft + (point - left) * (nright - nleft) // (right - left))
                break
        result.append(candidate)
    return result


def reconcile_file(chunks, path, blob, old, new):
    """Keep the partition's shape through edits; collapsing regions propose retirement."""
    ordered = sorted(chunks, key=lambda item: item.start)
    if old == new:
        return [item.model_copy(update={"path": path, "blob": blob}) for item in ordered]
    boundaries = [0, *aligned_boundaries(old, new, [c.end for c in ordered[:-1]]), len(new)]
    return [chunk(path, blob, new, start, end, item.id)
            for item, start, end in zip(ordered, boundaries, boundaries[1:])
            if end > start or (len(new) == 0 and item is ordered[0])]
