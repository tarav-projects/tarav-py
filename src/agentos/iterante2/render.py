"""Call frame rendering — Markdown output the agent sees."""

from __future__ import annotations

from agentos.iterante2.redact import redact


def render_frame(*, call: dict, token: str, tick: int, mission_id: str | None = None) -> str:
    """Render a call into a full Markdown frame: header + content + footer."""
    parts = []

    # Header
    label = f"[{mission_id}]" if mission_id else "[run]"
    parts.append(f"## {label} Turn {tick}")
    parts.append("")

    # Content
    call_type = call.get("type", "freeform")
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

    # Footer
    parts.append("---")
    if call_type == "handoff":
        parts.append(f"Submit your report: `iterante2 submit --token {token}`")
    else:
        parts.append(f"When done: `iterante2 submit --token {token}`")
    parts.append("")

    # Defense-in-depth: the frame dict is path-free by construction, but a leak
    # into a call body (e.g. a mission-built title) is scrubbed here, and every
    # launcher that renders inherits it.
    return redact("\n".join(parts))
