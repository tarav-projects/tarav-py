"""Read-only checks of deposit metadata, without payload inspection."""

from collections import defaultdict
from uuid import UUID

from pydantic import ValidationError

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.actions.pois import POIResolutionAction
from tarav.l1.checks import CheckPOI, CheckResult, CheckSuite, SituationCheck
from tarav.l1.checks.chains import SituationChain

from .model import Attic, Deposit
from .workflow import ATTIC_WORKFLOW_SHIP


class ManifestMissing(CheckPOI):
    """A deposit directory has no deposit.json."""

    action = "Tarav.Attic.Manifest.Missing.Action"

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("b62e307c-c73a-4f71-8abf-9db02c7a191e"),
                          name="Tarav.Attic.Manifest.Missing.POI", workflow=ATTIC_WORKFLOW_SHIP)


class ManifestUnreadable(CheckPOI):
    """A deposit manifest cannot be read as UTF-8 text."""

    action = "Tarav.Attic.Manifest.Unreadable.Action"

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("69b637a7-29fc-4c93-b52e-8f9cff45673d"),
                          name="Tarav.Attic.Manifest.Unreadable.POI", workflow=ATTIC_WORKFLOW_SHIP)


class ManifestInvalid(CheckPOI):
    """A deposit manifest does not have the declared JSON format."""

    action = "Tarav.Attic.Manifest.Invalid.Action"

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("22f46a22-eb5c-43d2-bd56-d8c4930c1e85"),
                          name="Tarav.Attic.Manifest.Invalid.POI", workflow=ATTIC_WORKFLOW_SHIP)


class DuplicateUUID(CheckPOI):
    """Multiple valid manifests declare the same deposit UUID."""

    action = "Tarav.Attic.UUID.Duplicate.Action"

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("7a0319f9-41f3-4b0f-b236-71f0905d3135"),
                          name="Tarav.Attic.UUID.Duplicate.POI", workflow=ATTIC_WORKFLOW_SHIP)


class ListingUnreadable(CheckPOI):
    """The Attic's deposit directories cannot be listed."""

    action = "Tarav.Attic.Listing.Unreadable.Action"

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("72675ef6-d27f-46b8-b576-09ac0c456a51"),
                          name="Tarav.Attic.Listing.Unreadable.POI", workflow=ATTIC_WORKFLOW_SHIP)


class ManifestMissingResolution(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("b45ff559-9759-461b-8f50-916f7fddfb2e"),
                          name="Tarav.Attic.Manifest.Missing.Action", workflow=ATTIC_WORKFLOW_SHIP)


class ManifestUnreadableResolution(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("6c32b3db-8d60-4c1c-9aa7-37a32d159ab1"),
                          name="Tarav.Attic.Manifest.Unreadable.Action", workflow=ATTIC_WORKFLOW_SHIP)


class ManifestInvalidResolution(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("b096b8b1-d7ea-44da-b34b-f03404604a9a"),
                          name="Tarav.Attic.Manifest.Invalid.Action", workflow=ATTIC_WORKFLOW_SHIP)


class DuplicateUUIDResolution(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("8b02c315-f242-4679-975c-40565bc84e79"),
                          name="Tarav.Attic.UUID.Duplicate.Action", workflow=ATTIC_WORKFLOW_SHIP)


class ListingUnreadableResolution(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("77061f08-aaf5-4d94-97ae-fc5442186785"),
                          name="Tarav.Attic.Listing.Unreadable.Action", workflow=ATTIC_WORKFLOW_SHIP)


# tarav.breadcrumb 40514745136a
class ManifestCheck(SituationCheck):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("51585b69-b533-4ce3-8664-c9c7706b2907"),
                          name="Tarav.Attic.Manifest.Check", workflow=ATTIC_WORKFLOW_SHIP)

    def __init__(self, *, situation, deposit: Deposit):
        super().__init__(situation=situation)
        self.deposit = deposit
        self.manifest = None

    def _run(self):
        self.manifest = None
        try:
            self.manifest = self.deposit.read_manifest()
        except FileNotFoundError:
            kind, error = ManifestMissing, "No deposit.json"
        except (OSError, UnicodeError) as exc:
            kind, error = ManifestUnreadable, str(exc)
        except ValidationError as exc:
            kind, error = ManifestInvalid, str(exc)
        else:
            return CheckResult(self, status="completed")
        return CheckResult(self, status="completed", pois=[self.poi(
            kind, message=f"{self.deposit.path.name}: {error}",
            details={"path": str(self.deposit.manifest_path)})])


class UUIDCheck(SituationCheck):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("616d906e-46cf-4d9d-8582-f531b55456bf"),
                          name="Tarav.Attic.UUID.Check", workflow=ATTIC_WORKFLOW_SHIP)

    def __init__(self, *, situation, deposits):
        super().__init__(situation=situation)
        self.deposits = tuple(deposits)

    def _run(self):
        pois = [] if len(self.deposits) < 2 else [self.poi(
            DuplicateUUID, message=f"Deposit UUID {self.situation['uuid']} is declared more than once",
            details={"deposits": list(self.deposits)})]
        return CheckResult(self, status="completed", pois=pois)


class ListingCheck(SituationCheck):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("4f219ac2-303a-4741-b150-ae34d8ab3ff9"),
                          name="Tarav.Attic.Listing.Check", workflow=ATTIC_WORKFLOW_SHIP)

    def __init__(self, *, situation, attic: Attic):
        super().__init__(situation=situation)
        self.attic = attic
        self.deposits = None

    def _run(self):
        self.deposits = None
        try:
            self.deposits = self.attic.deposits()
        except OSError as exc:
            return CheckResult(self, status="completed", pois=[self.poi(
                ListingUnreadable, message=f"Cannot list Attic deposits: {exc}")])
        return CheckResult(self, status="completed")


class ManifestChain(SituationChain):
    Check = ManifestCheck
    POIs = (ManifestMissing, ManifestUnreadable, ManifestInvalid)

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("539f9499-b407-481f-a347-a787da83ead5"),
                          name="Tarav.Attic.Manifest.Chain", workflow=ATTIC_WORKFLOW_SHIP)


class UUIDChain(SituationChain):
    Check = UUIDCheck
    POIs = (DuplicateUUID,)

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("b105ce17-f437-4d77-a68d-1d01d28337a8"),
                          name="Tarav.Attic.UUID.Chain", workflow=ATTIC_WORKFLOW_SHIP)


class ListingChain(SituationChain):
    Check = ListingCheck
    POIs = (ListingUnreadable,)

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("779f344b-c4f0-4930-a1ce-91da9762bdb4"),
                          name="Tarav.Attic.Listing.Chain", workflow=ATTIC_WORKFLOW_SHIP)


class AtticSuite(CheckSuite):
    """Read immediate deposit manifests once; material stays entirely opaque."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("061df655-23ca-46bd-b98d-a2380cf50880"),
                          name="Tarav.Attic.Suite", workflow=ATTIC_WORKFLOW_SHIP)

    def __init__(self, attic: Attic):
        self.attic = attic
        super().__init__(name="Attic metadata", key=str(attic.root))

    def produce(self):
        listing = ListingChain({"root": self.key}).check(attic=self.attic)
        yield listing
        if listing.deposits is None:
            # Incomplete discovery cannot settle earlier deposit findings.
            self._refused += 1
            return
        declarations = defaultdict(list)
        for deposit in listing.deposits:
            check = ManifestChain({"root": self.key, "deposit": deposit.path.name}).check(
                deposit=deposit)
            yield check
            if check.manifest is not None:
                declarations[str(UUID(check.manifest.uuid))].append(deposit.path.name)
        for uuid, deposits in sorted(declarations.items()):
            yield UUIDChain({"root": self.key, "uuid": uuid}).check(deposits=deposits)


ATTIC_POI_TYPES = (ManifestMissing, ManifestUnreadable, ManifestInvalid, DuplicateUUID,
                   ListingUnreadable)
ATTIC_ACTION_TYPES = (ManifestMissingResolution, ManifestUnreadableResolution,
                      ManifestInvalidResolution, DuplicateUUIDResolution,
                      ListingUnreadableResolution)
