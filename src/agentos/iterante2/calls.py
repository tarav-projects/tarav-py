"""Call builders — pure factories for the call objects a turn sets on `ctx.call`.

Reached as `iterante2.calls.<type>(...)` after `import iterante2`. These are the
mission's vocabulary for what the harness should ask the operator to do next.
"""

from __future__ import annotations

import copy


def task(*, id: str, title: str, body: str | None = None) -> dict:
    call = {"type": "task", "id": id, "title": title}
    if body is not None:
        call["body"] = body
    return call


def branch(*, id: str, title: str, answers: list[str], body: str | None = None) -> dict:
    call = {"type": "branch", "id": id, "title": title, "answers": list(answers)}
    if body is not None:
        call["body"] = body
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


def handoff(*, title: str = "Write handoff report", body: str | None = None) -> dict:
    call = {"type": "handoff", "id": "handoff", "title": title}
    if body is not None:
        call["body"] = body
    return call


def freeform(*, id: str, title: str, body: str | None = None) -> dict:
    call = {"type": "freeform", "id": id, "title": title}
    if body is not None:
        call["body"] = body
    return call
