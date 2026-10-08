"""Explicit entry into Tarav for callers outside ``tarav run``."""

import os


_ENTRY_MARK = "_TARAV_IMPORT_ENTRY"
os.environ.setdefault(_ENTRY_MARK, "bypass")


# tarav.breadcrumb d29310dbbd6386cbe6cda3f35b489b102ff1076a385c74c1700514e9034e684a
def cli_main() -> int:
    """Enter the ordinary Tarav CLI before importing its guarded package."""
    os.environ[_ENTRY_MARK] = "cli"
    from tarav.l3.cli import main

    return main()


def daemon_main() -> int:
    """Enter the daemon, including when launchd supplies no shell environment."""
    os.environ[_ENTRY_MARK] = "daemon"
    from tarav.l3.daemon.entrypoint import main

    return main()
