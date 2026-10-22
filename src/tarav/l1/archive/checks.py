"""Read-only locator observations, independent of DOI lookup and maintenance."""
# tarav.breadcrumb aa572176acf3

from pathlib import Path
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.actions.pois import POIResolutionAction
from tarav.l1.checks import CheckPOI, CheckResult, CheckSuite, SituationCheck, SuiteCheckpoint
from tarav.l1.checks.chains import SituationChain
from . import Archive
from .identity import ARCHIVE_WORKFLOW_SHIP
from .model import LocalLocator, RemoteLocator


class LocatorMissing(CheckPOI):
    """The local path is missing, or an HTTP endpoint reports 404/410."""

    action = "Tarav.Archive.Locator.Missing.Action"

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("d32d7cef-068b-4ce9-9ef1-7eccd1ba21d4"),
                          name="Tarav.Archive.Locator.Missing.POI", workflow=ARCHIVE_WORKFLOW_SHIP)


class LocatorUnreachable(CheckPOI):
    """Access failed; the observation does not prove the resource is missing."""

    action = "Tarav.Archive.Locator.Unreachable.Action"

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("224b8891-8c56-4359-96c0-e124f8032343"),
                          name="Tarav.Archive.Locator.Unreachable.POI", workflow=ARCHIVE_WORKFLOW_SHIP)


class LocatorMissingAction(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("101f301d-5f6a-4bd3-b3a5-cef0897cfd3b"),
                          name="Tarav.Archive.Locator.Missing.Action", workflow=ARCHIVE_WORKFLOW_SHIP)


class LocatorUnreachableAction(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("6c429f83-c4b3-4bf3-afc6-5724246288aa"),
                          name="Tarav.Archive.Locator.Unreachable.Action", workflow=ARCHIVE_WORKFLOW_SHIP)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocatorCheck(SituationCheck):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("603c38d8-119d-40f7-a69f-0acf4931fb5f"),
                          name="Tarav.Archive.Locator.Check", workflow=ARCHIVE_WORKFLOW_SHIP)

    def __init__(self, *, situation, locator, timeout=3.0):
        super().__init__(situation=situation)
        self.locator, self.timeout = locator, timeout

    def _run(self):
        kind, reason = None, None
        try:
            if isinstance(self.locator, LocalLocator):
                if self.locator.host != socket.gethostname():
                    return CheckResult(self, status="incomplete", reason="Locator belongs to another host")
                Path(self.locator.path).stat()
            elif isinstance(self.locator, RemoteLocator):
                if urlsplit(self.locator.uri).scheme not in {"http", "https"}:
                    return CheckResult(self, status="incomplete", reason="Protocol has no locator check")
                request = Request(self.locator.uri, method="HEAD")
                with build_opener(_NoRedirect()).open(request, timeout=self.timeout):
                    pass
            else:
                return CheckResult(self, status="incomplete", reason="Locator Type has no check")
        except FileNotFoundError:
            kind, reason = LocatorMissing, "Local path does not exist"
        except HTTPError as exc:
            code = exc.code
            exc.close()
            if code in {401, 403, 405, 501} or 300 <= code < 400:
                return CheckResult(self, status="incomplete",
                                   reason=f"HTTP {code}; availability not established by HEAD")
            kind = LocatorMissing if code in {404, 410} else LocatorUnreachable
            reason = f"HTTP {code}"
        except (OSError, URLError, ValueError) as exc:
            kind, reason = LocatorUnreachable, f"{type(exc).__name__}: {exc}"
        pois = [] if kind is None else [self.poi(kind, message=reason,
                                               details={"locator": self.locator.records.to_record()})]
        return CheckResult(self, status="completed", pois=pois)


class LocatorChain(SituationChain):
    Check = LocatorCheck
    POIs = (LocatorMissing, LocatorUnreachable)

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("58aa1030-901a-492c-a2ed-fdfe01ebca7d"),
                          name="Tarav.Archive.Locator.Chain", workflow=ARCHIVE_WORKFLOW_SHIP)


class ArchiveLocatorSuite(CheckSuite):
    """Discover DOI locators without provisioning storage or changing declarations."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("de3f283a-71db-4402-891a-b862b0dd09dd"),
                          name="Tarav.Archive.Locator.Suite", workflow=ARCHIVE_WORKFLOW_SHIP)

    def __init__(self, archive=None):
        self.archive = archive if archive is not None else Archive()
        super().__init__(name="Archive DOI locators", key=str(self.archive.root),
                         checkpoint_types={"locators": (LocatorCheck,)})

    def produce(self):
        if not self.archive.store.marker.exists():
            return
        for identity in self.archive.ids():
            doi = self.archive.read(identity)
            for locator in doi.locators:
                yield LocatorChain({"registry": str(self.archive.root), "doi": doi.id,
                                    "locator": locator.records.to_record()}).check(locator=locator)
        yield SuiteCheckpoint("locators")


ARCHIVE_CHECK_TYPES = (LocatorMissing, LocatorUnreachable, LocatorCheck, LocatorChain,
                       ArchiveLocatorSuite)
ARCHIVE_ACTION_TYPES = (LocatorMissingAction, LocatorUnreachableAction)
