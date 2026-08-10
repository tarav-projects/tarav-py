# $kw: ^workspaces-public --from Run.Workspace --note [DF] the public surface for one-run agentic workspaces, rooted outside every project ^<anchor-on-landing>
"""`Run.Workspace`: one-run agentic workspaces, deletable whole."""

from .guide import GuideError, guide_text, guide_token, parse_guide_token

__all__ = [
    "GuideError",
    "guide_text",
    "guide_token",
    "parse_guide_token",
]
