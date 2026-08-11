# $kw: --from Iterante.Ctx
"""Call frame rendering — Markdown output the agent sees."""

from __future__ import annotations

import json

from agentos.iterante.redact import redact

_ANSWER_HINTS = {
    "str": '--answer "<text>"',
    "bool": "--answer <true|false>",
    "int": "--answer <int>",
    "float": "--answer <number>",
}


def _is_answer_contract(expects: object) -> bool:
    return isinstance(expects, dict) and set(expects) == {"answer"}


def _submit_command(expects: object, token: str) -> str:
    """Derive the exact submit command for a declared `expects` contract."""
    base = f"iterante submit --token {token}"
    if expects is None:
        return base
    if _is_answer_contract(expects):
        marker = expects["answer"]
        if isinstance(marker, list):
            return f"{base} --answer <{'|'.join(str(m) for m in marker)}>"
        hint = _ANSWER_HINTS.get(marker)
        if hint:
            return f"{base} {hint}"
    return f"{base} --data '<json>'"


def render_frame(*, call: dict, token: str, tick: int, mission_id: str | None = None) -> str:
    """Render a call into a full Markdown frame: header + content + footer."""
    parts = []


    label = f"[{mission_id}]" if mission_id else "[run]"
    parts.append(f"## {label} Turn {tick}")
    parts.append("")

    call_type = call.get("type", "freeform")


    if call_type == "completed":
        parts.append("### Mission complete")
        parts.append("")
        parts.append(
            "This mission is finished. Stop here — do not continue, re-run, or "
            "write any file. The next iteration reconstructs context from git "
            "history and the work product itself."
        )
        parts.append("")
        return redact("\n".join(parts))


    title = call.get("title", "")
    parts.append(f"### {title}")
    parts.append("")

    body = call.get("body")
    if body:
        parts.append(str(body))
        parts.append("")

    if call_type == "branch":
        answers = call.get("answers", [])
        if answers:
            parts.append("**Choose one:**")
            for a in answers:
                parts.append(f"- `{a}`")
            parts.append("")

    if call_type == "poll":
        question = call.get("question")
        if question:
            q_text = question.get("text", str(question))
            parts.append(f"**Question:** {q_text}")
            parts.append("")



    has_contract = "expects" in call
    expects = call.get("expects")
    if has_contract and isinstance(expects, dict) and not _is_answer_contract(expects):
        parts.append("**Submit this shape:**")
        parts.append("```json")
        parts.append(json.dumps(expects, indent=2))
        parts.append("```")
        parts.append("")


    parts.append("---")
    cmd = _submit_command(expects, token) if has_contract else f"iterante submit --token {token}"
    parts.append(f"When done: `{cmd}`")
    parts.append("")




    return redact("\n".join(parts))
