# $kw: --from Agentos.Skills
"""How a Project selects skills and installs them where its agents look.

Skill mechanics that know nothing of Projects (finding skills, reading their
frontmatter) live in `tarav.l1.skills`.
"""
# tarav.breadcrumb 15e4efa97779
from .commands import (
    _cmd_skills_import,
    _cmd_skills_list,
    _cmd_skills_path,
    _cmd_skills_status,
    register_skills_commands,
)

__all__ = [
    "_cmd_skills_import",
    "_cmd_skills_list",
    "_cmd_skills_path",
    "_cmd_skills_status",
    "register_skills_commands",
]
