# $kw: --from Iterante.Driver
"""iterante CLI — a pure connector over `iterante.runtime`.

The CLI holds no capability the library lacks. It only forwards argv to the
runtime; all resolution, state, env-crossing, turn execution, and rendering live
in `iterante.runtime`. The CLI is just one caller — a python script calling the
`iterante.runtime` facade is an equal peer.
"""

from __future__ import annotations

import sys

from tarav.l1.iterante import runtime


def main():
    runtime.main(sys.argv[1:])
