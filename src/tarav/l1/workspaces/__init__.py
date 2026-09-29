# $kw: ^workspaces-public --from Run.Workspace --note [DF] the public surface for one-run agentic workspaces, rooted outside every project ^<anchor-on-landing>
"""`Run.Workspace`: one-run agentic workspaces, deletable whole."""

from .guide import GuideError, guide_text, guide_token, parse_guide_token
from .manifest import Manifest, ManifestError, Status, read_manifest, render_agents_md
from .root import resolve_workspaces_root

__all__ = [
    "GuideError",
    "Manifest",
    "ManifestError",
    "Status",
    "read_manifest",
    "render_agents_md",
    "resolve_workspaces_root",
    "guide_text",
    "guide_token",
    "parse_guide_token",
]
