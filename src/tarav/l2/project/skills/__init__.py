# $kw: --from Agentos.Skills
"""How a Project selects skills and installs them where its agents look.

Skill mechanics that know nothing of Projects (finding skills, reading their
frontmatter) live in `tarav.l1.skills`.
"""
# tarav.breadcrumb 15e4efa9777939e0da206e606ab8e38e719b6e4f760e4b41e067b1a4e9429403
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
