"""Attic: opaque conservation with cheap, self-declared deposit metadata."""

from .model import Attic, Deposit, DepositManifest
from .workflow import ATTIC_WORKFLOW_SHIP, AtticWorkflow
from .checks import ATTIC_ACTION_TYPES, ATTIC_POI_TYPES, AtticSuite

ATTIC_RECORD_TYPES = (Attic, Deposit, *ATTIC_POI_TYPES)

__all__ = ["ATTIC_ACTION_TYPES", "ATTIC_RECORD_TYPES", "ATTIC_WORKFLOW_SHIP", "Attic",
           "AtticSuite", "AtticWorkflow", "Deposit", "DepositManifest"]
