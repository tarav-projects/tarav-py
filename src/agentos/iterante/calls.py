"""Call builders — pure factories for the call objects a turn sets on `ctx.call`.

Reached as `iterante.calls.<type>(...)` after `import iterante`. These are the
mission's vocabulary for what the harness should ask the operator to do next.
"""

from __future__ import annotations

import copy

# Sentinel so an omitted `expects` leaves the key off the call (lenient,
# back-compat) while an explicit `expects=None` records a no-payload contract.
_UNSET = object()


def task(*, id: str, title: str, body: str | None = None, expects: object = _UNSET) -> dict:
    call = {"type": "task", "id": id, "title": title}
    if body is not None:
        call["body"] = body
    if expects is not _UNSET:
        call["expects"] = copy.deepcopy(expects)
    return call


def branch(*, id: str, title: str, answers: list[str], body: str | None = None) -> dict:
    call = {"type": "branch", "id": id, "title": title, "answers": list(answers)}
    if body is not None:
        call["body"] = body
    # branch is sugar over the general contract: its answer is an enum.
    call["expects"] = {"answer": list(answers)}
    return call


def poll(*, id: str, title: str, question: dict, schema: dict, body: str | None = None) -> dict:
    call = {
        "type": "poll",
        "id": id,
        "title": title,
        "question": copy.deepcopy(question),
        "schema": copy.deepcopy(schema),
    }
    if body is not None:
        call["body"] = body
    return call


def completed() -> dict:
    """Terminal signal: the mission is finished.

    Carries no text — the Runtime owns the completion message (and the
    re-engagement guard). Missions declare the signal, nothing more; there is
    no report or summary (continuity is git history + the work product).
    """
    return {"type": "completed", "id": "completed"}


def freeform(*, id: str, title: str, body: str | None = None, expects: object = _UNSET) -> dict:
    call = {"type": "freeform", "id": id, "title": title}
    if body is not None:
        call["body"] = body
    if expects is not _UNSET:
        call["expects"] = copy.deepcopy(expects)
    return call
