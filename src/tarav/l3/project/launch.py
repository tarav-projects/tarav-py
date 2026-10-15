"""`python -I -m tarav.l3.project.launch`: start a Project in its harness environment.

The Project's project.json names its Type (`harness.type`); this process is
the environment's interpreter, so the Type is imported from what that
environment installed.
"""

from __future__ import annotations

from .harness import main


if __name__ == "__main__":
    raise SystemExit(main())
