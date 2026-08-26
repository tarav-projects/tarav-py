# $kw: --from Deep.Modules
__all__ = ["__version__"]

import logging


__version__ = "0.1.0"

# Tarav libraries emit diagnostics but leave handler configuration to the host.
logging.getLogger(__name__).addHandler(logging.NullHandler())
