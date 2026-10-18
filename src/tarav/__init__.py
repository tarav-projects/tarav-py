"""Tarav's guarded import entry; functionality lives in explicit layers."""

from os import environ as _environ


class TaravImportError(ImportError):
    """Tarav was imported outside a Tarav-started process."""


# tarav.breadcrumb d817fd1d728c
# tarav.breadcrumb b1e1e982d426
# Deliberate library callers import tarav_bypass first. Keep that package out
# of this import path so the guarded entry stays independent of its bypass.
if "_TARAV_IMPORT_ENTRY" not in _environ:
    raise TaravImportError(
        "Tarav was imported from a process that was not started through Tarav. "
        "Run the script with 'tarav run -- <script>' or "
        "'tarav run --project -- <script>' so it uses the intended environment."
    )

__version__ = "0.1.0"
